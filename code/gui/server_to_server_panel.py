from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox, QInputDialog, QLineEdit, QStyle, QFrame
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon
import posixpath
import gc
import secrets

import os
from code.gui.file_panel import FilePanel
from code.core.auth_manager import AuthManager
from code.core.sftp_client import SFTPClient
from code.core.transfer_manager import TransferManager, TransferType
from code.utils.secure_string import SecureTemporaryCredentials


class DualPanelWidget(QWidget):
    """
    Base class for dual-panel layouts with equal spacing.
    Provides common layout structure that can be reused.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_base_layout()
    
    def setup_base_layout(self):
        """Set up the base dual-panel layout with equal spacing."""
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(6)
        
        # Will be populated by subclasses
        self.left_layout = QVBoxLayout()
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(5)
        
        self.right_layout = QVBoxLayout()  
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(5)
        
        # Add layouts with equal stretch factors for 50/50 split
        self.main_layout.addLayout(self.left_layout, 1)
        
        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        self.main_layout.addWidget(separator, 0)
        
        self.main_layout.addLayout(self.right_layout, 1)


class ServerToServerPanel(DualPanelWidget):
    """
    Panel for managing server-to-server file transfers.
    Contains two FilePanel instances for source and destination servers.
    """
    def __init__(self, parent=None, auth_manager: AuthManager = None, transfer_manager: TransferManager = None, signal_bridge=None):
        self.auth_manager = auth_manager
        self.transfer_manager = transfer_manager
        self.signal_bridge = signal_bridge # For connecting to transfer progress updates

        self.source_client = None
        self.dest_client = None

        super().__init__(parent)  # This calls setup_base_layout
        self.setup_panels()

    def setup_panels(self):
        """Set up the server-to-server specific panels."""
        # Source Server Panel
        source_label = QLabel("Source Server:")
        source_label.setStyleSheet("font-weight: bold; font-size: 10pt;")
        self.left_layout.addWidget(source_label)

        self.source_panel = FilePanel(is_remote=True)
        self.source_panel.itemSelected.connect(self.source_item_selected)
        self.left_layout.addWidget(self.source_panel)

        # Destination Server Panel
        dest_label = QLabel("Destination Server:")
        dest_label.setStyleSheet("font-weight: bold; font-size: 10pt;")
        self.right_layout.addWidget(dest_label)

        self.destination_panel = FilePanel(is_remote=True)
        self.destination_panel.itemSelected.connect(self.dest_item_selected)
        self.right_layout.addWidget(self.destination_panel)

        # Initialize connection lists for both panels
        self.refresh_connections()

    def refresh_connections(self):
        """Refresh the list of connections in both combo boxes."""
        connections = self.auth_manager.list_connections()
        
        # Clear and populate source panel combo
        self.source_panel.conn_combo.clear()
        self.source_panel.conn_combo.addItem("") # Add empty item for no selection
        for conn in connections:
            name = conn.get('name')
            if name:
                self.source_panel.conn_combo.addItem(name)
        
        # Clear and populate destination panel combo
        self.destination_panel.conn_combo.clear()
        self.destination_panel.conn_combo.addItem("") # Add empty item for no selection
        for conn in connections:
            name = conn.get('name')
            if name:
                self.destination_panel.conn_combo.addItem(name)

    def source_item_selected(self, path, is_dir):
        """
        Handle item selection in the source panel.
        This method initiates a server-to-server transfer.
        """
        if not self.source_panel.client or not self.destination_panel.client:
            QMessageBox.warning(self, "Connection Error", "Please connect to both source and destination servers.")
            return

        source_full_path = posixpath.normpath(path.replace("\\", "/"))
        # print(f"Source full path: {source_full_path}")
        dest_base_path = posixpath.normpath(self.destination_panel.current_path.replace("\\", "/"))
        # print(f"Destination base path: {dest_base_path}")
        dest_full_path = posixpath.join(dest_base_path, posixpath.basename(path.replace("\\", "/")))
        # print(f"Destination full path: {dest_full_path}")

        if is_dir:
            reply = QMessageBox.question(
                self, "Transfer Directory",
                f"Transfer directory '{os.path.basename(path)}' from source to destination '{dest_full_path}'?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply != QMessageBox.Yes:
                return
        else:
            # For files, allow user to specify destination filename/path
            dest_full_path, ok = QInputDialog.getText(
                self, "Transfer File",
                "Destination path on second server:",
                QLineEdit.Normal,
                dest_full_path)
            if not ok or not dest_full_path:
                return

        # Create overwrite callback for server-to-server transfer
        def s2s_overwrite_callback(file_path):
            reply = QMessageBox.question(
                self, "File Exists",
                f"The file '{os.path.basename(file_path)}' already exists on the destination server.\n\n"
                f"Destination path: {file_path}\n\n"
                "Do you want to overwrite it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            return reply == QMessageBox.Yes

        # Get connection configs for transfer manager
        source_conn_name = self.source_panel.conn_combo.currentText()
        dest_conn_name = self.destination_panel.conn_combo.currentText()
        
        source_config = self.auth_manager.get_connection_secure(source_conn_name)
        dest_config = self.auth_manager.get_connection_secure(dest_conn_name)

        if not source_config or not dest_config:
            QMessageBox.critical(self, "Configuration Error", "Could not retrieve connection details for transfer.")
            return

        # Queue the server-to-server transfer with secure credential handling
        # The transfer manager will handle secure credential extraction internally
        try:
            transfer_id = self.transfer_manager.queue_server_to_server(
                source_full_path,
                dest_full_path,
                source_config,
                dest_config,
                # Pass lambda with TransferType.SERVER_TO_SERVER and the destination panel reference
                progress_callback=lambda tid, tr, tt: self.signal_bridge.update_progress(
                    tid, tr, tt, TransferType.SERVER_TO_SERVER, self.destination_panel),
                overwrite_callback=s2s_overwrite_callback
            )

            if transfer_id:
                QMessageBox.information(self, "Transfer Started", f"Server-to-server transfer started with ID: {transfer_id}")
                # Force immediate update of the transfer panel in MainWindow
                if hasattr(self.parent(), 'transfer_panel'):
                    self.parent().transfer_panel.update_transfers()
            else:
                QMessageBox.critical(self, "Transfer Failed", "Failed to start server-to-server transfer.")
                
        except Exception as e:
            QMessageBox.critical(self, "Transfer Failed", f"Failed to start transfer: {e}")
        finally:
            # Force garbage collection to clear any lingering credential references
            gc.collect()

    def dest_item_selected(self, path, is_dir):
        """
        Handle item selection in the destination panel.
        This is primarily for navigation within the destination server's file system.
        """
        # This panel's item selection doesn't initiate a transfer directly,
        # but it could be used for context menu actions like "Create New Folder" etc.
        # For now, just log or provide a placeholder.
        print(f"Destination item selected: {path}, is_dir: {is_dir}")

    def disconnect_all(self):
        """Disconnect both source and destination SFTP clients."""
        if self.source_panel.client:
            self.source_panel.client.disconnect()
            self.source_panel.set_client(None) # Clear panel's client
            self.source_panel.file_model.removeRows(0, self.source_panel.file_model.rowCount()) # Clear view
            self.source_panel.path_edit.setText("") # Clear path
        if self.destination_panel.client:
            self.destination_panel.client.disconnect()
            self.destination_panel.set_client(None) # Clear panel's client
            self.destination_panel.file_model.removeRows(0, self.destination_panel.file_model.rowCount()) # Clear view
            self.destination_panel.path_edit.setText("") # Clear path

    def showEvent(self, event):
        """Handle show event to ensure connections are refreshed and panels are ready."""
        super().showEvent(event)
        self.refresh_connections()
        # Optionally, connect to the currently selected connections if they exist
        # This would require more sophisticated logic to remember previous selections
        # For now, just ensure the dropdowns are populated.


class LocalToServerPanel(DualPanelWidget):
    """
    Panel for managing local-to-server file transfers.
    Contains one local FilePanel and one remote FilePanel.
    """
    def __init__(self, parent=None, local_panel=None, remote_panel=None):
        self.local_panel = local_panel
        self.remote_panel = remote_panel
        
        super().__init__(parent)  # This calls setup_base_layout
        self.setup_panels()

    def setup_panels(self):
        """Set up the local-to-server specific panels."""
        # Left side - Local Panel with heading
        local_label = QLabel("Local Files:")
        local_label.setStyleSheet("font-weight: bold; font-size: 10pt;")
        self.left_layout.addWidget(local_label)
        self.left_layout.addWidget(self.local_panel)

        # Right side - Remote Panel  
        remote_label = QLabel("Remote Server:")
        remote_label.setStyleSheet("font-weight: bold; font-size: 10pt;")
        self.right_layout.addWidget(remote_label)
        self.right_layout.addWidget(self.remote_panel)
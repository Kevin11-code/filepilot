import os
import sys
import time  # Add this import for file panel

from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTabWidget, QFileDialog, QMessageBox, QTreeView, 
    QHeaderView, QAbstractItemView, QProgressBar, QMenu, QAction, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QSplitter, QFrame, QInputDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QModelIndex, QSize, QSettings
from PyQt5.QtGui import QIcon, QStandardItemModel, QStandardItem

from code.core.auth_manager import AuthManager
from code.core.transfer_manager import TransferManager
from code.core.sftp_client import SFTPClient
from code.utils.logger import LoggerSetup
from code.gui.conn_dialog import ConnectionDialog
from code.gui.file_panel import FilePanel
from code.gui.transfer_panel import TransferPanel
from code.gui.conn_manager import ConnectionManagerDialog



class MainWindow(QMainWindow):
    """Main application window for the SFTP client"""
    
    def __init__(self):
        super().__init__()
        self.auth_manager = AuthManager()
        self.transfer_manager = TransferManager()
        self.sftp_client = None
        
        self.setup_ui()
        self.setup_logger()
        
        # Start transfer manager
        self.transfer_manager.start()
    
    def setup_logger(self):
        """Set up the application logger"""
        log_file = os.path.join(os.path.dirname(__file__), "..", "logs", "filepilot.log")
        self.logger = LoggerSetup.setup_logger(
            name="filepilot",
            log_file=log_file,
            log_to_console=True
        )
    
    def setup_ui(self):
        """Set up the main window UI"""
        self.setWindowTitle("FilePilot SFTP Client")
        self.setMinimumSize(1000, 600)
        
        # Central widget
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # Split view with file panels and transfer panel
        splitter = QSplitter(Qt.Vertical)
        
        # File panels container
        file_panels = QWidget()
        file_layout = QHBoxLayout(file_panels)
        file_layout.setContentsMargins(0, 0, 0, 0)
        
        # Local file panel
        self.local_panel = FilePanel(is_remote=False)
        file_layout.addWidget(self.local_panel)
        
        # Add a vertical separator
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        file_layout.addWidget(separator)
        
        # Remote file panel
        self.remote_panel = FilePanel(is_remote=True)
        file_layout.addWidget(self.remote_panel)
        
        # Connect item selection signals
        self.local_panel.itemSelected.connect(self.local_item_selected)
        self.remote_panel.itemSelected.connect(self.remote_item_selected)
        
        # Add file panels to splitter
        splitter.addWidget(file_panels)
        
        # Transfer panel
        self.transfer_panel = TransferPanel(transfer_manager=self.transfer_manager)
        splitter.addWidget(self.transfer_panel)
        
        # Set initial sizes
        splitter.setSizes([400, 200])
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")
        
        # Set central widget
        self.setCentralWidget(central_widget)
        
        # Create menu bar
        self.create_menus()
        
        # Initialize the local panel with home directory
        self.local_panel.load_directory(os.path.expanduser('~'))
    
    def create_menus(self):
        """Create the application menu bar"""
        # File menu
        file_menu = self.menuBar().addMenu("File")
        
        new_conn_action = QAction("New Connection...", self)
        new_conn_action.triggered.connect(self.new_connection)
        file_menu.addAction(new_conn_action)
        
        manage_conn_action = QAction("Manage Connections...", self)
        manage_conn_action.triggered.connect(self.manage_connections)
        file_menu.addAction(manage_conn_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Transfer menu
        transfer_menu = self.menuBar().addMenu("Transfer")
        
        upload_action = QAction("Upload...", self)
        upload_action.triggered.connect(self.upload_file)
        transfer_menu.addAction(upload_action)
        
        download_action = QAction("Download...", self)
        download_action.triggered.connect(self.download_file)
        transfer_menu.addAction(download_action)
        
        server_to_server_action = QAction("Server to Server Transfer...", self)
        server_to_server_action.triggered.connect(self.server_to_server_transfer)
        transfer_menu.addAction(server_to_server_action)
        
        # Help menu
        help_menu = self.menuBar().addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        # Restore the window geometry if available
        self.restore_geometry()
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Save the window geometry
        self.save_geometry()
        
        # Stop transfer manager
        self.transfer_manager.stop()
        
        event.accept()
    
    def save_geometry(self):
        """Save the window geometry to settings"""
        settings = QSettings("YourCompany", "FilePilot")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
    
    def restore_geometry(self):
        """Restore the window geometry from settings"""
        settings = QSettings("YourCompany", "FilePilot")
        if settings.contains("geometry"):
            self.restoreGeometry(settings.value("geometry"))
        if settings.contains("windowState"):
            self.restoreState(settings.value("windowState"))
    
    def new_connection(self):
        """Open the connection dialog to create a new connection"""
        dialog = ConnectionDialog(self)
        if dialog.exec_():
            # Refresh connection list
            self.refresh_connections()
    
    def manage_connections(self):
        """Open the connection manager dialog"""
        dialog = ConnectionManagerDialog(self.auth_manager, self)
        dialog.exec_()
    
    def refresh_connections(self):
        """Refresh the list of connections in the combo boxes"""
        # Refresh in file panels
        # Only access conn_combo on the remote panel
        self.remote_panel.conn_combo.clear()
        
        connections = self.auth_manager.list_connections()
        for conn in connections:
            name = conn.get('name')
            if name:
                self.remote_panel.conn_combo.addItem(name)
    
    def local_item_selected(self, path, is_dir):
        """Handle file or directory selection in the local panel"""
        # Extract the file/directory name from the path
        name = os.path.basename(path)
        
        # Get the current path in the remote panel
        remote_path = self.remote_panel.current_path
        
        if not remote_path or not self.remote_panel.client:
            QMessageBox.warning(self, "No Remote Connection", 
                              "Please connect to a remote server before uploading.")
            return
        
        # Set up source and destination paths
        source_path = path
        
        if is_dir:
            # If it's a directory, use the remote path as destination
            destination_path = os.path.join(remote_path, name)
            
            # Confirm directory upload
            reply = QMessageBox.question(
                self, "Upload Directory",
                f"Upload directory '{name}' to '{destination_path}'?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                
            if reply != QMessageBox.Yes:
                return
        else:
            # If it's a file, ask where to upload
            default_dest = os.path.join(remote_path, name) if remote_path else name
            destination_path = QInputDialog.getText(
                self, "Upload File", 
                "Remote destination path:", 
                QLineEdit.Normal, 
                default_dest)[0]
            
            if not destination_path:
                return
        
        # Start the transfer
        transfer_id = self.transfer_manager.upload_file(
            source_path, destination_path, self.on_transfer_progress)
        
        if transfer_id:
            self.status_bar.showMessage(f"Upload started: {name} → {destination_path}", 5000)
        else:
            QMessageBox.critical(self, "Upload Failed", "Failed to start upload.")
    
    def remote_item_selected(self, path, is_dir):
        """Handle file or directory selection in the remote panel"""
        # Extract the file/directory name from the path
        name = os.path.basename(path)
        
        # Get the current path in the local panel
        local_path = self.local_panel.current_path
        
        # Set up source and destination paths
        source_path = path
        
        if is_dir:
            # If it's a directory, ask for confirmation and use the local path as destination
            destination_path = os.path.join(local_path, name)
            
            # Confirm directory download
            reply = QMessageBox.question(
                self, "Download Directory",
                f"Download directory '{name}' to '{destination_path}'?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                
            if reply != QMessageBox.Yes:
                return
        else:
            # If it's a file, ask where to download
            default_dest = os.path.join(local_path, name)
            destination_path, _ = QFileDialog.getSaveFileName(
                self, "Download File", default_dest)
            
            if not destination_path:
                return
        
        # Start the transfer
        transfer_id = self.transfer_manager.download_file(
            source_path, destination_path, self.on_transfer_progress)
        
        if transfer_id:
            self.status_bar.showMessage(f"Download started: {name} → {destination_path}", 5000)
        else:
            QMessageBox.critical(self, "Download Failed", "Failed to start download.")
    
    def upload_file(self):
        """Upload a file or directory to the remote server"""
        # Get the selected file or directory from the local panel
        selected_items = self.local_panel.file_view.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a file or directory to upload.")
            return
        
        # For now, just get the first selected item
        index = selected_items[0]
        name = index.data(Qt.UserRole)
        is_dir = index.data(Qt.UserRole + 1)
        
        # Get the current path in the remote panel
        remote_path = self.remote_panel.current_path
        
        if is_dir:
            # If it's a directory, just use the remote path
            source_path = os.path.join(self.local_panel.current_path, name)
            destination_path = remote_path
        else:
            # If it's a file, ask where to upload
            destination_path, _ = QFileDialog.getSaveFileName(self, "Upload File", remote_path)
            source_path = os.path.join(self.local_panel.current_path, name)
        
        if destination_path:
            # Start the transfer
            transfer_id = self.transfer_manager.upload_file(
                source_path, destination_path, self.on_transfer_progress)
            
            if transfer_id:
                QMessageBox.information(self, "Upload Started", 
                                        f"Upload started with ID: {transfer_id}")
            else:
                QMessageBox.critical(self, "Upload Failed", "Failed to start upload.")
    
    def download_file(self):
        """Download a file or directory from the remote server"""
        # Get the selected file or directory from the remote panel
        selected_items = self.remote_panel.file_view.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a file or directory to download.")
            return
        
        # For now, just get the first selected item
        index = selected_items[0]
        name = index.data(Qt.UserRole)
        is_dir = index.data(Qt.UserRole + 1)
        
        # Get the current path in the local panel
        local_path = self.local_panel.current_path
        
        if is_dir:
            # If it's a directory, just use the local path
            source_path = os.path.join(self.remote_panel.current_path, name)
            destination_path = local_path
        else:
            # If it's a file, ask where to download
            destination_path, _ = QFileDialog.getSaveFileName(self, "Download File", local_path)
            source_path = os.path.join(self.remote_panel.current_path, name)
        
        if destination_path:
            # Start the transfer
            transfer_id = self.transfer_manager.download_file(
                source_path, destination_path, self.on_transfer_progress)
            
            if transfer_id:
                QMessageBox.information(self, "Download Started", 
                                        f"Download started with ID: {transfer_id}")
            else:
                QMessageBox.critical(self, "Download Failed", "Failed to start download.")
    
    def server_to_server_transfer(self):
        """Transfer a file or directory between two servers"""
        # This is a placeholder for the server-to-server transfer implementation
        QMessageBox.information(self, "Server to Server Transfer", 
                                "This feature is not yet implemented.")
    
    def on_transfer_progress(self, transfer_id, transferred, total):
        """Update the transfer progress in the UI"""
        # Find the transfer in the active table
        table = self.transfer_panel.active_table
        for row in range(table.rowCount()):
            if int(table.item(row, 0).text()) == transfer_id:
                # Update the progress column
                progress_item = QTableWidgetItem(f"{transferred} / {total}")
                table.setItem(row, 5, progress_item)
                break
    
    def show_about(self):
        """Show the about dialog"""
        QMessageBox.about(self, "About FilePilot",
                          "<h2>FilePilot SFTP Client</h2>"
                          "<p>Version 1.0</p>"
                          "<p>A simple SFTP client using PyQt and Paramiko.</p>"
                          "<p>Copyright © 2025 ALT+F4</p>"
                          "<p><a href='https://www.altf4.com'>www.altf4.com</a></p>")


def run_app():
    """
    Initialize and launch the FilePilot application.
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    window.refresh_connections()
    sys.exit(app.exec_())

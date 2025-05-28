import os
import sys
import time

from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTabWidget, QFileDialog, QMessageBox, QTreeView, 
    QHeaderView, QAbstractItemView, QProgressBar, QMenu, QAction, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QSplitter, QFrame, QInputDialog, QStyle, QStackedWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QModelIndex, QSize, QSettings, QObject
from PyQt5.QtGui import QIcon, QStandardItemModel, QStandardItem, QFont

from code.core.auth_manager import AuthManager
from code.core.transfer_manager import TransferManager, TransferType
from code.core.sftp_client import SFTPClient
from code.utils.logger import LoggerSetup
from code.gui.conn_dialog import ConnectionDialog
from code.gui.file_panel import FilePanel
from code.gui.transfer_panel import TransferPanel
from code.gui.conn_manager import ConnectionManagerDialog
from code.gui.server_to_server_panel import ServerToServerPanel, DualPanelWidget, LocalToServerPanel # Import the new classes


class TransferSignalBridge(QObject):
    """
    Bridge class to safely emit signals from transfer worker threads to the UI thread.
    Solves the QObject timer thread issues by ensuring all Qt operations happen on the main thread.
    """
    # Define a signal that will be emitted when transfer progress updates
    # Added 'transfer_type' and 'destination_panel_ref' for S2S transfers
    progressUpdated = pyqtSignal(int, int, int, TransferType, object) #
    
    def __init__(self):
        super().__init__()
        
    def update_progress(self, transfer_id: int, bytes_transferred: int, total_bytes: int,
                        transfer_type: TransferType = TransferType.DOWNLOAD, destination_panel_ref=None): #
        """
        This method is called from worker threads, but safely emits a signal
        that will be processed on the main Qt thread.
        """
        self.progressUpdated.emit(transfer_id, bytes_transferred, total_bytes, transfer_type, destination_panel_ref) #


class MainWindow(QMainWindow):
    """Main application window for the SFTP client"""
    
    def __init__(self):
        super().__init__()
        self.auth_manager = AuthManager()
        
        # Initialize logger first
        self.setup_logger()
        
        # Pass logger to transfer manager
        self.transfer_manager = TransferManager(logger=self.logger)
        self.sftp_client = None
        
        # Dictionary to track downloads and their destination paths
        self.active_downloads = {} # For local downloads
        # New: Dictionary to track uploads for refresh purposes (not strictly needed with panel ref, but good for consistency)
        self.active_uploads = {} 
        
        # Create and initialize the signal bridge for thread-safe UI updates
        self.signal_bridge = TransferSignalBridge()
        self.signal_bridge.progressUpdated.connect(self.on_transfer_progress) #
        
        # Initialize panels (will be added to stacked widget)
        self.local_panel = FilePanel(is_remote=False)
        self.remote_panel = FilePanel(is_remote=True)
        self.server_to_server_panel = ServerToServerPanel(
            parent=self,
            auth_manager=self.auth_manager,
            transfer_manager=self.transfer_manager,
            signal_bridge=self.signal_bridge
        )

        self.current_mode = "local_to_server" # Initial mode

        self.setup_ui()
        
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
        
        # Set application style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QSplitter::handle {
                background-color: #cccccc;
            }
            QStatusBar {
                background-color: #f0f0f0;
                border-top: 1px solid #ddd;
                padding: 2px;
                color: #333;
            }
            QMenuBar {
                background-color: #f0f0f0;
                border-bottom: 1px solid #ddd;
            }
            QMenuBar::item {
                padding: 5px 10px;
                margin: 0px;
                background-color: transparent;
            }
            QMenuBar::item:selected {
                background-color: #e0e0e0;
                border-radius: 2px;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                padding: 5px;
            }
            QMenu::item {
                padding: 5px 25px 5px 30px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #5c9eff;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background-color: #dddddd;
                margin: 4px 0px;
            }
            QMessageBox {
                background-color: #ffffff;
            }
        """)
        
        # Central widget
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)
        
        # Split view with file panels and transfer panel
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(6)  # Wider handle for easier resizing
        
        # --- Use the new LocalToServerPanel class instead of manual layout ---
        self.local_to_server_widget = LocalToServerPanel(
            parent=self,
            local_panel=self.local_panel,
            remote_panel=self.remote_panel
        )

        # Connect item selection signals for local-to-server mode
        self.local_panel.itemSelected.connect(self.local_item_selected)
        self.remote_panel.itemSelected.connect(self.remote_item_selected)

        # --- Stacked Widget for different transfer modes ---
        self.transfer_mode_stacked_widget = QStackedWidget()
        self.transfer_mode_stacked_widget.addWidget(self.local_to_server_widget) # Index 0: Local to Server
        self.transfer_mode_stacked_widget.addWidget(self.server_to_server_panel) # Index 1: Server to Server

        # Set initial view
        self.transfer_mode_stacked_widget.setCurrentIndex(0) #
        
        # Add the stacked widget to the main splitter
        splitter.addWidget(self.transfer_mode_stacked_widget) #
        
        # Transfer panel
        self.transfer_panel = TransferPanel(transfer_manager=self.transfer_manager)
        splitter.addWidget(self.transfer_panel)
        
        # Set initial sizes
        splitter.setSizes([400, 200]) #
        
        main_layout.addWidget(splitter)
        
        # Status bar with modern styling
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready") #
        
        # Set central widget
        self.setCentralWidget(central_widget) #
        
        # Create menu bar
        self.create_menus()
        
        # Initialize the local panel with home directory
        self.local_panel.load_directory(os.path.expanduser('~')) #
        
        # Set application font with modern typography
        self.setup_modern_fonts()
        
    def setup_modern_fonts(self):
        """Configure modern fonts for the application"""
        # Set up the main application font with fallbacks
        main_font = QFont()
        
        # Try to use system fonts in order of preference with better detection
        font_families = [
            "Inter",         # Modern web/UI font if available
            "-apple-system", # macOS system font
            "BlinkMacSystemFont", # Alternative macOS system font
            "Segoe UI",      # Windows 10/11 system font
            "Roboto",        # Android/Material Design
            "Oxygen",        # KDE Plasma font
            "Ubuntu",        # Ubuntu system font
            "Cantarell",     # GNOME system font
            "Fira Sans",     # Mozilla's font
            "Droid Sans",    # Alternative Android font
            "Helvetica Neue", # Modern Helvetica
            "sans-serif"     # Generic fallback
        ]
        
        # Find the first available font with better matching
        selected_font = "sans-serif"  # fallback
        for font_family in font_families:
            test_font = QFont(font_family)
            if test_font.exactMatch() or font_family in ["sans-serif", "-apple-system", "BlinkMacSystemFont"]:
                selected_font = font_family
                break
        
        # Configure main font properties with better settings
        main_font.setFamily(selected_font)
        main_font.setPointSize(10)  # Optimal size for readability
        main_font.setWeight(QFont.Normal)
        main_font.setStyleHint(QFont.SansSerif)
        main_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        main_font.setHintingPreference(QFont.PreferFullHinting)
        
        # Set as the default application font
        QApplication.setFont(main_font)
        
        # Configure specific fonts for different UI elements
        self.setup_ui_specific_fonts()
        
    def setup_ui_specific_fonts(self):
        """Setup fonts for specific UI elements with better typography"""
        # Header font for labels and important text
        self.header_font = QFont()
        header_families = ["Inter", "Segoe UI", "SF Pro Display", "Roboto", "Ubuntu", "sans-serif"]
        for font_family in header_families:
            self.header_font.setFamily(font_family)
            if self.header_font.exactMatch() or font_family == "sans-serif":
                break
        self.header_font.setPointSize(12)
        self.header_font.setWeight(QFont.DemiBold)
        self.header_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        
        # Monospace font for file paths and technical data
        self.mono_font = QFont()
        mono_families = [
            "JetBrains Mono",     # Modern coding font
            "SF Mono",            # macOS monospace
            "Cascadia Code",      # Windows Terminal font
            "Fira Code",          # Popular coding font
            "Source Code Pro",    # Adobe's coding font
            "Consolas",           # Windows monospace
            "Monaco",             # macOS fallback
            "Menlo",              # macOS alternative
            "Ubuntu Mono",        # Ubuntu monospace
            "DejaVu Sans Mono",   # Linux fallback
            "Liberation Mono",    # Open source alternative
            "monospace"           # Generic fallback
        ]
        
        for font_family in mono_families:
            self.mono_font.setFamily(font_family)
            if self.mono_font.exactMatch() or font_family == "monospace":
                break
        self.mono_font.setPointSize(9)
        self.mono_font.setWeight(QFont.Normal)
        self.mono_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        
        # Small font for status and secondary information
        self.small_font = QFont()
        small_families = ["Inter", "Segoe UI", "SF Pro Text", "Roboto", "Ubuntu", "sans-serif"]
        for font_family in small_families:
            self.small_font.setFamily(font_family)
            if self.small_font.exactMatch() or font_family == "sans-serif":
                break
        self.small_font.setPointSize(9)
        self.small_font.setWeight(QFont.Normal)
        self.small_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        
        # Button font for better button typography
        self.button_font = QFont()
        button_families = ["Inter", "Segoe UI", "SF Pro Text", "Roboto Medium", "Ubuntu", "sans-serif"]
        for font_family in button_families:
            self.button_font.setFamily(font_family)
            if self.button_font.exactMatch() or font_family == "sans-serif":
                break
        self.button_font.setPointSize(10)
        self.button_font.setWeight(QFont.Medium)
        self.button_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        
    def create_menus(self):
        """Create the application menu bar with icons"""
        # File menu
        file_menu = self.menuBar().addMenu("File") #
        
        new_conn_action = QAction(self.style().standardIcon(QStyle.SP_ComputerIcon),
                                 "New Connection...", self)
        new_conn_action.triggered.connect(self.new_connection)
        file_menu.addAction(new_conn_action) #
        
        manage_conn_action = QAction(self.style().standardIcon(QStyle.SP_FileDialogListView),
                                    "Manage Connections...", self)
        manage_conn_action.triggered.connect(self.manage_connections)
        file_menu.addAction(manage_conn_action) #
        
        file_menu.addSeparator() #
        
        exit_action = QAction(self.style().standardIcon(QStyle.SP_DialogCloseButton), 
                             "Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action) #
        
        # Transfer menu
        transfer_menu = self.menuBar().addMenu("Transfer") #
        
        upload_action = QAction(self.style().standardIcon(QStyle.SP_ArrowUp), 
                               "Upload...", self)
        upload_action.triggered.connect(self.upload_file)
        transfer_menu.addAction(upload_action) #
        
        download_action = QAction(self.style().standardIcon(QStyle.SP_ArrowDown),
                                 "Download...", self)
        download_action.triggered.connect(self.download_file)
        transfer_menu.addAction(download_action) #
        
        # Toggle Server to Server / Local to Server action
        self.toggle_transfer_mode_action = QAction(
            self.style().standardIcon(QStyle.SP_DirLinkIcon),
            "Server to Server Transfer", self) # Initial text for switching TO S2S
        self.toggle_transfer_mode_action.triggered.connect(self.toggle_transfer_mode)
        transfer_menu.addAction(self.toggle_transfer_mode_action) #
        
        # Help menu
        help_menu = self.menuBar().addMenu("Help") #
        
        about_action = QAction(self.style().standardIcon(QStyle.SP_DialogHelpButton),
                              "About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action) #
        
        # Restore the window geometry if available
        self.restore_geometry() #
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Save the window geometry
        self.save_geometry() #
        
        # Disconnect any active SFTP clients
        if self.remote_panel.client:
            self.remote_panel.client.disconnect()
        self.server_to_server_panel.disconnect_all() # Disconnect both clients in S2S panel

        # Stop transfer manager
        self.transfer_manager.stop() #
        
        event.accept() #
    
    def save_geometry(self):
        """Save the window geometry to settings"""
        settings = QSettings("YourCompany", "FilePilot")
        settings.setValue("geometry", self.saveGeometry()) #
        settings.setValue("windowState", self.saveState()) #
    
    def restore_geometry(self):
        """Restore the window geometry from settings"""
        settings = QSettings("YourCompany", "FilePilot")
        if settings.contains("geometry"):
            self.restoreGeometry(settings.value("geometry")) #
        if settings.contains("windowState"):
            self.restoreState(settings.value("windowState")) #
    
    def new_connection(self):
        """Open the connection dialog to create a new connection"""
        dialog = ConnectionDialog(self)
        if dialog.exec_():
            # Refresh connection list in all panels
            self.refresh_connections() #
    
    def manage_connections(self):
        """Open the connection manager dialog"""
        dialog = ConnectionManagerDialog(self.auth_manager, self)
        dialog.exec_() #
    
    def refresh_connections(self):
        """Refresh the list of connections in the combo boxes for all panels"""
        # Refresh in local-to-server remote panel
        self.remote_panel.refresh_connections() #
        # Refresh in server-to-server panels
        self.server_to_server_panel.refresh_connections() #

    def toggle_transfer_mode(self):
        """Toggle between local-to-server and server-to-server transfer modes."""
        if self.current_mode == "local_to_server": #
            # Switch to server-to-server mode
            self.current_mode = "server_to_server" #
            self.transfer_mode_stacked_widget.setCurrentIndex(1) # Show server-to-server panel
            self.toggle_transfer_mode_action.setText("Local to Server Transfer") #
            self.toggle_transfer_mode_action.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon)) # Change icon
            
            # Disconnect previous remote connection if any
            if self.remote_panel.client:
                self.remote_panel.client.disconnect()
                self.remote_panel.set_client(None) # Clear panel's client
                self.remote_panel.file_model.removeRows(0, self.remote_panel.file_model.rowCount()) # Clear view
                self.remote_panel.path_edit.setText("") # Clear path
            self.status_bar.showMessage("Switched to Server to Server mode.") #
            self.server_to_server_panel.refresh_connections() # Ensure connections are loaded
        else:
            # Switch to local-to-server mode
            self.current_mode = "local_to_server" #
            self.transfer_mode_stacked_widget.setCurrentIndex(0) # Show local-to-server panel
            self.toggle_transfer_mode_action.setText("Server to Server Transfer") #
            self.toggle_transfer_mode_action.setIcon(self.style().standardIcon(QStyle.SP_DirLinkIcon)) # Change icon

            # Disconnect server-to-server connections if any
            self.server_to_server_panel.disconnect_all() #
            self.status_bar.showMessage("Switched to Local to Server mode.") #
            # Re-initialize local panel to home directory
            self.local_panel.load_directory(os.path.expanduser('~')) #

    def local_item_selected(self, path, is_dir):
        """Handle file or directory selection in the local panel (only in local-to-server mode)."""
        if self.current_mode != "local_to_server": 
            # If not in local-to-server mode, this signal should ideally not be active or handled differently.
            # For now, we'll just return to prevent unintended behavior.
            return 

        # Extract the file/directory name from the path
        name = os.path.basename(path) 
        
        # Get the current path in the remote panel
        remote_path = self.remote_panel.current_path 
        
        if not remote_path or not self.remote_panel.client:
            QMessageBox.warning(self, "No Remote Connection", 
                              "Please connect to a remote server before uploading.")
            return
        
        # Set up source and destination paths
        source_full_path = path 
        destination_full_path = os.path.join(remote_path, name).replace('\\', '/')
        
        # Ask for confirmation with the predetermined destination path
        if is_dir:
            # Confirm directory upload
            reply = QMessageBox.question(
                self, "Upload Directory",
                f"Upload directory '{name}' to '{destination_full_path}'?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        else:
            # Confirm file upload
            reply = QMessageBox.question(
                self, "Upload File",
                f"Upload file '{name}' to '{destination_full_path}'?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                
        if reply != QMessageBox.Yes:
            return
        
        # Create overwrite callback for upload
        def upload_overwrite_callback(remote_file_path):
            reply = QMessageBox.question(
                self, "File Exists",
                f"The file '{os.path.basename(remote_file_path)}' already exists on the remote server.\n\n"
                f"Remote path: {remote_file_path}\n\n"
                "Do you want to overwrite it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            return reply == QMessageBox.Yes
        
        # Start the transfer using the signal bridge for thread-safe callbacks
        transfer_id = self.transfer_manager.upload_file(
            source_full_path, destination_full_path, 
            # Pass TransferType.UPLOAD and a reference to the remote_panel
            lambda tid, tr, tt: self.signal_bridge.update_progress(tid, tr, tt, TransferType.UPLOAD, self.remote_panel),
            upload_overwrite_callback)
        
        if transfer_id:
            # Track the upload with its destination path (for refresh)
            self.active_uploads[transfer_id] = destination_full_path 

            self.status_bar.showMessage(f"Upload started: {name} → {destination_full_path}", 5000) 
            # Force immediate update of the transfer panel
            self.transfer_panel.update_transfers() 
        else:
            QMessageBox.critical(self, "Upload Failed", "Failed to start upload.")
    
    def remote_item_selected(self, path, is_dir):
        """Handle file or directory selection in the remote panel (only in local-to-server mode)."""
        if self.current_mode != "local_to_server":
            # If not in local-to-server mode, this signal should ideally not be active or handled differently.
            # For now, we'll just return to prevent unintended behavior.
            return

        # Extract the file/directory name from the path
        name = os.path.basename(path)
        
        # Get the current path in the local panel
        local_path = self.local_panel.current_path
        
        # Set up source and destination paths
        source_full_path = path
        destination_full_path = os.path.join(local_path, name)
        
        # Ask for confirmation with the predetermined destination path
        if is_dir:
            # Confirm directory download
            reply = QMessageBox.question(
                self, "Download Directory",
                f"Download directory '{name}' to '{destination_full_path}'?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        else:
            # Confirm file download
            reply = QMessageBox.question(
                self, "Download File",
                f"Download file '{name}' to '{destination_full_path}'?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                
        if reply != QMessageBox.Yes:
            return
        
        # Create overwrite callback for download
        def download_overwrite_callback(local_file_path):
            reply = QMessageBox.question(
                self, "File Exists",
                f"The file '{os.path.basename(local_file_path)}' already exists locally.\n\n"
                f"Local path: {local_file_path}\n\n"
                "Do you want to overwrite it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            return reply == QMessageBox.Yes
        
        # Start the transfer using the signal bridge for thread-safe callbacks
        transfer_id = self.transfer_manager.download_file(
                source_full_path, destination_full_path, 
                lambda tid, tr, tt: self.signal_bridge.update_progress(tid, tr, tt, TransferType.DOWNLOAD, None),
                download_overwrite_callback)
            
        if transfer_id:
            # Track the download with its destination path
            self.active_downloads[transfer_id] = destination_full_path
            
            self.status_bar.showMessage(f"Download started: {name} → {destination_full_path}", 5000)
            # Force immediate update of the transfer panel
            self.transfer_panel.update_transfers()
        else:
            QMessageBox.critical(self, "Download Failed", "Failed to start download.")
    
    def upload_file(self):
        """Upload a file or directory to the remote server (only in local-to-server mode)."""
        if self.current_mode != "local_to_server": #
            QMessageBox.information(self, "Mode Mismatch", "Upload/Download actions are for Local to Server mode. Please switch modes or use Server to Server transfer directly.")
            return

        # Get the selected file or directory from the local panel
        selected_items = self.local_panel.file_view.selectedIndexes() #
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a file or directory to upload.")
            return
        
        # For now, just get the first selected item
        index = selected_items[0] #
        # Data is stored in column 0 of the model, not the index itself
        full_path = index.sibling(index.row(), 0).data(Qt.UserRole) 
        is_dir = index.sibling(index.row(), 0).data(Qt.UserRole + 1)
        
        # Get the current path in the remote panel
        remote_path = self.remote_panel.current_path #
        
        if is_dir:
            # If it's a directory, just use the remote path as the base for destination
            source_path = full_path
            # The destination path should be the remote_path plus the directory name
            destination_path = os.path.join(remote_path, os.path.basename(full_path)).replace('\\', '/')
        else:
            # If it's a file, ask where to upload
            # Pre-fill with the remote current path and the file name
            default_remote_path = os.path.join(remote_path, os.path.basename(full_path)).replace('\\', '/')
            destination_path, ok = QInputDialog.getText(self, "Upload File", "Remote destination path:", QLineEdit.Normal, default_remote_path)
            if not ok or not destination_path:
                return
            source_path = full_path
        
        if destination_path:
            # Start the transfer using the signal bridge for thread-safe callbacks
            transfer_id = self.transfer_manager.upload_file(
                source_path, destination_path, 
                # Pass TransferType.UPLOAD and a reference to the remote_panel
                lambda tid, tr, tt: self.signal_bridge.update_progress(tid, tr, tt, TransferType.UPLOAD, self.remote_panel))
            
            if transfer_id:
                # Track the upload with its destination path (for refresh)
                self.active_uploads[transfer_id] = destination_path

                QMessageBox.information(self, "Upload Started", 
                                        f"Upload of '{os.path.basename(source_path)}' started.") #
                # Force immediate update of the transfer panel
                self.transfer_panel.update_transfers() #
            else:
                QMessageBox.critical(self, "Upload Failed", "Failed to start upload.") #
    
    def download_file(self):
        """Download a file or directory from the remote server (only in local-to-server mode)."""
        if self.current_mode != "local_to_server": #
            QMessageBox.information(self, "Mode Mismatch", "Upload/Download actions are for Local to Server mode. Please switch modes or use Server to Server transfer directly.")
            return

        # Get the selected file or directory from the remote panel
        selected_items = self.remote_panel.file_view.selectedIndexes() #
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a file or directory to download.")
            return
        
        # For now, just get the first selected item
        index = selected_items[0] #
        # Data is stored in column 0 of the model, not the index itself
        full_path = index.sibling(index.row(), 0).data(Qt.UserRole)
        is_dir = index.sibling(index.row(), 0).data(Qt.UserRole + 1)
        
        # Get the current path in the local panel
        local_path = self.local_panel.current_path #
        
        if is_dir:
            # If it's a directory, use the local path as the base for destination
            source_path = full_path
            # The destination path should be the local_path plus the directory name
            destination_path = os.path.join(local_path, os.path.basename(full_path))
            
            # Confirm directory download
            reply = QMessageBox.question(
                self, "Download Directory",
                f"Download directory '{os.path.basename(source_path)}' to '{destination_path}'?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                
            if reply != QMessageBox.Yes:
                return
        else:
            # If it's a file, ask where to download
            # Pre-fill with the local current path and the file name
            default_local_path = os.path.join(local_path, os.path.basename(full_path))
            destination_path, _ = QFileDialog.getSaveFileName(self, "Download File", default_local_path)
            if not destination_path:
                return
            source_path = full_path
        
        if destination_path:
            # Start the transfer using the signal bridge for thread-safe callbacks
            transfer_id = self.transfer_manager.download_file(
                source_path, destination_path, 
                lambda tid, tr, tt: self.signal_bridge.update_progress(tid, tr, tt, TransferType.DOWNLOAD, None)) #
            
            if transfer_id:
                # Track the download with its destination path
                self.active_downloads[transfer_id] = destination_path #
                
                QMessageBox.information(self, "Download Started", 
                                        f"Download of '{os.path.basename(source_path)}' started.") #
                # Force immediate update of the transfer panel
                self.transfer_panel.update_transfers() #
            else:
                QMessageBox.critical(self, "Download Failed", "Failed to start download.") #
    
    def server_to_server_transfer(self):
        """This menu action is now handled by toggle_transfer_mode."""
        pass # This method is no longer directly called by the menu action
    
    def on_transfer_progress(self, transfer_id: int, transferred: int, total: int,
                            transfer_type: TransferType, destination_panel_ref: object = None): #
        """
        Update the transfer progress in the UI and refresh panels on transfer completion.
        'destination_panel_ref' is the actual FilePanel object for S2S transfers.
        """
        # Find the transfer in the active table
        table = self.transfer_panel.active_table #
        found = False
        
        for row in range(table.rowCount()): #
            if table.item(row, 0) and int(table.item(row, 0).text()) == transfer_id: #
                # Update the progress column
                progress_item = QTableWidgetItem(f"{transferred / total * 100:.1f}%") #
                table.setItem(row, 5, progress_item) #
                
                # Update size column
                size_text = f"{transferred / (1024*1024):.2f} MB / {total / (1024*1024):.2f} MB"
                table.setItem(row, 7, QTableWidgetItem(size_text)) #
                
                found = True
                break
        
        # Check if this is a completed transfer (either by bytes or by checking transfer status)
        transfer_completed = False
        
        # Check completion by bytes transferred
        if transferred >= total and total > 0:
            transfer_completed = True
        
        # Also check the actual transfer status in case bytes comparison isn't reliable
        if not transfer_completed:
            transfer_status = self.transfer_manager.get_transfer_status(transfer_id)
            if transfer_status and transfer_status.get('status') == 'COMPLETED':
                transfer_completed = True
        
        if transfer_completed:
            if transfer_type == TransferType.DOWNLOAD:
                if transfer_id in self.active_downloads:
                    dest_path = self.active_downloads[transfer_id]
                    # Always refresh the local panel on download completion
                    QTimer.singleShot(500, self.local_panel.refresh)
                    self.status_bar.showMessage(f"Download completed: {os.path.basename(dest_path)}", 5000)
                    del self.active_downloads[transfer_id]
                else:
                    # Fallback: refresh local panel even if transfer ID not tracked
                    QTimer.singleShot(500, self.local_panel.refresh)
                    self.status_bar.showMessage("Download completed", 5000)
            
            elif transfer_type == TransferType.UPLOAD:
                if transfer_id in self.active_uploads:
                    dest_path = self.active_uploads[transfer_id]
                    # Refresh the remote panel on upload completion
                    QTimer.singleShot(500, self.remote_panel.refresh)
                    self.status_bar.showMessage(f"Upload completed: {os.path.basename(dest_path)}", 5000)
                    del self.active_uploads[transfer_id]
                else:
                    # Fallback: refresh remote panel even if transfer ID not tracked
                    QTimer.singleShot(500, self.remote_panel.refresh)
                    self.status_bar.showMessage("Upload completed", 5000)
            
            elif transfer_type == TransferType.SERVER_TO_SERVER:
                # Refresh the destination panel if a reference was provided
                if destination_panel_ref and isinstance(destination_panel_ref, FilePanel):
                    QTimer.singleShot(500, destination_panel_ref.refresh)
                    self.status_bar.showMessage(f"Server-to-server transfer completed to {destination_panel_ref.current_path}", 5000)
                else:
                    # Fallback: refresh both server-to-server panels if no specific reference
                    QTimer.singleShot(500, self.server_to_server_panel.source_panel.refresh)
                    QTimer.singleShot(500, self.server_to_server_panel.destination_panel.refresh)
                    self.status_bar.showMessage("Server-to-server transfer completed", 5000)
            
            # Force an immediate transfer panel update to reflect completion
            QTimer.singleShot(100, self.transfer_panel.update_transfers)
        
        # If transfer wasn't found in the table, request UI update
        if not found:
            self.transfer_panel.update_transfers()
    
    def show_about(self):
        """Show the about dialog"""
        QMessageBox.about(self, "About FilePilot",
                          "<h2>FilePilot SFTP Client</h2>"
                          "<p>Version 1.0</p>"
                          "<p>A simple SFTP client using PyQt and Paramiko.</p>"
                          "<p>Copyright © 2025 ALT+F4</p>"
                          "<p><a href='https://www.altf4.com'>www.altf4.com</a></p>") #


def run_app():
    """
    Initialize and launch the FilePilot application.
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    window.refresh_connections() #
    sys.exit(app.exec_()) #
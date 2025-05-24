import os
import sys
import time  # Add this import for file panel

from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTabWidget, QFileDialog, QMessageBox, QTreeView, 
    QHeaderView, QAbstractItemView, QProgressBar, QMenu, QAction, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QSplitter, QFrame, QInputDialog, QStyle
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QModelIndex, QSize, QSettings, QObject
from PyQt5.QtGui import QIcon, QStandardItemModel, QStandardItem, QFont

from code.core.auth_manager import AuthManager
from code.core.transfer_manager import TransferManager
from code.core.sftp_client import SFTPClient
from code.utils.logger import LoggerSetup
from code.gui.conn_dialog import ConnectionDialog
from code.gui.file_panel import FilePanel
from code.gui.transfer_panel import TransferPanel
from code.gui.conn_manager import ConnectionManagerDialog



class TransferSignalBridge(QObject):
    """
    Bridge class to safely emit signals from transfer worker threads to the UI thread.
    Solves the QObject timer thread issues by ensuring all Qt operations happen on the main thread.
    """
    # Define a signal that will be emitted when transfer progress updates
    progressUpdated = pyqtSignal(int, int, int)  # transfer_id, bytes_transferred, total_bytes
    
    def __init__(self):
        super().__init__()
        
    def update_progress(self, transfer_id, bytes_transferred, total_bytes):
        """
        This method is called from worker threads, but safely emits a signal
        that will be processed on the main Qt thread
        """
        self.progressUpdated.emit(transfer_id, bytes_transferred, total_bytes)


class MainWindow(QMainWindow):
    """Main application window for the SFTP client"""
    
    def __init__(self):
        super().__init__()
        self.auth_manager = AuthManager()
        self.transfer_manager = TransferManager()
        self.sftp_client = None
        
        # Dictionary to track downloads and their destination paths
        self.active_downloads = {}
        
        # Create and initialize the signal bridge for thread-safe UI updates
        self.signal_bridge = TransferSignalBridge()
        self.signal_bridge.progressUpdated.connect(self.on_transfer_progress)
        
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
        
        # File panels container
        file_panels = QWidget()
        file_layout = QHBoxLayout(file_panels)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(6)
        
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
        
        # Status bar with modern styling
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")
        
        # Set central widget
        self.setCentralWidget(central_widget)
        
        # Create menu bar
        self.create_menus()
        
        # Initialize the local panel with home directory
        self.local_panel.load_directory(os.path.expanduser('~'))
        
        # Set application font
        font = QFont()
        font.setFamily("Arial")
        font.setPointSize(9)
        QApplication.setFont(font)
        
    def create_menus(self):
        """Create the application menu bar with icons"""
        # File menu
        file_menu = self.menuBar().addMenu("File")
        
        new_conn_action = QAction(self.style().standardIcon(QStyle.SP_ComputerIcon),
                                 "New Connection...", self)
        new_conn_action.triggered.connect(self.new_connection)
        file_menu.addAction(new_conn_action)
        
        manage_conn_action = QAction(self.style().standardIcon(QStyle.SP_FileDialogListView),
                                    "Manage Connections...", self)
        manage_conn_action.triggered.connect(self.manage_connections)
        file_menu.addAction(manage_conn_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction(self.style().standardIcon(QStyle.SP_DialogCloseButton), 
                             "Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Transfer menu
        transfer_menu = self.menuBar().addMenu("Transfer")
        
        upload_action = QAction(self.style().standardIcon(QStyle.SP_ArrowUp), 
                               "Upload...", self)
        upload_action.triggered.connect(self.upload_file)
        transfer_menu.addAction(upload_action)
        
        download_action = QAction(self.style().standardIcon(QStyle.SP_ArrowDown),
                                 "Download...", self)
        download_action.triggered.connect(self.download_file)
        transfer_menu.addAction(download_action)
        
        server_to_server_action = QAction(self.style().standardIcon(QStyle.SP_DirLinkIcon),
                                         "Server to Server Transfer...", self)
        server_to_server_action.triggered.connect(self.server_to_server_transfer)
        transfer_menu.addAction(server_to_server_action)
        
        # Help menu
        help_menu = self.menuBar().addMenu("Help")
        
        about_action = QAction(self.style().standardIcon(QStyle.SP_DialogHelpButton),
                              "About", self)
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
        
        # Start the transfer using the signal bridge for thread-safe callbacks
        transfer_id = self.transfer_manager.upload_file(
            source_path, destination_path, self.signal_bridge.update_progress)
        
        if transfer_id:
            self.status_bar.showMessage(f"Upload started: {name} → {destination_path}", 5000)
            # Force immediate update of the transfer panel
            self.transfer_panel.update_transfers()
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
        
        # Start the transfer using the signal bridge for thread-safe callbacks
        transfer_id = self.transfer_manager.download_file(
            source_path, destination_path, self.signal_bridge.update_progress)
        
        if transfer_id:
            # Track the download with its destination path
            self.active_downloads[transfer_id] = destination_path
            
            self.status_bar.showMessage(f"Download started: {name} → {destination_path}", 5000)
            # Force immediate update of the transfer panel
            self.transfer_panel.update_transfers()
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
            # Start the transfer using the signal bridge for thread-safe callbacks
            transfer_id = self.transfer_manager.upload_file(
                source_path, destination_path, self.signal_bridge.update_progress)
            
            if transfer_id:
                QMessageBox.information(self, "Upload Started", 
                                        f"Upload started with ID: {transfer_id}")
                # Force immediate update of the transfer panel
                self.transfer_panel.update_transfers()
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
            # Start the transfer using the signal bridge for thread-safe callbacks
            transfer_id = self.transfer_manager.download_file(
                source_path, destination_path, self.signal_bridge.update_progress)
            
            if transfer_id:
                # Track the download with its destination path
                self.active_downloads[transfer_id] = destination_path
                
                QMessageBox.information(self, "Download Started", 
                                        f"Download started with ID: {transfer_id}")
                # Force immediate update of the transfer panel
                self.transfer_panel.update_transfers()
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
        found = False
        
        for row in range(table.rowCount()):
            if table.item(row, 0) and int(table.item(row, 0).text()) == transfer_id:
                # Update the progress column
                progress_item = QTableWidgetItem(f"{transferred / total * 100:.1f}%")
                table.setItem(row, 5, progress_item)
                
                # Update size column
                size_text = f"{transferred / (1024*1024):.2f} MB / {total / (1024*1024):.2f} MB"
                table.setItem(row, 7, QTableWidgetItem(size_text))
                
                found = True
                break
        
        # Check if this is a download and if it's complete
        if transfer_id in self.active_downloads and transferred >= total and total > 0:
            # Get the destination directory
            dest_path = self.active_downloads[transfer_id]
            dest_dir = os.path.dirname(dest_path)
            
            # Force refresh of the local panel
            if os.path.exists(dest_path):
                # If local panel is showing the destination directory
                if dest_dir == self.local_panel.current_path:
                    # Use QTimer to schedule refresh after a slight delay
                    QTimer.singleShot(500, self.local_panel.refresh)
                    self.status_bar.showMessage(f"Download completed: {os.path.basename(dest_path)}", 5000)
                
                # Remove from active downloads since it's complete
                del self.active_downloads[transfer_id]
        
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

import os
import sys
import time
from typing import Dict, List, Optional

from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTabWidget, QFileDialog, QMessageBox, QTreeView, 
    QHeaderView, QAbstractItemView, QProgressBar, QMenu, QAction, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QSplitter, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QModelIndex, QSize, QSettings
from PyQt5.QtGui import QIcon, QStandardItemModel, QStandardItem

from ..core.sftp_client import SFTPClient
from ..core.auth_manager import AuthManager
from ..core.transfer_manager import TransferManager, TransferType
from ..utils.logger import LoggerSetup


class ConnectionDialog(QDialog):
    """Dialog for creating and editing SFTP connections"""
    
    def __init__(self, parent=None, auth_manager=None, connection_name=None):
        super().__init__(parent)
        self.auth_manager = auth_manager or AuthManager()
        self.connection_name = connection_name
        self.setWindowTitle("SFTP Connection")
        self.resize(400, 350)
        self.setup_ui()
        
        # Load connection data if editing existing connection
        if connection_name:
            self.load_connection(connection_name)
    
    def setup_ui(self):
        """Set up the dialog UI"""
        layout = QVBoxLayout(self)
        
        # Create form layout
        form = QFormLayout()
        
        # Connection name
        self.name_edit = QLineEdit()
        form.addRow("Connection Name:", self.name_edit)
        
        # Host
        self.host_edit = QLineEdit()
        form.addRow("Host:", self.host_edit)
        
        # Port
        self.port_spin = QSpinBox()
        self.port_spin.setMinimum(1)
        self.port_spin.setMaximum(65535)
        self.port_spin.setValue(22)
        form.addRow("Port:", self.port_spin)
        
        # Username
        self.username_edit = QLineEdit()
        form.addRow("Username:", self.username_edit)
        
        # Authentication type selector
        self.auth_type = QComboBox()
        self.auth_type.addItems(["Password", "Key File"])
        self.auth_type.currentTextChanged.connect(self.toggle_auth_fields)
        form.addRow("Auth Type:", self.auth_type)
        
        # Password field
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addRow("Password:", self.password_edit)
        
        # Key file path
        self.key_path_edit = QLineEdit()
        self.browse_btn = QPushButton("Browse...")
        key_layout = QHBoxLayout()
        key_layout.addWidget(self.key_path_edit)
        key_layout.addWidget(self.browse_btn)
        form.addRow("Key File:", key_layout)
        
        # Key passphrase (optional)
        self.passphrase_edit = QLineEdit()
        self.passphrase_edit.setEchoMode(QLineEdit.Password)
        form.addRow("Passphrase:", self.passphrase_edit)
        
        # Storage options
        self.use_keyring = QCheckBox("Store credentials in system keyring")
        self.use_keyring.setChecked(True)
        self.encrypt_config = QCheckBox("Encrypt configuration file")
        
        # Encryption password
        self.encryption_password = QLineEdit()
        self.encryption_password.setEchoMode(QLineEdit.Password)
        form.addRow("Encryption Password:", self.encryption_password)
        
        # Add form to layout
        layout.addLayout(form)
        
        # Add keyring and encryption options
        layout.addWidget(self.use_keyring)
        layout.addWidget(self.encrypt_config)
        
        # Test connection button
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self.test_connection)
        layout.addWidget(self.test_btn)
        
        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_connection)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Connect signals
        self.browse_btn.clicked.connect(self.browse_key_file)
        self.encrypt_config.stateChanged.connect(self.toggle_encryption_password)
        
        # Initial state
        self.toggle_auth_fields("Password")
        self.toggle_encryption_password(False)
    
    def toggle_auth_fields(self, auth_type):
        """Toggle visibility of auth fields based on selected auth type"""
        if auth_type == "Password":
            self.password_edit.setEnabled(True)
            self.key_path_edit.setEnabled(False)
            self.browse_btn.setEnabled(False)
            self.passphrase_edit.setEnabled(False)
        else:
            self.password_edit.setEnabled(False)
            self.key_path_edit.setEnabled(True)
            self.browse_btn.setEnabled(True)
            self.passphrase_edit.setEnabled(True)
    
    def toggle_encryption_password(self, state):
        """Toggle encryption password field based on checkbox state"""
        self.encryption_password.setEnabled(state)
    
    def browse_key_file(self):
        """Open file dialog to select key file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Private Key", "", "All Files (*)"
        )
        if file_path:
            self.key_path_edit.setText(file_path)
    
    def load_connection(self, name):
        """Load connection settings for editing"""
        connection = self.auth_manager.get_connection(name)
        if connection:
            self.name_edit.setText(connection.get('name', ''))
            self.host_edit.setText(connection.get('host', ''))
            self.port_spin.setValue(connection.get('port', 22))
            self.username_edit.setText(connection.get('username', ''))
            
            # Set auth type
            if connection.get('key_path'):
                self.auth_type.setCurrentText("Key File")
                self.key_path_edit.setText(connection.get('key_path', ''))
                if 'passphrase' in connection:
                    self.passphrase_edit.setText(connection['passphrase'])
            else:
                self.auth_type.setCurrentText("Password")
                if 'password' in connection:
                    self.password_edit.setText(connection['password'])
    
    def test_connection(self):
        """Test the SFTP connection with current settings"""
        # Get connection parameters
        host = self.host_edit.text()
        port = self.port_spin.value()
        username = self.username_edit.text()
        
        if not (host and username):
            QMessageBox.warning(self, "Input Error", "Host and username are required.")
            return
        
        # Create client
        client = SFTPClient()
        
        # Build connection parameters
        params = {
            'host': host,
            'port': port,
            'username': username
        }
        
        if self.auth_type.currentText() == "Password":
            params['password'] = self.password_edit.text()
        else:
            key_path = self.key_path_edit.text()
            if not key_path:
                QMessageBox.warning(self, "Input Error", "Key file path is required.")
                return
                
            params['key_path'] = key_path
            if self.passphrase_edit.text():
                params['passphrase'] = self.passphrase_edit.text()
                
        # Try to connect
        try:
            if client.connect(**params):
                client.disconnect()
                QMessageBox.information(self, "Success", "Connection successful!")
            else:
                QMessageBox.critical(self, "Error", "Connection failed.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Connection error: {str(e)}")
    
    def save_connection(self):
        """Save the connection to storage"""
        name = self.name_edit.text()
        host = self.host_edit.text()
        port = self.port_spin.value()
        username = self.username_edit.text()
        
        if not (name and host and username):
            QMessageBox.warning(self, "Input Error", "Name, host and username are required.")
            return
        
        # Build connection parameters for saving
        params = {
            'name': name,
            'host': host,
            'port': port,
            'username': username,
            'use_keyring': self.use_keyring.isChecked(),
            'encrypt': self.encrypt_config.isChecked()
        }
        
        if self.auth_type.currentText() == "Password":
            params['password'] = self.password_edit.text()
        else:
            params['key_path'] = self.key_path_edit.text()
            if self.passphrase_edit.text():
                params['passphrase'] = self.passphrase_edit.text()
                
        if self.encrypt_config.isChecked():
            params['encryption_password'] = self.encryption_password.text()
            
        # Save connection
        try:
            if self.auth_manager.save_connection(**params):
                self.accept()  # Close dialog
            else:
                QMessageBox.critical(self, "Error", "Failed to save connection.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving connection: {str(e)}")


class FilePanel(QWidget):
    """
    Panel for displaying files in local or remote location
    """
    itemSelected = pyqtSignal(str, bool)  # Path, isDir
    
    def __init__(self, parent=None, is_remote=False):
        super().__init__(parent)
        self.is_remote = is_remote
        self.current_path = ""
        self.client = None
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Path display and navigation
        path_layout = QHBoxLayout()
        
        self.path_label = QLabel("Path:")
        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(self.navigate_to_path)
        
        self.up_button = QPushButton("↑")
        self.up_button.clicked.connect(self.navigate_up)
        self.up_button.setMaximumWidth(30)
        
        self.refresh_button = QPushButton("⟳")
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh_button.setMaximumWidth(30)
        
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.up_button)
        path_layout.addWidget(self.refresh_button)
        
        layout.addLayout(path_layout)
        
        # File tree view
        self.file_model = QStandardItemModel()
        self.file_model.setHorizontalHeaderLabels(["Name", "Size", "Type", "Modified"])
        
        self.file_view = QTreeView()
        self.file_view.setModel(self.file_model)
        self.file_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_view.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_view.doubleClicked.connect(self.item_double_clicked)
        self.file_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_view.customContextMenuRequested.connect(self.show_context_menu)
        
        layout.addWidget(self.file_view)
        
        # If remote, add connection selector
        if self.is_remote:
            conn_layout = QHBoxLayout()
            self.conn_label = QLabel("Connection:")
            self.conn_combo = QComboBox()
            self.conn_combo.currentTextChanged.connect(self.connection_changed)
            self.conn_button = QPushButton("New...")
            self.conn_button.clicked.connect(self.new_connection)
            
            conn_layout.addWidget(self.conn_label)
            conn_layout.addWidget(self.conn_combo)
            conn_layout.addWidget(self.conn_button)
            
            layout.insertLayout(0, conn_layout)
    
    def set_client(self, client):
        """Set the SFTP client for remote panel"""
        self.client = client
        self.refresh()
    
    def connection_changed(self, connection_name):
        """Handle change of selected connection"""
        if not connection_name:
            self.client = None
            return
            
        try:
            # Get connection details from auth manager
            parent_window = self.window()
            if parent_window and hasattr(parent_window, 'auth_manager'):
                auth_manager = parent_window.auth_manager
                connection = auth_manager.get_connection(connection_name)
                
                if connection:
                    # Create new SFTP client
                    client = SFTPClient()
                    
                    # Build connection parameters
                    params = {
                        'host': connection.get('host', ''),
                        'port': connection.get('port', 22),
                        'username': connection.get('username', '')
                    }
                    
                    if connection.get('key_path'):
                        params['key_path'] = connection.get('key_path')
                        if 'passphrase' in connection:
                            params['passphrase'] = connection.get('passphrase')
                    else:
                        params['password'] = connection.get('password', '')
                    
                    # Try to connect
                    if client.connect(**params):
                        self.set_client(client)
                        if hasattr(parent_window, 'status_bar'):
                            parent_window.status_bar.showMessage(f"Connected to {connection_name}")
                    else:
                        QMessageBox.critical(self, "Error", "Failed to connect to server.")
            else:
                QMessageBox.warning(self, "Error", "Could not access connection manager.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Connection error: {str(e)}")
    
    def new_connection(self):
        """Open dialog to create a new connection"""
        # Get the parent window to access the auth_manager
        parent_window = self.window()
        auth_manager = parent_window.auth_manager if hasattr(parent_window, 'auth_manager') else None
        
        dialog = ConnectionDialog(self, auth_manager)
        if dialog.exec_():
            # Refresh connection list
            if hasattr(parent_window, 'refresh_connections'):
                parent_window.refresh_connections()
    
    def navigate_to_path(self):
        """Navigate to the path entered in the path field"""
        path = self.path_edit.text()
        self.load_directory(path)
    
    def navigate_up(self):
        """Navigate to the parent directory"""
        if self.current_path:
            parent = os.path.dirname(self.current_path)
            self.load_directory(parent)
    
    def refresh(self):
        """Refresh the current directory"""
        if self.current_path:
            self.load_directory(self.current_path)
        else:
            # Load default path
            if self.is_remote and self.client:
                self.load_directory('.')
            elif not self.is_remote:
                self.load_directory(os.path.expanduser('~'))
    
    def load_directory(self, path):
        """Load directory contents into the view"""
        self.file_model.removeRows(0, self.file_model.rowCount())
        
        try:
            if self.is_remote and self.client:
                # Remote directory listing
                files = self.client.list_directory(path)
                self.current_path = path
                self.path_edit.setText(path)
                
                for name, size, ftype, modified in files:
                    self.add_file_item(name, size, ftype, modified)
            elif not self.is_remote:
                # Local directory listing
                if os.path.isdir(path):
                    self.current_path = path
                    self.path_edit.setText(path)
                    
                    entries = os.listdir(path)
                    for entry in entries:
                        full_path = os.path.join(path, entry)
                        if os.path.isdir(full_path):
                            ftype = 'dir'
                            size = 0
                        else:
                            ftype = 'file'
                            size = os.path.getsize(full_path)
                        
                        modified = time.strftime('%Y-%m-%d %H:%M:%S', 
                                               time.localtime(os.path.getmtime(full_path)))
                        
                        self.add_file_item(entry, size, ftype, modified)
                else:
                    raise ValueError(f"Not a directory: {path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load directory: {str(e)}")
    
    def add_file_item(self, name, size, ftype, modified):
        """Add a file item to the model"""
        name_item = QStandardItem(name)
        name_item.setData(name, Qt.UserRole)
        name_item.setData(ftype == 'dir', Qt.UserRole + 1)
        
        if ftype == 'dir':
            size_str = "<DIR>"
        else:
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size/1024:.1f} KB"
            elif size < 1024 * 1024 * 1024:
                size_str = f"{size/(1024*1024):.1f} MB"
            else:
                size_str = f"{size/(1024*1024*1024):.2f} GB"
        
        size_item = QStandardItem(size_str)
        type_item = QStandardItem(ftype)
        modified_item = QStandardItem(modified)
        
        self.file_model.appendRow([name_item, size_item, type_item, modified_item])
    
    def item_double_clicked(self, index):
        """Handle double-click on an item"""
        if index.column() != 0:  # Only process if name column was clicked
            return
            
        name_index = self.file_model.index(index.row(), 0)
        is_dir = name_index.data(Qt.UserRole + 1)
        name = name_index.data(Qt.UserRole)
        
        if is_dir:
            # Navigate to this directory
            new_path = os.path.join(self.current_path, name)
            self.load_directory(new_path)
        else:
            # Emit signal that file was selected
            full_path = os.path.join(self.current_path, name)
            self.itemSelected.emit(full_path, False)
    
    def show_context_menu(self, position):
        """Show context menu for file/directory operations"""
        menu = QMenu()
        
        # Add actions based on selection
        indexes = self.file_view.selectedIndexes()
        if indexes:
            row = indexes[0].row()
            name_index = self.file_model.index(row, 0)
            name = name_index.data(Qt.UserRole)
            is_dir = name_index.data(Qt.UserRole + 1)
            
            if is_dir:
                menu.addAction("Open", lambda: self.load_directory(
                    os.path.join(self.current_path, name)))
            
            # Transfer actions will be implemented by the main window
            # These actions just signal the main window
            if self.is_remote:
                menu.addAction("Download", lambda: self.itemSelected.emit(
                    os.path.join(self.current_path, name), is_dir))
            else:
                menu.addAction("Upload", lambda: self.itemSelected.emit(
                    os.path.join(self.current_path, name), is_dir))
        
        menu.exec_(self.file_view.viewport().mapToGlobal(position))


class TransferPanel(QWidget):
    """Panel for displaying and managing file transfers"""
    
    def __init__(self, parent=None, transfer_manager=None):
        super().__init__(parent)
        self.transfer_manager = transfer_manager
        self.setup_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_transfers)
        self.timer.start(1000)  # Update every second
    
    def setup_ui(self):
        """Set up the transfer panel UI"""
        layout = QVBoxLayout(self)
        
        # Tabs for different transfer views
        self.tabs = QTabWidget()
        
        # Active transfers tab
        self.active_table = QTableWidget()
        self.setup_transfer_table(self.active_table)
        self.tabs.addTab(self.active_table, "Active")
        
        # Queued transfers tab
        self.queued_table = QTableWidget()
        self.setup_transfer_table(self.queued_table)
        self.tabs.addTab(self.queued_table, "Queued")
        
        # History tab
        self.history_table = QTableWidget()
        self.setup_transfer_table(self.history_table)
        self.tabs.addTab(self.history_table, "History")
        
        layout.addWidget(self.tabs)
        
        # Transfer controls
        controls_layout = QHBoxLayout()
        self.pause_button = QPushButton("Pause")
        self.resume_button = QPushButton("Resume")
        self.cancel_button = QPushButton("Cancel")
        self.clear_button = QPushButton("Clear Completed")
        
        self.pause_button.clicked.connect(self.pause_selected)
        self.resume_button.clicked.connect(self.resume_selected)
        self.cancel_button.clicked.connect(self.cancel_selected)
        self.clear_button.clicked.connect(self.clear_completed)
        
        controls_layout.addWidget(self.pause_button)
        controls_layout.addWidget(self.resume_button)
        controls_layout.addWidget(self.cancel_button)
        controls_layout.addWidget(self.clear_button)
        
        layout.addLayout(controls_layout)
    
    def setup_transfer_table(self, table):
        """Set up a transfer table with the correct columns"""
        headers = ["ID", "Type", "Source", "Destination", "Status", 
                  "Progress", "Speed", "Size"]
        
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        
        # Set up columns
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)  # Source
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)  # Destination
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Status
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Progress
        table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Speed
        table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Size
    
    def update_transfers(self):
        """Update the transfer tables with current status"""
        if not self.transfer_manager:
            return
            
        transfers = self.transfer_manager.get_all_transfers()
        
        # Update active transfers
        self.update_table(self.active_table, transfers['active'])
        
        # Update queued transfers
        self.update_table(self.queued_table, transfers['queued'])
        
        # Update history
        self.update_table(self.history_table, transfers['history'])
        
        # Update tab counters
        self.tabs.setTabText(0, f"Active ({len(transfers['active'])})")
        self.tabs.setTabText(1, f"Queued ({len(transfers['queued'])})")
        self.tabs.setTabText(2, f"History ({len(transfers['history'])})")
    
    def update_table(self, table, transfers):
        """Update a table with transfer data"""
        table.setRowCount(len(transfers))
        
        for row, transfer in enumerate(transfers):
            # ID
            table.setItem(row, 0, QTableWidgetItem(str(transfer['id'])))
            
            # Type
            table.setItem(row, 1, QTableWidgetItem(transfer['type']))
            
            # Source
            table.setItem(row, 2, QTableWidgetItem(transfer['source']))
            
            # Destination
            table.setItem(row, 3, QTableWidgetItem(transfer['destination']))
            
            # Status
            status_item = QTableWidgetItem(transfer['status'])
            table.setItem(row, 4, status_item)
            
            # Progress
            progress_item = QTableWidgetItem(transfer['progress'])
            table.setItem(row, 5, progress_item)
            
            # Speed
            table.setItem(row, 6, QTableWidgetItem(transfer['rate']))
            
            # Size
            size_text = f"{transfer['transferred']} / {transfer['total']}"
            table.setItem(row, 7, QTableWidgetItem(size_text))
            
            # Set row color based on status
            if 'COMPLETED' in transfer['status']:
                self._set_row_background(table, row, Qt.green, 0.2)
            elif 'FAILED' in transfer['status']:
                self._set_row_background(table, row, Qt.red, 0.2)
            elif 'PAUSED' in transfer['status']:
                self._set_row_background(table, row, Qt.yellow, 0.2)
    
    def _set_row_background(self, table, row, color, alpha=0.1):
        """Set background color for a row"""
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item:
                color_with_alpha = color  # In a real implementation, would set alpha
                item.setBackground(color_with_alpha)
    
    def pause_selected(self):
        """Pause the selected transfers"""
        current_table = self.tabs.currentWidget()
        selected_rows = set(index.row() for index in current_table.selectedIndexes())
        
        for row in selected_rows:
            transfer_id = int(current_table.item(row, 0).text())
            if self.transfer_manager:
                self.transfer_manager.pause_transfer(transfer_id)
    
    def resume_selected(self):
        """Resume the selected transfers"""
        current_table = self.tabs.currentWidget()
        selected_rows = set(index.row() for index in current_table.selectedIndexes())
        
        for row in selected_rows:
            transfer_id = int(current_table.item(row, 0).text())
            if self.transfer_manager:
                self.transfer_manager.resume_transfer(transfer_id)
    
    def cancel_selected(self):
        """Cancel the selected transfers"""
        current_table = self.tabs.currentWidget()
        selected_rows = set(index.row() for index in current_table.selectedIndexes())
        
        if not selected_rows:
            return
            
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText("Are you sure you want to cancel the selected transfers?")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        
        if msg_box.exec_() == QMessageBox.Yes:
            for row in selected_rows:
                transfer_id = int(current_table.item(row, 0).text())
                if self.transfer_manager:
                    self.transfer_manager.cancel_transfer(transfer_id)
    
    def clear_completed(self):
        """Clear completed transfers from the history"""
        # This would require adding a method to the TransferManager
        # For now, we'll just refresh the display
        self.update_transfers()


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
        # For now, just print the selected item
        print(f"Local item selected: {path} (Directory: {is_dir})")
    
    def remote_item_selected(self, path, is_dir):
        """Handle file or directory selection in the remote panel"""
        # For now, just print the selected item
        print(f"Remote item selected: {path} (Directory: {is_dir})")
    
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
                          "<p>Copyright © 2023 Your Company</p>"
                          "<p><a href='https://www.yourcompany.com'>www.yourcompany.com</a></p>",
                          QMessageBox.Ok)


def run_app():
    """
    Initialize and launch the FilePilot application.
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    window.refresh_connections()
    sys.exit(app.exec_())

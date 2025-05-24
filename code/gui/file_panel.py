from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeView, QHeaderView, QAbstractItemView, QMessageBox, QComboBox, QMenu, QStyle, QStyledItemDelegate
from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QColor, QPalette, QFont
import os
import time
from code.gui.conn_dialog import ConnectionDialog
from code.core.sftp_client import SFTPClient
from code.utils.file_utils import FileIconProvider

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
        self.icon_provider = FileIconProvider()
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)  # Tighter spacing for a more modern look
        
        # Path display and navigation
        path_layout = QHBoxLayout()
        path_layout.setSpacing(5)
        
        self.path_label = QLabel("Path:")
        self.path_label.setStyleSheet("font-weight: bold;")
        
        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(self.navigate_to_path)
        self.path_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 3px 5px;
                background-color: #f8f8f8;
            }
            QLineEdit:hover {
                border-color: #aaa;
            }
            QLineEdit:focus {
                border-color: #5c9eff;
                background-color: white;
            }
        """)
        
        # Modern buttons with icons from system theme
        self.up_button = QPushButton()
        self.up_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowUp))
        self.up_button.clicked.connect(self.navigate_up)
        self.up_button.setToolTip("Go to parent directory")
        self.up_button.setMaximumWidth(30)
        self.up_button.setStyleSheet("""
            QPushButton {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: #f8f8f8;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-color: #aaa;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
        """)
        
        self.refresh_button = QPushButton()
        self.refresh_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh_button.setToolTip("Refresh current directory")
        self.refresh_button.setMaximumWidth(30)
        self.refresh_button.setStyleSheet("""
            QPushButton {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: #f8f8f8;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-color: #aaa;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
        """)
        
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.up_button)
        path_layout.addWidget(self.refresh_button)
        
        layout.addLayout(path_layout)
        
        # File tree view with modern styling
        self.file_model = QStandardItemModel()
        self.file_model.setHorizontalHeaderLabels(["Name", "Size", "Type", "Modified"])
        
        # Make all items in the model non-editable
        self.file_model.itemChanged.connect(self.prevent_edit)
        
        self.file_view = QTreeView()
        self.file_view.setModel(self.file_model)
        self.file_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_view.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_view.doubleClicked.connect(self.item_double_clicked)
        self.file_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_view.customContextMenuRequested.connect(self.show_context_menu)
        self.file_view.setAlternatingRowColors(True)
        self.file_view.setAnimated(True)
        self.file_view.setIconSize(QSize(24, 24))  # Larger icons for better visibility
        
        # Make items non-editable
        self.file_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # Set modern styling for the QTreeView
        self.file_view.setStyleSheet("""
            QTreeView {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
                selection-background-color: #5c9eff;
                selection-color: black;  /* Changed from white to black for better readability */
                alternate-background-color: #f5f5f5;
            }
            QTreeView::item {
                padding: 4px;
                border-bottom: 1px solid #f0f0f0;
            }
            QTreeView::item:hover {
                background-color: #e8f0ff;
            }
            QTreeView::item:selected {
                background-color: #5c9eff;
                color: black;  /* Ensure text is black when selected */
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 5px;
                border: 1px solid #ddd;
                font-weight: bold;
            }
        """)
        
        layout.addWidget(self.file_view)
        
        # If remote, add connection selector
        if self.is_remote:
            conn_layout = QHBoxLayout()
            conn_layout.setSpacing(5)
            
            self.conn_label = QLabel("Connection:")
            self.conn_label.setStyleSheet("font-weight: bold;")
            
            self.conn_combo = QComboBox()
            self.conn_combo.currentTextChanged.connect(self.connection_changed)
            self.conn_combo.setStyleSheet("""
                QComboBox {
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 3px 5px;
                    background-color: #f8f8f8;
                }
                QComboBox:hover {
                    border-color: #aaa;
                }
                QComboBox:focus {
                    border-color: #5c9eff;
                }
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 20px;
                    border-left: 1px solid #ccc;
                }
            """)
            
            self.conn_button = QPushButton("New...")
            self.conn_button.clicked.connect(self.new_connection)
            self.conn_button.setStyleSheet("""
                QPushButton {
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 3px 10px;
                    background-color: #f8f8f8;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                    border-color: #aaa;
                }
                QPushButton:pressed {
                    background-color: #d0d0d0;
                }
            """)
            
            conn_layout.addWidget(self.conn_label)
            conn_layout.addWidget(self.conn_combo)
            conn_layout.addWidget(self.conn_button)
            
            layout.insertLayout(0, conn_layout)
            
        # Set a clean modern font for all widgets
        font = QFont()
        font.setFamily("Arial")
        font.setPointSize(9)
        self.setFont(font)
    
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
        
        # Set the icon for the item
        icon = self.icon_provider.icon(ftype, name)
        name_item.setIcon(icon)
        
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
            
            # Add delete option for both remote and local files/directories
            menu.addSeparator()
            menu.addAction("Delete", lambda: self.delete_item(name, is_dir))
        
        menu.exec_(self.file_view.viewport().mapToGlobal(position))
    
    def delete_item(self, name, is_dir):
        """Delete the selected file or directory"""
        full_path = os.path.join(self.current_path, name)
        item_type = "directory" if is_dir else "file"
        
        # Ask for confirmation
        reply = QMessageBox.question(
            self, 
            f"Delete {item_type.capitalize()}", 
            f"Are you sure you want to delete this {item_type}?\n\n{full_path}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            if self.is_remote and self.client:
                # Remote file/directory deletion
                if is_dir:
                    self.delete_remote_directory(full_path)
                else:
                    self.client.sftp.remove(full_path)
                    self.refresh()
                    if hasattr(self.window(), 'status_bar'):
                        self.window().status_bar.showMessage(f"Deleted: {full_path}", 5000)
            else:
                # Local file/directory deletion
                if is_dir:
                    import shutil
                    shutil.rmtree(full_path)
                else:
                    os.remove(full_path)
                
                self.refresh()
                if hasattr(self.window(), 'status_bar'):
                    self.window().status_bar.showMessage(f"Deleted: {full_path}", 5000)
                
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Delete Failed", 
                f"Failed to delete {item_type}: {full_path}\n\nError: {str(e)}"
            )
    
    def delete_remote_directory(self, dir_path):
        """Recursively delete a remote directory"""
        try:
            # List all directory contents
            for item in self.client.list_directory(dir_path):
                name, _, item_type, _ = item
                item_path = f"{dir_path}/{name}"
                
                if item_type == 'dir':
                    # Recursively delete subdirectory
                    self.delete_remote_directory(item_path)
                else:
                    # Delete file
                    self.client.sftp.remove(item_path)
            
            # Delete the now empty directory
            self.client.sftp.rmdir(dir_path)
            self.refresh()
            
            if hasattr(self.window(), 'status_bar'):
                self.window().status_bar.showMessage(f"Deleted directory: {dir_path}", 5000)
                
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Delete Failed", 
                f"Failed to delete directory: {dir_path}\n\nError: {str(e)}"
            )
    
    def prevent_edit(self, item):
        """Prevent items from being edited by immediately reverting any changes"""
        # This is an additional safeguard in case any items somehow become editable
        # Even though we've set EditTriggers to NoEditTriggers, this adds an extra layer of protection
        # The method is called by the itemChanged signal of the model
        
        # Get the original data from the user role and reset it
        if item.data(Qt.UserRole) is not None:
            original_text = item.data(Qt.UserRole)
            item.setText(original_text)
            
        # Also make sure the item remains non-editable
        item.setEditable(False)


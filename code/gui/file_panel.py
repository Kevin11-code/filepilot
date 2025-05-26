from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTreeView, QHeaderView, QAbstractItemView, QMenu, QAction, QInputDialog,
    QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QComboBox, QCompleter, QStyle
)
from PyQt5.QtCore import Qt, QTimer, QModelIndex, QUrl, QSize, QDir, pyqtSignal
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QDesktopServices, QIcon

import os
import stat
import datetime
from pathlib import Path
import shutil # Import shutil for recursive local directory deletion

from code.core.auth_manager import AuthManager
from code.core.sftp_client import SFTPClient
from code.utils.file_utils import FileIconProvider

class FilePanel(QWidget):
    itemSelected = pyqtSignal(str, bool) # path, is_directory
    
    def __init__(self, parent=None, is_remote=False):
        super().__init__(parent)
        self.is_remote = is_remote
        self.client = None # SFTPClient instance for remote, or None for local
        self.current_path = "" # Initialize current_path attribute
        self.auth_manager = AuthManager() # Initialize AuthManager
        self.icon_provider = FileIconProvider() # Initialize icon provider

        self.setup_ui()
        self.load_directory(os.path.expanduser("~") if not is_remote else "/") # Initial directory

    def setup_ui(self):
        """Sets up the UI elements for the file panel."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Connection / Path Bar
        path_bar_layout = QHBoxLayout()
        path_bar_layout.setContentsMargins(0, 0, 0, 0)
        path_bar_layout.setSpacing(5)

        if self.is_remote:
            self.conn_combo = QComboBox()
            self.conn_combo.setPlaceholderText("Select Connection")
            self.conn_combo.currentIndexChanged.connect(self.on_connection_selected)
            self.conn_combo.setMinimumWidth(150)
            path_bar_layout.addWidget(self.conn_combo)

            self.connect_button = QPushButton("Connect")
            self.connect_button.clicked.connect(self.connect_to_server)
            path_bar_layout.addWidget(self.connect_button)
            
            self.disconnect_button = QPushButton("Disconnect")
            self.disconnect_button.clicked.connect(self.disconnect_from_server)
            self.disconnect_button.setEnabled(False) # Disable initially
            path_bar_layout.addWidget(self.disconnect_button)
        else:
            # For local panel, add a drive/root selection combo if needed
            pass # Currently no drive selection, just path edit

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Enter path...")
        self.path_edit.returnPressed.connect(self.go_to_path)
        path_bar_layout.addWidget(self.path_edit)
        
        self.go_button = QPushButton("Go")
        self.go_button.clicked.connect(self.go_to_path)
        path_bar_layout.addWidget(self.go_button)

        self.refresh_button = QPushButton(self.style().standardIcon(QStyle.SP_BrowserReload), "")
        self.refresh_button.setToolTip("Refresh Directory")
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh_button.setFixedSize(QSize(28, 28))
        self.refresh_button.setIconSize(QSize(20, 20))
        path_bar_layout.addWidget(self.refresh_button)

        self.up_button = QPushButton(self.style().standardIcon(QStyle.SP_ArrowUp), "")
        self.up_button.setToolTip("Go Up Directory")
        self.up_button.clicked.connect(self.go_up_directory)
        self.up_button.setFixedSize(QSize(28, 28))
        self.up_button.setIconSize(QSize(20, 20))
        path_bar_layout.addWidget(self.up_button)

        main_layout.addLayout(path_bar_layout)

        # File List View
        self.file_model = QStandardItemModel()
        self.file_model.setHorizontalHeaderLabels(["Name", "Size", "Type", "Permissions", "Modified"])

        self.file_view = QTreeView()
        self.file_view.setModel(self.file_model)
        self.file_view.setHeaderHidden(False)
        self.file_view.setRootIsDecorated(False)
        self.file_view.setSortingEnabled(True)
        self.file_view.setIndentation(10)
        self.file_view.setSelectionMode(QAbstractItemView.ExtendedSelection) # Allow multiple selection
        self.file_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_view.setEditTriggers(QAbstractItemView.NoEditTriggers)  # Disable all cell editing
        self.file_view.clicked.connect(self.on_item_clicked)  # Handle single clicks
        self.file_view.doubleClicked.connect(self.on_item_double_clicked)
        self.file_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_view.customContextMenuRequested.connect(self.show_context_menu)
        self.file_view.header().setStretchLastSection(False)
        self.file_view.header().setSectionResizeMode(0, QHeaderView.Stretch) # Name column stretches
        self.file_view.header().setSectionResizeMode(1, QHeaderView.ResizeToContents) # Size
        self.file_view.header().setSectionResizeMode(2, QHeaderView.ResizeToContents) # Type
        self.file_view.header().setSectionResizeMode(3, QHeaderView.ResizeToContents) # Permissions
        self.file_view.header().setSectionResizeMode(4, QHeaderView.ResizeToContents) # Modified

        main_layout.addWidget(self.file_view)
        
        # Populate initial connection list for remote panels
        if self.is_remote:
            self.refresh_connections()

    def set_client(self, client: SFTPClient):
        """Sets the SFTP client for the panel."""
        self.client = client
        self.disconnect_button.setEnabled(client is not None)
        self.connect_button.setEnabled(client is None)
        self.conn_combo.setEnabled(client is None)

    def on_connection_selected(self, index):
        """Handle selection change in the connection combo box."""
        if self.client:
            reply = QMessageBox.question(self, "Disconnect",
                                         "You are currently connected. Disconnect and switch?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.disconnect_from_server()
            else:
                # Revert to previous selection if user cancels
                self.conn_combo.currentIndexChanged.disconnect(self.on_connection_selected)
                # Find the index of the current client's connection name and set it
                if self.client and hasattr(self.client, 'connection_config') and self.client.connection_config:
                    conn_name = self.client.connection_config.get('name')
                    idx = self.conn_combo.findText(conn_name)
                    if idx != -1:
                        self.conn_combo.setCurrentIndex(idx)
                else:
                    self.conn_combo.setCurrentIndex(0) # Select empty if no client
                self.conn_combo.currentIndexChanged.connect(self.on_connection_selected)
                return

        selected_name = self.conn_combo.currentText()
        if selected_name:
            self.connect_to_server()

    def connect_to_server(self):
        """Connects to the selected SFTP server."""
        if not self.is_remote:
            return

        conn_name = self.conn_combo.currentText()
        if not conn_name:
            QMessageBox.warning(self, "Connect Error", "Please select a connection.")
            return

        config = self.auth_manager.get_connection_secure(conn_name)
        if not config:
            QMessageBox.critical(self, "Connect Error", f"Connection '{conn_name}' not found.")
            return
        
        try:
            # Initialize SFTPClient without config, as its __init__ does not take it
            new_client = SFTPClient() 
            
            # Create a copy of the config and remove internal keys not used by connect
            connect_params = config.copy()
            connect_params.pop('name', None)
            connect_params.pop('has_password', None)
            connect_params.pop('has_passphrase', None)

            # Handle SecureString objects - convert to plain strings for connection
            if 'password' in connect_params and hasattr(connect_params['password'], 'get_value'):
                connect_params['password'] = connect_params['password'].get_value()
            if 'passphrase' in connect_params and hasattr(connect_params['passphrase'], 'get_value'):
                connect_params['passphrase'] = connect_params['passphrase'].get_value()

            # Pass unpacked dictionary to connect method
            connected = new_client.connect(**connect_params)
            
            if connected:
                self.set_client(new_client)
                # Get the user's home directory instead of defaulting to root
                home_dir = new_client.get_home_directory()
                self.current_path = home_dir
                self.load_directory(self.current_path)
                self.path_edit.setText(self.current_path)
                QMessageBox.information(self, "Connected", f"Successfully connected to {conn_name}.")
            else:
                QMessageBox.critical(self, "Connection Failed", "SFTPClient.connect() returned False.")
                self.set_client(None) # Ensure client is None on failure
        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", f"Failed to connect: {e}")
            self.set_client(None) # Ensure client is None on failure

    def disconnect_from_server(self):
        """Disconnects from the current SFTP server."""
        if self.client:
            self.client.disconnect()
            self.set_client(None)
            self.file_model.removeRows(0, self.file_model.rowCount()) # Clear view
            self.path_edit.setText("") # Clear path
            self.conn_combo.setCurrentIndex(0) # Reset combo box
            QMessageBox.information(self, "Disconnected", "Disconnected from server.")

    def load_directory(self, path):
        """Loads and displays the contents of a directory."""
        self.file_model.removeRows(0, self.file_model.rowCount()) # Clear existing items
        self.current_path = path

        try:
            if self.is_remote:
                if not self.client:
                    self.file_model.setHorizontalHeaderLabels(["Name", "Size", "Type", "Permissions", "Modified"])
                    item = QStandardItem("Not Connected")
                    item.setFlags(item.flags() & ~Qt.ItemIsSelectable) # Make it non-selectable
                    self.file_model.appendRow(item)
                    self.path_edit.setText("")
                    return
                
                # SFTPClient.list_directory now returns paramiko.SFTPAttributes objects directly
                files = self.client.list_directory(path)
                
                # --- DEBUG PRINTS ---
                print(f"--- Debugging remote directory listing for path: {path} ---")
                if files:
                    print(f"First file object type: {type(files[0])}")
                    print(f"Attributes of first file object: {dir(files[0])}")
                    # Attempt to access owner_name and group_name with a try-except
                    try:
                        print(f"First file owner_name: {getattr(files[0], 'owner_name', 'N/A')}")
                    except AttributeError:
                        print("First file object has no 'owner_name' attribute (caught by direct access attempt).")
                    try:
                        print(f"First file group_name: {getattr(files[0], 'group_name', 'N/A')}")
                    except AttributeError:
                        print("First file object has no 'group_name' attribute (caught by direct access attempt).")
                else:
                    print("No files found or directory is empty.")
                print("-------------------------------------------------------")
                # --- END DEBUG PRINTS ---

            else:
                files = self.get_local_directory_contents(path)

            for f in files:
                if self.is_remote:
                    item_name = QStandardItem(f.filename)
                    # Store full path for operations
                    item_name.setData(os.path.join(path, f.filename).replace('\\', '/'), Qt.UserRole)
                    item_name.setData(stat.S_ISDIR(f.st_mode), Qt.UserRole + 1) # is_directory
                    
                    # Use custom icons from FileIconProvider
                    if stat.S_ISDIR(f.st_mode):
                        item_name.setIcon(self.icon_provider.get_folder_icon())
                    else:
                        item_name.setIcon(self.icon_provider.get_icon_for_file(f.filename))
                    
                    self.file_model.appendRow([
                        item_name,
                        QStandardItem("" if stat.S_ISDIR(f.st_mode) else self.format_size(f.st_size)),
                        QStandardItem("Directory" if stat.S_ISDIR(f.st_mode) else "File"),
                        QStandardItem(self.format_permissions(f.st_mode)),
                        QStandardItem(self.format_datetime(f.st_mtime))
                    ])
                else: # Local file
                    item_name = QStandardItem(f['name'])
                    item_name.setData(f['path'], Qt.UserRole) # Store full path
                    item_name.setData(f['is_dir'], Qt.UserRole + 1) # is_directory
                    
                    # Use custom icons from FileIconProvider
                    if f['is_dir']:
                        item_name.setIcon(self.icon_provider.get_folder_icon())
                    else:
                        item_name.setIcon(self.icon_provider.get_icon_for_file(f['name']))

                    self.file_model.appendRow([
                        item_name,
                        QStandardItem("" if f['is_dir'] else self.format_size(f['size'])),
                        QStandardItem("Directory" if f['is_dir'] else "File"),
                        QStandardItem(f['permissions']),
                        QStandardItem(f['modified_time'])
                    ])
            self.path_edit.setText(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load directory '{path}': {e}")
            self.file_model.removeRows(0, self.file_model.rowCount()) # Clear existing items
            item = QStandardItem(f"Error loading directory: {e}")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.file_model.appendRow(item)
            self.path_edit.setText(self.current_path) # Revert to previous path if error

    def get_local_directory_contents(self, path):
        """Helper to get contents of a local directory."""
        contents = []
        try:
            # Ensure path exists before listing
            if not os.path.exists(path):
                return []
            
            for entry in os.listdir(path):
                full_path = os.path.join(path, entry)
                # Use os.path.lexists to handle broken symlinks gracefully if needed,
                # but os.path.exists is fine for most cases.
                if os.path.exists(full_path):
                    stats = os.stat(full_path)
                    is_dir = os.path.isdir(full_path)
                    contents.append({
                        'name': entry,
                        'path': full_path,
                        'size': stats.st_size,
                        'is_dir': is_dir,
                        'permissions': stat.filemode(stats.st_mode),
                        'owner': str(stats.st_uid), # On Windows, this might be a number
                        'group': str(stats.st_gid), # On Windows, this might be a number
                        'modified_time': datetime.datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    })
        except Exception as e:
            QMessageBox.critical(self, "Local Directory Error", f"Error accessing local directory: {e}")
        return contents

    def go_to_path(self):
        """Changes the current directory to the path in the QLineEdit."""
        new_path = self.path_edit.text()
        if not new_path:
            return
        if self.is_remote and not self.client:
            QMessageBox.warning(self, "Not Connected", "Please connect to a server first.")
            return
        self.load_directory(new_path)

    def go_up_directory(self):
        """Moves up one level in the directory tree."""
        if not self.current_path:
            return

        parent_path = str(Path(self.current_path).parent)
        if self.is_remote and parent_path == ".": # Handle root for remote
            parent_path = "/"
        elif not self.is_remote and parent_path == self.current_path and os.path.ismount(self.current_path):
             # On Windows, going up from C:\ might stay C:\. On Linux, going up from / stays /.
             # We should stop if we hit the actual root of the file system
             pass # Already at root, cannot go up further
        
        if parent_path != self.current_path: # Prevent endless loop at root
            self.load_directory(parent_path.replace("\\", "/"))

    def refresh(self):
        """Refreshes the current directory view."""
        self.load_directory(self.current_path)

    def on_item_double_clicked(self, index: QModelIndex):
        """Handle double-clicking on an item in the file view."""
        if index.isValid():
            # Get the index for the first column (name column) to retrieve data
            name_index = self.file_model.index(index.row(), 0)
            path = name_index.data(Qt.UserRole)
            is_dir = name_index.data(Qt.UserRole + 1)
            
            if is_dir:
                # For directories, navigate into them
                self.load_directory(path)
            else:
                # For files, emit signal for transfer (upload/download)
                self.itemSelected.emit(path, False)

    def on_item_clicked(self, index: QModelIndex):
        """Handle single-clicking on an item in the file view."""
        # Single click just selects the row - no additional action needed
        # The selection is handled automatically by the QTreeView
        pass

    def show_context_menu(self, position):
        """Show context menu for selected items."""
        # Get the index of the item at the clicked position
        index = self.file_view.indexAt(position)
        
        # If no item is clicked, or if the clicked item is not in the first column, return
        if not index.isValid() or index.column() != 0:
            return

        menu = QMenu()
        
        # Add "Open" action only for local panels
        if not self.is_remote:
            open_action = menu.addAction("Open")
        
        # Show appropriate transfer action based on panel type
        if self.is_remote:
            transfer_action = menu.addAction("Download")  # Remote panel downloads files
        else:
            transfer_action = menu.addAction("Upload")    # Local panel uploads files
            
        rename_action = menu.addAction("Rename") 
        delete_action = menu.addAction("Delete")

        action = menu.exec_(self.file_view.viewport().mapToGlobal(position))

        # Now, `index` specifically refers to the item that was right-clicked
        full_path = index.data(Qt.UserRole)
        is_dir = index.data(Qt.UserRole + 1)

        if not self.is_remote and action == open_action:
            if not is_dir:
                self.open_file(full_path)
            else:
                self.load_directory(full_path)
        elif action == rename_action: 
            old_full_path = full_path
            old_name = os.path.basename(old_full_path)
            
            new_name, ok = QInputDialog.getText(self, "Rename Item", "Enter new name:", QLineEdit.Normal, old_name)
            if ok and new_name and new_name != old_name:
                # Ensure the new path is correctly formed, especially for remote paths
                new_full_path = os.path.join(os.path.dirname(old_full_path), new_name).replace('\\', '/')
                self.rename_item(old_full_path, new_full_path)
        elif action == delete_action:
            if QMessageBox.question(self, "Confirm Delete", 
                                  f"Are you sure you want to delete '{os.path.basename(full_path)}'? This cannot be undone.",
                                  QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.delete_item(full_path, is_dir)
        elif action == transfer_action:
            if not is_dir:
                if self.is_remote:
                    # Remote panel - confirm download
                    if QMessageBox.question(self, "Confirm Download",
                                            f"Do you want to download '{os.path.basename(full_path)}'?",
                                            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                        self.itemSelected.emit(full_path, False)
                else:
                    # Local panel - confirm upload
                    if QMessageBox.question(self, "Confirm Upload",
                                            f"Do you want to upload '{os.path.basename(full_path)}'?",
                                            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                        self.itemSelected.emit(full_path, False)


    def open_file(self, file_path):
        """Opens a file using the default system application."""
        if self.is_remote:
            QMessageBox.information(self, "Open File", "Remote files cannot be opened directly from here. Please download them first.")
        else:
            if not os.path.exists(file_path):
                QMessageBox.warning(self, "File Not Found", f"The file '{file_path}' does not exist.")
                return
            
            url = QUrl.fromLocalFile(file_path)
            if not QDesktopServices.openUrl(url):
                QMessageBox.warning(self, "Error", f"Could not open file: {file_path}")

    def delete_item(self, path, is_dir):
        """Deletes a file or directory."""
        try:
            success = False
            if self.is_remote:
                if self.client:
                    if is_dir:
                        success = self.client.rmdir(path) # This now handles recursive deletion
                    else:
                        success = self.client.remove(path)
                else:
                    QMessageBox.warning(self, "Delete Error", "Not connected to remote server.")
                    return
            else: # Local file/directory
                if is_dir:
                    # For local directories, use shutil.rmtree for recursive deletion
                    # or os.rmdir for empty directories.
                    # shutil.rmtree is safer for user experience but permanent.
                    if os.path.exists(path):
                        shutil.rmtree(path) 
                        success = True
                    else:
                        QMessageBox.warning(self, "Delete Error", f"Local directory not found: {path}")
                        return
                else:
                    if os.path.exists(path):
                        os.remove(path)
                        success = True
                    else:
                        QMessageBox.warning(self, "Delete Error", f"Local file not found: {path}")
                        return

            if success:
                QMessageBox.information(self, "Delete Success", f"Successfully deleted '{os.path.basename(path)}'.")
                # Refresh immediately after successful deletion
                QTimer.singleShot(100, self.refresh)
            else:
                # If success is False, an error message should have been logged/displayed by SFTPClient or local ops
                QMessageBox.critical(self, "Delete Failed", f"Failed to delete '{os.path.basename(path)}'. Check logs for details.")
        except Exception as e:
            QMessageBox.critical(self, "Delete Error", f"Failed to delete '{os.path.basename(path)}': {e}")

    def rename_item(self, old_path, new_path):
        """Renames a file or directory."""
        try:
            success = False
            if self.is_remote:
                if self.client:
                    success = self.client.rename(old_path, new_path)
                else:
                    QMessageBox.warning(self, "Rename Error", "Not connected to remote server.")
                    return
            else: # Local file/directory
                if os.path.exists(old_path):
                    os.rename(old_path, new_path)
                    success = True
                else:
                    QMessageBox.warning(self, "Rename Error", f"Local item not found: {old_path}")
                    return

            if success:
                QMessageBox.information(self, "Rename Success", f"Successfully renamed '{os.path.basename(old_path)}' to '{os.path.basename(new_path)}'.")
                # Refresh immediately after successful rename
                QTimer.singleShot(100, self.refresh)
            else:
                QMessageBox.critical(self, "Rename Failed", f"Failed to rename '{os.path.basename(old_path)}'. Check logs for details.")
        except Exception as e:
            QMessageBox.critical(self, "Rename Error", f"Failed to rename '{os.path.basename(old_path)}': {e}")

    # Helper methods for formatting
    def format_size(self, size):
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.2f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"

    def format_permissions(self, mode):
        # paramiko.SFTPAttributes.longname often contains this, but we can reconstruct from st_mode
        return stat.filemode(mode)

    def format_datetime(self, timestamp):
        # Ensure timestamp is a float/int before converting
        if isinstance(timestamp, (int, float)):
            return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        return "N/A" # Or handle as error/unknown

    def refresh_connections(self):
        """Refreshes the list of connections in the combo box."""
        if not self.is_remote:
            return
        
        connections = self.auth_manager.list_connections()
        self.conn_combo.clear()
        self.conn_combo.addItem("") # Add empty item for no selection
        for conn in connections:
            name = conn.get('name')
            if name:
                self.conn_combo.addItem(name)

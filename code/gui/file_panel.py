from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, 
    QTreeView, QLineEdit, QLabel, QSplitter,
    QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QComboBox, QCompleter, QStyle,
    QAbstractItemView, QHeaderView, QMenu, QInputDialog, QApplication,
    QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QDir, QTimer, QThread, QUrl, QModelIndex
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon, QPixmap, QFont, QDesktopServices

import os
import stat
import platform
import shutil
from datetime import datetime
from pathlib import Path

from code.core.sftp_client import SFTPClient
from code.core.auth_manager import AuthManager
from code.gui.custom_message_box import CustomMessageBox, SFTPMessages

from code.utils.file_utils import FileIconProvider
from code.utils.secure_string import SecureTemporaryCredentials
import secrets
import gc

class FilePanel(QWidget):
    itemSelected = pyqtSignal(str, bool) # path, is_directory
    
    def __init__(self, parent=None, is_remote=False):
        super().__init__(parent)
        self.is_remote = is_remote
        self.client = None # SFTPClient instance for remote, or None for local
        self.current_path = "" # Initialize current_path attribute
        self.auth_manager = AuthManager() # Initialize AuthManager
        self.icon_provider = FileIconProvider() # Initialize icon provider
        # Get reference to parent's overwrite handler for thread-safe dialogs
        self.overwrite_handler = None
        if hasattr(parent, 'overwrite_handler'):
            self.overwrite_handler = parent.overwrite_handler

        self.setup_ui()
        self.load_directory(os.path.expanduser("~") if not is_remote else "/") # Initial directory

    def setup_ui(self):
        """Sets up the UI elements for the file panel."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Set overall widget style for black and white theme
        self.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                color: #2c2c2c;
                font-family: 'Segoe UI', 'San Francisco', 'Helvetica Neue', Arial, sans-serif;
            }
            QTreeView {
                background-color: #ffffff;
                border: none;
                gridline-color: #f5f5f5;
                selection-background-color: #0078d4;
                selection-color: #ffffff;
                font-size: 12px;
            }
            QTreeView::item {
                padding: 1px 2px;
                border-bottom: 1px solid #f5f5f5;
            }
            QTreeView::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            QTreeView::item:selected:active {
                background-color: #0078d4;
                color: #ffffff;
            }
            QTreeView::item:selected:!active {
                background-color: #0078d4;
                color: #ffffff;
            }
            QTreeView::item:selected:focus {
                background-color: #0078d4;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #ffffff;
                padding: 5px 3px;
                border: none;
                border-bottom: 1px solid #e5e5e5;
                font-weight: 600;
                color: #666666;
                text-transform: uppercase;
                font-size: 10px;
                letter-spacing: 1px;
            }
            QTreeView::item:hover {
                background-color: #e6f3ff;
            }
            QTreeView::item:hover:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            QPushButton {
                background-color: transparent;
                color: #1a1a1a;
                border: 1px solid #e5e5e5;
                padding: 5px 10px;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #f8f8f8;
                border-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
                color: #ffffff;
            }
            QLineEdit {
                border: 1px solid #e5e5e5;
                padding: 5px;
                background-color: #ffffff;
                selection-background-color: #0078d4;
                selection-color: #ffffff;
            }
            QComboBox {
                border: 1px solid #e5e5e5;
                padding: 5px;
                background-color: #ffffff;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #e5e5e5;
            }
            QComboBox::down-arrow {
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                border: 1px solid #e5e5e5;
                selection-background-color: #0078d4;
                selection-color: #ffffff;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid #e5e5e5;
                padding: 5px;
            }
            QMenu::item {
                padding: 5px 25px 5px 20px;
                border-radius: 2px;
            }
            
            /* Modern thin scrollbar styling */
            QScrollBar:vertical {
                border: none;
                background: #f5f5f5;
                width: 8px;
                margin: 0px;
            }
            
            QScrollBar::handle:vertical {
                background: #c1c1c1;
                min-height: 20px;
                border-radius: 4px;
            }
            
            QScrollBar::handle:vertical:hover {
                background: #a8a8a8;
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            
            QScrollBar:horizontal {
                border: none;
                background: #f5f5f5;
                height: 8px;
                margin: 0px;
            }
            
            QScrollBar::handle:horizontal {
                background: #c1c1c1;
                min-width: 20px;
                border-radius: 4px;
            }
            
            QScrollBar::handle:horizontal:hover {
                background: #a8a8a8;
            }
            
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                background: none;
            }
            
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

        # Connection / Path Bar
        path_bar_layout = QHBoxLayout()
        path_bar_layout.setContentsMargins(0, 0, 0, 0)
        path_bar_layout.setSpacing(5)
        
        # Add back and refresh buttons at the start
        self.up_button = QPushButton(QIcon("resources/icons/back.svg"), "")
        self.up_button.setToolTip("Go Up Directory")
        self.up_button.clicked.connect(self.go_up_directory)
        path_bar_layout.addWidget(self.up_button)
        
        self.refresh_button = QPushButton(QIcon("resources/icons/refresh.svg"), "")
        self.refresh_button.setToolTip("Refresh Directory")
        self.refresh_button.clicked.connect(self.refresh)
        path_bar_layout.addWidget(self.refresh_button)

        if self.is_remote:
            self.conn_combo = QComboBox()
            self.conn_combo.setPlaceholderText("Select Connection")
            self.conn_combo.currentIndexChanged.connect(self.on_connection_selected)
            self.conn_combo.setMinimumWidth(150)
            path_bar_layout.addWidget(self.conn_combo)

            self.connection_button = QPushButton("Connect")
            self.connection_button.clicked.connect(self.toggle_connection)
            path_bar_layout.addWidget(self.connection_button)
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
        
        # Set last section to stretch to create space between last column and scrollbar
        self.file_view.header().setStretchLastSection(True)
        
        # Configure dynamic column sizing with responsive behavior
        self.setup_responsive_columns()
        
        # Connect resize event to adjust columns when window size changes
        self.file_view.installEventFilter(self)

        main_layout.addWidget(self.file_view)
        
        # Populate initial connection list for remote panels
        if self.is_remote:
            self.refresh_connections()

    def set_client(self, client: SFTPClient):
        """Sets the SFTP client for the panel."""
        self.client = client
        
        # Update the connection button text and state based on connection
        if client is not None:
            self.connection_button.setText("Disconnect")
        else:
            self.connection_button.setText("Connect")
            
        self.conn_combo.setEnabled(client is None)

    def on_connection_selected(self, index):
        """Handle selection change in the connection combo box."""
        if self.client:
            reply = CustomMessageBox.question(self, "Disconnect",
                                         "You are currently connected. Disconnect and switch?",
                                         CustomMessageBox.Yes | CustomMessageBox.No)
            if reply == CustomMessageBox.Yes:
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
                    self.conn_combo.setCurrentIndex(0) # Select "Select a server" item
                self.conn_combo.currentIndexChanged.connect(self.on_connection_selected)
                return

        selected_name = self.conn_combo.currentText()
        if selected_name and selected_name != "Select a server":
            self.connect_to_server()

    def connect_to_server(self):
        """Connects to the selected SFTP server with secure credential handling."""
        if not self.is_remote:
            return

        conn_name = self.conn_combo.currentText()
        if not conn_name or conn_name == "Select a server":
            title, text = SFTPMessages.NO_CONNECTION
            CustomMessageBox.warning(self, title, text)
            return

        config = self.auth_manager.get_connection_secure(conn_name)
        if not config:
            title, text = SFTPMessages.CONNECTION_FAILED
            CustomMessageBox.critical(self, title, f"Connection '{conn_name}' not found.")
            return
        
        try:
            new_client = SFTPClient()
            
            # Prepare connection parameters
            connect_params = config.copy()
            connect_params.pop('name', None)
            connect_params.pop('has_password', None)
            connect_params.pop('has_passphrase', None)

            # Use secure context manager for credential extraction
            # Credentials are automatically cleared when exiting context
            with SecureTemporaryCredentials(connect_params) as temp_params:
                connected = new_client.connect(**temp_params)
            
            # At this point, all plain text credentials have been securely cleared
            
            if connected:
                self.set_client(new_client)
                # Get the user's home directory instead of defaulting to root
                home_dir = new_client.get_home_directory()
                self.current_path = home_dir
                self.load_directory(self.current_path)
                self.path_edit.setText(self.current_path)
                title, text = SFTPMessages.CONNECTION_SUCCESS
                CustomMessageBox.information(self, title, text)
            else:
                title, text = SFTPMessages.CONNECTION_FAILED
                CustomMessageBox.critical(self, title, text)
                self.set_client(None) # Ensure client is None on failure
        except Exception as e:
            title, text = SFTPMessages.CONNECTION_FAILED
            CustomMessageBox.critical(self, title, f"Failed to connect: {e}")
            self.set_client(None)
        finally:
            # Force garbage collection to clear any lingering references
            gc.collect()

    def disconnect_from_server(self):
        """Disconnects from the current SFTP server."""
        if self.client:
            self.client.disconnect()
            self.set_client(None)
            self.file_model.removeRows(0, self.file_model.rowCount()) # Clear view
            self.path_edit.setText("") # Clear path
            self.conn_combo.setCurrentIndex(0) # Reset combo box to "Select a server"
            title, text = SFTPMessages.CONNECTION_CLOSED
            CustomMessageBox.information(self, title, text)

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
                
                # # --- DEBUG PRINTS ---
                # print(f"--- Debugging remote directory listing for path: {path} ---")
                # if files:
                #     print(f"First file object type: {type(files[0])}")
                #     print(f"Attributes of first file object: {dir(files[0])}")
                #     # Attempt to access owner_name and group_name with a try-except
                #     try:
                #         print(f"First file owner_name: {getattr(files[0], 'owner_name', 'N/A')}")
                #     except AttributeError:
                #         print("First file object has no 'owner_name' attribute (caught by direct access attempt).")
                #     try:
                #         print(f"First file group_name: {getattr(files[0], 'group_name', 'N/A')}")
                #     except AttributeError:
                #         print("First file object has no 'group_name' attribute (caught by direct access attempt).")
                # else:
                #     print("No files found or directory is empty.")
                # print("-------------------------------------------------------")
                # # --- END DEBUG PRINTS ---

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
            CustomMessageBox.critical(self, "Error", f"Could not load directory '{path}': {e}")
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
                        'modified_time': datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    })
        except Exception as e:
            CustomMessageBox.critical(self, "Local Directory Error", f"Error accessing local directory: {e}")
        return contents

    def go_to_path(self):
        """Changes the current directory to the path in the QLineEdit."""
        new_path = self.path_edit.text()
        if not new_path:
            return
        if self.is_remote and not self.client:
            CustomMessageBox.warning(self, "Not Connected", "Please connect to a server first.")
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
        perm_action = menu.addAction("Change Permissions...")  # <-- Add this line

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
            if CustomMessageBox.question(self, "Confirm Delete", 
                                  f"Are you sure you want to delete '{os.path.basename(full_path)}'? This cannot be undone.",
                                  CustomMessageBox.Yes | CustomMessageBox.No) == CustomMessageBox.Yes:
                self.delete_item(full_path, is_dir)
        elif action == perm_action:
            self.change_permissions(full_path, is_dir)
        elif action == transfer_action:
            if not is_dir:
                if self.is_remote:
                    # Remote panel - confirm download
                    if CustomMessageBox.question(self, "Confirm Download",
                                            f"Do you want to download '{os.path.basename(full_path)}'?",
                                            CustomMessageBox.Yes | CustomMessageBox.No) == CustomMessageBox.Yes:
                        self.itemSelected.emit(full_path, False)
                else:
                    # Local panel - confirm upload
                    if CustomMessageBox.question(self, "Confirm Upload",
                                            f"Do you want to upload '{os.path.basename(full_path)}'?",
                                            CustomMessageBox.Yes | CustomMessageBox.No) == CustomMessageBox.Yes:
                        self.itemSelected.emit(full_path, False)

    def open_file(self, file_path):
        """Opens a file using the default system application."""
        if self.is_remote:
            CustomMessageBox.information(self, "Open File", 
                "Remote files cannot be opened directly from here. Please download them first.")
            return
        
        if not os.path.exists(file_path):
            CustomMessageBox.warning(self, "File Not Found", 
                f"The file '{file_path}' does not exist.")
            return
            
        if not self.check_permissions(file_path, os.R_OK):
            CustomMessageBox.warning(self, "Permission Denied", 
                "Cannot open file: Read permission required.")
            return
            
        url = QUrl.fromLocalFile(file_path)
        if not QDesktopServices.openUrl(url):
            CustomMessageBox.warning(self, "Error", f"Could not open file: {file_path}")

    def delete_item(self, path, is_dir):
        """Deletes a file or directory with thread-safe UI updates and permission checks."""
        try:
            # Check write permissions on both the item and its parent directory
            parent_dir = os.path.dirname(path)
            
            if not self.check_permissions(path, os.W_OK):
                CustomMessageBox.warning(self, "Permission Denied", 
                    "Cannot delete: Write permission required for this item.")
                return
                
            if not self.check_permissions(parent_dir, os.W_OK):
                CustomMessageBox.warning(self, "Permission Denied", 
                    "Cannot delete: Write permission required for parent directory.")
                return

            # If permissions are OK, proceed with deletion
            success = False
            if self.is_remote:
                if is_dir:
                    success = self.client.rmdir(path)
                else:
                    success = self.client.remove(path)
            else:
                if is_dir:
                    if os.path.exists(path):
                        # Check parent directory permissions too
                        parent_dir = os.path.dirname(path)
                        if not os.access(parent_dir, os.W_OK):
                            CustomMessageBox.warning(self, "Permission Denied", 
                                "Cannot delete: Insufficient permissions on parent directory.")
                            return
                        shutil.rmtree(path)
                        success = True
                else:
                    if os.path.exists(path):
                        # Check parent directory permissions
                        parent_dir = os.path.dirname(path)
                        if not os.access(parent_dir, os.W_OK):
                            CustomMessageBox.warning(self, "Permission Denied", 
                                "Cannot delete: Insufficient permissions on parent directory.")
                            return
                        os.remove(path)
                        success = True

            if success:
                self._schedule_safe_refresh()
            else:
                CustomMessageBox.critical(self, "Delete Failed", 
                    f"Failed to delete '{os.path.basename(path)}'. Check logs for details.")
        except PermissionError as pe:
            CustomMessageBox.warning(self, "Permission Denied", 
                f"Cannot delete '{os.path.basename(path)}': Permission denied.")
        except Exception as e:
            CustomMessageBox.critical(self, "Delete Error", 
                f"Failed to delete '{os.path.basename(path)}': {e}")

    def rename_item(self, old_path, new_path):
        """Renames a file or directory with thread-safe UI updates."""
        try:
            # Check permissions
            parent_dir = os.path.dirname(old_path)
            
            if not self.check_permissions(old_path, os.W_OK):
                CustomMessageBox.warning(self, "Permission Denied", 
                    "Cannot rename: Write permission required for this item.")
                return
                
            if not self.check_permissions(parent_dir, os.W_OK):
                CustomMessageBox.warning(self, "Permission Denied", 
                    "Cannot rename: Write permission required for parent directory.")
                return

            success = False
            if self.is_remote:
                if self.client:
                    success = self.client.rename(old_path, new_path)
                else:
                    CustomMessageBox.warning(self, "Rename Error", "Not connected to remote server.")
                    return
            else: # Local file/directory
                if os.path.exists(old_path):
                    os.rename(old_path, new_path)
                    success = True
                else:
                    CustomMessageBox.warning(self, "Rename Error", f"Local item not found: {old_path}")
                    return

            if success:
                # Use thread-safe refresh scheduling to prevent Qt threading errors
                self._schedule_safe_refresh()
            else:
                CustomMessageBox.critical(self, "Rename Failed", f"Failed to rename '{os.path.basename(old_path)}'. Check logs for details.")
        except Exception as e:
            CustomMessageBox.critical(self, "Rename Error", f"Failed to rename '{os.path.basename(old_path)}': {e}")
    
    def toggle_connection(self):
        """Toggles between connecting and disconnecting from the server."""
        if self.client:
            # We're already connected, so disconnect
            self.disconnect_from_server()
        else:
            # We're not connected, so connect
            self.connect_to_server()

    def _schedule_safe_refresh(self):
        """Schedule a safe refresh that only runs on the main Qt thread."""
        # Ensure this method only runs on the main thread
        if not QApplication.instance() or QThread.currentThread() != QApplication.instance().thread():
            # If called from a worker thread, schedule on main thread
            QTimer.singleShot(0, self._schedule_safe_refresh)
            return
        
        # Only schedule refresh if application is not shutting down
        if QApplication.instance() and not QApplication.instance().closingDown():
            QTimer.singleShot(100, self._perform_safe_refresh)
    
    def _perform_safe_refresh(self):
        """Perform the actual refresh operation safely on the main thread."""
        try:
            # Double-check we're on the main thread and app is still running
            if (QApplication.instance() and 
                not QApplication.instance().closingDown() and 
                QThread.currentThread() == QApplication.instance().thread()):
                self.refresh()
        except Exception as e:
            # Log error but don't crash
            print(f"Error during safe refresh: {str(e)}")

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
            return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        return "N/A" # Or handle as error/unknown

    def refresh_connections(self):
        """Refreshes the list of connections in the combo box."""
        if not self.is_remote:
            return
        
        connections = self.auth_manager.list_connections()
        self.conn_combo.clear()
        self.conn_combo.addItem("Select a server") # Add descriptive text for no selection
        for conn in connections:
            name = conn.get('name')
            if name:
                self.conn_combo.addItem(name)

    def setup_responsive_columns(self):
        """Configure responsive column sizing that adapts to available space"""
        # Set minimum sizes for columns to prevent them from becoming too narrow
        self.file_view.header().setMinimumSectionSize(60)
        
        # Initial column setup - we'll adjust these proportionally when the view resizes
        total_width = self.file_view.width()
        
        # Calculate proportional widths
        # Name takes 40% of space (with a minimum of 120px)
        name_width = max(120, int(total_width * 0.4))
        
        # Set initial column widths
        self.file_view.header().setSectionResizeMode(0, QHeaderView.Interactive)  # Name column
        self.file_view.header().resizeSection(0, name_width)
        
        # Size, Type, Permissions columns are Interactive but with proportional sizes
        self.file_view.header().setSectionResizeMode(1, QHeaderView.Interactive)  # Size
        self.file_view.header().setSectionResizeMode(2, QHeaderView.Interactive)  # Type
        self.file_view.header().setSectionResizeMode(3, QHeaderView.Interactive)  # Permissions
        
        # Size gets 15% of space
        self.file_view.header().resizeSection(1, max(60, int(total_width * 0.15)))
        # Type gets 15% of space
        self.file_view.header().resizeSection(2, max(60, int(total_width * 0.15)))
        # Permissions gets 15% of space
        self.file_view.header().resizeSection(3, max(60, int(total_width * 0.15)))
        
        # Modified date gets remaining space and stretches
        self.file_view.header().setSectionResizeMode(4, QHeaderView.Stretch)  # Modified

    def eventFilter(self, source, event):
        """Filter events to catch resize events on the file view"""
        from PyQt5.QtCore import QEvent
        
        if (source == self.file_view and event.type() == QEvent.Resize):
            # Resize event occurred on the file view - adjust columns
            self.adjust_columns_for_current_width()
            return False  # Let the event continue
            
        # For all other events, let them through
        return super().eventFilter(source, event)
        
    def adjust_columns_for_current_width(self):
        """Adjust column widths based on current view width"""
        if not self.file_view.isVisible():
            return
            
        # Get current width of the view
        total_width = self.file_view.width()
        
        # Skip if width is too small
        if total_width < 200:
            return
            
        # Calculate new proportional widths while preserving user adjustments
        # We use min width for very small windows, and proportional for larger ones
        
        # Name takes 40% of space (with a minimum of 120px)
        name_width = max(120, int(total_width * 0.3))
        
        # Keep the width that user might have manually set, unless view was resized significantly
        current_name_width = self.file_view.header().sectionSize(0)
        if abs(current_name_width - name_width) > 50:  # Only adjust if difference is significant
            self.file_view.header().resizeSection(0, name_width)
            
        # Apply similar logic to other columns (except the last one which stretches)
        self.file_view.header().resizeSection(1, max(60, int(total_width * 0.15)))  # Size
        self.file_view.header().resizeSection(2, max(60, int(total_width * 0.15)))  # Type 
        self.file_view.header().resizeSection(3, max(60, int(total_width * 0.15)))  # Permissions
        
        # The Modified column automatically stretches to fill remaining space

    def change_permissions(self, path, is_dir):
        """Show dialog and change file/directory permissions."""
        try:
            if self.is_remote:
                if not self.client:
                    CustomMessageBox.warning(self, "Not Connected", "Please connect to a server first.")
                    return
                # Get current mode from remote
                attrs = self.client.stat(path)
                current_mode = attrs.st_mode
            else:
                if not os.path.exists(path):
                    CustomMessageBox.warning(self, "Not Found", f"Path not found: {path}")
                    return
                current_mode = os.stat(path).st_mode

            dlg = PermissionsDialog(self, current_mode)
            if dlg.exec_() == QDialog.Accepted:
                new_mode = dlg.get_mode()
                if new_mode is None:
                    CustomMessageBox.warning(self, "Invalid", "Invalid octal value.")
                    return
                if self.is_remote:
                    ok = self.client.chmod(path, new_mode)
                    if not ok:
                        CustomMessageBox.critical(self, "Failed", "Failed to change permissions.")
                        return
                else:
                    os.chmod(path, new_mode)
                self._schedule_safe_refresh()
        except Exception as e:
            CustomMessageBox.critical(self, "Error", f"Failed to change permissions: {e}")

    def check_permissions(self, path, required_permission):
        """
        Check if we have the required permissions for a file/directory operation.
        required_permission can be: os.W_OK, os.R_OK, os.X_OK
        """
        try:
            if self.is_remote:
                if not self.client:
                    return False
                # Get remote file attributes
                attrs = self.client.stat(path)
                mode = attrs.st_mode
                
                # Map os.* permission constants to stat.* constants
                perm_map = {
                    os.W_OK: stat.S_IWUSR,
                    os.R_OK: stat.S_IRUSR,
                    os.X_OK: stat.S_IXUSR
                }
                
                return bool(mode & perm_map[required_permission])
            else:
                return os.access(path, required_permission)
        except Exception:
            return False

class PermissionsDialog(QDialog):
    def __init__(self, parent, current_mode):
        super().__init__(parent)
        self.setWindowTitle("Change Permissions")
        self.setModal(True)
        self.setMinimumSize(350, 200) 
        layout = QVBoxLayout(self)

        # Owner, Group, Others checkboxes
        self.checks = {}
        perms = [
            ("Owner", stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR),
            ("Group", stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP),
            ("Others", stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH),
        ]
        for label, r, w, x in perms:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            for name, bit in zip(["R", "W", "X"], [r, w, x]):
                cb = QCheckBox(name)
                cb.setChecked(bool(current_mode & bit))
                self.checks[(label, name)] = cb
                row.addWidget(cb)
            layout.addLayout(row)

        # Octal input
        self.octal_edit = QLineEdit(oct(current_mode & 0o777)[2:].zfill(3))
        layout.addWidget(QLabel("Octal:"))
        layout.addWidget(self.octal_edit)

        # Buttons
        btns = QHBoxLayout()
        ok = QPushButton("OK")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        # Sync checkboxes and octal
        for cb in self.checks.values():
            cb.stateChanged.connect(self.update_octal)
        self.octal_edit.textChanged.connect(self.update_checks)

    def update_octal(self):
        mode = 0
        if self.checks[("Owner", "R")].isChecked(): mode |= stat.S_IRUSR
        if self.checks[("Owner", "W")].isChecked(): mode |= stat.S_IWUSR
        if self.checks[("Owner", "X")].isChecked(): mode |= stat.S_IXUSR
        if self.checks[("Group", "R")].isChecked(): mode |= stat.S_IRGRP
        if self.checks[("Group", "W")].isChecked(): mode |= stat.S_IWGRP
        if self.checks[("Group", "X")].isChecked(): mode |= stat.S_IXGRP
        if self.checks[("Others", "R")].isChecked(): mode |= stat.S_IROTH
        if self.checks[("Others", "W")].isChecked(): mode |= stat.S_IWOTH
        if self.checks[("Others", "X")].isChecked(): mode |= stat.S_IXOTH
        self.octal_edit.setText(oct(mode & 0o777)[2:].zfill(3))

    def update_checks(self):
        try:
            val = int(self.octal_edit.text(), 8)
        except Exception:
            return
        for (label, name), bit in [
            (("Owner", "R"), stat.S_IRUSR), (("Owner", "W"), stat.S_IWUSR), (("Owner", "X"), stat.S_IXUSR),
            (("Group", "R"), stat.S_IRGRP), (("Group", "W"), stat.S_IWGRP), (("Group", "X"), stat.S_IXGRP),
            (("Others", "R"), stat.S_IROTH), (("Others", "W"), stat.S_IWOTH), (("Others", "X"), stat.S_IXOTH),
        ]:
            self.checks[(label, name)].setChecked(bool(val & bit))

    def get_mode(self):
        try:
            return int(self.octal_edit.text(), 8)
        except Exception:
            return None

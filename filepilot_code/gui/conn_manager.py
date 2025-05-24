from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                           QAbstractItemView, QHeaderView, QPushButton,
                           QTableWidgetItem, QMessageBox, QInputDialog, QLineEdit)
from filepilot_code.gui.conn_dialog import ConnectionDialog

class ConnectionManagerDialog(QDialog):
    """Dialog for managing saved SFTP connections"""
    
    def __init__(self, auth_manager, parent=None):
        super().__init__(parent)
        self.auth_manager = auth_manager
        self.setWindowTitle("Manage Connections")
        self.resize(600, 400)
        self.setup_ui()
        self.load_connections()
        
    def setup_ui(self):
        """Set up the dialog UI"""
        layout = QVBoxLayout(self)
        
        # Connection table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Host", "Port", "Username"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.new_btn = QPushButton("New")
        self.edit_btn = QPushButton("Edit")
        self.delete_btn = QPushButton("Delete")
        self.close_btn = QPushButton("Close")
        
        self.new_btn.clicked.connect(self.new_connection)
        self.edit_btn.clicked.connect(self.edit_connection)
        self.delete_btn.clicked.connect(self.delete_connection)
        self.close_btn.clicked.connect(self.close)
        
        button_layout.addWidget(self.new_btn)
        button_layout.addWidget(self.edit_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
    
    def load_connections(self):
        """Load saved connections into the table"""
        # Clear existing rows
        self.table.setRowCount(0)
        
        # Get all connections
        connections = self.auth_manager.list_connections()
        
        # Add connections to the table
        for idx, conn in enumerate(connections):
            self.table.insertRow(idx)
            
            # Name
            name_item = QTableWidgetItem(conn.get('name', ''))
            self.table.setItem(idx, 0, name_item)
            
            # Host
            host_item = QTableWidgetItem(conn.get('host', ''))
            self.table.setItem(idx, 1, host_item)
            
            # Port
            port_item = QTableWidgetItem(str(conn.get('port', 22)))
            self.table.setItem(idx, 2, port_item)
            
            # Username
            username_item = QTableWidgetItem(conn.get('username', ''))
            self.table.setItem(idx, 3, username_item)
    
    def new_connection(self):
        """Open dialog to create a new connection"""
        dialog = ConnectionDialog(self, self.auth_manager)
        if dialog.exec_():
            self.load_connections()
            # Signal the parent window to refresh its connection lists
            parent = self.parent()
            if parent and hasattr(parent, 'refresh_connections'):
                parent.refresh_connections()
    
    def edit_connection(self):
        """Edit the selected connection"""
        selected_rows = self.table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a connection to edit.")
            return
        
        # Get selected connection name
        row = self.table.currentRow()
        connection_name = self.table.item(row, 0).text()
        
        # Open edit dialog
        dialog = ConnectionDialog(self, self.auth_manager, connection_name)
        if dialog.exec_():
            self.load_connections()
            # Signal the parent window to refresh its connection lists
            parent = self.parent()
            if parent and hasattr(parent, 'refresh_connections'):
                parent.refresh_connections()
    
    def delete_connection(self):
        """Delete the selected connection"""
        selected_rows = self.table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a connection to delete.")
            return
        
        # Get selected connection name
        row = self.table.currentRow()
        connection_name = self.table.item(row, 0).text()
        
        # Confirm deletion
        reply = QMessageBox.question(self, "Confirm Deletion", 
                                     f"Are you sure you want to delete the connection '{connection_name}'?",
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)
                                     
        if reply == QMessageBox.Yes:
            # Ask for encryption password if needed
            encrypt_password = None
            try:
                # Try to delete the connection
                if self.auth_manager.delete_connection(connection_name, False, encrypt_password):
                    self.load_connections()
                    # Signal the parent window to refresh its connection lists
                    parent = self.parent()
                    if parent and hasattr(parent, 'refresh_connections'):
                        parent.refresh_connections()
                else:
                    # Try with encryption - assume config is encrypted
                    password, ok = QInputDialog.getText(self, "Encryption Password",
                                                       "This connection was saved with encryption.\nEnter the password:",
                                                       QLineEdit.Password)
                    if ok and password:
                        if self.auth_manager.delete_connection(connection_name, True, password):
                            self.load_connections()
                            # Signal the parent window to refresh its connection lists
                            parent = self.parent()
                            if parent and hasattr(parent, 'refresh_connections'):
                                parent.refresh_connections()
                        else:
                            QMessageBox.critical(self, "Error", "Failed to delete the connection. Incorrect password?")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error deleting connection: {str(e)}")

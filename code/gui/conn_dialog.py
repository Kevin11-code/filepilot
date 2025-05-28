from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QSpinBox, QComboBox, QPushButton, QHBoxLayout, QCheckBox, QDialogButtonBox, QFileDialog, QMessageBox
from code.core.auth_manager import AuthManager
from code.core.sftp_client import SFTPClient

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
        self.passphrase_edit.setPlaceholderText("Leave empty if key has no passphrase")
        form.addRow("Passphrase (Optional):", self.passphrase_edit)
        
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
            self, "Select Private Key", "", 
            "Private Key Files (*.ppk *.pem *.key);;PuTTY Private Keys (*.ppk);;OpenSSH Keys (*.pem *.key);;All Files (*)"
        )
        if file_path:
            self.key_path_edit.setText(file_path)
    
    def load_connection(self, name):
        """Load connection settings for editing"""
        connection = self.auth_manager.get_connection_secure(name)
        if connection:
            self.name_edit.setText(connection.get('name', ''))
            self.host_edit.setText(connection.get('host', ''))
            self.port_spin.setValue(connection.get('port', 22))
            self.username_edit.setText(connection.get('username', ''))
            
            # Set auth type
            if connection.get('key_path'):
                self.auth_type.setCurrentText("Key File")
                self.key_path_edit.setText(connection.get('key_path', ''))
                # Handle SecureString passphrase
                if 'passphrase' in connection:
                    passphrase = connection['passphrase']
                    if hasattr(passphrase, 'get_value'):
                        # Use secure temporary credentials for GUI display
                        from utils.secure_string import SecureTemporaryCredentials
                        with SecureTemporaryCredentials({'passphrase': passphrase}) as temp_creds:
                            self.passphrase_edit.setText(temp_creds.get('passphrase', ''))
                    else:
                        self.passphrase_edit.setText(str(passphrase))
            else:
                self.auth_type.setCurrentText("Password")
                # Handle SecureString password
                if 'password' in connection:
                    password = connection['password']
                    if hasattr(password, 'get_value'):
                        # Use secure temporary credentials for GUI display
                        from utils.secure_string import SecureTemporaryCredentials
                        with SecureTemporaryCredentials({'password': password}) as temp_creds:
                            self.password_edit.setText(temp_creds.get('password', ''))
                    else:
                        self.password_edit.setText(str(password))
    
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
        
        # Get auth parameters
        password = None
        key_path = None
        passphrase = None
        
        if self.auth_type.currentText() == "Password":
            password = self.password_edit.text() if self.password_edit.text() else None
        else:
            key_path = self.key_path_edit.text() if self.key_path_edit.text() else None
            passphrase = self.passphrase_edit.text() if self.passphrase_edit.text() else None
        
        # Get encryption password if needed
        encryption_password = None
        if self.encrypt_config.isChecked():
            encryption_password = self.encryption_password.text()
            if not encryption_password:
                QMessageBox.warning(self, "Input Error", "Encryption password is required when encryption is enabled.")
                return
            
        # Save connection using the secure method
        try:
            success = self.auth_manager.save_connection_secure(
                name=name,
                host=host,
                port=port,
                username=username,
                password=password,
                key_path=key_path,
                passphrase=passphrase,
                use_keyring=self.use_keyring.isChecked(),
                encrypt=self.encrypt_config.isChecked(),
                encryption_password=encryption_password
            )
            
            if success:
                self.accept()  # Close dialog
            else:
                QMessageBox.critical(self, "Error", "Failed to save connection.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving connection: {str(e)}")

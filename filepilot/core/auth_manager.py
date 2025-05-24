import os
import json
import base64
import getpass
import keyring
from typing import Dict, Optional, Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class AuthManager:
    """
    Manages authentication credentials for SFTP connections with secure storage options.
    """
    def __init__(self, config_dir='config'):
        """Initialize the authentication manager with a config directory."""
        self.config_dir = config_dir
        self.connections_file = os.path.join(config_dir, 'connections.json')
        self._ensure_config_dir()
        
    def _ensure_config_dir(self):
        """Ensure the config directory exists."""
        os.makedirs(self.config_dir, exist_ok=True)
        
    def _generate_key(self, password, salt=None):
        """Generate a Fernet key based on a password."""
        if salt is None:
            salt = b'filepilot_salt'  # In production, use a secure random salt
            
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
        
    def save_connection(self, 
                      name: str, 
                      host: str,
                      port: int = 22, 
                      username: str = None,
                      password: str = None,
                      key_path: str = None,
                      passphrase: str = None,
                      use_keyring: bool = True,
                      encrypt: bool = False,
                      encryption_password: str = None) -> bool:
        """
        Save a connection with secure credential handling.
        
        Args:
            name: Unique name for this connection
            host: Server hostname or IP
            port: Server port
            username: Login username
            password: Password (for password auth)
            key_path: Path to private key (for key auth)
            passphrase: Key passphrase if needed
            use_keyring: Store sensitive data in system keyring
            encrypt: Encrypt config file
            encryption_password: Password for config encryption
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Create connection data structure
        connection = {
            'name': name,
            'host': host,
            'port': port,
            'username': username,
            'key_path': key_path
        }
        
        try:
            # Handle sensitive data based on storage method
            if use_keyring:
                # Store in system keyring
                if password:
                    keyring.set_password('filepilot', f'{name}_password', password)
                    connection['has_password'] = True
                    
                if passphrase:
                    keyring.set_password('filepilot', f'{name}_passphrase', passphrase)
                    connection['has_passphrase'] = True
            else:
                # Store in config (potentially encrypted)
                if password:
                    connection['password'] = password
                if passphrase:
                    connection['passphrase'] = passphrase
            
            # Load existing connections
            connections = self.list_connections()
            
            # Update or add this connection
            found = False
            for i, conn in enumerate(connections):
                if conn.get('name') == name:
                    connections[i] = connection
                    found = True
                    break
                    
            if not found:
                connections.append(connection)
                
            # Write to file (encrypting if requested)
            if encrypt and encryption_password:
                fernet = Fernet(self._generate_key(encryption_password))
                data = json.dumps(connections).encode()
                encrypted = fernet.encrypt(data)
                
                with open(self.connections_file, 'wb') as f:
                    f.write(encrypted)
            else:
                with open(self.connections_file, 'w') as f:
                    json.dump(connections, f, indent=2)
                    
            return True
            
        except Exception as e:
            print(f"Failed to save connection: {str(e)}")
            return False
            
    def list_connections(self, 
                        decrypt: bool = False,
                        encryption_password: str = None) -> list:
        """
        List all saved connections.
        
        Args:
            decrypt: Whether to decrypt an encrypted config
            encryption_password: Password for decryption
            
        Returns:
            list: List of connection dictionaries
        """
        if not os.path.exists(self.connections_file):
            return []
            
        try:
            if decrypt and encryption_password:
                # Try to decrypt file
                with open(self.connections_file, 'rb') as f:
                    encrypted = f.read()
                    
                fernet = Fernet(self._generate_key(encryption_password))
                decrypted = fernet.decrypt(encrypted)
                connections = json.loads(decrypted)
            else:
                # Try to read as plain JSON
                try:
                    with open(self.connections_file, 'r') as f:
                        connections = json.load(f)
                except json.JSONDecodeError:
                    # File might be encrypted
                    return []
                    
            return connections
            
        except Exception as e:
            print(f"Failed to list connections: {str(e)}")
            return []
            
    def get_connection(self, 
                     name: str, 
                     decrypt: bool = False,
                     encryption_password: str = None) -> Dict:
        """
        Get a connection by name with complete credentials.
        
        Args:
            name: Connection name
            decrypt: Whether to decrypt an encrypted config
            encryption_password: Password for decryption
            
        Returns:
            Dict: Connection details with credentials
        """
        connections = self.list_connections(decrypt, encryption_password)
        
        for conn in connections:
            if conn.get('name') == name:
                # Found connection, now retrieve any sensitive data
                connection = conn.copy()
                
                # Try to get password from keyring
                if conn.get('has_password', False):
                    try:
                        password = keyring.get_password('filepilot', f'{name}_password')
                        if password:
                            connection['password'] = password
                    except:
                        pass
                        
                # Try to get passphrase from keyring
                if conn.get('has_passphrase', False):
                    try:
                        passphrase = keyring.get_password('filepilot', f'{name}_passphrase')
                        if passphrase:
                            connection['passphrase'] = passphrase
                    except:
                        pass
                        
                return connection
                
        return {}
        
    def delete_connection(self, 
                        name: str,
                        decrypt: bool = False,
                        encryption_password: str = None) -> bool:
        """
        Delete a connection by name.
        
        Args:
            name: Connection name
            decrypt: Whether config is encrypted
            encryption_password: Password for encryption/decryption
            
        Returns:
            bool: True if successful, False otherwise
        """
        connections = self.list_connections(decrypt, encryption_password)
        
        # Find and remove the connection
        for i, conn in enumerate(connections):
            if conn.get('name') == name:
                # Remove from keyring if needed
                if conn.get('has_password', False):
                    try:
                        keyring.delete_password('filepilot', f'{name}_password')
                    except:
                        pass
                        
                if conn.get('has_passphrase', False):
                    try:
                        keyring.delete_password('filepilot', f'{name}_passphrase')
                    except:
                        pass
                        
                # Remove from list
                connections.pop(i)
                
                # Save updated list
                if decrypt and encryption_password:
                    fernet = Fernet(self._generate_key(encryption_password))
                    data = json.dumps(connections).encode()
                    encrypted = fernet.encrypt(data)
                    
                    with open(self.connections_file, 'wb') as f:
                        f.write(encrypted)
                else:
                    with open(self.connections_file, 'w') as f:
                        json.dump(connections, f, indent=2)
                        
                return True
                
        return False
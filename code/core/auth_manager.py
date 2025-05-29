import os
import json
import base64
import getpass
import keyring
import secrets
from typing import Dict, Optional, Union, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Import secure string management from utils
from code.utils.secure_string import SecureString, SecureCredentialManager, get_credential_manager


class AuthManager:
    """
    Manages authentication credentials for SFTP connections with secure storage options.
    """
    def __init__(self, config_dir='config'):
        """Initialize the authentication manager with a config directory."""
        self.config_dir = config_dir
        self.connections_file = os.path.join(config_dir, 'connections.json')
        self._credential_manager = get_credential_manager()
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
    
    def _secure_input_password(self, prompt: str = "Password: ") -> SecureString:
        """
        Securely input a password using getpass and return as SecureString.
        
        Args:
            prompt: The prompt to display
            
        Returns:
            SecureString: Secure password object
        """
        try:
            # Use getpass for hidden input
            password_value = getpass.getpass(prompt)
            
            # Immediately create SecureString using the credential manager
            secure_password = self._credential_manager.create_secure_string(password_value)
            
            # Immediately clear the original variable by overwriting with random data
            for _ in range(3):
                password_value = secrets.token_urlsafe(64)
            password_value = None
            del password_value
            
            return secure_password
        except KeyboardInterrupt:
            print("\nPassword input cancelled.")
            return SecureString("")
        except Exception as e:
            print(f"Error during password input: {e}")
            return SecureString("")
    
    def save_connection_secure(self, 
                      name: str, 
                      host: str,
                      port: int = 22, 
                      username: str = None,
                      password: Union[str, SecureString] = None,
                      key_path: str = None,
                      passphrase: Union[str, SecureString] = None,
                      use_keyring: bool = True,
                      encrypt: bool = False,
                      encryption_password: str = None) -> bool:
        """
        Save a connection with secure credential handling using SecureString.
        
        Args:
            name: Unique name for this connection
            host: Server hostname or IP
            port: Server port
            username: Login username
            password: SecureString or string containing password (for password auth)
            key_path: Path to private key (for key auth)
            passphrase: SecureString or string containing key passphrase if needed
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
            # Convert string passwords to SecureString if needed
            secure_password = None
            secure_passphrase = None
            
            if password:
                if isinstance(password, str):
                    secure_password = self._credential_manager.create_secure_string(password)
                else:
                    secure_password = password
            
            if passphrase:
                if isinstance(passphrase, str):
                    secure_passphrase = self._credential_manager.create_secure_string(passphrase)
                else:
                    secure_passphrase = passphrase
            
            # Handle sensitive data based on storage method
            if use_keyring:
                # Store in system keyring using secure credentials
                temp_creds = {}
                if secure_password and not secure_password.is_cleared():
                    temp_creds['password'] = secure_password
                    connection['has_password'] = True
                if secure_passphrase and not secure_passphrase.is_cleared():
                    temp_creds['passphrase'] = secure_passphrase
                    connection['has_passphrase'] = True
                
                # Use secure context manager for keyring storage
                if temp_creds:
                    from utils.secure_string import SecureTemporaryCredentials
                    with SecureTemporaryCredentials(temp_creds) as plain_creds:
                        if 'password' in plain_creds:
                            keyring.set_password('filepilot', f'{name}_password', plain_creds['password'])
                        if 'passphrase' in plain_creds:
                            keyring.set_password('filepilot', f'{name}_passphrase', plain_creds['passphrase'])
            else:
                # Store in config (potentially encrypted) using secure credentials
                temp_creds = {}
                if secure_password and not secure_password.is_cleared():
                    temp_creds['password'] = secure_password
                if secure_passphrase and not secure_passphrase.is_cleared():
                    temp_creds['passphrase'] = secure_passphrase
                
                # Use secure context manager for config storage
                if temp_creds:
                    from utils.secure_string import SecureTemporaryCredentials
                    with SecureTemporaryCredentials(temp_creds) as plain_creds:
                        if 'password' in plain_creds:
                            connection['password'] = plain_creds['password']
                        if 'passphrase' in plain_creds:
                            connection['passphrase'] = plain_creds['passphrase']
            
            # Clear sensitive data from SecureString objects
            if secure_password:
                secure_password.clear()
            if secure_passphrase:
                secure_passphrase.clear()
            
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
        finally:
            # Ensure cleanup even if an error occurs
            if 'secure_password' in locals() and secure_password:
                secure_password.clear()
            if 'secure_passphrase' in locals() and secure_passphrase:
                secure_passphrase.clear()
    
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
            
    def get_connection_secure(self, 
                     name: str, 
                     decrypt: bool = False,
                     encryption_password: str = None) -> Dict:
        """
        Get a connection by name with credentials wrapped in SecureString.
        
        Args:
            name: Connection name
            decrypt: Whether to decrypt an encrypted config
            encryption_password: Password for decryption
            
        Returns:
            Dict: Connection details with SecureString credentials
        """
        connections = self.list_connections(decrypt, encryption_password)
        
        for conn in connections:
            if conn.get('name') == name:
                # Found connection, now retrieve any sensitive data
                connection = conn.copy()
                
                # Try to get password from keyring and wrap in SecureString
                if conn.get('has_password', False):
                    try:
                        password = keyring.get_password('filepilot', f'{name}_password')
                        if password:
                            connection['password'] = self._credential_manager.create_secure_string(password)
                            # Clear the retrieved password
                            password = None
                            del password
                    except:
                        pass
                elif 'password' in conn:
                    # Password stored in config file
                    connection['password'] = self._credential_manager.create_secure_string(conn['password'])
                        
                # Try to get passphrase from keyring and wrap in SecureString
                if conn.get('has_passphrase', False):
                    try:
                        passphrase = keyring.get_password('filepilot', f'{name}_passphrase')
                        if passphrase:
                            connection['passphrase'] = self._credential_manager.create_secure_string(passphrase)
                            # Clear the retrieved passphrase
                            passphrase = None
                            del passphrase
                    except:
                        pass
                elif 'passphrase' in conn:
                    # Passphrase stored in config file
                    connection['passphrase'] = self._credential_manager.create_secure_string(conn['passphrase'])

                # print("returning: ", connections)      
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
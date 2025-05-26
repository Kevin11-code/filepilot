import os
import json
import base64
import getpass
import keyring
import secrets
import array
import ctypes
import gc
import weakref
from typing import Dict, Optional, Union, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class SecureString:
    """
    A secure string implementation that encrypts sensitive data in memory
    and provides automatic cleanup to prevent memory dump attacks.
    """
    
    # Class-level registry to track all instances for cleanup
    _instances = weakref.WeakSet()
    
    def __init__(self, value: str = ""):
        """
        Initialize a secure string with the given value.
        
        Args:
            value: The sensitive string value to protect
        """
        # Generate a random key for XOR encryption
        self._key = secrets.randbits(len(value) * 8) if value else 0
        
        # Convert string to byte array and encrypt with XOR
        if value:
            self._data = array.array('B', [
                ord(char) ^ ((self._key >> (i * 8)) & 0xFF) 
                for i, char in enumerate(value)
            ])
        else:
            self._data = array.array('B')
        
        # Store original length
        self._length = len(value)
        
        # Flag to track if cleared
        self._cleared = False
        
        # Add to instance registry for global cleanup
        SecureString._instances.add(self)
    
    def get_value(self) -> str:
        """
        Decrypt and return the stored value.
        
        Returns:
            str: The decrypted value
            
        Raises:
            ValueError: If the SecureString has been cleared
        """
        if self._cleared:
            raise ValueError("SecureString has been cleared")
        
        if not self._data:
            return ""
        
        # Decrypt the data using XOR
        decrypted_chars = [
            chr(byte ^ ((self._key >> (i * 8)) & 0xFF))
            for i, byte in enumerate(self._data)
        ]
        
        return ''.join(decrypted_chars)
    
    def clear(self):
        """
        Securely clear the stored value by overwriting with random data.
        """
        if not self._cleared and self._data:
            # Overwrite data array with random bytes multiple times
            for _ in range(3):
                for i in range(len(self._data)):
                    self._data[i] = secrets.randbits(8)
            
            # Clear the array
            self._data = array.array('B')
            
            # Overwrite the key
            self._key = secrets.randbits(64)
            
            # Reset length
            self._length = 0
            
            # Mark as cleared
            self._cleared = True
            
            # Force garbage collection
            gc.collect()
    
    def is_cleared(self) -> bool:
        """
        Check if this SecureString has been cleared.
        
        Returns:
            bool: True if cleared, False otherwise
        """
        return self._cleared
    
    def __len__(self) -> int:
        """Return the length of the stored value."""
        return self._length if not self._cleared else 0
    
    def __str__(self) -> str:
        """Return a safe string representation."""
        if self._cleared:
            return "<cleared>"
        return f"<SecureString: {'*' * min(self._length, 8)}>"
    
    def __repr__(self) -> str:
        """Return a safe string representation."""
        return self.__str__()
    
    def __del__(self):
        """Ensure cleanup when object is destroyed."""
        self.clear()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.clear()
    
    @classmethod
    def clear_all(cls):
        """
        Emergency function to clear all SecureString instances.
        Useful for application shutdown or security emergencies.
        """
        # Create a copy of the set to avoid modification during iteration
        instances = list(cls._instances)
        for instance in instances:
            try:
                instance.clear()
            except:
                pass  # Ignore errors during emergency cleanup
        
        # Force garbage collection
        gc.collect()


class SecureCredentialManager:
    """
    Manages secure credential operations with automatic cleanup.
    """
    
    def __init__(self):
        """Initialize the secure credential manager."""
        self._active_credentials = weakref.WeakSet()
    
    def create_secure_string(self, value: str) -> SecureString:
        """
        Create a SecureString and track it for cleanup.
        
        Args:
            value: The sensitive value to protect
            
        Returns:
            SecureString: Protected string object
        """
        secure_str = SecureString(value)
        self._active_credentials.add(secure_str)
        return secure_str
    
    def clear_all_credentials(self):
        """Clear all tracked credentials."""
        credentials = list(self._active_credentials)
        for cred in credentials:
            try:
                cred.clear()
            except:
                pass
        
        # Also clear all SecureString instances globally
        SecureString.clear_all()


# Global credential manager instance
_credential_manager = SecureCredentialManager()


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
            
            # Create SecureString
            secure_password = SecureString(password_value)
            
            # Clear the original variable
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
                    secure_password = SecureString(password)
                else:
                    secure_password = password
            
            if passphrase:
                if isinstance(passphrase, str):
                    secure_passphrase = SecureString(passphrase)
                else:
                    secure_passphrase = passphrase
            
            # Handle sensitive data based on storage method
            if use_keyring:
                # Store in system keyring
                if secure_password and not secure_password.is_cleared():
                    keyring.set_password('filepilot', f'{name}_password', secure_password.get_value())
                    connection['has_password'] = True
                    
                if secure_passphrase and not secure_passphrase.is_cleared():
                    keyring.set_password('filepilot', f'{name}_passphrase', secure_passphrase.get_value())
                    connection['has_passphrase'] = True
            else:
                # Store in config (potentially encrypted)
                if secure_password and not secure_password.is_cleared():
                    connection['password'] = secure_password.get_value()
                if secure_passphrase and not secure_passphrase.is_cleared():
                    connection['passphrase'] = secure_passphrase.get_value()
            
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
                            connection['password'] = SecureString(password)
                            # Clear the retrieved password
                            password = None
                            del password
                    except:
                        pass
                elif 'password' in conn:
                    # Password stored in config file
                    connection['password'] = SecureString(conn['password'])
                        
                # Try to get passphrase from keyring and wrap in SecureString
                if conn.get('has_passphrase', False):
                    try:
                        passphrase = keyring.get_password('filepilot', f'{name}_passphrase')
                        if passphrase:
                            connection['passphrase'] = SecureString(passphrase)
                            # Clear the retrieved passphrase
                            passphrase = None
                            del passphrase
                    except:
                        pass
                elif 'passphrase' in conn:
                    # Passphrase stored in config file
                    connection['passphrase'] = SecureString(conn['passphrase'])
                        
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
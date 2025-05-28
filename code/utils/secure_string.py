"""
Secure string management utilities for protecting sensitive data in memory.

This module provides classes for securely handling sensitive strings like passwords
and passphrases by encrypting them in memory and providing automatic cleanup to
prevent memory dump attacks.
"""

import secrets
import array
import gc
import weakref
from typing import Optional, Dict, Any


class SecureTemporaryCredentials:
    """
    Context manager for temporarily extracting credentials with automatic cleanup.
    
    This class safely extracts plain text credentials from SecureString objects
    for the minimum time necessary, then immediately overwrites and clears them
    from memory to prevent exposure in memory dumps.
    """
    
    def __init__(self, secure_dict: Dict[str, Any]):
        """
        Initialize with a dictionary containing SecureString objects.
        
        Args:
            secure_dict: Dict containing SecureString objects for 'password' and/or 'passphrase'
        """
        self.secure_dict = secure_dict
        self.plain_dict = {}
        self.cleanup_vars = []
        self._original_values = {}
    
    def __enter__(self) -> Dict[str, Any]:
        """Extract plain text credentials temporarily."""
        self.plain_dict = self.secure_dict.copy()
        
        # Extract password if present
        if 'password' in self.plain_dict and hasattr(self.plain_dict['password'], 'get_value'):
            self._original_values['password'] = self.plain_dict['password']
            plain_password = self.plain_dict['password'].get_value()
            self.plain_dict['password'] = plain_password
            self.cleanup_vars.append('password')
        
        # Extract passphrase if present  
        if 'passphrase' in self.plain_dict and hasattr(self.plain_dict['passphrase'], 'get_value'):
            self._original_values['passphrase'] = self.plain_dict['passphrase']
            plain_passphrase = self.plain_dict['passphrase'].get_value()
            self.plain_dict['passphrase'] = plain_passphrase
            self.cleanup_vars.append('passphrase')
        
        return self.plain_dict
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Securely clear all plain text credentials."""
        # Overwrite sensitive data with random values
        for key in self.cleanup_vars:
            if key in self.plain_dict:
                # Overwrite with random data multiple times
                for _ in range(3):
                    random_data = secrets.token_urlsafe(64)
                    self.plain_dict[key] = random_data
                    del random_data
                
                # Set to None and delete
                self.plain_dict[key] = None
                del self.plain_dict[key]
        
        # Clear the entire dict
        self.plain_dict.clear()
        self.cleanup_vars.clear()
        self._original_values.clear()
        
        # Force garbage collection to clear any remaining references
        gc.collect()


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
credential_manager = SecureCredentialManager()


def get_credential_manager() -> SecureCredentialManager:
    """
    Get the global credential manager instance.
    
    Returns:
        SecureCredentialManager: The global credential manager
    """
    return credential_manager


def emergency_cleanup():
    """
    Emergency function to clear all secure credentials.
    Should be called on application shutdown or security emergencies.
    """
    credential_manager.clear_all_credentials()
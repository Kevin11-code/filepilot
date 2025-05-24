import paramiko
import os
import json
import logging
import time
from typing import Dict, Optional, Union, Tuple, Callable

class SFTPClient:
    """
    Enhanced SFTP client supporting password and key-based authentication
    with chunked file transfer and progress reporting.
    """
    def __init__(self, logger=None):
        """Initialize the SFTP client with an optional logger."""
        self.ssh = None
        self.sftp = None
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
            
    def connect(self, 
                host: str, 
                port: int = 22, 
                username: str = None, 
                password: str = None, 
                key_path: str = None, 
                passphrase: str = None) -> bool:
        """
        Connect to an SFTP server using either password or key-based authentication.
        
        Args:
            host: SFTP server hostname or IP
            port: SFTP server port (default 22)
            username: Login username
            password: Password for password-based authentication
            key_path: Path to private key for key-based authentication
            passphrase: Optional passphrase for encrypted private key
            
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.logger.info(f"Connecting to {host}:{port} as {username}")
            
            if key_path:
                # Key-based authentication
                self.logger.info(f"Using key-based authentication with key: {key_path}")
                if passphrase:
                    key = paramiko.RSAKey.from_private_key_file(key_path, password=passphrase)
                else:
                    key = paramiko.RSAKey.from_private_key_file(key_path)
                self.ssh.connect(host, port=port, username=username, pkey=key)
            else:
                # Password-based authentication
                self.logger.info("Using password-based authentication")
                self.ssh.connect(host, port=port, username=username, password=password)
                
            self.sftp = self.ssh.open_sftp()
            self.logger.info(f"Connected successfully to {host}")
            return True
            
        except Exception as e:
            self.logger.error(f"Connection failed: {str(e)}")
            if self.ssh:
                self.ssh.close()
            return False
            
    def disconnect(self):
        """Close the SFTP and SSH connections."""
        if self.sftp:
            self.sftp.close()
        if self.ssh:
            self.ssh.close()
        self.logger.info("Disconnected from server")
            
    def upload_file(self, 
                   local_path: str, 
                   remote_path: str, 
                   chunks: int = 10, 
                   progress_callback: Callable[[float, float, float], None] = None) -> bool:
        """
        Upload a file to the SFTP server with chunking and progress reporting.
        
        Args:
            local_path: Path to the local file
            remote_path: Destination path on the server
            chunks: Number of chunks to split the file into
            progress_callback: Optional callback function for progress updates:
                               func(bytes_transferred, total_bytes, percentage)
        
        Returns:
            bool: True if upload successful, False otherwise
        """
        if not self.sftp:
            self.logger.error("Not connected to an SFTP server")
            return False
            
        try:
            file_size = os.path.getsize(local_path)
            chunk_size = max(file_size // chunks, 1024)  # Ensure minimum chunk size
            
            self.logger.info(f"Starting upload: '{local_path}' -> '{remote_path}'")
            self.logger.info(f"File Size: {file_size} bytes (~{file_size / (1024**3):.2f} GB), Chunk Size: {chunk_size} bytes")
            
            with open(local_path, 'rb') as local_file:
                with self.sftp.open(remote_path, 'wb') as remote_file:
                    bytes_transferred = 0
                    start_time = time.time()
                    
                    while True:
                        chunk_data = local_file.read(chunk_size)
                        if not chunk_data:
                            break
                            
                        remote_file.write(chunk_data)
                        remote_file.flush()
                        
                        bytes_transferred += len(chunk_data)
                        percent = (bytes_transferred / file_size) * 100
                        
                        # Call the progress callback if provided
                        if progress_callback:
                            progress_callback(bytes_transferred, file_size, percent)
                        
                        # Calculate and log transfer rate
                        elapsed_time = max(time.time() - start_time, 0.1)
                        transfer_rate = bytes_transferred / elapsed_time / (1024 * 1024)  # MB/s
                        
                        self.logger.info(f"Progress: {bytes_transferred/(1024**3):.2f} GB of {file_size/(1024**3):.2f} GB "
                                        f"({percent:.1f}%) at {transfer_rate:.2f} MB/s")
                        
            self.logger.info(f"File upload completed successfully: {local_path} -> {remote_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Upload failed: {str(e)}")
            return False
            
    def download_file(self, 
                     remote_path: str, 
                     local_path: str, 
                     chunks: int = 10, 
                     progress_callback: Callable[[float, float, float], None] = None) -> bool:
        """
        Download a file from the SFTP server with chunking and progress reporting.
        
        Args:
            remote_path: Path to the file on the server
            local_path: Destination path on the local system
            chunks: Number of chunks to split the file into
            progress_callback: Optional callback function for progress updates:
                               func(bytes_transferred, total_bytes, percentage)
        
        Returns:
            bool: True if download successful, False otherwise
        """
        if not self.sftp:
            self.logger.error("Not connected to an SFTP server")
            return False
            
        try:
            file_size = self.sftp.stat(remote_path).st_size
            chunk_size = max(file_size // chunks, 1024)  # Ensure minimum chunk size
            
            self.logger.info(f"Starting download: '{remote_path}' -> '{local_path}'")
            self.logger.info(f"File Size: {file_size} bytes (~{file_size / (1024**3):.2f} GB), Chunk Size: {chunk_size} bytes")
            
            os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
            
            with self.sftp.open(remote_path, 'rb') as remote_file:
                with open(local_path, 'wb') as local_file:
                    bytes_transferred = 0
                    start_time = time.time()
                    
                    while True:
                        chunk_data = remote_file.read(chunk_size)
                        if not chunk_data:
                            break
                            
                        local_file.write(chunk_data)
                        local_file.flush()
                        
                        bytes_transferred += len(chunk_data)
                        percent = (bytes_transferred / file_size) * 100
                        
                        # Call the progress callback if provided
                        if progress_callback:
                            progress_callback(bytes_transferred, file_size, percent)
                        
                        # Calculate and log transfer rate
                        elapsed_time = max(time.time() - start_time, 0.1)
                        transfer_rate = bytes_transferred / elapsed_time / (1024 * 1024)  # MB/s
                        
                        self.logger.info(f"Progress: {bytes_transferred/(1024**3):.2f} GB of {file_size/(1024**3):.2f} GB "
                                        f"({percent:.1f}%) at {transfer_rate:.2f} MB/s")
                        
            self.logger.info(f"File download completed successfully: {remote_path} -> {local_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Download failed: {str(e)}")
            return False

    def server_to_server_transfer(self,
                                source_config: Dict,
                                dest_config: Dict,
                                source_path: str,
                                dest_path: str,
                                temp_path: str = None,
                                chunks: int = 10,
                                progress_callback: Callable[[float, float, float], None] = None) -> bool:
        """
        Transfer a file from one server to another via the local system as an intermediary.
        
        Args:
            source_config: Connection config for source server
            dest_config: Connection config for destination server
            source_path: Path to the file on the source server
            dest_path: Destination path on the destination server
            temp_path: Temporary file path on local system (optional)
            chunks: Number of chunks for transfer
            progress_callback: Optional callback function for progress updates
            
        Returns:
            bool: True if transfer successful, False otherwise
        """
        if temp_path is None:
            temp_path = os.path.join(os.path.dirname(__file__), "..", "temp", 
                                    os.path.basename(source_path))
        
        # Ensure temp directory exists
        os.makedirs(os.path.dirname(os.path.abspath(temp_path)), exist_ok=True)
        
        self.logger.info(f"Starting server-to-server transfer: {source_path} -> {dest_path}")
        
        # Connect to source server and download
        source_client = SFTPClient(logger=self.logger)
        if not source_client.connect(**source_config):
            self.logger.error("Failed to connect to source server")
            return False
            
        self.logger.info(f"Downloading from source server to temp location: {temp_path}")
        download_result = source_client.download_file(
            source_path, temp_path, chunks, 
            lambda bytes_t, total, percent: progress_callback(bytes_t, total, percent/2) if progress_callback else None
        )
        source_client.disconnect()
        
        if not download_result:
            self.logger.error("Failed to download from source server")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
                
        # Connect to destination server and upload
        dest_client = SFTPClient(logger=self.logger)
        if not dest_client.connect(**dest_config):
            self.logger.error("Failed to connect to destination server")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
            
        self.logger.info(f"Uploading from temp location to destination server: {dest_path}")
        upload_result = dest_client.upload_file(
            temp_path, dest_path, chunks,
            lambda bytes_t, total, percent: progress_callback(bytes_t, total, 50 + percent/2) if progress_callback else None
        )
        dest_client.disconnect()
        
        # Clean up
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        if upload_result:
            self.logger.info(f"Server-to-server transfer completed successfully")
            return True
        else:
            self.logger.error("Failed to upload to destination server")
            return False

    def list_directory(self, remote_path: str = '.') -> list:
        """
        List the contents of a directory on the SFTP server.
        
        Args:
            remote_path: Path to the directory on the server
            
        Returns:
            list: Directory contents or empty list on error
        """
        if not self.sftp:
            self.logger.error("Not connected to an SFTP server")
            return []
            
        try:
            files = self.sftp.listdir_attr(remote_path)
            return [(f.filename, f.st_size, 
                   'dir' if f.st_mode & 0o40000 else 'file', 
                   time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(f.st_mtime)))
                   for f in files]
        except Exception as e:
            self.logger.error(f"Failed to list directory {remote_path}: {str(e)}")
            return []
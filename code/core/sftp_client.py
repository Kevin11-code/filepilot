import paramiko
import os
import json
import logging
import time
import stat
import io
import tempfile
import subprocess
from typing import Dict, Optional, Union, Tuple, Callable
import socket

from code.utils.secure_string import SecureTemporaryCredentials

class SFTPClient:
    """
    Enhanced SFTP client supporting password and key-based authentication
    with chunked file transfer and progress reporting.
    """
    def __init__(self, logger=None):
        """Initialize the SFTP client with an optional logger."""
        self.ssh = None
        self.sftp = None
        # Store connection configuration after successful connection
        self.connection_config = None 
        self._remote_os_type = None # Added to store detected remote OS type
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
                try:
                    # Handle different key formats
                    if key_path.lower().endswith('.ppk'):
                        self.logger.info("Detected PuTTY private key (.ppk) format")
                        
                        # Create a temporary PEM file to convert the PPK format
                        temp_pem_file = None
                        
                        try:
                            # Try using puttygen to convert the key (if available)
                            try:
                                # Create a temporary file for the converted key
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.pem') as tmp:
                                    temp_pem_file = tmp.name
                                
                                # Try to convert using puttygen command
                                cmd = ["puttygen", key_path, "-O", "private-openssh", "-o", temp_pem_file]
                                if passphrase:
                                    # If the source has a passphrase
                                    cmd.extend(["-P", passphrase])
                                
                                self.logger.info(f"Attempting to convert PPK using puttygen: {' '.join(cmd)}")
                                subprocess.run(cmd, check=True)
                                self.logger.info(f"PPK conversion successful, using converted key at {temp_pem_file}")
                                
                                # Now connect using the converted key
                                self.ssh.connect(
                                    host, 
                                    port=port, 
                                    username=username, 
                                    key_filename=temp_pem_file
                                )
                                
                            except (subprocess.SubprocessError, FileNotFoundError):
                                # puttygen not available or failed, try ssh-keygen
                                self.logger.warning("puttygen failed, trying ssh-keygen")
                                
                                if temp_pem_file and os.path.exists(temp_pem_file):
                                    os.unlink(temp_pem_file)
                                
                                # Create a new temp file for ssh-keygen output
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.pem') as tmp:
                                    temp_pem_file = tmp.name
                                
                                # Try to use ssh-keygen to extract public key
                                cmd = ["ssh-keygen", "-f", key_path, "-e", "-m", "pem"]
                                self.logger.info(f"Attempting to convert PPK using ssh-keygen: {' '.join(cmd)}")
                                
                                try:
                                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                                    with open(temp_pem_file, 'w') as f:
                                        f.write(result.stdout)
                                    
                                    # Now connect using the converted key
                                    self.ssh.connect(
                                        host, 
                                        port=port, 
                                        username=username, 
                                        key_filename=temp_pem_file
                                    )
                                except subprocess.SubprocessError:
                                    # Both conversion methods failed, fall back to direct paramiko methods
                                    self.logger.warning("All conversion methods failed, trying direct paramiko loading")
                                    raise
                            
                        except Exception as convert_err:
                            self.logger.warning(f"PPK conversion failed: {str(convert_err)}, trying direct paramiko loading")
                            
                            # Last resort: try to load directly with paramiko
                            try:
                                # Try RSA key format
                                key = paramiko.RSAKey.from_private_key_file(
                                    key_path, 
                                    password=passphrase if passphrase else None
                                )
                                self.ssh.connect(host, port=port, username=username, pkey=key)
                            except Exception as rsa_err:
                                # If RSA doesn't work, try DSS
                                try:
                                    key = paramiko.DSSKey.from_private_key_file(
                                        key_path, 
                                        password=passphrase if passphrase else None
                                    )
                                    self.ssh.connect(host, port=port, username=username, pkey=key)
                                except Exception as dss_err:
                                    # If that doesn't work, try Ed25519
                                    try:
                                        key = paramiko.Ed25519Key.from_private_key_file(
                                            key_path, 
                                            password=passphrase if passphrase else None
                                        )
                                        self.ssh.connect(host, port=port, username=username, pkey=key)
                                    except Exception as ed_err:
                                        # If all direct loading methods fail, try SSH agent
                                        try:
                                            agent = paramiko.Agent()
                                            agent_keys = agent.get_keys()
                                            if not agent_keys:
                                                raise Exception("No SSH agent keys available")
                                                
                                            for agent_key in agent_keys:
                                                try:
                                                    self.ssh.connect(host, port=port, username=username, pkey=agent_key)
                                                    self.logger.info("Connected successfully using SSH agent key")
                                                    break
                                                except:
                                                    continue
                                            else:
                                                raise Exception("No SSH agent keys worked for authentication")
                                        except Exception as agent_err:
                                            # If everything fails, raise a detailed error
                                            raise Exception(f"Failed to load .ppk key file after trying all methods: {str(agent_err)}")
                                            
                        finally:
                            # Clean up the temporary file if it exists
                            if temp_pem_file and os.path.exists(temp_pem_file):
                                try:
                                    os.unlink(temp_pem_file)
                                except:
                                    pass
                                    
                    else:
                        # Standard OpenSSH keys (.pem, .key, etc)
                        self.logger.info("Using standard OpenSSH key format")
                        self.ssh.connect(
                            host, 
                            port=port, 
                            username=username, 
                            key_filename=key_path,
                            passphrase=passphrase if passphrase else None
                        )
                    
                except Exception as key_err:
                    self.logger.error(f"Key authentication error: {str(key_err)}")
                    raise
            else:
                # Password-based authentication
                self.logger.info("Using password-based authentication")
                self.ssh.connect(host, port=port, username=username, password=password)
                
            self.sftp = self.ssh.open_sftp()
            self.logger.info(f"Connected successfully to {host}")
            
            # Store the connection config for later use (e.g., in FilePanel.on_connection_selected)
            self.connection_config = {
                'host': host,
                'port': port,
                'username': username,
                'password': password, # Note: storing password here is generally discouraged for security
                'key_path': key_path,
                'passphrase': passphrase
            }
            # Detect remote OS type after successful connection
            self._detect_remote_os()
            return True

        except socket.gaierror as e:
            # Specifically catch DNS resolution errors
            self.logger.error(f"Connection failed due to DNS resolution issue: Host '{host}' could not be resolved. "
                              f"Please check the hostname/IP address and your network's DNS settings. Error: {e}")
            if self.ssh:
                self.ssh.close()
            return False

        except Exception as e:
            self.logger.error(f"Connection failed: {str(e)}")
            if self.ssh:
                self.ssh.close()
            return False
            
    def disconnect(self):
        """Close the SFTP and SSH connections."""
        if self.sftp:
            self.sftp.close()
            self.sftp = None
        if self.ssh:
            self.ssh.close()
            self.ssh = None
        self.connection_config = None # Clear stored config
        self._remote_os_type = None # Clear detected OS type
        self.logger.info("Disconnected from server")

    def _detect_remote_os(self):
        """Attempts to detect the remote operating system."""
        if not self.ssh:
            self.logger.warning("SSH connection not established, cannot detect remote OS.")
            return

        try:
            stdin, stdout, stderr = self.ssh.exec_command('cat /etc/os-release', timeout=5)
            output = stdout.read().decode('utf-8', errors='ignore').strip()
            error = stderr.read().decode('utf-8', errors='ignore').strip()
            
            if output and "No such file or directory" not in error:
                
                if "ID_LIKE=debian" in output or "ID=ubuntu" in output or "ID=debian" in output:
                    self._remote_os_type = "Linux (Debian/Ubuntu)"
                elif "ID_LIKE=rhel" in output or "ID=centos" in output or "ID=rhel" in output or "ID=fedora" in output:
                    self._remote_os_type = "Linux (RHEL/CentOS/Fedora)"
                elif "PRETTY_NAME" in output or "NAME=" in output:
                    self._remote_os_type = "Linux (Generic)"
                
                self.logger.info(f"Detected OS from /etc/os-release: {self._remote_os_type}")
                return self._remote_os_type
            
            elif error and "No such file or directory" in error:
                self.logger.debug("'/etc/os-release' not found. Trying other methods.")
            
            else:
                self.logger.warning(f"Error or unexpected output from '/etc/os-release': {error if error else output[:100]}")
        
        except paramiko.SSHException as e:
            self.logger.warning(f"SSH error during /etc/os-release check: {e}")
       
        except Exception as e:
            self.logger.error(f"Unexpected error during /etc/os-release check: {e}")


        # Priority 2: Try 'uname -a' (Unix-like systems)
        try:
            stdin, stdout, stderr = self.ssh.exec_command('uname -a', timeout=5)
            output = stdout.read().decode('utf-8', errors='ignore').strip().lower()
            error = stderr.read().decode('utf-8', errors='ignore').strip()
            
            if output and "not found" not in error:
                
                if "linux" in output:
                    self._remote_os_type = "Linux"
                elif "darwin" in output:
                    self._remote_os_type = "macOS"
                elif "bsd" in output:
                    self._remote_os_type = "Other Unix (BSD)"
                else:
                    self._remote_os_type = "Other Unix" # Generic Unix-like
                
                self.logger.info(f"Detected OS from uname -a: {self._remote_os_type}")
                return self._remote_os_type
            
            elif error and "not found" in error:
                self.logger.debug("'uname' command not found. Trying Windows methods.")
            
            else:
                self.logger.warning(f"Error or unexpected output from 'uname -a': {error if error else output[:100]}")
        
        except paramiko.SSHException as e:
            self.logger.warning(f"SSH error during uname check: {e}")
        
        except Exception as e:
            self.logger.error(f"Unexpected error during uname check: {e}")


        # Priority 3: Try Windows-specific commands
        # Try 'ver' for a simpler Windows check
        try:
            stdin, stdout, stderr = self.ssh.exec_command('ver', timeout=5)
            output = stdout.read().decode('utf-8', errors='ignore').strip().lower()
            error = stderr.read().decode('utf-8', errors='ignore').strip()
            
            if "windows" in output:
                self._remote_os_type = "Windows"
                self.logger.info(f"Detected OS from 'ver': {self._remote_os_type}")
                return self._remote_os_type
            
            elif error and "not recognized" not in error:
                self.logger.debug(f"Error or unexpected output from 'ver': {error if error else output[:100]}")
        
        except paramiko.SSHException as e:
            self.logger.warning(f"SSH error during 'ver' check: {e}")
        
        except Exception as e:
            self.logger.error(f"Unexpected error during 'ver' check: {e}")


        # Fallback if no specific OS is detected
        self._remote_os_type = None
        self.logger.warning("Could not definitively detect remote OS, defaulting to 'None'.")
        return self._remote_os_type

    
    def get_remote_file_sha256(self, remote_path: str) -> Optional[str]:
        """
        Calculates the SHA-256 hash of a remote file.
        Adjusts command based on detected remote OS.

        Args:
            remote_path: Path to the remote file.

        Returns:
            str: The SHA-256 hash of the file if successful, None otherwise.
        """
        if not self.ssh:
            self.logger.error("Not connected to an SSH server, cannot get remote file hash.")
            return None

        if self._remote_os_type is None:
            self.logger.warning("Remote OS not detected or detection failed. Attempting to re-detect.")
            self._detect_remote_os()
            if self._remote_os_type is None:
                self.logger.error("Could not determine remote OS to get file hash.")
                return None

        hash_command = ""
        # Normalize remote path for command execution (e.g., Windows paths in PowerShell)
        normalized_remote_path = remote_path.replace('/', '\\') if self._remote_os_type.lower() == "windows" else remote_path

        if "linux" in self._remote_os_type.lower() or "unix" in self._remote_os_type.lower():
            hash_command = f"sha256sum '{normalized_remote_path}'"

        elif "macos" in self._remote_os_type.lower():
            hash_command = f"shasum -a 256 '{normalized_remote_path}'"
        
        elif "windows" in self._remote_os_type.lower():
            # PowerShell command to get SHA256 hash
            hash_command = f'powershell.exe -Command "(Get-FileHash -Algorithm SHA256 \'{normalized_remote_path}\').Hash"'
        
        else:
            self.logger.error(f"Unsupported remote OS for SHA-256 hash: {self._remote_os_type}")
            return None

        self.logger.info(f"Executing remote command: {hash_command}")
        try:
            stdin, stdout, stderr = self.ssh.exec_command(hash_command)
            output = stdout.read().decode('utf-8').strip()
            error = stderr.read().decode('utf-8').strip()

            if error:
                self.logger.error(f"Error executing remote hash command: {error}")
                return None

            # Parse the output to get the hash
            if "linux" in self._remote_os_type.lower() or "macos" in self._remote_os_type.lower():
                # sha256sum output: hash  filename
                # shasum -a 256 output: hash  filename
                if output and ' ' in output:
                    return output.split(' ')[0]
            elif "windows" in self._remote_os_type.lower():
                # PowerShell output is just the hash string
                if output and len(output) == 64: # SHA256 hash is 64 hex characters
                    return output
            else:
                self.logger.error(f"Could not parse hash output for OS type: {self._remote_os_type}. Output: {output}")
                return None

        except Exception as e:
            self.logger.error(f"Failed to get remote file hash: {str(e)}")
            return None

        return None

    def upload_file(self, 
                    local_path: str, 
                    remote_path: str, 
                    chunks: int = 10, 
                    progress_callback: Callable[[float, float, float], None] = None,
                    overwrite_callback: Callable[[str], bool] = None,
                    cancel_event=None) -> bool:
        """
        Upload a file to the SFTP server with chunking and progress reporting.
        
        Args:
            local_path: Path to the local file
            remote_path: Destination path on the server
            chunks: Number of chunks to split the file into
            progress_callback: Optional callback function for progress updates:
                               func(bytes_transferred, total_bytes, percentage)
            overwrite_callback: Optional callback function to ask user about overwriting:
                               func(remote_path) -> bool (True to overwrite, False to cancel)
        
        Returns:
            bool: True if upload successful, False otherwise
        """
        if not self.sftp:
            self.logger.error("Not connected to an SFTP server")
            return False
            
        try:
            # Check if local file exists
            if not os.path.exists(local_path):
                self.logger.error(f"Local file does not exist: {local_path}")
                return False
            
            # Normalize the remote path (handle both Windows and Unix-style paths)
            remote_path = remote_path.replace('\\', '/')
            
            # Handle cases where the remote path ends with a directory separator
            if remote_path.endswith('/'):
                local_filename = os.path.basename(local_path)
                remote_path = f"{remote_path}{local_filename}"
                self.logger.info(f"Remote path is a directory, appending filename: {remote_path}")
            
            # Check if remote path is a directory
            try:
                remote_stat = self.sftp.stat(remote_path)
                if stat.S_ISDIR(remote_stat.st_mode):
                    # It's a directory, append the local filename
                    local_filename = os.path.basename(local_path)
                    remote_path = f"{remote_path}/{local_filename}"
                    self.logger.info(f"Remote path is a directory, appending filename: {remote_path}")
            except FileNotFoundError:
                # Path doesn't exist yet, which is fine for a new file upload
                pass
            except Exception as e:
                self.logger.warning(f"Error checking remote path type: {str(e)}")
            
            # Check if remote file already exists and ask for overwrite confirmation
            try:
                existing_stat = self.sftp.stat(remote_path)
            except FileNotFoundError:
                # File doesn't exist, safe to upload
                pass
            else:
                # File exists, check if we should overwrite
                if overwrite_callback:
                    if not overwrite_callback(remote_path):
                        self.logger.info(f"Upload canceled by user: {remote_path}")
                        return False
                else:
                    self.logger.warning(f"Remote file exists but no overwrite callback provided: {remote_path}")
            
            # Check if remote directory exists, and create it if it doesn't exist
            remote_dir = os.path.dirname(remote_path)
            if remote_dir:
                try:
                    self.sftp.stat(remote_dir)
                    self.logger.info(f"Remote directory exists: {remote_dir}")
                except FileNotFoundError:
                    self.logger.info(f"Remote directory doesn't exist, creating: {remote_dir}")
                    try:
                        # Create directories recursively
                        self._create_remote_directory(remote_dir)
                    except PermissionError as e:
                        self.logger.error(f"Permission denied creating directory {remote_dir}: {str(e)}")
                        return False
                    except Exception as dir_err:
                        self.logger.error(f"Failed to create remote directory: {str(dir_err)}")
                        return False
            
            file_size = os.path.getsize(local_path)
            # Use adaptive chunk size based on file size, but ensure it's reasonable
            min_chunk_size = 64 * 1024  # 64KB minimum
            max_chunk_size = 1024 * 1024  # 1MB maximum
            chunk_size = max(min_chunk_size, min(file_size // chunks, max_chunk_size))
            
            self.logger.info(f"Starting upload: '{local_path}' -> '{remote_path}'")
            self.logger.info(f"File Size: {file_size} bytes ({file_size / (1024**2):.1f} MB), Chunk Size: {chunk_size} bytes, Target Chunks: {chunks}")
            
            # Check if we have write permission by attempting to create a temporary file
            temp_test_path = f"{remote_dir}/.filepilot_test_{int(time.time())}"
            try:
                with self.sftp.open(temp_test_path, 'wb') as test_file:
                    test_file.write(b'test')
                self.sftp.remove(temp_test_path)
                self.logger.info("Successfully verified write permission")
            except Exception as perm_err:
                self.logger.error(f"Cannot write to destination directory: {str(perm_err)}")
                return False
            
            # Check disk space on remote server if possible
            try:
                # This is implementation-specific and might not work on all servers
                channel = self.ssh.get_transport().open_session()
                channel.exec_command(f"df -P {remote_dir} | tail -1 | awk '{{print $4}}'")
                stdout = channel.makefile('r')
                free_space_kb = int(stdout.read().strip())
                free_space_bytes = free_space_kb * 1024
                
                if file_size > free_space_bytes:
                    self.logger.error(f"Not enough disk space on remote server. Required: {file_size} bytes, Available: {free_space_bytes} bytes")
                    return False
                    
                self.logger.info(f"Sufficient disk space available: {free_space_bytes} bytes")
            except Exception as space_err:
                # Can't check disk space, just log and continue
                self.logger.warning(f"Could not check disk space on remote server: {str(space_err)}")
            
            # Start the actual file upload
            try:
                with open(local_path, 'rb') as local_file:
                    with self.sftp.open(remote_path, 'wb') as remote_file:
                        bytes_transferred = 0
                        start_time = time.time()
                        last_progress_time = start_time
                        last_log_time = start_time
                        
                        while True:
                            if (cancel_event and cancel_event.is_set()):
                                self.logger.info("Upload cancelled by user.")
                                return False
                            chunk_data = local_file.read(chunk_size)
                            if not chunk_data:
                                break
                                
                            remote_file.write(chunk_data)
                            remote_file.flush()
                            
                            bytes_transferred += len(chunk_data)
                            percent = (bytes_transferred / file_size) * 100
                            
                            current_time = time.time()
                            
                            # Call progress callback every 100ms to avoid UI flooding
                            if progress_callback and (current_time - last_progress_time) >= 0.1:
                                progress_callback(bytes_transferred, file_size, percent)
                                last_progress_time = current_time
                            
                            # Log progress every 5 seconds or every 10% completion to reduce log spam
                            should_log = (current_time - last_log_time) >= 5.0 or percent % 10 < 0.1
                            if should_log:
                                elapsed_time = max(current_time - start_time, 0.1)
                                transfer_rate = bytes_transferred / elapsed_time / (1024 * 1024)  # MB/s
                                
                                self.logger.info(f"Progress: {bytes_transferred/(1024**2):.1f} MB of {file_size/(1024**2):.1f} MB "
                                                 f"({percent:.1f}%) at {transfer_rate:.2f} MB/s")
                                last_log_time = current_time
                        
                        # Final progress callback
                        if progress_callback:
                            progress_callback(bytes_transferred, file_size, 100.0)
                            
            except PermissionError as pe:
                self.logger.error(f"Permission denied writing to {remote_path}: {str(pe)}")
                return False
            except IOError as ioe:
                self.logger.error(f"I/O error writing to {remote_path}: {str(ioe)}")
                return False
            except Exception as upload_err:
                self.logger.error(f"Error during file upload: {str(upload_err)}")
                return False
            
            # Verify the file was uploaded correctly
            try:
                remote_stat = self.sftp.stat(remote_path)
                if remote_stat.st_size != file_size:
                    self.logger.error(f"File size mismatch after upload: Local {file_size} bytes, Remote {remote_stat.st_size} bytes")
                    return False
            except Exception as verify_err:
                self.logger.error(f"Failed to verify uploaded file: {str(verify_err)}")
                return False
                        
            self.logger.info(f"File upload completed successfully: {local_path} -> {remote_path}")
            return True
            
        except PermissionError as perr:
            self.logger.error(f"Upload failed: Permission denied: {str(perr)}")
            return False
        except IOError as ioerr:
            self.logger.error(f"Upload failed: I/O error: {str(ioerr)}")
            return False
        except Exception as e:
            self.logger.error(f"Upload failed: {str(e)}")
            return False
            
    def rename(self, old_path: str, new_path: str) -> bool:
        """
        Rename a file or directory on the SFTP server.

        Args:
            old_path: The current path of the file/directory.
            new_path: The new path/name for the file/directory.

        Returns:
            bool: True if rename successful, False otherwise.
        """
        if not self.sftp:
            self.logger.error("Not connected to SFTP server for rename operation.")
            return False
        try:
            self.sftp.rename(old_path, new_path)
            self.logger.info(f"Successfully renamed '{old_path}' to '{new_path}'")
            return True
        except Exception as e:
            self.logger.error(f"Failed to rename '{old_path}' to '{new_path}': {e}")
            return False

    def _create_remote_directory(self, path):
        """
        Create a remote directory recursively.
        
        Args:
            path: Remote directory path to create
        """
        if not path:
            return
            
        path = path.replace('\\', '/')  # Normalize path separators
        
        # Split the path into parts and create each directory level
        parts = path.split('/')
        current = ""
        
        for part in parts:
            if not part:
                continue  # Skip empty parts (like leading /)
                
            if current:
                current = f"{current}/{part}"
            else:
                current = part
                
            try:
                self.sftp.stat(current)
                # Directory exists, continue to next part
            except FileNotFoundError:
                # Directory doesn't exist, create it
                self.logger.info(f"Creating directory: {current}")
                try:
                    self.sftp.mkdir(current)
                except Exception as e:
                    if "already exists" in str(e).lower():
                        # Race condition - directory was created between check and mkdir
                        pass
                    else:
                        raise

    def download_file(self, 
                      remote_path: str, 
                      local_path: str, 
                      chunks: int = 10, 
                      progress_callback: Callable[[float, float, float], None] = None,
                      overwrite_callback: Callable[[str], bool] = None,
                      cancel_event=None) -> bool:
        """
        Download a file from the SFTP server with chunking and progress reporting.
        
        Args:
            remote_path: Path to the file on the server
            local_path: Destination path on the local system
            chunks: Number of chunks to split the file into
            progress_callback: Optional callback function for progress updates:
                               func(bytes_transferred, total_bytes, percentage)
            overwrite_callback: Optional callback function to ask user about overwriting:
                               func(local_path) -> bool (True to overwrite, False to cancel)
        
        Returns:
            bool: True if download successful, False otherwise
        """
        if not self.sftp:
            self.logger.error("Not connected to an SFTP server")
            return False
            
        try:
            file_size = self.sftp.stat(remote_path).st_size
            
            # Check if local file already exists and ask for overwrite confirmation
            if os.path.exists(local_path):
                if overwrite_callback:
                    if not overwrite_callback(local_path):
                        self.logger.info(f"Download canceled by user: {local_path}")
                        return False
                else:
                    self.logger.warning(f"Local file exists but no overwrite callback provided: {local_path}")
                    # Continue with download if no callback is provided (backward compatibility)
            
            # Use adaptive chunk size based on file size, but ensure it's reasonable
            min_chunk_size = 64 * 1024  # 64KB minimum
            max_chunk_size = 1024 * 1024  # 1MB maximum
            chunk_size = max(min_chunk_size, min(file_size // chunks, max_chunk_size))
            
            self.logger.info(f"Starting download: '{remote_path}' -> '{local_path}'")
            self.logger.info(f"File Size: {file_size} bytes ({file_size / (1024**2):.1f} MB), Chunk Size: {chunk_size} bytes, Target Chunks: {chunks}")
            
            os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
            
            with self.sftp.open(remote_path, 'rb') as remote_file:
                with open(local_path, 'wb') as local_file:
                    bytes_transferred = 0
                    start_time = time.time()
                    last_progress_time = start_time
                    last_log_time = start_time
                    
                    while True:
                        if (cancel_event and cancel_event.is_set()):
                            self.logger.info("Download cancelled by user.")
                            return False
                        chunk_data = remote_file.read(chunk_size)
                        if not chunk_data:
                            break
                            
                        local_file.write(chunk_data)
                        local_file.flush()
                        
                        bytes_transferred += len(chunk_data)
                        percent = (bytes_transferred / file_size) * 100
                        
                        current_time = time.time()
                        
                        # Call progress callback every 100ms to avoid UI flooding
                        if progress_callback and (current_time - last_progress_time) >= 0.1:
                            progress_callback(bytes_transferred, file_size, percent)
                            last_progress_time = current_time
                        
                        # Log progress every 5 seconds or every 10% completion to reduce log spam
                        should_log = (current_time - last_log_time) >= 5.0 or percent % 10 < 0.1
                        if should_log:
                            elapsed_time = max(current_time - start_time, 0.1)
                            transfer_rate = bytes_transferred / elapsed_time / (1024 * 1024)  # MB/s
                            
                            self.logger.info(f"Progress: {bytes_transferred/(1024**2):.1f} MB of {file_size/(1024**2):.1f} MB "
                                             f"({percent:.1f}%) at {transfer_rate:.2f} MB/s")
                            last_log_time = current_time
                    
                    # Final progress callback
                    if progress_callback:
                        progress_callback(bytes_transferred, file_size, 100.0)
                        
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
                                  progress_callback: Callable[[float, float, float], None] = None,
                                  overwrite_callback: Callable[[str], bool] = None,
                                  cancel_event=None) -> bool:
        """
        Transfer a file from one server to another via the local system as an intermediary.
        Uses secure temporary file handling to prevent credential exposure.
        
        Args:
            source_config: Connection config for source server
            dest_config: Connection config for destination server
            source_path: Path to the file on the source server
            dest_path: Destination path on the destination server
            temp_path: Temporary file path on local system (optional)
            chunks: Number of chunks for transfer
            progress_callback: Optional callback function for progress updates
            overwrite_callback: Optional callback function for overwrite confirmation
            
        Returns:
            bool: True if transfer successful, False otherwise
        """
        
        source_client = None
        dest_client = None

        # Create secure temporary file
        temp_dir = os.path.join(os.path.dirname(__file__), "..", "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        if temp_path is None:
            # Create a secure temporary file with restricted permissions
            temp_fd, temp_path = tempfile.mkstemp(
                prefix="filepilot_s2s_",
                suffix=f"_{os.path.basename(source_path)}",
                dir=temp_dir
            )
            # Set restrictive permissions (owner read/write only)
            os.chmod(temp_path, 0o600)
            os.close(temp_fd)  # Close the file descriptor, we'll open it properly later
        
        self.logger.info(f"Starting server-to-server transfer: {source_path} -> {dest_path}")
        self.logger.info(f"Using secure temporary file: {temp_path}")
        
        try:
            # Connect to source server and download
            source_client = SFTPClient(logger=self.logger)
            # Create a copy of the config and remove the 'name' and 'has_password' keys
            source_connect_params = source_config.copy()
            source_connect_params.pop('name', None)
            source_connect_params.pop('has_password', None)
            source_connect_params.pop('has_passphrase', None) # Also remove has_passphrase
            
            with SecureTemporaryCredentials(source_connect_params) as temp_params:
                if not source_client.connect(**temp_params):
                    self.logger.error("Failed to connect to source server")
                    return False
                
            self.logger.info(f"Downloading from source server to secure temp location: {temp_path}")

            if cancel_event and cancel_event.is_set():
                self.logger.info("Download cancelled by user before download.")
                return False

            download_result = source_client.download_file(
                source_path, 
                temp_path, 
                chunks, 
                lambda bytes_t, total, percent: progress_callback(bytes_t, total, percent/2) if progress_callback else None,
                overwrite_callback,
                cancel_event=cancel_event
            )
            source_client.disconnect()
            
            if not download_result:
                self.logger.error("Failed to download from source server")
                return False
                    
            if cancel_event and cancel_event.is_set():
                self.logger.info("Download cancelled by user after download.")
                return False    
            # Connect to destination server and upload
            dest_client = SFTPClient(logger=self.logger)
            # Create a copy of the config and remove the 'name' and 'has_password' keys
            dest_connect_params = dest_config.copy()
            dest_connect_params.pop('name', None)
            dest_connect_params.pop('has_password', None)
            dest_connect_params.pop('has_passphrase', None) # Also remove has_passphrase

            with SecureTemporaryCredentials(dest_connect_params) as temp_params:
                if not dest_client.connect(**temp_params):
                    self.logger.error("Failed to connect to destination server")
                    return False
                
            self.logger.info(f"Uploading from secure temp location to destination server: {dest_path}")

            if cancel_event and cancel_event.is_set():
                self.logger.info("Transfer cancelled by user before upload.")
                return False    

            upload_result = dest_client.upload_file(
                temp_path, dest_path, chunks,
                lambda bytes_t, total, percent: progress_callback(bytes_t, total, 50 + percent/2) if progress_callback else None,
                overwrite_callback,
                cancel_event=cancel_event
            )

            if not upload_result or cancel_event and cancel_event.is_set():
                self.logger.info("Transfer cancelled by user during or after upload.")
                return False
            dest_client.disconnect()
            
            if upload_result:
                self.logger.info(f"Server-to-server transfer completed successfully")
                return True
            else:
                self.logger.error("Failed to upload to destination server")
                return False
                
        except Exception as e:
            self.logger.error(f"Server-to-server transfer failed: {str(e)}")
            return False
        finally:
            # Close any opened connections
            if source_client:
                try:
                    source_client.disconnect()
                except:
                    pass
            if dest_client:
                try:
                    dest_client.disconnect()
                except:
                    pass
            # Secure cleanup of temporary file
            if os.path.exists(temp_path):
                try:
                    # Overwrite the file with random data before deletion
                    file_size = os.path.getsize(temp_path)
                    with open(temp_path, 'r+b') as f:
                        # Overwrite with random data multiple times
                        for _ in range(3):
                            f.seek(0)
                            f.write(os.urandom(file_size))
                            f.flush()
                            os.fsync(f.fileno())  # Force write to disk
                    
                    # Remove the file
                    os.remove(temp_path)
                    self.logger.info("Secure cleanup of temporary file completed")
                except Exception as cleanup_err:
                    self.logger.warning(f"Failed to securely clean up temporary file: {cleanup_err}")
                    # Still try to remove the file normally
                    try:
                        os.remove(temp_path)
                    except:
                        pass

    def stream_remote_to_remote(self,
                                source_client: 'SFTPClient',
                                source_path: str,
                                dest_client: 'SFTPClient',
                                dest_path: str,
                                chunk_size: int = 1048576,  # e.g., 1MB chunks
                                progress_callback: Callable = None,
                                overwrite_callback: Callable[[str], bool] = None) -> bool:
        """
        Streams a file directly from one remote SFTP server to another
        without saving it to the local disk.

        Args:
            source_client: An initialized SFTPClient instance connected to the source server.
            source_path: The path to the file on the source server.
            dest_client: An initialized SFTPClient instance connected to the destination server.
            dest_path: The path to the destination file on the target server.
            chunk_size: The size of data chunks to read/write in bytes.
            progress_callback: Optional callback for progress updates (current_bytes, total_bytes).
            overwrite_callback: Optional callback function for overwrite confirmation.

        Returns:
            bool: True if the transfer was successful, False otherwise.
        """
        if not source_client.sftp or not dest_client.sftp:
            self.logger.error("Both source and destination SFTP clients must be connected.")
            return False

        try:
            if overwrite_callback:
                if not overwrite_callback(source_path):
                    self.logger.info(f"Upload canceled by user: {dest_path}")
                    return False
                
            # Get file size for progress reporting
            sftp_attrs = source_client.sftp.stat(source_path)
            total_bytes = sftp_attrs.st_size
            transferred_bytes = 0

            # Open remote source file for reading
            # 'rb' mode for binary read
            with source_client.sftp.open(source_path, 'rb') as sftp_source_file:
                # Open remote destination file for writing
                # 'wb' mode for binary write; creates file if it doesn't exist, truncates if it does
                with dest_client.sftp.open(dest_path, 'wb') as sftp_dest_file:
                    while True:
                        chunk = sftp_source_file.read(chunk_size)
                        if not chunk:
                            break  # End of file

                        sftp_dest_file.write(chunk)
                        transferred_bytes += len(chunk)

                        if progress_callback:
                            progress_callback(transferred_bytes, total_bytes, (transferred_bytes/total_bytes) * 100)

            self.logger.info(f"Successfully streamed '{source_path}' from source to '{dest_path}' on destination.")
            return True

        except FileNotFoundError:
            self.logger.error(f"One of the files not found during streaming: {source_path} or {dest_path}")
            return False
        except paramiko.SFTPError as e:
            self.logger.error(f"SFTP error during streaming: {e}")
            return False
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during streaming: {e}")
            return False
    
    
    def list_directory(self, remote_path: str = '.') -> list:
        """
        List the contents of a directory on the SFTP server.
        
        Args:
            remote_path: Path to the directory on the server
            
        Returns:
            list: Directory contents (list of paramiko.SFTPAttributes) or empty list on error
        """
        if not self.sftp:
            self.logger.error("Not connected to an SFTP server")
            return []
            
        try:
            # paramiko.SFTPClient.listdir_attr returns a list of paramiko.SFTPAttributes objects
            files = self.sftp.listdir_attr(remote_path)
            return files # Return the raw SFTPAttribute objects
        except Exception as e:
            self.logger.error(f"Failed to list directory {remote_path}: {str(e)}")
            return []

    def remove(self, remote_path: str) -> bool:
        """
        Deletes a file on the SFTP server.
        
        Args:
            remote_path: Path to the file on the server.
            
        Returns:
            bool: True if deletion successful, False otherwise.
        """
        if not self.sftp:
            self.logger.error("Not connected to an SFTP server.")
            return False
        try:
            self.sftp.remove(remote_path)
            self.logger.info(f"Successfully deleted remote file: {remote_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete remote file {remote_path}: {str(e)}")
            return False

    def rmdir(self, remote_path: str) -> bool:
        """
        Deletes a directory on the SFTP server.
        Attempts recursive deletion if the directory is not empty.
        
        Args:
            remote_path: Path to the directory on the server.
            
        Returns:
            bool: True if deletion successful, False otherwise.
        """
        if not self.sftp:
            self.logger.error("Not connected to an SFTP server.")
            return False
        try:
            # Try to remove empty directory first
            self.sftp.rmdir(remote_path)
            self.logger.info(f"Successfully deleted empty remote directory: {remote_path}")
            return True
        except IOError as e:
            # Directory not empty or other IOError
            if "Directory not empty" in str(e) or "is not empty" in str(e):
                self.logger.warning(f"Remote directory {remote_path} is not empty. Attempting recursive deletion.")
                return self._rmdir_recursive(remote_path)
            else:
                self.logger.error(f"Failed to delete remote directory {remote_path}: {str(e)}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to delete remote directory {remote_path}: {str(e)}")
            return False

    def _rmdir_recursive(self, remote_path: str) -> bool:
        """
        Recursively deletes a directory and its contents on the SFTP server.
        
        Args:
            remote_path: Path to the directory to delete recursively.
            
        Returns:
            bool: True if recursive deletion successful, False otherwise.
        """
        if not self.sftp:
            self.logger.error("Not connected to an SFTP server for recursive deletion.")
            return False
        
        try:
            # List contents
            for entry in self.sftp.listdir_attr(remote_path):
                if entry.filename in ('.', '..'):
                    continue
                
                full_entry_path = os.path.join(remote_path, entry.filename).replace('\\', '/')
                
                if stat.S_ISDIR(entry.st_mode):
                    # Recursively delete sub-directory
                    if not self._rmdir_recursive(full_entry_path):
                        self.logger.error(f"Failed to recursively delete sub-directory: {full_entry_path}")
                        return False
                else:
                    # Delete file
                    if not self.remove(full_entry_path):
                        self.logger.error(f"Failed to delete file during recursive deletion: {full_entry_path}")
                        return False
            
            # After deleting all contents, remove the directory itself
            self.sftp.rmdir(remote_path)
            self.logger.info(f"Successfully recursively deleted remote directory: {remote_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error during recursive remote directory deletion of {remote_path}: {str(e)}")
            return False

    def get_home_directory(self) -> str:
        """
        Get the home directory of the current user on the remote server.
        
        Returns:
            str: Path to the user's home directory, or "/" if unable to determine
        """
        if not self.sftp:
            self.logger.error("Not connected to an SFTP server")
            return "/"
            
        try:
            # Try to get the home directory using the SFTP normalize method
            # This works by normalizing "." which should resolve to the user's home directory
            home_path = self.sftp.normalize(".")
            self.logger.info(f"Home directory determined as: {home_path}")
            return home_path
        except Exception as e:
            self.logger.warning(f"Could not determine home directory using SFTP normalize: {e}")
            
            try:
                # Fallback: try using SSH to execute pwd command
                if self.ssh:
                    stdin, stdout, stderr = self.ssh.exec_command("pwd")
                    home_path = stdout.read().decode().strip()
                    if home_path and home_path != "/":
                        self.logger.info(f"Home directory determined via SSH pwd: {home_path}")
                        return home_path
            except Exception as ssh_e:
                self.logger.warning(f"Could not determine home directory using SSH pwd: {ssh_e}")
            
            try:
                # Another fallback: try echo $HOME (Unix/Linux/macOS)
                if self.ssh:
                    stdin, stdout, stderr = self.ssh.exec_command("echo $HOME")
                    home_path = stdout.read().decode().strip()
                    if home_path and home_path != "/" and not home_path.startswith("$"):
                        self.logger.info(f"Home directory determined via SSH $HOME: {home_path}")
                        return home_path
            except Exception as env_e:
                self.logger.warning(f"Could not determine home directory using $HOME: {env_e}")
            
            try:
                # Windows fallback: try echo %USERPROFILE%
                if self.ssh:
                    stdin, stdout, stderr = self.ssh.exec_command("echo %USERPROFILE%")
                    home_path = stdout.read().decode().strip()
                    if home_path and not home_path.startswith("%") and len(home_path) > 3:
                        # Convert Windows path to forward slashes for consistency
                        home_path = home_path.replace("\\", "/")
                        self.logger.info(f"Home directory determined via Windows %USERPROFILE%: {home_path}")
                        return home_path
            except Exception as win_e:
                self.logger.warning(f"Could not determine home directory using Windows %USERPROFILE%: {win_e}")
            
            try:
                # Windows alternative: try echo %HOMEPATH% with %HOMEDRIVE%
                if self.ssh:
                    stdin, stdout, stderr = self.ssh.exec_command("echo %HOMEDRIVE%%HOMEPATH%")
                    home_path = stdout.read().decode().strip()
                    if home_path and not home_path.startswith("%") and len(home_path) > 3:
                        # Convert Windows path to forward slashes for consistency
                        home_path = home_path.replace("\\", "/")
                        self.logger.info(f"Home directory determined via Windows %HOMEDRIVE%%HOMEPATH%: {home_path}")
                        return home_path
            except Exception as win2_e:
                self.logger.warning(f"Could not determine home directory using Windows %HOMEDRIVE%%HOMEPATH%: {win2_e}")
            
            # Final fallback for different operating systems
            if self.connection_config and self.connection_config.get('username'):
                username = self.connection_config['username']
                
                # Try common home directory patterns
                try:
                    # Linux/Unix pattern
                    linux_home = f"/home/{username}"
                    try:
                        self.sftp.stat(linux_home)
                        self.logger.info(f"Found Linux-style home directory: {linux_home}")
                        return linux_home
                    except FileNotFoundError:
                        pass
                    
                    # Try root home
                    if username == "root":
                        try:
                            self.sftp.stat("/root")
                            self.logger.info("Found root home directory: /root")
                            return "/root"
                        except FileNotFoundError:
                            pass
                    
                    # macOS pattern (same as Linux usually)
                    mac_home = f"/Users/{username}"
                    try:
                        self.sftp.stat(mac_home)
                        self.logger.info(f"Found macOS-style home directory: {mac_home}")
                        return mac_home
                    except FileNotFoundError:
                        pass
                    
                    # Windows patterns
                    # Try C:/Users/username (modern Windows)
                    win_home_modern = f"C:/Users/{username}"
                    try:
                        self.sftp.stat(win_home_modern)
                        self.logger.info(f"Found Windows-style home directory: {win_home_modern}")
                        return win_home_modern
                    except FileNotFoundError:
                        pass
                    
                    # Try C:/Documents and Settings/username (older Windows)
                    win_home_old = f"C:/Documents and Settings/{username}"
                    try:
                        self.sftp.stat(win_home_old)
                        self.logger.info(f"Found old Windows-style home directory: {win_home_old}")
                        return win_home_old
                    except FileNotFoundError:
                        pass
                        
                except Exception as pattern_e:
                    self.logger.warning(f"Could not check common home directory patterns: {pattern_e}")
            
            # If all else fails, return root
            self.logger.warning("Could not determine home directory, defaulting to root (/)")
            return "/"
    
    def stat(self, path):
        """Return stat info for a remote file or directory."""
        return self.sftp.stat(path)
    
    def chmod(self, path, mode):
        """Change permissions of a remote file or directory."""
        try:
            self.sftp.chmod(path, mode)
            return True
        except Exception:
            return False
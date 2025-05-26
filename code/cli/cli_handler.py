import os
import sys
import time
import argparse
import getpass
from typing import Dict, List, Optional
import json
import stat

from ..core.sftp_client import SFTPClient
from ..core.auth_manager import AuthManager, SecureString, _credential_manager
from ..core.transfer_manager import TransferManager
from ..utils.logger import LoggerSetup


class CLIHandler:
    """
    Command Line Interface handler for FilePilot.
    Provides command-line operations for SFTP transfers with secure credential handling.
    """
    def __init__(self, config_dir=None):
        """
        Initialize the CLI handler.
        
        Args:
            config_dir: Optional directory for config files
        """
        # Setup logger
        log_file = os.path.join(
            os.path.dirname(__file__), "..", "logs", "filepilot_cli.log"
        )
        self.logger = LoggerSetup.setup_logger(
            name="filepilot_cli",
            log_file=log_file,
            log_to_console=True
        )
        
        # Initialize managers
        self.config_dir = config_dir or os.path.join(
            os.path.dirname(__file__), "..", "config"
        )
        self.auth_manager = AuthManager(self.config_dir)
        self.transfer_manager = TransferManager(logger=self.logger)
        
        # Track active credentials for cleanup
        self._active_credentials = []

    def _cleanup_credentials(self):
        """Clean up all active credentials."""
        for cred in self._active_credentials:
            try:
                if hasattr(cred, 'clear'):
                    cred.clear()
            except:
                pass
        self._active_credentials.clear()
        
        # Also clear global credentials
        _credential_manager.clear_all_credentials()

    def parse_args(self):
        """
        Parse command line arguments.
        
        Returns:
            argparse.Namespace: Parsed arguments
        """
        parser = argparse.ArgumentParser(
            description="FilePilot SFTP Client - Command Line Interface"
        )
        
        # Common arguments
        parser.add_argument('--verbose', action='store_true', 
                          help='Enable verbose output')
        parser.add_argument('--quiet', action='store_true',
                          help='Suppress all output except errors')
        parser.add_argument('--connection', type=str,
                          help='Use a saved connection')
        
        # Create subparsers for commands
        subparsers = parser.add_subparsers(dest='command', help='Command to execute')
        
        # Upload command
        upload_parser = subparsers.add_parser('upload', help='Upload files to SFTP server')
        upload_parser.add_argument('local_path', help='Local file or directory to upload')
        upload_parser.add_argument('remote_path', help='Remote destination path')
        self._add_connection_args(upload_parser)
        
        # Download command
        download_parser = subparsers.add_parser('download', help='Download files from SFTP server')
        download_parser.add_argument('remote_path', help='Remote file or directory to download')
        download_parser.add_argument('local_path', help='Local destination path')
        self._add_connection_args(download_parser)

        # Rename command
        rename_parser = subparsers.add_parser('rename', help='Rename a file or directory on the server')
        rename_parser.add_argument('old_path', help='Current path of the file/directory')
        rename_parser.add_argument('new_path', help='New path/name for the file/directory')
        self._add_connection_args(rename_parser)
        
        # Server to server command
        s2s_parser = subparsers.add_parser('s2s', help='Server-to-server file transfer')
        s2s_parser.add_argument('source_path', help='Source file path')
        s2s_parser.add_argument('dest_path', help='Destination file path')
        s2s_parser.add_argument('--source-host', required=True, help='Source server hostname or IP')
        s2s_parser.add_argument('--source-username', required=True, help='Source server username')
        s2s_parser.add_argument('--source-password', required=True, help='Source server password')
        s2s_parser.add_argument('--dest-host', required=True, help='Destination server hostname or IP')
        s2s_parser.add_argument('--dest-username', required=True, help='Destination server username')
        s2s_parser.add_argument('--dest-password', required=True, help='Destination server password')
        self._add_connection_args(s2s_parser, prefix='source_')
        self._add_connection_args(s2s_parser, prefix='dest_')
        
        # List command
        list_parser = subparsers.add_parser('list', help='List directory contents')
        list_parser.add_argument('remote_path', nargs='?', default=None,
                               help='Remote path to list (default: user home directory)')
        self._add_connection_args(list_parser)
        
        # Connection management commands
        conn_parser = subparsers.add_parser('connection', help='Connection management')
        conn_subparsers = conn_parser.add_subparsers(dest='conn_command', help='Connection command')
        
        # Add connection
        add_conn = conn_subparsers.add_parser('add', help='Add a new connection')
        add_conn.add_argument('name', help='Connection name')
        self._add_connection_args(add_conn)
        add_conn.add_argument('--encrypt', action='store_true',
                            help='Encrypt the connection configuration')
        add_conn.add_argument('--use-keyring', action='store_true',
                            help='Store sensitive data in system keyring')
        
        # List connections
        list_conn = conn_subparsers.add_parser('list', help='List saved connections')
        
        # Remove connection
        del_conn = conn_subparsers.add_parser('remove', help='Remove a connection')
        del_conn.add_argument('name', help='Connection name to remove')
        
        return parser.parse_args()
    
    def _add_connection_args(self, parser, prefix=''):
        """
        Add connection arguments to a parser.
        
        Args:
            parser: Parser to add arguments to
            prefix: Optional prefix for argument names
        """
        # Add hostname/port
        parser.add_argument(f'--{prefix}host', type=str,
                          help=f'SFTP server hostname or IP')
        parser.add_argument(f'--{prefix}port', type=int, default=22,
                          help=f'SFTP server port (default: 22)')
        
        # Add username
        parser.add_argument(f'--{prefix}username', type=str,
                          help=f'SFTP username')
        
        # Authentication options
        auth_group = parser.add_mutually_exclusive_group()
        auth_group.add_argument(f'--{prefix}password', type=str,
                              help=f'SFTP password (not recommended for security reasons)')
        auth_group.add_argument(f'--{prefix}password-stdin', action='store_true',
                              help=f'Read password from stdin')
        auth_group.add_argument(f'--{prefix}password-env', type=str, metavar='ENV_VAR',
                              help=f'Read password from environment variable')
        auth_group.add_argument(f'--{prefix}key-file', type=str,
                              help=f'Private key file path')
        
        # Key passphrase options
        parser.add_argument(f'--{prefix}passphrase', type=str,
                          help=f'Private key passphrase')
        parser.add_argument(f'--{prefix}passphrase-stdin', action='store_true',
                          help=f'Read passphrase from stdin')
        parser.add_argument(f'--{prefix}passphrase-env', type=str, metavar='ENV_VAR',
                          help=f'Read passphrase from environment variable')
    
    def _get_connection_config(self, args, prefix=''):
        """
        Extract connection configuration from arguments.
        
        Args:
            args: Parsed arguments
            prefix: Optional prefix used in argument names
            
        Returns:
            dict: Connection configuration
        """
        # Check if using a saved connection
        conn_arg = getattr(args, f'{prefix}connection', None) or getattr(args, 'connection', None)
        if conn_arg:
            # Load saved connection
            conn = self.auth_manager.get_connection(conn_arg)
            if not conn:
                self.logger.error(f"Connection not found: {conn_arg}")
                sys.exit(1)
            return conn
        
        # Build connection config from arguments
        host = getattr(args, f'{prefix}host', None)
        if not host:
            self.logger.error(f"Host is required. Use --{prefix}host or --connection")
            sys.exit(1)
            
        username = getattr(args, f'{prefix}username', None)
        if not username:
            self.logger.error(f"Username is required. Use --{prefix}username")
            sys.exit(1)
            
        # Build the basic config
        config = {
            'host': host,
            'port': getattr(args, f'{prefix}port', 22),
            'username': username
        }
        
        # Handle authentication
        key_file = getattr(args, f'{prefix}key_file', None)
        
        if key_file:
            # Key-based authentication
            if not os.path.exists(key_file):
                self.logger.error(f"Key file not found: {key_file}")
                sys.exit(1)
                
            config['key_path'] = key_file
            
            # Handle passphrase if needed
            passphrase = getattr(args, f'{prefix}passphrase', None)
            passphrase_stdin = getattr(args, f'{prefix}passphrase_stdin', False)
            passphrase_env = getattr(args, f'{prefix}passphrase_env', None)
            
            if passphrase:
                config['passphrase'] = passphrase
            elif passphrase_stdin:
                config['passphrase'] = getpass.getpass('Key passphrase: ')
            elif passphrase_env:
                config['passphrase'] = os.environ.get(passphrase_env)
                if not config['passphrase']:
                    self.logger.error(f"Passphrase environment variable {passphrase_env} not found")
                    sys.exit(1)
        else:
            # Password-based authentication
            password = getattr(args, f'{prefix}password', None)
            password_stdin = getattr(args, f'{prefix}password_stdin', False)
            password_env = getattr(args, f'{prefix}password_env', None)
            
            if password:
                config['password'] = password
            elif password_stdin:
                config['password'] = getpass.getpass('SFTP password: ')
            elif password_env:
                config['password'] = os.environ.get(password_env)
                if not config['password']:
                    self.logger.error(f"Password environment variable {password_env} not found")
                    sys.exit(1)
            else:
                # If no password method specified, prompt
                config['password'] = getpass.getpass('SFTP password: ')
                
        return config
    
    def _get_connection_config_secure(self, args, prefix=''):
        """
        Extract connection configuration from arguments using SecureString for passwords.
        
        Args:
            args: Parsed arguments
            prefix: Optional prefix used in argument names
            
        Returns:
            dict: Connection configuration with SecureString for sensitive data
        """
        # Check if using a saved connection
        conn_arg = getattr(args, f'{prefix}connection', None) or getattr(args, 'connection', None)
        if conn_arg:
            # Load saved connection with secure credentials
            conn = self.auth_manager.get_connection_secure(conn_arg)
            if not conn:
                self.logger.error(f"Connection not found: {conn_arg}")
                sys.exit(1)
            
            # Track credentials for cleanup
            if 'password' in conn and isinstance(conn['password'], SecureString):
                self._active_credentials.append(conn['password'])
            if 'passphrase' in conn and isinstance(conn['passphrase'], SecureString):
                self._active_credentials.append(conn['passphrase'])
                
            return conn
        
        # Build connection config from arguments
        host = getattr(args, f'{prefix}host', None)
        if not host:
            self.logger.error(f"Host is required. Use --{prefix}host or --connection")
            sys.exit(1)
            
        username = getattr(args, f'{prefix}username', None)
        if not username:
            self.logger.error(f"Username is required. Use --{prefix}username")
            sys.exit(1)
            
        # Build the basic config
        config = {
            'host': host,
            'port': getattr(args, f'{prefix}port', 22),
            'username': username
        }
        
        # Handle authentication
        key_file = getattr(args, f'{prefix}key_file', None)
        
        if key_file:
            # Key-based authentication
            if not os.path.exists(key_file):
                self.logger.error(f"Key file not found: {key_file}")
                sys.exit(1)
                
            config['key_path'] = key_file
            
            # Handle passphrase if needed - wrap in SecureString
            passphrase = getattr(args, f'{prefix}passphrase', None)
            passphrase_stdin = getattr(args, f'{prefix}passphrase_stdin', False)
            passphrase_env = getattr(args, f'{prefix}passphrase_env', None)
            
            if passphrase:
                secure_passphrase = SecureString(passphrase)
                config['passphrase'] = secure_passphrase
                self._active_credentials.append(secure_passphrase)
                # Clear the original variable
                passphrase = None
                del passphrase
            elif passphrase_stdin:
                passphrase_value = getpass.getpass('Key passphrase: ')
                secure_passphrase = SecureString(passphrase_value)
                config['passphrase'] = secure_passphrase
                self._active_credentials.append(secure_passphrase)
                # Clear the local variable
                passphrase_value = None
                del passphrase_value
            elif passphrase_env:
                passphrase_value = os.environ.get(passphrase_env)
                if not passphrase_value:
                    self.logger.error(f"Passphrase environment variable {passphrase_env} not found")
                    sys.exit(1)
                secure_passphrase = SecureString(passphrase_value)
                config['passphrase'] = secure_passphrase
                self._active_credentials.append(secure_passphrase)
                # Clear the local variable
                passphrase_value = None
                del passphrase_value
        else:
            # Password-based authentication - wrap in SecureString
            password = getattr(args, f'{prefix}password', None)
            password_stdin = getattr(args, f'{prefix}password_stdin', False)
            password_env = getattr(args, f'{prefix}password_env', None)
            
            if password:
                secure_password = SecureString(password)
                config['password'] = secure_password
                self._active_credentials.append(secure_password)
                # Clear the original variable
                password = None
                del password
            elif password_stdin:
                password_value = getpass.getpass('SFTP password: ')
                secure_password = SecureString(password_value)
                config['password'] = secure_password
                self._active_credentials.append(secure_password)
                # Clear the local variable
                password_value = None
                del password_value
            elif password_env:
                password_value = os.environ.get(password_env)
                if not password_value:
                    self.logger.error(f"Password environment variable {password_env} not found")
                    sys.exit(1)
                secure_password = SecureString(password_value)
                config['password'] = secure_password
                self._active_credentials.append(secure_password)
                # Clear the local variable
                password_value = None
                del password_value
            else:
                # If no password method specified, prompt
                password_value = getpass.getpass('SFTP password: ')
                secure_password = SecureString(password_value)
                config['password'] = secure_password
                self._active_credentials.append(secure_password)
                # Clear the local variable
                password_value = None
                del password_value
                
        return config

    def run(self):
        """
        Run the CLI application based on arguments.
        """
        try:
            args = self.parse_args()
            
            # Set up verbosity
            if args.quiet:
                self.logger.setLevel(40)  # ERROR level
            elif args.verbose:
                self.logger.setLevel(10)  # DEBUG level
            
            # Process commands using secure methods
            if args.command == 'upload':
                self._handle_upload_secure(args)
            elif args.command == 'download':
                self._handle_download_secure(args)
            elif args.command == 'rename':
                self._handle_rename_secure(args)
            elif args.command == 's2s':
                self._handle_server_to_server_secure(args)
            elif args.command == 'list':
                self._handle_list_secure(args)
            elif args.command == 'connection':
                self._handle_connection_commands_secure(args)
            else:
                self.logger.error("No command specified. Use -h for help.")
                sys.exit(1)
        finally:
            # Always cleanup credentials
            self._cleanup_credentials()
    
    def _handle_upload_secure(self, args):
        """Handle file upload command with secure credential handling."""
        if not os.path.exists(args.local_path):
            self.logger.error(f"Local path not found: {args.local_path}")
            sys.exit(1)
            
        config = self._get_connection_config_secure(args)
        
        # Create SFTP client
        client = SFTPClient(logger=self.logger)
        
        # Extract credentials for connection
        connect_config = config.copy()
        
        # Convert SecureString objects to plain strings for connection
        if 'password' in connect_config and isinstance(connect_config['password'], SecureString):
            connect_config['password'] = connect_config['password'].get_value()
        if 'passphrase' in connect_config and isinstance(connect_config['passphrase'], SecureString):
            connect_config['passphrase'] = connect_config['passphrase'].get_value()
        
        # Remove non-connection fields
        connect_config.pop('name', None)
        
        # Connect to server
        self.logger.info(f"Connecting to {config['host']}:{config['port']} as {config['username']}")
        if not client.connect(**connect_config):
            self.logger.error("Connection failed")
            sys.exit(1)
            
        # Clear connection config after use
        if 'password' in connect_config:
            connect_config['password'] = None
            del connect_config['password']
        if 'passphrase' in connect_config:
            connect_config['passphrase'] = None
            del connect_config['passphrase']
            
        # Upload file
        if os.path.isdir(args.local_path):
            self.logger.error("Directory upload not implemented in CLI yet")
            sys.exit(1)
        else:
            # Progress callback for direct upload
            def progress(bytes_transferred, total_bytes, percent):
                if not args.quiet:
                    sys.stdout.write(f"\rUploading: {percent:.1f}% ({bytes_transferred/(1024*1024):.2f} MB / {total_bytes/(1024*1024):.2f} MB)")
                    sys.stdout.flush()
            
            self.logger.info(f"Uploading {args.local_path} to {args.remote_path}")
            result = client.upload_file(args.local_path, args.remote_path, progress_callback=progress)
            
            if result:
                if not args.quiet:
                    print("\nUpload completed successfully")
                self.logger.info("Upload completed successfully")
            else:
                if not args.quiet:
                    print("\nUpload failed")
                self.logger.error("Upload failed")
                sys.exit(1)
                
        # Disconnect
        client.disconnect()
    
    def _handle_download_secure(self, args):
        """Handle file download command with secure credential handling."""
        config = self._get_connection_config_secure(args)
        
        # Create SFTP client
        client = SFTPClient(logger=self.logger)
        
        # Extract credentials for connection
        connect_config = config.copy()
        
        # Convert SecureString objects to plain strings for connection
        if 'password' in connect_config and isinstance(connect_config['password'], SecureString):
            connect_config['password'] = connect_config['password'].get_value()
        if 'passphrase' in connect_config and isinstance(connect_config['passphrase'], SecureString):
            connect_config['passphrase'] = connect_config['passphrase'].get_value()
        
        # Remove non-connection fields
        connect_config.pop('name', None)
        
        # Connect to server
        self.logger.info(f"Connecting to {config['host']}:{config['port']} as {config['username']}")
        if not client.connect(**connect_config):
            self.logger.error("Connection failed")
            sys.exit(1)
            
        # Clear connection config after use
        if 'password' in connect_config:
            connect_config['password'] = None
            del connect_config['password']
        if 'passphrase' in connect_config:
            connect_config['passphrase'] = None
            del connect_config['passphrase']
            
        # Check if remote path exists
        try:
            client.sftp.stat(args.remote_path)
        except:
            self.logger.error(f"Remote path not found: {args.remote_path}")
            sys.exit(1)
            
        # Download file
        def progress(bytes_transferred, total_bytes, percent):
            if not args.quiet:
                sys.stdout.write(f"\rDownloading: {percent:.1f}% ({bytes_transferred/(1024*1024):.2f} MB / {total_bytes/(1024*1024):.2f} MB)")
                sys.stdout.flush()
        
        self.logger.info(f"Downloading {args.remote_path} to {args.local_path}")
        result = client.download_file(args.remote_path, args.local_path, progress_callback=progress)
        
        if result:
            if not args.quiet:
                print("\nDownload completed successfully")
            self.logger.info("Download completed successfully")
        else:
            if not args.quiet:
                print("\nDownload failed")
            self.logger.error("Download failed")
            sys.exit(1)
            
        # Disconnect
        client.disconnect()

    def _handle_rename_secure(self, args):
        """Handle rename command with secure credential handling."""
        config = self._get_connection_config_secure(args)
        client = SFTPClient(logger=self.logger)
        
        # Extract credentials for connection
        connect_config = config.copy()
        
        # Convert SecureString objects to plain strings for connection
        if 'password' in connect_config and isinstance(connect_config['password'], SecureString):
            connect_config['password'] = connect_config['password'].get_value()
        if 'passphrase' in connect_config and isinstance(connect_config['passphrase'], SecureString):
            connect_config['passphrase'] = connect_config['passphrase'].get_value()
        
        # Remove non-connection fields
        connect_config.pop('name', None)
        
        self.logger.info(f"Connecting to {config['host']}:{config['port']} as {config['username']}")
        if not client.connect(**connect_config):
            self.logger.error("Connection failed")
            sys.exit(1)
            
        # Clear connection config after use
        if 'password' in connect_config:
            connect_config['password'] = None
            del connect_config['password']
        if 'passphrase' in connect_config:
            connect_config['passphrase'] = None
            del connect_config['passphrase']
            
        result = client.rename(args.old_path, args.new_path)
        client.disconnect()
        
        if result:
            print(f"Renamed '{args.old_path}' to '{args.new_path}' successfully.")
        else:
            print(f"Failed to rename '{args.old_path}'.")
    
    def _handle_server_to_server_secure(self, args):
        """Handle server to server transfer command with secure credential handling."""
        source_config = self._get_connection_config_secure(args, prefix='source_')
        dest_config = self._get_connection_config_secure(args, prefix='dest_')
        
        # Create SFTP client
        client = SFTPClient(logger=self.logger)
        
        # Extract credentials for connection
        source_connect_config = source_config.copy()
        dest_connect_config = dest_config.copy()
        
        # Convert SecureString objects to plain strings for connection
        if 'password' in source_connect_config and isinstance(source_connect_config['password'], SecureString):
            source_connect_config['password'] = source_connect_config['password'].get_value()
        if 'passphrase' in source_connect_config and isinstance(source_connect_config['passphrase'], SecureString):
            source_connect_config['passphrase'] = source_connect_config['passphrase'].get_value()
            
        if 'password' in dest_connect_config and isinstance(dest_connect_config['password'], SecureString):
            dest_connect_config['password'] = dest_connect_config['password'].get_value()
        if 'passphrase' in dest_connect_config and isinstance(dest_connect_config['passphrase'], SecureString):
            dest_connect_config['passphrase'] = dest_connect_config['passphrase'].get_value()
        
        # Remove non-connection fields
        source_connect_config.pop('name', None)
        dest_connect_config.pop('name', None)
        
        # Progress callback for transfer
        def progress(bytes_transferred, total_bytes, percent):
            if not args.quiet:
                sys.stdout.write(f"\rTransferring: {percent:.1f}% ({bytes_transferred/(1024*1024):.2f} MB / {total_bytes/(1024*1024):.2f} MB)")
                sys.stdout.flush()
        
        # Perform server to server transfer
        self.logger.info(f"Starting server-to-server transfer from {args.source_path} to {args.dest_path}")
        result = client.server_to_server_transfer(
            source_connect_config, 
            dest_connect_config, 
            args.source_path, 
            args.dest_path,
            progress_callback=progress
        )
        
        # Clear connection configs after use
        for config in [source_connect_config, dest_connect_config]:
            if 'password' in config:
                config['password'] = None
                del config['password']
            if 'passphrase' in config:
                config['passphrase'] = None
                del config['passphrase']
        
        if result:
            if not args.quiet:
                print("\nServer-to-server transfer completed successfully")
            self.logger.info("Server-to-server transfer completed successfully")
        else:
            if not args.quiet:
                print("\nServer-to-server transfer failed")
            self.logger.error("Server-to-server transfer failed")
            sys.exit(1)
    
    def _handle_list_secure(self, args):
        """Handle list directory command with secure credential handling."""
        config = self._get_connection_config_secure(args)
        
        # Create SFTP client
        client = SFTPClient(logger=self.logger)
        
        # Extract credentials for connection
        connect_config = config.copy()
        
        # Convert SecureString objects to plain strings for connection
        if 'password' in connect_config and isinstance(connect_config['password'], SecureString):
            connect_config['password'] = connect_config['password'].get_value()
        if 'passphrase' in connect_config and isinstance(connect_config['passphrase'], SecureString):
            connect_config['passphrase'] = connect_config['passphrase'].get_value()
        
        # Remove non-connection fields
        connect_config.pop('name', None)
        
        # Connect to server
        self.logger.info(f"Connecting to {config['host']}:{config['port']} as {config['username']}")
        if not client.connect(**connect_config):
            self.logger.error("Connection failed")
            sys.exit(1)
            
        # Clear connection config after use
        if 'password' in connect_config:
            connect_config['password'] = None
            del connect_config['password']
        if 'passphrase' in connect_config:
            connect_config['passphrase'] = None
            del connect_config['passphrase']
            
        # Determine the path to list
        if args.remote_path is None:
            list_path = client.get_home_directory()
            self.logger.info(f"No path specified, using home directory: {list_path}")
        else:
            list_path = args.remote_path
            
        # List directory
        try:
            files = client.list_directory(list_path)
            
            if not args.quiet:
                print(f"Contents of {list_path}:")
                print("{:<40} {:<12} {:<6} {:<20}".format("Name", "Size", "Type", "Modified"))
                print("-" * 80)
                
                for attr in files:
                    name = attr.filename
                    size = attr.st_size
                    ftype = 'dir' if stat.S_ISDIR(attr.st_mode) else 'file'
                    modified = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(attr.st_mtime))
                    if ftype == 'dir':
                        size_str = ""
                    else:
                        if size < 1024:
                            size_str = f"{size} B"
                        elif size < 1024 * 1024:
                            size_str = f"{size/1024:.1f} KB"
                        elif size < 1024 * 1024 * 1024:
                            size_str = f"{size/(1024*1024):.1f} MB"
                        else:
                            size_str = f"{size/(1024*1024*1024):.2f} GB"
                    print("{:<40} {:<12} {:<6} {:<20}".format(
                        name, size_str, ftype, modified))
        except Exception as e:
            self.logger.error(f"Failed to list directory: {str(e)}")
            sys.exit(1)
            
        # Disconnect
        client.disconnect()
    
    def _handle_connection_commands_secure(self, args):
        """Handle connection management commands with secure credential handling."""
        if args.conn_command == 'add':
            self._handle_add_connection_secure(args)
        elif args.conn_command == 'list':
            self._handle_list_connections(args)
        elif args.conn_command == 'remove':
            self._handle_remove_connection(args)
        else:
            self.logger.error("Unknown connection command. Use -h for help.")
            sys.exit(1)
    
    def _handle_add_connection_secure(self, args):
        """Handle adding a connection with secure credential handling."""
        config = self._get_connection_config_secure(args)
        
        # Extract SecureString objects for secure storage
        password = config.pop('password', None)
        passphrase = config.pop('passphrase', None)
        
        # Add name and encryption options
        use_keyring = getattr(args, 'use_keyring', False)
        encrypt = getattr(args, 'encrypt', False)
        
        encryption_password = None
        if encrypt:
            encryption_password = getpass.getpass('Encryption password: ')
        
        # Save connection using secure method
        self.logger.info(f"Saving connection: {args.name}")
        success = self.auth_manager.save_connection_secure(
            name=args.name,
            host=config['host'],
            port=config['port'],
            username=config['username'],
            key_path=config.get('key_path'),
            password=password,
            passphrase=passphrase,
            use_keyring=use_keyring,
            encrypt=encrypt,
            encryption_password=encryption_password
        )
        
        # Clear encryption password
        if encryption_password:
            encryption_password = None
            del encryption_password
        
        if success:
            if not args.quiet:
                print(f"Connection {args.name} saved securely")
            self.logger.info(f"Connection {args.name} saved securely")
        else:
            self.logger.error(f"Failed to save connection {args.name}")
            sys.exit(1)


def main():
    """Entry point for the CLI application."""
    cli_handler = CLIHandler()
    cli_handler.run()
    
if __name__ == "__main__":
    main()
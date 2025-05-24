# FilePilot

A cross-platform SFTP solution with both GUI and CLI interfaces for secure file transfers.

## Features

- **Cross-platform** - Works on Windows, macOS, and Linux
- **Multiple authentication methods**:
  - Password-based authentication
  - Key-based authentication (with and without passphrase)
- **Secure credential handling**:
  - System keyring integration
  - Optional configuration encryption
  - Environment variables support
  - Stdin password input
- **Transfer capabilities**:
  - Local to server transfers
  - Server to server transfers
  - Large file handling with chunked transfers
  - Transfer queue with pause/resume/cancel
- **Dual interface**:
  - User-friendly GUI with file browser
  - Command line interface for scripting and automation

## Installation

### Prerequisites

- Python 3.7 or higher
- pip package manager

### Install from Source

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/filepilot.git
   cd filepilot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install the package:
   ```bash
   pip install -e .
   ```

## Usage

FilePilot can be used in both GUI and CLI modes:

### GUI Mode

Launch the GUI interface by running:

```bash
filepilot
```

Or if installed in development mode:

```bash
python -m filepilot.main
```

The GUI provides:
- Double panel interface (local and remote file browsers)
- Connection management
- Transfer queue with progress monitoring

### CLI Mode

Access the command line interface with:

```bash
filepilot --cli [command] [options]
```

Available commands:

#### Upload files

```bash
filepilot --cli upload [options] local_path remote_path
```

Examples:
```bash
# Using direct credentials
filepilot --cli upload ./myfile.txt /remote/path/myfile.txt --host example.com --username user --password-stdin

# Using key authentication
filepilot --cli upload ./myfile.txt /remote/path/myfile.txt --host example.com --username user --key-file ~/.ssh/id_rsa

# Using saved connection
filepilot --cli upload ./myfile.txt /remote/path/myfile.txt --connection myserver
```

#### Download files

```bash
filepilot --cli download [options] remote_path local_path
```

Example:
```bash
filepilot --cli download /remote/path/file.txt ./downloaded_file.txt --host example.com --username user --password-env SSH_PASSWORD
```

#### Server to server transfer

```bash
filepilot --cli s2s [options] source_path dest_path
```

Example:
```bash
filepilot --cli s2s /source/path/file.txt /dest/path/file.txt --source-connection server1 --dest-connection server2
```

#### List directory contents

```bash
filepilot --cli list [options] [remote_path]
```

Example:
```bash
filepilot --cli list /remote/directory --host example.com --username user --password-stdin
```

#### Connection management

```bash
# Add a connection
filepilot --cli connection add myserver --host example.com --username user --key-file ~/.ssh/id_rsa --use-keyring

# List connections
filepilot --cli connection list

# Remove a connection
filepilot --cli connection remove myserver
```

### Authentication Options

FilePilot supports multiple secure ways to provide credentials:

1. **Direct password** (not recommended):
   ```bash
   --password "your_password"
   ```

2. **Password from stdin** (recommended for interactive use):
   ```bash
   --password-stdin
   ```

3. **Password from environment variable** (recommended for scripts):
   ```bash
   --password-env PASSWORD_VAR
   ```

4. **Key-based authentication**:
   ```bash
   --key-file /path/to/private_key
   ```

5. **Key with passphrase**:
   ```bash
   --key-file /path/to/private_key --passphrase-stdin
   ```

## Development

### Directory Structure

```
filepilot/
├── core/              # Core SFTP implementation
│   ├── sftp_client.py   # SFTP client implementation
│   ├── auth_manager.py  # Authentication handling
│   └── transfer_manager.py # Transfer queue management
├── gui/               # GUI interface
│   └── main_window.py   # PyQt5 GUI implementation
├── cli/               # CLI interface
│   └── cli_handler.py   # Command-line handling
├── utils/             # Utility modules
│   └── logger.py        # Logging configuration
├── config/            # Configuration files
├── logs/              # Log files
└── temp/              # Temporary files for server-to-server transfers
```

### Building & Packaging

To create a distributable package:

```bash
pip install build
python -m build
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

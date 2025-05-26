# FilePilot

A secure, cross-platform SFTP client with both GUI and command-line interfaces.

## Security Features

FilePilot includes several security measures to protect sensitive credentials from memory dump attacks:

### SecureString Implementation
- Passwords and passphrases are encrypted in memory using XOR encryption with random keys
- Sensitive data is automatically cleared when no longer needed
- Memory is overwritten with random data on cleanup
- String representations don't expose actual values

### Secure Credential Storage
- System keyring integration for encrypted credential storage
- Optional configuration file encryption
- Environment variable support for scripting
- Stdin password input to avoid command-line exposure

## Features

- **Cross-platform** - Works on Windows, macOS, and Linux
- **Multiple authentication methods**:
  - Password-based authentication
  - Key-based authentication (with and without passphrase)
- **Secure credential handling**:
  - **Memory-safe password handling** - Credentials are encrypted in memory and cleared after use
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

## Security Best Practices

### Memory Dump Protection
FilePilot uses a `SecureString` class to minimize password exposure in memory dumps:

```python
from code.core.auth_manager import SecureString

# Create secure password wrapper
secure_password = SecureString("my_password")

# Use the password (automatically decrypted when needed)
password_value = secure_password.get_value()

# Clear from memory when done
secure_password.clear()
```

### Recommended Authentication Methods

1. **System Keyring** (Most Secure):
   ```bash
   filepilot connection add myserver --host server.com --username user --use-keyring --password-stdin
   ```

2. **Environment Variables** (For Scripts):
   ```bash
   export SFTP_PASSWORD="your_password"
   filepilot upload file.txt /remote/path --password-env SFTP_PASSWORD
   ```

3. **Interactive Input** (For Manual Use):
   ```bash
   filepilot upload file.txt /remote/path --password-stdin
   ```

### Avoid These Methods
- Direct password on command line: `--password "plaintext"` (visible in process lists)
- Storing passwords in shell scripts without proper protection

## Installation

### Prerequisites
- Python 3.7 or higher
- pip (Python package installer)

### Install from source
```bash
git clone https://github.com/yourusername/filepilot.git
cd filepilot
pip install -e .
```

### Install dependencies
```bash
pip install -r requirements.txt
```

## Usage

### GUI Mode
Launch the graphical interface:
```bash
filepilot-gui
```

### Command Line Mode

#### Upload Files
```bash
# Using saved connection with secure keyring storage
filepilot upload local_file.txt /remote/path/file.txt --connection myserver

# Using environment variable for password
filepilot upload file.txt /remote/path/ --host server.com --username user --password-env SFTP_PASSWORD

# Interactive password input (secure)
filepilot upload file.txt /remote/path/ --host server.com --username user --password-stdin
```

#### Download Files
```bash
# Download with saved connection
filepilot download /remote/file.txt ./local_file.txt --connection myserver

# Download with key-based auth
filepilot download /remote/file.txt ./local_file.txt --host server.com --username user --key-file ~/.ssh/id_rsa
```

#### Server-to-Server Transfer
```bash
filepilot s2s /source/file.txt /dest/file.txt \
  --source-host source.com --source-username user1 --source-password-env SRC_PASS \
  --dest-host dest.com --dest-username user2 --dest-password-env DEST_PASS
```

#### List Remote Directory
```bash
filepilot list /remote/directory --connection myserver
```

### Connection Management

#### Add Secure Connection
```bash
# Add connection with keyring storage (most secure)
filepilot connection add myserver --host server.com --username user --use-keyring --password-stdin

# Add connection with encrypted config file
filepilot connection add myserver --host server.com --username user --encrypt --password-stdin
```

#### List Connections
```bash
filepilot connection list
```

#### Remove Connection
```bash
filepilot connection remove myserver
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

## API Usage

### Secure Credential Handling in Code

```python
from code.core.auth_manager import AuthManager, SecureString

# Initialize auth manager
auth_manager = AuthManager()

# Create secure password
password = SecureString("my_secret_password")

# Save connection securely
auth_manager.save_connection_secure(
    name="myserver",
    host="server.com",
    username="user",
    password=password,  # SecureString object
    use_keyring=True    # Store in system keyring
)

# Retrieve connection with secure credentials
config = auth_manager.get_connection_secure("myserver")
# config['password'] will be a SecureString object

# Use the password safely
if 'password' in config:
    plain_password = config['password'].get_value()
    # Use plain_password for connection
    # Clear when done
    config['password'].clear()
```

## Security Considerations

### Memory Dump Protection
- **Issue**: Plain text passwords in Python strings can appear in memory dumps
- **Solution**: FilePilot's `SecureString` class encrypts passwords in memory and clears them after use
- **Limitation**: Complete protection against memory dumps in Python is limited due to string immutability

### Best Practices
1. Use system keyring storage when possible (`--use-keyring`)
2. Use environment variables for automated scripts
3. Use stdin input for interactive sessions
4. Avoid command-line password arguments
5. Enable config file encryption for additional protection
6. Regularly rotate passwords and SSH keys

### System Requirements for Keyring
- **Windows**: Uses Windows Credential Manager
- **macOS**: Uses Keychain
- **Linux**: Requires python-keyring and a keyring backend (gnome-keyring, kwallet, etc.)

## Configuration

### Config Directory
FilePilot stores configuration in:
- **Windows**: `%APPDATA%\filepilot\config`
- **macOS/Linux**: `~/.config/filepilot/config`

### Encrypted Config
When using `--encrypt`, the connections.json file is encrypted using Fernet (AES 128) with PBKDF2 key derivation.

## Troubleshooting

### Common Issues

1. **Keyring not available**:
   ```
   Error: Keyring backend not found
   ```
   **Solution**: Install a keyring backend for your system or use `--encrypt` instead

2. **Permission denied**:
   ```
   Error: Permission denied (publickey,password)
   ```
   **Solution**: Check username, password, and SSH key permissions

3. **Connection timeout**:
   ```
   Error: Connection timed out
   ```
   **Solution**: Check host, port, and network connectivity

## Development

### Running Tests
```bash
python -m pytest tests/
```

### Building from Source
```bash
python setup.py build
python setup.py install
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Security Reporting

If you discover security vulnerabilities, please report them privately to the maintainers rather than opening public issues.

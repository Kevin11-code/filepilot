#!/bin/bash
# Cross-platform virtual environment setup script for FilePilot
# This script works on Linux, macOS, and Windows (with Git Bash or WSL)
# Specifically targeting Python 3.12

# Detect the OS
case "$(uname -s)" in
    Linux*)     OS="Linux";;
    Darwin*)    OS="macOS";;
    CYGWIN*|MINGW*|MSYS*) OS="Windows";;
    *)          OS="Unknown";;
esac

echo "Detected OS: $OS"
echo "Setting up virtual environment for FilePilot with Python 3.12..."

# Define virtual environment directory
VENV_DIR="venv"

# Check if Python 3.12 is installed
if command -v python3.12 &>/dev/null; then
    PYTHON="python3.12"
elif command -v python3 &>/dev/null; then
    # Check if Python3 is version 3.12
    PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    if [[ "$PY_VERSION" == 3.12* ]]; then
        PYTHON="python3"
    else
        echo "Warning: Python 3.12 not found. Using available Python 3 version: $PY_VERSION"
        echo "For best compatibility, consider installing Python 3.12."
        PYTHON="python3"
    fi
elif command -v python &>/dev/null; then
    # Check if Python is version 3.12
    PY_VERSION=$(python --version 2>&1 | awk '{print $2}')
    if [[ "$PY_VERSION" == 3.12* ]]; then
        PYTHON="python"
    else
        echo "Warning: Python 3.12 not found. Using available Python version: $PY_VERSION"
        # Check if this is at least Python 3
        if [[ "$PY_VERSION" == 3* ]]; then
            echo "For best compatibility, consider installing Python 3.12."
            PYTHON="python"
        else
            echo "Error: Python 3 is required but not found. Please install Python 3.12."
            exit 1
        fi
    fi
else
    echo "Error: Python is not installed. Please install Python 3.12."
    exit 1
fi

echo "Using $PYTHON ($(${PYTHON} --version))"

# Check if pip is installed
if ! ${PYTHON} -m pip --version &>/dev/null; then
    echo "Error: pip is not installed for ${PYTHON}. Please install pip."
    exit 1
fi

# Check for virtualenv
echo "Checking for virtualenv..."
if ! ${PYTHON} -m pip list | grep -q virtualenv; then
    echo "Installing virtualenv..."
    ${PYTHON} -m pip install virtualenv
fi

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR directory with ${PYTHON}..."
    ${PYTHON} -m virtualenv "$VENV_DIR"
else
    echo "Virtual environment already exists in $VENV_DIR."
    echo "To recreate it with Python 3.12, delete the directory first and run this script again."
fi

# Activate the virtual environment and install dependencies
echo "Activating virtual environment and installing dependencies..."

# Source the appropriate activation script based on OS
if [ "$OS" = "Windows" ]; then
    # For Windows
    # Check if we're in Git Bash or similar
    if [ -f "$VENV_DIR/Scripts/activate" ]; then
        source "$VENV_DIR/Scripts/activate" || . "$VENV_DIR/Scripts/activate"
        ACTIVATE_CMD="$VENV_DIR\\Scripts\\activate"
    else
        echo "Error: Unable to find activation script. Make sure you're using Git Bash or WSL on Windows."
        exit 1
    fi
else
    # For Linux and macOS
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate" || . "$VENV_DIR/bin/activate"
        ACTIVATE_CMD="source $VENV_DIR/bin/activate"
    else
        echo "Error: Unable to find activation script."
        exit 1
    fi
fi

# Install requirements
echo "Installing dependencies from requirements.txt..."
${PYTHON} -m pip install -r requirements.txt

# Install package in development mode
echo "Installing FilePilot package in development mode..."
${PYTHON} -m pip install -e .

echo ""
echo "======================================================="
echo "FilePilot virtual environment setup complete with $(python --version)!"
echo "To activate the virtual environment, run:"
echo "  $ACTIVATE_CMD"
echo ""
echo "To run FilePilot with GUI:"
echo "  filepilot"
echo "Or:"
echo "  ${PYTHON} -m filepilot.main"
echo ""
echo "To run FilePilot in CLI mode:"
echo "  filepilot --cli --help"
echo "======================================================="

# Deactivate at the end so user can activate manually
if [[ "$(type -t deactivate)" == "function" ]]; then
    deactivate
fi

# Create a Windows batch file for easier activation on Windows
if [ "$OS" = "Windows" ]; then
    echo "Creating Windows activation script (activate.bat)..."
    echo "@echo off" > activate.bat
    echo "call %~dp0\\$VENV_DIR\\Scripts\\activate.bat" >> activate.bat
    echo "Creating Windows runner script (run_filepilot.bat)..."
    echo "@echo off" > run_filepilot.bat
    echo "call %~dp0\\$VENV_DIR\\Scripts\\activate.bat" >> run_filepilot.bat
    echo "python -m filepilot.main %*" >> run_filepilot.bat
fi
#!/bin/bash

# Configuration
SCRIPT_NAME="code/main.py"
APP_NAME="FilePilot"

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build dist *.spec

# Detect OS
OS="$(uname)"
echo "Detected OS: $OS"

# Build for the detected platform
if [[ "$OS" == "Linux" ]]; then
    echo "Building for Linux..."
    pyinstaller --onefile --name "$APP_NAME" "$SCRIPT_NAME"

elif [[ "$OS" == "Darwin" ]]; then
    echo "Building for macOS..."
    pyinstaller --onefile --name "$APP_NAME" "$SCRIPT_NAME"

elif [[ "$OS" == "MINGW"* || "$OS" == "MSYS"* || "$OS" == "CYGWIN"* ]]; then
    echo "Building for Windows..."
    pyinstaller --onefile --name "$APP_NAME" "$SCRIPT_NAME"

else
    echo "Unsupported OS: $OS"
    exit 1
fi

echo "Build complete! Executable is in the 'dist' folder."

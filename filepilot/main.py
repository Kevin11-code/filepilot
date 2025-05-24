#!/usr/bin/env python3
"""
FilePilot main entry script.
Allows launching either the GUI or CLI interface.
"""
import os
import sys
import argparse

def main():
    """Main entry point for FilePilot"""
    parser = argparse.ArgumentParser(
        description='FilePilot: Cross-platform SFTP Client',
        epilog='Run without arguments to launch the GUI.')
        
    parser.add_argument('--cli', action='store_true',
                      help='Launch in CLI mode (pass --help after --cli for CLI options)')
    
    # Check if the first argument is --cli
    if len(sys.argv) > 1 and sys.argv[1] == '--cli':
        # Remove the --cli argument for the CLI parser
        sys.argv.pop(1)
        # Launch CLI interface
        from filepilot.cli.cli_handler import main as cli_main
        cli_main()
    else:
        # Parse remaining arguments for GUI mode
        args = parser.parse_args()
        
        try:
            # Import GUI dependencies
            from PyQt5.QtWidgets import QApplication
            from filepilot.gui.main_window import MainWindow, run_app
        except ImportError:
            print("Error: PyQt5 is required for the GUI interface.")
            print("Install it with: pip install PyQt5")
            print("Or run FilePilot with --cli for command line interface.")
            sys.exit(1)
            
        # Launch GUI
        run_app()

if __name__ == "__main__":
    main()
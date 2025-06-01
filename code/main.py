"""
FilePilot main entry script.
Allows launching either the GUI or CLI interface.
"""
import os
import sys
import argparse

# Add parent directory to path to help resolve imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

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
        try:
            from code.cli.cli_handler import main as cli_main
        except ImportError:
            # Try relative import if running from within package
            try:
                from cli.cli_handler import main as cli_main
            except ImportError:
                print("Error: Could not import CLI module.")
                import traceback
                traceback.print_exc()
                sys.exit(1)
        cli_main()
    else:
        # Parse remaining arguments for GUI mode
        args = parser.parse_args()
        
        try:
            # Import GUI dependencies
            from PyQt5.QtWidgets import QApplication
            try:
                from code.gui.main_window import MainWindow, run_app
            except ImportError:
                # Try relative import if running from within package
                try:
                    from gui.main_window import MainWindow, run_app
                except ImportError:
                    print("Error: Could not import GUI module.")
                    import traceback
                    traceback.print_exc()
                    sys.exit(1)
        except ImportError:
            print("Error: PyQt5 is required for the GUI interface.")
            print("Install it with: pip install PyQt5")
            print("Or run FilePilot with --cli for command line interface.")
            sys.exit(1)
            
        # Launch GUI
        run_app()

if __name__ == "__main__":
    main()
import os
import sys

def get_resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    :param relative_path: Path relative to the project root (e.g. 'code/resources/icons/back.svg')
    """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller: resources are unpacked to _MEIPASS
        base_path = sys._MEIPASS
        # Remove leading 'code/' if present, since PyInstaller --add-data puts files at root
        if relative_path.startswith('code/'):
            relative_path = relative_path[5:]
        return os.path.join(base_path, relative_path)
    else:
        # Development: relative to this file's location
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', relative_path))
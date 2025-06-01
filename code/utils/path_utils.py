import os
import sys

def get_user_config_path(filename="connections.json"):
    """Return a user-writable config file path for any OS."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        config_dir = os.path.join(base, "FilePilot")
    elif sys.platform == "darwin":
        config_dir = os.path.expanduser("~/Library/Application Support/FilePilot")
    else:
        config_dir = os.path.expanduser("~/.filepilot")
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, filename)
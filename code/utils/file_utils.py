import os
from PyQt5.QtGui import QIcon
import mimetypes

class FileIconProvider:
    """
    Provides icons for different file types based on file extension or mime type.
    Uses icons from the resources directory.
    """
    def __init__(self):
        # Initialize mimetypes database
        mimetypes.init()
        
        # Base path to icons
        self.icons_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'code',
            'resources', 'icons'
        )
        
        # Icons dictionary
        self.icons = {}
        
        # Map of extensions to icon files
        self.extension_map = {
            # Archives
            '.zip': 'archive.svg',
            '.tar': 'archive.svg',
            '.gz': 'archive.svg',
            '.rar': 'archive.svg',
            '.7z': 'archive.svg',
            
            # Audio
            '.mp3': 'audio.svg',
            '.wav': 'audio.svg',
            '.ogg': 'audio.svg',
            '.flac': 'audio.svg',
            
            # Documents
            '.pdf': 'pdf.svg',
            '.doc': 'file.svg',
            '.docx': 'file.svg',
            '.xls': 'file.svg',
            '.xlsx': 'file.svg',
            '.ppt': 'file.svg',
            '.pptx': 'file.svg',
            
            # Executables
            '.exe': 'executable.svg',
            '.bat': 'executable.svg',
            '.sh': 'script.svg',
            '.ps1': 'script.svg',
            
            # Images
            '.jpg': 'image.svg',
            '.jpeg': 'image.svg',
            '.png': 'image.svg',
            '.gif': 'image.svg',
            '.svg': 'image.svg',
            '.bmp': 'image.svg',
            
            # Programming
            '.py': 'python.svg',
            '.js': 'script.svg',
            '.java': 'script.svg',
            '.php': 'script.svg',
            '.cs': 'script.svg',
            '.cpp': 'script.svg',
            '.c': 'script.svg',
            '.h': 'script.svg',
            '.rb': 'script.svg',
            
            # Video
            '.mp4': 'video.svg',
            '.avi': 'video.svg',
            '.mkv': 'video.svg',
            '.mov': 'video.svg',
            '.wmv': 'video.svg',
        }
        
        # Default icons
        self.default_file_icon = os.path.join(self.icons_path, 'file.svg')
        self.folder_icon = os.path.join(self.icons_path, 'folder.svg')
        
    def get_icon_for_file(self, filename):
        """
        Get the appropriate icon for a file based on its extension
        
        Args:
            filename: Name of the file (with extension)
            
        Returns:
            QIcon object for the appropriate file type
        """
        if os.path.isdir(filename):
            return self.get_folder_icon()
            
        # Get file extension
        _, ext = os.path.splitext(filename.lower())
        
        # Check if we have a specific icon for this extension
        if ext in self.extension_map:
            icon_file = self.extension_map[ext]
        else:
            # Try to guess based on mime type
            mime_type, _ = mimetypes.guess_type(filename)
            
            if mime_type:
                category = mime_type.split('/')[0]
                
                if category == 'image':
                    icon_file = 'image.svg'
                elif category == 'audio':
                    icon_file = 'audio.svg'
                elif category == 'video':
                    icon_file = 'video.svg'
                elif category == 'application':
                    if 'compressed' in mime_type or 'zip' in mime_type:
                        icon_file = 'archive.svg'
                    elif 'pdf' in mime_type:
                        icon_file = 'pdf.svg'
                    elif 'executable' in mime_type:
                        icon_file = 'executable.svg'
                    else:
                        icon_file = 'file.svg'
                else:
                    icon_file = 'file.svg'
            else:
                icon_file = 'file.svg'
        
        # Get the full path to the icon
        icon_path = os.path.join(self.icons_path, icon_file)
        
        # Check if icon exists, otherwise use default
        if not os.path.exists(icon_path):
            icon_path = self.default_file_icon
            
        # Cache and return the icon
        if icon_path not in self.icons:
            self.icons[icon_path] = QIcon(icon_path)
            
        return self.icons[icon_path]
        
    def get_folder_icon(self):
        """Get the folder icon"""
        if self.folder_icon not in self.icons:
            self.icons[self.folder_icon] = QIcon(self.folder_icon)
            
        return self.icons[self.folder_icon]
        
    def get_icon_for_mime_type(self, mime_type):
        """
        Get an icon based on mime type
        
        Args:
            mime_type: MIME type string (e.g., 'image/jpeg')
            
        Returns:
            QIcon object for the given mime type
        """
        category = mime_type.split('/')[0]
        
        if category == 'image':
            icon_file = 'image.svg'
        elif category == 'audio':
            icon_file = 'audio.svg'
        elif category == 'video':
            icon_file = 'video.svg'
        elif category == 'application':
            if 'compressed' in mime_type or 'zip' in mime_type:
                icon_file = 'archive.svg'
            elif 'pdf' in mime_type:
                icon_file = 'pdf.svg'
            elif 'executable' in mime_type:
                icon_file = 'executable.svg'
            else:
                icon_file = 'file.svg'
        else:
            icon_file = 'file.svg'
            
        icon_path = os.path.join(self.icons_path, icon_file)
        
        if not os.path.exists(icon_path):
            icon_path = self.default_file_icon
            
        if icon_path not in self.icons:
            self.icons[icon_path] = QIcon(icon_path)
            
        return self.icons[icon_path]
    
    def icon(self, ftype, name):
        """
        Get icon based on file type and name
        
        Args:
            ftype: File type ('dir' or 'file')
            name: File name (for determining extension)
        
        Returns:
            QIcon object for the file type
        """
        if ftype == 'dir':
            return self.get_folder_icon()
        else:
            return self.get_icon_for_file(name)
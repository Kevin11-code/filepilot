from PyQt5.QtWidgets import ( QDialog, QVBoxLayout, QHBoxLayout, 
                           QLabel, QPushButton, QFrame, QWidget, QApplication)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QPoint, QThread, QTimer
from PyQt5.QtGui import QFont, QPixmap, QPainter, QColor, QIcon

class SFTPMessages:
    """Predefined messages for common SFTP scenarios with professional titles and content"""
    
    # Authentication & Connection Messages
    CONNECTION_SUCCESS = ("Connected", "Successfully connected to the server.")
    CONNECTION_FAILED = ("Connection Failed", "Could not connect to the server. Please check your credentials or network.")
    HOST_UNREACHABLE = ("Server Unreachable", "Unable to reach the server. Ensure the address is correct and network is available.")
    INVALID_CREDENTIALS = ("Login Failed", "The username or password you entered is incorrect.")
    CONNECTION_CLOSED = ("Connection Closed", "The connection to the server was closed.")
    
    # File Transfer Messages
    UPLOAD_SUCCESS = ("Upload Complete", "Your file was uploaded successfully.")
    UPLOAD_FAILED = ("Upload Failed", "Something went wrong while uploading. Please try again.")
    DOWNLOAD_SUCCESS = ("Download Complete", "File downloaded successfully.")
    DOWNLOAD_FAILED = ("Download Error", "Unable to download the file. Please check the file path or permissions.")
    TRANSFER_IN_PROGRESS = ("Transferring Files", "Your files are being transferred. This may take a moment.")
    
    # Warning & Error Messages
    FILE_EXISTS = ("File Already Exists", "A file with the same name already exists. Do you want to overwrite it?")
    PERMISSION_DENIED = ("Access Denied", "You don't have permission to access or modify this file.")
    DIRECTORY_NOT_FOUND = ("Invalid Directory", "The selected folder doesn't exist on the server.")
    FILE_TOO_LARGE = ("File Size Limit", "The selected file exceeds the maximum allowed size.")
    TRANSFER_INTERRUPTED = ("Transfer Interrupted", "The file transfer was interrupted. Would you like to retry?")
    
    # Confirmation Dialog Messages
    DELETE_FILE = ("Delete File?", "Are you sure you want to permanently delete this file?")
    DISCONNECT_SERVER = ("Disconnect from Server?", "This will close your current session. Are you sure you want to disconnect?")
    OVERWRITE_FILE = ("Overwrite File?", "This file already exists. Do you want to replace it?")
    EXIT_APPLICATION = ("Exit Application?", "Are you sure you want to close the application? Unsaved changes may be lost.")
    
    # Information Messages
    APP_INFO = ("About This App", "SFTP Client v1.0\nSecure and simple file transfers.")
    NO_CONNECTION = ("No Connection", "You're not connected to any server. Please connect first to proceed.")
    SESSION_EXPIRED = ("Session Expired", "You were disconnected due to inactivity. Please reconnect.")
    
    # Success Messages
    DELETE_SUCCESS = ("Delete Success", "Successfully deleted '{}'.")
    RENAME_SUCCESS = ("Rename Success", "Successfully renamed '{}' to '{}'.")
    
    @staticmethod
    def get_message(message_key):
        """Get a predefined message tuple (title, text) by key"""
        if hasattr(SFTPMessages, message_key):
            return getattr(SFTPMessages, message_key)
        return ("Information", "Message not found")
    
    @staticmethod
    def format_message(message_tuple, *args):
        """Format a message tuple with arguments"""
        title, text = message_tuple
        return title, text.format(*args)

class CustomMessageBox(QDialog):
    """
    Modern minimalist message box with drag functionality
    """
    
    # Message box types
    Information = 1
    Warning = 2
    Critical = 3
    Question = 4
    
    # Standard buttons
    Ok = 1024
    Cancel = 4194304
    Yes = 16384
    No = 65536
    
    def __init__(self, parent=None, message_type=1):
        super().__init__(parent)
        self.message_type = message_type
        self.result_value = 4194304  # Cancel
        self.drag_position = QPoint()
        self.setup_ui()
        self.apply_modern_style()
        
    def setup_ui(self):
        """Setup the modern minimalist UI structure"""
        self.setModal(True)
        self.setFixedSize(400, 160)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Main container with shadow effect
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(0)
        
        # Content container with rounded background
        self.content_frame = QFrame()
        self.content_frame.setObjectName("contentFrame")
        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Title bar for dragging
        self.title_bar = QFrame()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(40)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(20, 0, 20, 0)
        
        # Icon and title
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setAlignment(Qt.AlignCenter)
        
        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        title_layout.addWidget(self.icon_label)
        title_layout.addSpacing(8)
        title_layout.addWidget(self.title_label, 1)
        
        # Message area
        message_frame = QFrame()
        message_frame.setObjectName("messageFrame")
        message_layout = QVBoxLayout(message_frame)
        message_layout.setContentsMargins(20, 15, 20, 20)
        
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.message_label.setMinimumHeight(30)
        message_layout.addWidget(self.message_label)
        
        # Button area
        button_frame = QFrame()
        button_frame.setObjectName("buttonFrame")
        self.button_layout = QHBoxLayout(button_frame)
        self.button_layout.setContentsMargins(20, 0, 20, 20)
        self.button_layout.setSpacing(12)
        self.button_layout.addStretch()
        
        # Add all frames to content
        content_layout.addWidget(self.title_bar)
        content_layout.addWidget(message_frame, 1)
        content_layout.addWidget(button_frame)
        
        main_layout.addWidget(self.content_frame)
        
    def apply_modern_style(self):
        """Apply minimalist black and white styling"""
        self.setStyleSheet("""
            QFrame#contentFrame {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
            QFrame#titleBar {
                background-color: transparent;
                border: none;
                border-bottom: 1px solid #f0f0f0;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QFrame#messageFrame {
                background-color: transparent;
                border: none;
            }
            QFrame#buttonFrame {
                background-color: transparent;
                border: none;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            QLabel {
                background-color: transparent;
                border: none;
                color: #000000;
            }
        """)
        
        # Clean minimalist typography
        title_font = QFont("Inter", 11, QFont.DemiBold)
        if not title_font.exactMatch():
            title_font = QFont("Segoe UI", 11, QFont.DemiBold)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("color: #000000; font-weight: 600;")
        
        message_font = QFont("Inter", 10, QFont.Normal)
        if not message_font.exactMatch():
            message_font = QFont("Segoe UI", 10, QFont.Normal)
        self.message_label.setFont(message_font)
        self.message_label.setStyleSheet("color: #333333; line-height: 1.4;")
        
    def set_icon_and_title(self):
        """Set minimalist icons based on message type, but keep the custom title"""
        if self.message_type == self.Information:
            self.set_modern_icon("ⓘ", "#000000")
            # Don't override the title - it's already set from the message
        elif self.message_type == self.Warning:
            self.set_modern_icon("⚠", "#666666")
            # Don't override the title - it's already set from the message
        elif self.message_type == self.Critical:
            self.set_modern_icon("✕", "#000000")
            # Don't override the title - it's already set from the message
        elif self.message_type == self.Question:
            self.set_modern_icon("?", "#000000")
            # Don't override the title - it's already set from the message
            
    def set_modern_icon(self, text, color):
        """Set modern circular icon with background"""
        self.icon_label.setText(text)
        self.icon_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-size: 14px;
                font-weight: 600;
                background-color: {color}15;
                border: 2px solid {color}30;
                border-radius: 10px;
                padding: 0px;
            }}
        """)
        
    def add_button(self, text, button_role, is_default=False):
        """Add minimalist black and white styled buttons"""
        button = QPushButton(text)
        button.setFixedSize(76, 32)
        button.setCursor(Qt.PointingHandCursor)
        
        if is_default:
            # Primary button with black background
            button.setStyleSheet("""
                QPushButton {
                    background-color: #000000;
                    color: #ffffff;
                    border: none;
                    border-radius: 4px;
                    font-weight: 500;
                    font-size: 10px;
                    padding: 0;
                }
                QPushButton:hover {
                    background-color: #333333;
                }
                QPushButton:pressed {
                    background-color: #1a1a1a;
                }
            """)
        else:
            # Secondary button with white background and black border
            button.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff;
                    color: #000000;
                    border: 1px solid #d0d0d0;
                    border-radius: 4px;
                    font-weight: 500;
                    font-size: 10px;
                    padding: 0;
                }
                QPushButton:hover {
                    background-color: #f5f5f5;
                    border-color: #b0b0b0;
                }
                QPushButton:pressed {
                    background-color: #e0e0e0;
                    border-color: #a0a0a0;
                }
            """)
        
        # Connect button click
        button.clicked.connect(lambda: self.done_with_result(button_role))
        self.button_layout.addWidget(button)
        return button
        
    def done_with_result(self, result):
        """Close dialog with animation"""
        self.result_value = result
        self.fade_out()
        
    def fade_out(self):
        """Smooth fade out animation"""
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(150)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.finished.connect(self.accept)
        self.animation.start()
        
    def showEvent(self, event):
        """Override show event with entrance animation"""
        super().showEvent(event)
        self.center_on_parent()
        self.fade_in()
        
    def center_on_parent(self):
        """Always center dialog on the screen"""
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
            
    def fade_in(self):
        """Smooth fade in animation"""
        self.setWindowOpacity(0.0)
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(200)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.start()
        
    def mousePressEvent(self, event):
        """Enable dragging from title bar"""
        if event.button() == Qt.LeftButton:
            # Check if click is in title bar area
            title_bar_rect = self.title_bar.geometry()
            if title_bar_rect.contains(event.pos()):
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
                self.title_bar.setStyleSheet("""
                    QFrame#titleBar {
                        background-color: #f0f0f0;
                        border: none;
                        border-bottom: 1px solid #d0d0d0;
                        border-top-left-radius: 8px;
                        border-top-right-radius: 8px;
                    }
                """)
        super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event):
        """Handle dragging"""
        if event.buttons() == Qt.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPos() - self.drag_position)
            event.accept()
        super().mouseMoveEvent(event)
        
    def mouseReleaseEvent(self, event):
        """Reset title bar styling after drag"""
        if event.button() == Qt.LeftButton:
            self.drag_position = QPoint()
            self.title_bar.setStyleSheet("""
                QFrame#titleBar {
                    background-color: transparent;
                    border: none;
                    border-bottom: 1px solid #f0f0f0;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                }
            """)
        super().mouseReleaseEvent(event)

    @staticmethod
    def information(parent, title, text, buttons=None):
        """Show information message box"""
        if buttons is None:
            buttons = CustomMessageBox.Ok
        return CustomMessageBox._show_message(parent, title, text, CustomMessageBox.Information, buttons)
    
    @staticmethod
    def warning(parent, title, text, buttons=None):
        """Show warning message box"""
        if buttons is None:
            buttons = CustomMessageBox.Ok
        return CustomMessageBox._show_message(parent, title, text, CustomMessageBox.Warning, buttons)
    
    @staticmethod
    def critical(parent, title, text, buttons=None):
        """Show critical/error message box"""
        if buttons is None:
            buttons = CustomMessageBox.Ok
        return CustomMessageBox._show_message(parent, title, text, CustomMessageBox.Critical, buttons)
    
    @staticmethod
    def question(parent, title, text, buttons=None, default_button=None):
        """Show question message box"""
        if buttons is None:
            buttons = CustomMessageBox.Yes | CustomMessageBox.No
        return CustomMessageBox._show_message(parent, title, text, CustomMessageBox.Question, buttons, default_button)
    
    @staticmethod
    def about(parent, title, text):
        """Show about message box"""
        return CustomMessageBox._show_message(parent, title, text, CustomMessageBox.Information, CustomMessageBox.Ok)
    
    @staticmethod
    def _show_message(parent, title, text, message_type, buttons, default_button=None):
        """Internal method to show message box"""
        dialog = CustomMessageBox(parent, message_type)
        dialog.setWindowTitle(title)
        dialog.title_label.setText(title)  # Set the meaningful title here
        dialog.set_icon_and_title()
        dialog.message_label.setText(text)
        
        # Add buttons based on the buttons parameter
        if buttons & CustomMessageBox.Ok:
            is_default = default_button == CustomMessageBox.Ok or default_button is None
            dialog.add_button("OK", CustomMessageBox.Ok, is_default)
        if buttons & CustomMessageBox.Cancel:
            is_default = default_button == CustomMessageBox.Cancel
            dialog.add_button("Cancel", CustomMessageBox.Cancel, is_default)
        if buttons & CustomMessageBox.Yes:
            is_default = default_button == CustomMessageBox.Yes
            dialog.add_button("Yes", CustomMessageBox.Yes, is_default)
        if buttons & CustomMessageBox.No:
            is_default = default_button == CustomMessageBox.No or (default_button is None and message_type == CustomMessageBox.Question)
            dialog.add_button("No", CustomMessageBox.No, is_default)
        
        # Show dialog and return result
        if dialog.exec_() == QDialog.Accepted:
            return dialog.result_value
        else:
            return CustomMessageBox.Cancel
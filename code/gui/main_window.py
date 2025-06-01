import os
import sys
import time
import threading

from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTabWidget, QFileDialog, QTreeView, 
    QHeaderView, QAbstractItemView, QProgressBar, QMenu, QAction, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QSplitter, QFrame, QInputDialog, QStyle, QStackedWidget,
    QPlainTextEdit, QSplashScreen
)

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QModelIndex, QSize, QSettings, QObject
from PyQt5.QtGui import QIcon, QStandardItemModel, QStandardItem, QFont, QPixmap, QColor, QPainter

from code.core.auth_manager import AuthManager
from code.core.transfer_manager import TransferManager, TransferType
from code.core.sftp_client import SFTPClient
from code.utils.logger import LoggerSetup
from code.gui.conn_dialog import ConnectionDialog
from code.gui.file_panel import FilePanel
from code.gui.transfer_panel import TransferPanel
from code.gui.conn_manager import ConnectionManagerDialog
from code.gui.custom_message_box import CustomMessageBox, SFTPMessages
from code.gui.server_to_server_panel import ServerToServerPanel, LocalToServerPanel

from code.utils.file_utils import FileIconProvider
    
class ThreadSafeOverwriteHandler(QObject):
    """
    Thread-safe handler for overwrite dialogs to prevent Qt threading violations.
    All dialog operations are queued and executed on the main thread.
    """
    overwriteRequested = pyqtSignal(str, str, int)  # file_path, dialog_type, request_id

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.pending_requests = {}
        self.request_counter = 0
        self.dialog_lock = threading.Lock()
        self.overwriteRequested.connect(self._handle_overwrite_dialog)

    def request_overwrite_confirmation(self, file_path, dialog_type="upload"):
        """
        Thread-safe method to request overwrite confirmation.
        Returns True/False for overwrite decision.
        """
        # Generate unique request ID
        with self.dialog_lock:
            request_id = self.request_counter
            self.request_counter += 1

            # Create event to wait for response
            response_event = threading.Event()
            self.pending_requests[request_id] = {
                'event': response_event,
                'result': False
            }

        # Emit signal to main thread (will be processed asynchronously)
        self.overwriteRequested.emit(file_path, dialog_type, request_id)

        # Wait for response with timeout to prevent deadlocks
        if response_event.wait(timeout=30):  # 30 second timeout
            with self.dialog_lock:
                result = self.pending_requests[request_id]['result']
                del self.pending_requests[request_id]
            return result
        else:
            # Timeout - cleanup and return False
            with self.dialog_lock:
                if request_id in self.pending_requests:
                    del self.pending_requests[request_id]
            return False

    def _handle_overwrite_dialog(self, file_path, dialog_type, request_id):
        """Handle overwrite dialog on main thread"""
        try:
            # Ensure we're on main thread
            if QThread.currentThread() != QApplication.instance().thread():
                QTimer.singleShot(0, lambda: self._handle_overwrite_dialog(file_path, dialog_type, request_id))
                return

            # Check if application is closing
            if not QApplication.instance() or QApplication.instance().closingDown():
                self._complete_request(request_id, False)
                return

            # Show dialog based on type
            file_name = os.path.basename(file_path)

            if dialog_type == "upload":
                title = "Overwrite Remote File?"
                message = (f"The file '{file_name}' already exists on the remote server.\n\n"
                          f"Remote path: {file_path}\n\n"
                          "Do you want to overwrite it?")
            elif dialog_type == "download":
                title = "Overwrite Local File?"
                message = (f"The file '{file_name}' already exists locally.\n\n"
                          f"Local path: {file_path}\n\n"
                          "Do you want to overwrite it?")
            else:  # server_to_server
                title = "Overwrite File?"
                message = (f"The file '{file_name}' already exists at the destination.\n\n"
                          f"Destination path: {file_path}\n\n"
                          "Do you want to overwrite it?")

            # Show dialog with proper parent and flags
            reply = CustomMessageBox.question(
                self.parent, title, message,
                CustomMessageBox.Yes | CustomMessageBox.No, 
                CustomMessageBox.No
            )

            result = (reply == CustomMessageBox.Yes)
            self._complete_request(request_id, result)

        except Exception as e:
            # Log error and return False
            if hasattr(self.parent, 'logger'):
                self.parent.logger.error(f"Error in overwrite dialog: {str(e)}")
            self._complete_request(request_id, False)

    def _complete_request(self, request_id, result):
        """Complete the overwrite request with the given result"""
        with self.dialog_lock:
            if request_id in self.pending_requests:
                self.pending_requests[request_id]['result'] = result
                self.pending_requests[request_id]['event'].set()


class TransferSignalBridge(QObject):
    """
    Bridge class to safely emit signals from transfer worker threads to the UI thread.
    Solves the QObject timer thread issues by ensuring all Qt operations happen on the main thread.
    """
    # Define a signal that will be emitted when transfer progress updates
    # Use string identifier instead of object reference to avoid Qt threading violations
    progressUpdated = pyqtSignal(int, int, int, TransferType, str)
    
    def __init__(self):
        super().__init__()
        
    def update_progress(self, transfer_id: int, bytes_transferred: int, total_bytes: int,
                        transfer_type: TransferType = TransferType.DOWNLOAD, destination_panel_id: str = None):
        """
        This method is called from worker threads, but safely emits a signal
        that will be processed on the main Qt thread.
        Uses string identifiers instead of object references to avoid threading violations.
        """
        self.progressUpdated.emit(transfer_id, bytes_transferred, total_bytes, transfer_type, destination_panel_id)


class FileChunkSizeDialog(QDialog):
    def __init__(self, parent=None, transfer_manager: TransferManager =None, settings: QSettings = None):
        super().__init__(parent)
        self.transfer_manager = transfer_manager
        self.settings = settings
        self.setWindowTitle("File Chunk Size")
        self.setMinimumWidth(320)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                border: 1px solid #ddd;
                font-family: 'Segoe UI', 'Inter', 'Roboto', sans-serif;
                font-size: 10pt;
            }
            QLabel {
                font-weight: 500;
                color: #333;
            }
            QComboBox {
                padding: 4px 8px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: #fdfdfd;
                min-width: 80px;
            }
            QComboBox::drop-down {
                width: 20px;
                border-left: 1px solid #ccc;
            }
            QDialogButtonBox QPushButton {
                padding: 6px 16px;
                border-radius: 4px;
                background-color: #333333;
                color: white;
                font-weight: 500;
            }
            QDialogButtonBox QPushButton:disabled {
                background-color: #ccc;
                color: #eee;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Input layout
        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)

        label = QLabel("File Chunk Size:")
        self.size_input = QComboBox()
        self.unit_input = QComboBox()
        self.unit_input.addItems(["KB", "MB"])
        self.unit_input.currentTextChanged.connect(self.update_size_options)

        input_layout.addWidget(label)
        input_layout.addWidget(self.size_input)
        input_layout.addWidget(self.unit_input)

        layout.addLayout(input_layout)

        # Dialog buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.setLayout(layout)
        self.load_values()

    def update_size_options(self):
        unit = self.unit_input.currentText()
        self.size_input.clear()
        if unit == "KB":
            self.size_input.addItems(["128", "256", "512"])
        else:
            self.size_input.addItems(["1", "2", "5", "10", "15", "20", "50", "100"])

    def load_values(self):
        chunk_size_bytes = self.settings.value("chunk_size_bytes", 1024 * 1024, type=int)
        if chunk_size_bytes >= 1024 * 1024:
            self.unit_input.setCurrentText("MB")
            size_val = chunk_size_bytes // (1024 * 1024)
        else:
            self.unit_input.setCurrentText("KB")
            size_val = chunk_size_bytes // 1024

        self.update_size_options()
        index = self.size_input.findText(str(size_val))
        if index != -1:
            self.size_input.setCurrentIndex(index)

    def accept(self):
        size = int(self.size_input.currentText())
        unit = self.unit_input.currentText()
        chunk_size_bytes = size * 1024 if unit == "KB" else size * 1024 * 1024
        self.settings.setValue("chunk_size_bytes", chunk_size_bytes)
        self.transfer_manager.set_file_chunk_size_in_bytes(chunk_size_bytes)
        super().accept()


class MainWindow(QMainWindow):
    """Main application window for the SFTP client"""
    
    def __init__(self):
        super().__init__()
        self.auth_manager = AuthManager()
        
        # Initialize logger first
        self.setup_logger()
        
        self.icon_provider = FileIconProvider()
        
        # Pass logger to transfer manager
        self.transfer_manager = TransferManager(logger=self.logger)
        self.sftp_client = None
        
        # Dictionary to track downloads and their destination paths
        self.active_downloads = {} # For local downloads
        # New: Dictionary to track uploads for refresh purposes (not strictly needed with panel ref, but good for consistency)
        self.active_uploads = {} 
        
        # Create and initialize the signal bridge for thread-safe UI updates
        self.signal_bridge = TransferSignalBridge()
        self.signal_bridge.progressUpdated.connect(self.on_transfer_progress) #
        
        # Add throttling mechanism for UI updates to prevent race conditions
        self._update_throttle_timer = QTimer()
        self._update_throttle_timer.setSingleShot(True)
        self._update_throttle_timer.timeout.connect(self._perform_throttled_updates)
        self._pending_refresh_panels = set()
        self._pending_transfer_update = False
        self._update_lock = threading.Lock()
        
        # Initialize panels (will be added to stacked widget)
        self.local_panel = FilePanel(parent=self, is_remote=False)
        self.remote_panel = FilePanel(parent=self, is_remote=True)
        self.server_to_server_panel = ServerToServerPanel(
            parent=self,
            auth_manager=self.auth_manager,
            transfer_manager=self.transfer_manager,
            signal_bridge=self.signal_bridge
        )

        # Load settings
        self.settings = QSettings("FilePilot", "FilePilotSFTPClient")
        self.load_settings()

        self.current_mode = "local_to_server" # Initial mode

        self.setup_ui()
        
        # Start transfer manager
        self.transfer_manager.start()
    
    def setup_logger(self):
        """Set up the application logger"""
        log_file = os.path.join(os.path.dirname(__file__), "..", "logs", "filepilot.log")
        self.logger = LoggerSetup.setup_logger(
            name="filepilot",
            log_file=log_file,
            log_to_console=True
        )
    
    def setup_ui(self):
        """Set up the main window UI"""
        self.setWindowTitle("FilePilot SFTP Client")
        self.setMinimumSize(1000, 600)
        
        # Set application style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QSplitter::handle {
                background-color: #e5e5e5;
                height: 1px;
                width: 1px;
            }
            QFrame[frameShape="4"],
            QFrame[frameShape="5"] {
                background-color: #e5e5e5;
                max-width: 1px;
                max-height: 1px;
                border: none;
            }
            QStatusBar {
                background-color: #f0f0f0;
                border-top: 1px solid #ddd;
                padding: 2px;
                color: #333;
            }
            QMenuBar {
                background-color: #f0f0f0;
                border-bottom: 1px solid #ddd;
            }
            QMenuBar::item {
                padding: 5px 10px;
                margin: 0px;
                background-color: transparent;
            }
            QMenuBar::item:selected {
                background-color: #e0e0e0;
                border-radius: 2px;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                padding: 5px;
            }
            QMenu::item {
                padding: 5px 25px 5px 30px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #5c9eff;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background-color: #dddddd;
                margin: 4px 0px;
            }
            CustomMessageBox {
                background-color: #ffffff;
            }
            
            /* Modern thin scrollbar styling */
            QScrollBar:vertical {
                border: none;
                background: #f5f5f5;
                width: 6px;
                margin: 0px;
            }
            
            QScrollBar::handle:vertical {
                background: #c1c1c1;
                min-height: 20px;
                border-radius: 3px;
            }
            
            QScrollBar::handle:vertical:hover {
                background: #a8a8a8;
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            
            QScrollBar:horizontal {
                border: none;
                background: #f5f5f5;
                height: 6px;
                margin: 0px;
            }
            
            QScrollBar::handle:horizontal {
                background: #c1c1c1;
                min-width: 20px;
                border-radius: 3px;
            }
            
            QScrollBar::handle:horizontal:hover {
                background: #a8a8a8;
            }
            
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                background: none;
            }
            
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)
        
        # Central widget
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)

        # --- Activity Panel (logs) ---
        self.activity_view = QPlainTextEdit()
        self.activity_view.setReadOnly(True)
        self.activity_view.setPlaceholderText("Activity log will appear here...")
        self.activity_view.setStyleSheet("""
            QPlainTextEdit {
                background-color: #fafafa;
                color: #2d3748;
                font-family: 'SF Mono', 'Monaco', 'Cascadia Code', 'Consolas', 'monospace';
                font-size: 11px;
                border: 1px solid #e2e8f0;
                padding: 4px;
                line-height: 1.3;
                border-radius: 3px;
            }
            
            QPlainTextEdit::selection {
                background-color: #bee3f8;
                color: #2d3748;
            }
            
            /* Ensure scrollbars in activity view match the modern thin style */
            QScrollBar:vertical {
                border: none;
                background: #f7fafc;
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            
            QScrollBar::handle:vertical {
                background: #cbd5e0;
                min-height: 20px;
                border-radius: 3px;
            }
            
            QScrollBar::handle:vertical:hover {
                background: #a0aec0;
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            
            QScrollBar:horizontal {
                border: none;
                background: #f7fafc;
                height: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            
            QScrollBar::handle:horizontal {
                background: #cbd5e0;
                min-width: 20px;
                border-radius: 3px;
            }
            
            QScrollBar::handle:horizontal:hover {
                background: #a0aec0;
            }
            
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                background: none;
            }
            
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)
        
        # Initialize activity tracking
        self._activity_log_last_pos = 0
        self._shown_activities = set()  # Track unique activities to avoid duplicates
        self._session_start_time = time.time()
        
        log_path = os.path.join(os.path.dirname(__file__), "..", "logs", "filepilot.log")
        log_path = os.path.abspath(log_path)
        try:
            with open(log_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                self._activity_log_last_pos = f.tell()
        except Exception:
            self._activity_log_last_pos = 0

        self.activity_timer = QTimer(self)
        self.activity_timer.timeout.connect(self.update_activity_view)
        self.activity_timer.start(2000)  # Check every 2 seconds instead of 1

        # --- Splitter for activity panel and main content ---
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.setHandleWidth(6)
        main_splitter.addWidget(self.activity_view)
        
        # Split view with file panels and transfer panel
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(6)  # Wider handle for easier resizing
        
        # --- Use the new LocalToServerPanel class instead of manual layout ---
        self.local_to_server_widget = LocalToServerPanel(
            parent=self,
            local_panel=self.local_panel,
            remote_panel=self.remote_panel
        )

        # Connect item selection signals for local-to-server mode
        self.local_panel.itemSelected.connect(self.local_item_selected)
        self.remote_panel.itemSelected.connect(self.remote_item_selected)

        # Create a container widget with transfer mode
        transfer_container = QWidget()
        transfer_container_layout = QVBoxLayout(transfer_container)
        transfer_container_layout.setContentsMargins(0, 0, 0, 0)
        transfer_container_layout.setSpacing(0)
        
        # --- Stacked Widget for different transfer modes ---
        self.transfer_mode_stacked_widget = QStackedWidget()
        self.transfer_mode_stacked_widget.addWidget(self.local_to_server_widget) # Index 0: Local to Server
        self.transfer_mode_stacked_widget.addWidget(self.server_to_server_panel) # Index 1: Server to Server
        transfer_container_layout.addWidget(self.transfer_mode_stacked_widget)

        # Set initial view
        self.transfer_mode_stacked_widget.setCurrentIndex(0) #
        
        # Add the container to the main splitter
        splitter.addWidget(transfer_container) #
        
        # Transfer panel
        self.transfer_panel = TransferPanel(transfer_manager=self.transfer_manager)
        splitter.addWidget(self.transfer_panel)
        
        # Set initial sizes
        splitter.setSizes([400, 200]) #
        
        main_splitter.addWidget(splitter)  # 'splitter' is your main content (file panels, transfer panel, etc.)

        # Set initial sizes: [activity panel height, rest of window]
        main_splitter.setSizes([80, 600])

        main_layout.addWidget(main_splitter)
        
        # Status bar with modern styling
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready") #
        
        # Set central widget
        self.setCentralWidget(central_widget) #
        
        # Create menu bar
        self.create_menus()
        
        # Initialize the local panel with home directory
        self.local_panel.load_directory(os.path.expanduser('~')) #
        
        # Set application font with modern typography
        self.setup_modern_fonts()
        
        # Initialize thread-safe overwrite handler
        self.overwrite_handler = ThreadSafeOverwriteHandler(self)

    def setup_modern_fonts(self):
        """Configure modern fonts for the application"""
        # Set up the main application font with fallbacks
        main_font = QFont()
        
        # Try to use system fonts in order of preference with better detection
        font_families = [
            "Inter",         # Modern web/UI font if available
            "-apple-system", # macOS system font
            "BlinkMacSystemFont", # Alternative macOS system font
            "Segoe UI",      # Windows 10/11 system font
            "Roboto",        # Android/Material Design
            "Oxygen",        # KDE Plasma font
            "Ubuntu",        # Ubuntu system font
            "Cantarell",     # GNOME system font
            "Fira Sans",     # Mozilla's font
            "Droid Sans",    # Alternative Android font
            "Helvetica Neue", # Modern Helvetica
            "sans-serif"     # Generic fallback
        ]
        
        # Find the first available font with better matching
        selected_font = "sans-serif"  # fallback
        for font_family in font_families:
            test_font = QFont(font_family)
            if test_font.exactMatch() or font_family in ["sans-serif", "-apple-system", "BlinkMacSystemFont"]:
                selected_font = font_family
                break
        
        # Configure main font properties with better settings
        main_font.setFamily(selected_font)
        main_font.setPointSize(10)  # Optimal size for readability
        main_font.setWeight(QFont.Normal)
        main_font.setStyleHint(QFont.SansSerif)
        main_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        main_font.setHintingPreference(QFont.PreferFullHinting)
        
        # Set as the default application font
        QApplication.setFont(main_font)
        
        # Configure specific fonts for different UI elements
        self.setup_ui_specific_fonts()
        
    def setup_ui_specific_fonts(self):
        """Setup fonts for specific UI elements with better typography"""
        # Header font for labels and important text
        self.header_font = QFont()
        header_families = ["Inter", "Segoe UI", "SF Pro Display", "Roboto", "Ubuntu", "sans-serif"]
        for font_family in header_families:
            self.header_font.setFamily(font_family)
            if self.header_font.exactMatch() or font_family == "sans-serif":
                break
        self.header_font.setPointSize(12)
        self.header_font.setWeight(QFont.DemiBold)
        self.header_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        
        # Monospace font for file paths and technical data
        self.mono_font = QFont()
        mono_families = [
            "JetBrains Mono",     # Modern coding font
            "SF Mono",            # macOS monospace
            "Cascadia Code",      # Windows Terminal font
            "Fira Code",          # Popular coding font
            "Source Code Pro",    # Adobe's coding font
            "Consolas",           # Windows monospace
            "Monaco",             # macOS fallback
            "Menlo",              # macOS alternative
            "Ubuntu Mono",        # Ubuntu monospace
            "DejaVu Sans Mono",   # Linux fallback
            "Liberation Mono",    # Open source alternative
            "monospace"           # Generic fallback
        ]
        
        for font_family in mono_families:
            self.mono_font.setFamily(font_family)
            if self.mono_font.exactMatch() or font_family == "monospace":
                break
        self.mono_font.setPointSize(9)
        self.mono_font.setWeight(QFont.Normal)
        self.mono_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        
        # Small font for status and secondary information
        self.small_font = QFont()
        small_families = ["Inter", "Segoe UI", "SF Pro Text", "Roboto", "Ubuntu", "sans-serif"]
        for font_family in small_families:
            self.small_font.setFamily(font_family)
            if self.small_font.exactMatch() or font_family == "sans-serif":
                break
        self.small_font.setPointSize(9)
        self.small_font.setWeight(QFont.Normal)
        self.small_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        
        # Button font for better button typography
        self.button_font = QFont()
        button_families = ["Inter", "Segoe UI", "SF Pro Text", "Roboto Medium", "Ubuntu", "sans-serif"]
        for font_family in button_families:
            self.button_font.setFamily(font_family)
            if self.button_font.exactMatch() or font_family == "sans-serif":
                break
        self.button_font.setPointSize(10)
        self.button_font.setWeight(QFont.Medium)
        self.button_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
        
    def create_menus(self):
        """Create the application menu bar with icons"""
        # File menu
        file_menu = self.menuBar().addMenu("File") #
        
        new_conn_action = QAction(self.style().standardIcon(QStyle.SP_ComputerIcon),
                                 "New Connection...", self)
        new_conn_action.triggered.connect(self.new_connection)
        file_menu.addAction(new_conn_action) #
        
        manage_conn_action = QAction(self.style().standardIcon(QStyle.SP_FileDialogListView),
                                    "Manage Connections...", self)
        manage_conn_action.triggered.connect(self.manage_connections)
        file_menu.addAction(manage_conn_action) #
        
        file_menu.addSeparator() #
        
        exit_action = QAction(self.style().standardIcon(QStyle.SP_DialogCloseButton), 
                             "Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action) #
        
        # Transfer menu
        transfer_menu = self.menuBar().addMenu("Transfer") #
        
        upload_action = QAction(self.style().standardIcon(QStyle.SP_ArrowUp), 
                               "Upload...", self)
        upload_action.triggered.connect(self.upload_file)
        transfer_menu.addAction(upload_action) #
        
        download_action = QAction(self.style().standardIcon(QStyle.SP_ArrowDown),
                                 "Download...", self)
        download_action.triggered.connect(self.download_file)
        transfer_menu.addAction(download_action) #
        
        # Toggle Server to Server / Local to Server action
        self.toggle_transfer_mode_action = QAction(
            self.style().standardIcon(QStyle.SP_DirLinkIcon),
            "Server to Server Transfer", self) # Initial text for switching TO S2S
        self.toggle_transfer_mode_action.triggered.connect(self.toggle_transfer_mode)
        transfer_menu.addAction(self.toggle_transfer_mode_action) #
        
        # Settings menu
        settings_menu = self.menuBar().addMenu("Settings")
        settings_action = QAction(self.icon_provider.get_settings_icon(), "Change file chunk size", self) 
        settings_action.triggered.connect(self.show_chunk_size_dialog)
        settings_menu.addAction(settings_action)

        # Help menu
        help_menu = self.menuBar().addMenu("Help") #
        
        about_action = QAction(self.style().standardIcon(QStyle.SP_DialogHelpButton),
                              "About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action) #
        
        # Restore the window geometry if available
        self.restore_geometry() #
    
    def load_settings(self):
        """Loads application settings from QSettings and applies them."""

        # Load chunk size (stored in bytes)
        # Ensure the key "chunk_size_bytes" is used, consistent with SettingsDialog
        
        chunk_size_bytes = self.settings.value("chunk_size_bytes", 1024*1024, type=int)
        
        if self.transfer_manager: # Ensure manager exists before setting
            self.transfer_manager.set_file_chunk_size_in_bytes(chunk_size_bytes)
            # self.logger.info(f"Loaded default chunk size: {chunk_size_bytes} bytes")
        else:
            self.logger.warning("Transfer manager not initialized during settings load. Chunk size defaults to 1MB.")

        # You might also want to call apply_settings_to_managers here if it's meant to apply all loaded settings
        # self.apply_settings_to_managers()

    def show_chunk_size_dialog(self):
        dialog = FileChunkSizeDialog(self, transfer_manager=self.transfer_manager, settings = self.settings)
        if dialog.exec_() == QDialog.Accepted:
            if self.transfer_manager:
                CustomMessageBox.information(self, "Settings Saved", "File chunk size updated.")
            else:
                CustomMessageBox.warning(self, "Error", "Transfer manager not initialized.")
                
    def closeEvent(self, event):
        """Handle window close event with enhanced cleanup for transfer safety"""
        # Save the window geometry
        self.save_geometry()
        
        # Stop the throttle timer to prevent any pending UI updates
        try:
            if hasattr(self, '_update_throttle_timer'):
                self._update_throttle_timer.stop()
        except Exception as timer_error:
            self.logger.error(f"Error stopping throttle timer: {str(timer_error)}")
        
        # Cancel all active transfers before disconnecting to prevent segfaults
        try:
            if self.transfer_manager:
                active_transfers = self.transfer_manager.get_all_transfers().get('active', [])
                for transfer in active_transfers:
                    try:
                        self.transfer_manager.cancel_transfer(transfer['id'])
                        self.logger.info(f"Canceled transfer {transfer['id']} during shutdown")
                    except Exception as cancel_error:
                        self.logger.error(f"Error canceling transfer {transfer['id']}: {str(cancel_error)}")
                
                # Give transfers a moment to clean up
                time.sleep(0.2)
        except Exception as transfer_cleanup_error:
            self.logger.error(f"Error during transfer cleanup: {str(transfer_cleanup_error)}")
        
        # Disconnect any active SFTP clients
        try:
            if self.remote_panel.client:
                self.remote_panel.client.disconnect()
        except Exception as remote_disconnect_error:
            self.logger.error(f"Error disconnecting remote panel: {str(remote_disconnect_error)}")
        
        try:
            self.server_to_server_panel.disconnect_all()
        except Exception as s2s_disconnect_error:
            self.logger.error(f"Error disconnecting S2S panels: {str(s2s_disconnect_error)}")

        # Stop transfer manager
        try:
            self.transfer_manager.stop()
        except Exception as manager_stop_error:
            self.logger.error(f"Error stopping transfer manager: {str(manager_stop_error)}")
        
        event.accept()
    
    def save_geometry(self):
        """Save the window geometry to settings"""
        settings = QSettings("YourCompany", "FilePilot")
        settings.setValue("geometry", self.saveGeometry()) #
        settings.setValue("windowState", self.saveState()) #
    
    def restore_geometry(self):
        """Restore the window geometry from settings"""
        settings = QSettings("YourCompany", "FilePilot")
        if settings.contains("geometry"):
            self.restoreGeometry(settings.value("geometry")) #
        if settings.contains("windowState"):
            self.restoreState(settings.value("windowState")) #
    
    def new_connection(self):
        """Open the connection dialog to create a new connection"""
        dialog = ConnectionDialog(self)
        if dialog.exec_():
            # Refresh connection list in all panels
            self.refresh_connections() #
    
    def manage_connections(self):
        """Open the connection manager dialog"""
        dialog = ConnectionManagerDialog(self.auth_manager, self)
        dialog.exec_() #
    
    def refresh_connections(self):
        """Refresh the list of connections in the combo boxes for all panels"""
        # Refresh in local-to-server remote panel
        self.remote_panel.refresh_connections() #
        # Refresh in server-to-server panels
        self.server_to_server_panel.refresh_connections() #

    def toggle_transfer_mode(self):
        """Toggle between local-to-server and server-to-server transfer modes."""
        if self.current_mode == "local_to_server": #
            # Switch to server-to-server mode
            self.current_mode = "server_to_server" #
            self.transfer_mode_stacked_widget.setCurrentIndex(1) # Show server-to-server panel
            self.toggle_transfer_mode_action.setText("Local to Server Transfer") #
            self.toggle_transfer_mode_action.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon)) # Change icon
            
            # Disconnect previous remote connection if any
            if self.remote_panel.client:
                self.remote_panel.client.disconnect()
                self.remote_panel.set_client(None) # Clear panel's client
                self.remote_panel.file_model.removeRows(0, self.remote_panel.file_model.rowCount()) # Clear view
                self.remote_panel.path_edit.setText("") # Clear path
            self.status_bar.showMessage("Switched to Server to Server mode.") #
            self.server_to_server_panel.refresh_connections() # Ensure connections are loaded
        else:
            # Switch to local-to-server mode
            self.current_mode = "local_to_server" #
            self.transfer_mode_stacked_widget.setCurrentIndex(0) # Show local-to-server panel
            self.toggle_transfer_mode_action.setText("Server to Server Transfer") #
            self.toggle_transfer_mode_action.setIcon(self.style().standardIcon(QStyle.SP_DirLinkIcon)) # Change icon

            # Disconnect server-to-server connections if any
            self.server_to_server_panel.disconnect_all() #
            self.status_bar.showMessage("Switched to Local to Server mode.") #
            # Re-initialize local panel to home directory
            self.local_panel.load_directory(os.path.expanduser('~')) #

    def local_item_selected(self, path, is_dir):
        """Handle file or directory selection in the local panel (only in local-to-server mode)."""
        if self.current_mode != "local_to_server": 
            # If not in local-to-server mode, this signal should ideally not be active or handled differently.
            # For now, we'll just return to prevent unintended behavior.
            return 

        conn_name = self.remote_panel.conn_combo.currentText()
        if not conn_name:
            title, text = SFTPMessages.NO_CONNECTION
            CustomMessageBox.warning(self, title, text)
            return

        config = self.auth_manager.get_connection_secure(conn_name)
        if not config:
            title, text = SFTPMessages.CONNECTION_FAILED
            CustomMessageBox.critical(self, title, f"Connection '{conn_name}' not found.")
            return
        
        # Get the current path in the remote panel
        remote_path = self.remote_panel.current_path 
        
        if not remote_path or not self.remote_panel.client:
            title, text = SFTPMessages.NO_CONNECTION
            CustomMessageBox.warning(self, title, text)
            return
        
        # Extract the file/directory name from the path
        name = os.path.basename(path)
        
        # Set up source and destination paths
        source_full_path = path 
        destination_full_path = os.path.join(remote_path, name).replace('\\', '/')
        
        # Ask for confirmation with the predetermined destination path
        if is_dir:
            # Confirm directory upload
            reply = CustomMessageBox.question(
                self, "Upload Directory",
                f"Upload directory '{name}' to '{destination_full_path}'?", 
                CustomMessageBox.Yes | CustomMessageBox.No, CustomMessageBox.Yes)
        else:
            # Confirm file upload
            reply = CustomMessageBox.question(
                self, "Upload File",
                f"Upload file '{name}' to '{destination_full_path}'?", 
                CustomMessageBox.Yes | CustomMessageBox.No, CustomMessageBox.Yes)
                
        if reply != CustomMessageBox.Yes:
            return
        
        remote_server_config = self.remote_panel.client.connection_config # Get the active connection config

        # Create overwrite callback for upload
        def upload_overwrite_callback(remote_file_path):
            return self.overwrite_handler.request_overwrite_confirmation(remote_file_path, "upload")
        
        # Start the transfer using the signal bridge for thread-safe callbacks
        transfer_id = self.transfer_manager.upload_file(
            source_full_path, destination_full_path, remote_server_config,
            # Pass TransferType.UPLOAD and panel identifier instead of object reference
            lambda tid, tr, tt: self.signal_bridge.update_progress(tid, tr, tt, TransferType.UPLOAD, "remote_panel"),
            upload_overwrite_callback)
        
        if transfer_id:
            # Track the upload with its destination path (for refresh)
            self.active_uploads[transfer_id] = destination_full_path 

            self.status_bar.showMessage(f"Upload started: {name} → {destination_full_path}", 5000) 
            # Force immediate update of the transfer panel
            self.transfer_panel.update_transfers() 
        else:
            CustomMessageBox.critical(self, "Upload Failed", "Failed to start upload.")
    
    def remote_item_selected(self, path, is_dir):
        """Handle file or directory selection in the remote panel (only in local-to-server mode)."""
        if self.current_mode != "local_to_server":
            # If not in local-to-server mode, this signal should ideally not be active or handled differently.
            # For now, we'll just return to prevent unintended behavior.
            return

        # Extract the file/directory name from the path
        name = os.path.basename(path)
        
        # Get the current path in the local panel
        local_path = self.local_panel.current_path
        
        # Set up source and destination paths
        source_full_path = path
        destination_full_path = os.path.join(local_path, name)
        
        # Ask for confirmation with the predetermined destination path
        if is_dir:
            # Confirm directory download
            reply = CustomMessageBox.question(
                self, "Download Directory",
                f"Download directory '{name}' to '{destination_full_path}'?", 
                CustomMessageBox.Yes | CustomMessageBox.No, CustomMessageBox.Yes)
        else:
            # Confirm file download
            reply = CustomMessageBox.question(
                self, "Download File",
                f"Download file '{name}' to '{destination_full_path}'?", 
                CustomMessageBox.Yes | CustomMessageBox.No, CustomMessageBox.Yes)
                
        if reply != CustomMessageBox.Yes:
            return
        
        if not self.remote_panel.client:
            CustomMessageBox.warning(self, "No Remote Connection", "Please connect to a remote server before downloading.")
            return

        remote_server_config = self.remote_panel.client.connection_config # Get the active connection config

        # Create overwrite callback for download
        def download_overwrite_callback(local_file_path):
            return self.overwrite_handler.request_overwrite_confirmation(local_file_path, "download")
        
        # Start the transfer using the signal bridge for thread-safe callbacks
        transfer_id = self.transfer_manager.download_file(
                source_full_path, destination_full_path, remote_server_config,
                lambda tid, tr, tt: self.signal_bridge.update_progress(tid, tr, tt, TransferType.DOWNLOAD, None),
                download_overwrite_callback)
            
        if transfer_id:
            # Track the download with its destination path
            self.active_downloads[transfer_id] = destination_full_path
            
            self.status_bar.showMessage(f"Download started: {name} → {destination_full_path}", 5000)
            # Force immediate update of the transfer panel
            self.transfer_panel.update_transfers()
        else:
            CustomMessageBox.critical(self, "Download Failed", "Failed to start download.")
    
    def upload_file(self):
        """Upload a file or directory to the remote server (only in local-to-server mode)."""
        if self.current_mode != "local_to_server":
            CustomMessageBox.information(self, "Mode Mismatch", "Upload/Download actions are for Local to Server mode. Please switch modes or use Server to Server transfer directly.")
            return

        # Get the selected file or directory from the local panel
        selected_items = self.local_panel.file_view.selectedIndexes()
        if not selected_items:
            CustomMessageBox.warning(self, "No Selection", "Please select a file or directory to upload.")
            return
        
        # For now, just get the first selected item
        index = selected_items[0]
        full_path = index.sibling(index.row(), 0).data(Qt.UserRole)
        is_dir = index.sibling(index.row(), 0).data(Qt.UserRole + 1)

        remote_path = self.remote_panel.current_path
        if is_dir:
            source_path = full_path
            destination_path = os.path.join(remote_path, os.path.basename(full_path)).replace('\\', '/')
        else:
            default_remote_path = os.path.join(remote_path, os.path.basename(full_path)).replace('\\', '/')
            destination_path, ok = QInputDialog.getText(self, "Upload File", "Remote destination path:", QLineEdit.Normal, default_remote_path)
            if not ok or not destination_path:
                return
            source_path = full_path

        if destination_path:
            if not self.remote_panel.client:
                CustomMessageBox.warning(self, "No Remote Connection", "Please connect to a remote server before uploading.")
                return

            remote_server_config = self.remote_panel.client.connection_config

            # Use thread-safe overwrite handler
            def upload_overwrite_callback(remote_file_path):
                return self.overwrite_handler.request_overwrite_confirmation(remote_file_path, "upload")

            transfer_id = self.transfer_manager.upload_file(
                source_path, destination_path, remote_server_config,
                lambda tid, tr, tt: self.signal_bridge.update_progress(tid, tr, tt, TransferType.UPLOAD, "remote_panel"),
                upload_overwrite_callback)

            if transfer_id:
                self.active_uploads[transfer_id] = destination_path
                CustomMessageBox.information(self, "Upload Started", f"Upload of '{os.path.basename(source_path)}' started.")
                self.transfer_panel.update_transfers()
            else:
                CustomMessageBox.critical(self, "Upload Failed", "Failed to start upload.")
    
    def download_file(self):
        """Download a file or directory from the remote server (only in local-to-server mode)."""
        if self.current_mode != "local_to_server":
            CustomMessageBox.information(self, "Mode Mismatch", "Upload/Download actions are for Local to Server mode. Please switch modes or use Server to Server transfer directly.")
            return

        # Get the selected file or directory from the remote panel
        selected_items = self.remote_panel.file_view.selectedIndexes()
        if not selected_items:
            CustomMessageBox.warning(self, "No Selection", "Please select a file or directory to download.")
            return
        
        # For now, just get the first selected item
        index = selected_items[0]
        # Data is stored in column 0 of the model, not the index itself
        full_path = index.sibling(index.row(), 0).data(Qt.UserRole)
        is_dir = index.sibling(index.row(), 0).data(Qt.UserRole + 1)
        
        # Get the current path in the local panel
        local_path = self.local_panel.current_path
        
        if is_dir:
            # If it's a directory, use the local path as the base for destination
            source_path = full_path
            # The destination path should be the local_path plus the directory name
            destination_path = os.path.join(local_path, os.path.basename(full_path))
            
            # Confirm directory download
            reply = CustomMessageBox.question(
                self, "Download Directory",
                f"Download directory '{os.path.basename(source_path)}' to '{destination_path}'?", 
                CustomMessageBox.Yes | CustomMessageBox.No, CustomMessageBox.Yes)
                
            if reply != CustomMessageBox.Yes:
                return
        else:
            # If it's a file, ask where to download
            # Pre-fill with the local current path and the file name
            default_local_path = os.path.join(local_path, os.path.basename(full_path))
            destination_path, _ = QFileDialog.getSaveFileName(self, "Download File", default_local_path)
            if not destination_path:
                return
            source_path = full_path
        
        if destination_path:
            remote_server_config = self.remote_panel.client.connection_config # Get the active connection config

            # Start the transfer using the signal bridge for thread-safe callbacks
            transfer_id = self.transfer_manager.download_file(
                source_path, destination_path, remote_server_config,
                lambda tid, tr, tt: self.signal_bridge.update_progress(tid, tr, tt, TransferType.DOWNLOAD, None))
            
            if transfer_id:
                # Track the download with its destination path
                self.active_downloads[transfer_id] = destination_path
                
                CustomMessageBox.information(self, "Download Started", 
                                        f"Download of '{os.path.basename(source_path)}' started.")
                # Force immediate update of the transfer panel
                self.transfer_panel.update_transfers()
            else:
                CustomMessageBox.critical(self, "Download Failed", "Failed to start download.")
    
    def server_to_server_transfer(self):
        """This menu action is now handled by toggle_transfer_mode."""
        pass # This method is no longer directly called by the menu action
    
    def on_transfer_progress(self, transfer_id: int, transferred: int, total: int,
                            transfer_type: TransferType, destination_panel_id: str = None):
        """
        Update the transfer progress in the UI and refresh panels on transfer completion.
        'destination_panel_id' is a string identifier for the destination panel.
        """
        # Ensure this method only runs on the main thread
        if not QApplication.instance() or QThread.currentThread() != QApplication.instance().thread():
            # If called from a worker thread, schedule on main thread
            QTimer.singleShot(0, lambda: self.on_transfer_progress(transfer_id, transferred, total, transfer_type, destination_panel_id))
            return
        
        # Skip processing if the application is shutting down
        if not QApplication.instance() or QApplication.instance().closingDown():
            return
        
        # Check if this is a completed transfer (either by bytes or by checking transfer status)
        transfer_completed = False
        
        # Check completion by bytes transferred
        if transferred >= total and total > 0:
            transfer_completed = True
        
        # Also check the actual transfer status in case bytes comparison isn't reliable
        if not transfer_completed:
            try:
                transfer_status = self.transfer_manager.get_transfer_status(transfer_id)
                if transfer_status and transfer_status.get('status') == 'COMPLETED':
                    transfer_completed = True
            except Exception as e:
                self.logger.error(f"Error checking transfer status for {transfer_id}: {str(e)}")
                return
        
        if transfer_completed:
            # Handle completion based on transfer type with throttled UI updates
            try:
                with self._update_lock:
                    if transfer_type == TransferType.DOWNLOAD:
                        if transfer_id in self.active_downloads:
                            dest_path = self.active_downloads[transfer_id]
                            self._pending_refresh_panels.add(self.local_panel)
                            self.status_bar.showMessage(f"Download completed: {os.path.basename(dest_path)}", 5000)
                            del self.active_downloads[transfer_id]
                        else:
                            # Fallback: refresh local panel even if transfer ID not tracked
                            self._pending_refresh_panels.add(self.local_panel)
                            self.status_bar.showMessage("Download completed", 5000)
                    
                    elif transfer_type == TransferType.UPLOAD:
                        if transfer_id in self.active_uploads:
                            dest_path = self.active_uploads[transfer_id]
                            self._pending_refresh_panels.add(self.remote_panel)
                            self.status_bar.showMessage(f"Upload completed: {os.path.basename(dest_path)}", 5000)
                            del self.active_uploads[transfer_id]
                        else:
                            # Fallback: refresh remote panel even if transfer ID not tracked
                            self._pending_refresh_panels.add(self.remote_panel)
                            self.status_bar.showMessage("Upload completed", 5000)
                    
                    elif transfer_type == TransferType.SERVER_TO_SERVER:
                        # Map panel identifiers to actual panel objects
                        destination_panel = None
                        if destination_panel_id == "source_panel" and hasattr(self.server_to_server_panel, 'source_panel'):
                            destination_panel = self.server_to_server_panel.source_panel
                        elif destination_panel_id == "destination_panel" and hasattr(self.server_to_server_panel, 'destination_panel'):
                            destination_panel = self.server_to_server_panel.destination_panel
                        
                        if destination_panel:
                            self._pending_refresh_panels.add(destination_panel)
                            self.status_bar.showMessage(f"Server-to-server transfer completed to {destination_panel.current_path}", 5000)
                        else:
                            # Fallback: refresh both server-to-server panels if no specific reference
                            if hasattr(self.server_to_server_panel, 'source_panel') and self.server_to_server_panel.source_panel:
                                self._pending_refresh_panels.add(self.server_to_server_panel.source_panel)
                            if hasattr(self.server_to_server_panel, 'destination_panel') and self.server_to_server_panel.destination_panel:
                                self._pending_refresh_panels.add(self.server_to_server_panel.destination_panel)
                            self.status_bar.showMessage("Server-to-server transfer completed", 5000)
                    
                    # Mark that transfer panel needs updating
                    self._pending_transfer_update = True
                    
                    # Start throttled update timer if not already running
                    if not self._update_throttle_timer.isActive():
                        self._update_throttle_timer.start(300)  # 300ms delay to batch updates
                
            except Exception as e:
                self.logger.error(f"Error handling transfer completion for {transfer_id}: {str(e)}")
        else:
            # For progress updates, not completion, use throttled transfer panel update
            try:
                with self._update_lock:
                    self._pending_transfer_update = True
                    if not self._update_throttle_timer.isActive():
                        self._update_throttle_timer.start(100)  # Shorter delay for progress updates
            except Exception as e:
                self.logger.error(f"Error updating transfer panel for {transfer_id}: {str(e)}")
    
    def _perform_throttled_updates(self):
        """Perform all pending UI updates in a single batch to prevent race conditions"""
        try:
            if not QApplication.instance() or QApplication.instance().closingDown():
                return
            
            with self._update_lock:
                # Refresh panels that need refreshing
                panels_to_refresh = list(self._pending_refresh_panels)
                self._pending_refresh_panels.clear()
                
                transfer_update_needed = self._pending_transfer_update
                self._pending_transfer_update = False
            
            # Perform panel refreshes outside the lock to prevent deadlocks
            for panel in panels_to_refresh:
                try:
                    if panel and hasattr(panel, 'refresh'):
                        panel.refresh()
                except Exception as e:
                    self.logger.error(f"Error refreshing panel during throttled update: {str(e)}")
            
            # Update transfer panel if needed
            if transfer_update_needed:
                try:
                    if (self.transfer_panel and 
                        hasattr(self.transfer_panel, 'update_transfers')):
                        self.transfer_panel.update_transfers()
                except Exception as e:
                    self.logger.error(f"Error updating transfer panel during throttled update: {str(e)}")
                    
        except Exception as e:
            self.logger.error(f"Error in throttled updates: {str(e)}")
    
    def _safe_refresh_panel(self, panel):
        """Safely refresh a file panel with error handling"""
        try:
            if panel and hasattr(panel, 'refresh') and QApplication.instance() and not QApplication.instance().closingDown():
                panel.refresh()
        except Exception as e:
            self.logger.error(f"Error refreshing panel: {str(e)}")
    
    def _safe_refresh_s2s_panels(self):
        """Safely refresh server-to-server panels with error handling"""
        try:
            if (self.server_to_server_panel and 
                QApplication.instance() and 
                not QApplication.instance().closingDown()):
                
                # Refresh source panel
                if hasattr(self.server_to_server_panel, 'source_panel') and self.server_to_server_panel.source_panel:
                    self._safe_refresh_panel(self.server_to_server_panel.source_panel)
                
                # Refresh destination panel
                if hasattr(self.server_to_server_panel, 'destination_panel') and self.server_to_server_panel.destination_panel:
                    self._safe_refresh_panel(self.server_to_server_panel.destination_panel)
        except Exception as e:
            self.logger.error(f"Error refreshing server-to-server panels: {str(e)}")
    
    def update_activity_view(self):
        """Update the activity log view with new log entries without timestamps and duplicates"""
        log_path = os.path.join(os.path.dirname(__file__), "..", "logs", "filepilot.log")
        log_path = os.path.abspath(log_path)
        
        try:
            with open(log_path, "rb") as f:
                f.seek(self._activity_log_last_pos)
                new_data = f.read()
                
                if new_data:
                    # Decode and split by lines
                    new_lines = new_data.decode('utf-8', errors='replace').splitlines()
                    
                    # Filter out empty lines and process each line
                    for line in new_lines:
                        if not line.strip():
                            continue
                        
                        # Skip progress-related messages
                        if any(skip_text in line for skip_text in [
                            "bytes transferred", 
                            "Progress:", 
                            "Transfer progress",
                            "Current speed:",
                            "Time remaining:"
                        ]):
                            continue
                                
                        # Remove timestamp prefix if present
                        if " - " in line:
                            parts = line.split(" - ", 1)
                            if len(parts) > 1:
                                if "filepilot - INFO - " in parts[1]:
                                    msg = parts[1].split("filepilot - INFO - ")[1]
                                else:
                                    msg = parts[1]
                            else:
                                msg = line
                        else:
                            msg = line

                        # Skip if message is just a timestamp or already shown
                        msg = msg.strip()
                        if (msg and 
                            not msg.startswith("202") and  # Skip timestamp lines
                            msg not in self._shown_activities):  # Skip duplicates
                            
                            self.activity_view.appendPlainText(msg)
                            self._shown_activities.add(msg)
                                
                            # Auto-scroll to bottom
                            scrollbar = self.activity_view.verticalScrollBar()
                            scrollbar.setValue(scrollbar.maximum())
            
            self._activity_log_last_pos = f.tell()
            
        except Exception as e:
            if not hasattr(self, '_error_shown'):
                self.activity_view.setPlainText(f"FilePilot Transfer Manager Started\n")
                self._error_shown = True

        important_events = []  # Collect important events to display

        try:
            with open(log_path, "r") as f:
                # Seek to the last known position
                f.seek(self._activity_log_last_pos)
                
                # Read new lines
                new_lines = f.readlines()
                
                for msg in new_lines:
                    msg = msg.strip()
                    if not msg:
                        continue  # Skip empty lines
                    
                    # Detect and handle important events
                    event_text = ""
                    event_type = "info"  # Default event type
                    
                    # Transfer completion events
                    if "Transfer completed with status COMPLETED" in msg and "ID:" in msg:
                        # Extract file info from the message
                        if "Source:" in msg and "Destination:" in msg:
                            try:
                                parts = msg.split("|")
                                source_part = [p.strip() for p in parts if "Source:" in p][0]
                                source_file = source_part.split("Source:")[-1].strip()
                                source_name = source_file.split("/")[-1] if "/" in source_file else source_file.split("\\")[-1]
                                event_text = f"Transfer completed: {source_name}"
                                event_type = "success"
                            except:
                                event_text = "Transfer completed"
                                event_type = "success"
                    elif "File upload completed successfully" in msg:
                        try:
                            file_info = msg.split("File upload completed successfully: ")[1]
                            if "->" in file_info:
                                src, dst = [s.strip() for s in file_info.split("->")]
                                file_name = src.split("/")[-1] if "/" in src else src.split("\\")[-1]
                                event_text = f"Upload completed: {file_name}"
                            else:
                                event_text = "Upload completed"
                        except:
                            event_text = "Upload completed"
                        event_type = "success"
                    elif "File download completed successfully" in msg:
                        try:
                            file_info = msg.split("File download completed successfully: ")[1]
                            if "->" in file_info:
                                src, dst = [s.strip() for s in file_info.split("->")]
                                file_name = src.split("/")[-1] if "/" in src else src.split("\\")[-1]
                                event_text = f"Download completed: {file_name}"
                            else:
                                event_text = "Download completed"
                        except:
                            event_text = "Download completed"
                        event_type = "success"
                    
                    # File operations
                    elif "Successfully deleted remote file" in msg:
                        file_path = msg.split("Successfully deleted remote file: ")[1]
                        file_name = file_path.split("/")[-1] if "/" in file_path else file_path.split("\\")[-1]
                        event_text = f"Deleted: {file_name}"
                        event_type = "warning"
                    elif "Successfully created remote directory" in msg:
                        dir_path = msg.split("Successfully created remote directory: ")[1]
                        dir_name = dir_path.split("/")[-1] if "/" in dir_path else dir_path.split("\\")[-1]
                        event_text = f"Created directory: {dir_name}"
                        event_type = "success"
                    elif "Successfully renamed" in msg:
                        parts = msg.split("Successfully renamed ")
                        if len(parts) > 1:
                            rename_info = parts[1]
                            if " to " in rename_info:
                                old_name, new_name = rename_info.split(" to ")
                                old_name = old_name.split("/")[-1] if "/" in old_name else old_name.split("\\")[-1]
                                new_name = new_name.split("/")[-1] if "/" in new_name else new_name.split("\\")[-1]
                                event_text = f"Renamed: {old_name} → {new_name}"
                            else:
                                event_text = f"File renamed"
                        event_type = "info"
                    
                    # System events
                    elif "Detected OS from" in msg:
                        os_info = msg.split("Detected OS from ")[1]
                        event_text = f"Remote OS detected: {os_info}"
                        event_type = "info"
                    elif "Home directory determined as" in msg:
                        home_dir = msg.split("Home directory determined as: ")[1]
                        event_text = f"Home directory: {home_dir}"
                        event_type = "info"
                    elif "Integrity check passed" in msg:
                        event_text = "Integrity check passed"
                        event_type = "success"
                    
                    # Transfer control events
                    elif "Transfer paused" in msg:
                        if "ID:" in msg:
                            try:
                                transfer_id = msg.split("ID:")[1].split("|")[0].strip()
                                event_text = f"Transfer paused (ID: {transfer_id})"
                            except:
                                event_text = "Transfer paused"
                        else:
                            event_text = "Transfer paused"
                        event_type = "warning"
                    elif "Transfer resumed" in msg:
                        if "ID:" in msg:
                            try:
                                transfer_id = msg.split("ID:")[1].split("|")[0].strip()
                                event_text = f"Transfer resumed (ID: {transfer_id})"
                            except:
                                event_text = "Transfer resumed"
                        else:
                            event_text = "Transfer resumed"
                        event_type = "info"
                    elif "Transfer canceled" in msg:
                        if "ID:" in msg:
                            try:
                                transfer_id = msg.split("ID:")[1].split("|")[0].strip()
                                event_text = f"Transfer cancelled (ID: {transfer_id})"
                            except:
                                event_text = "Transfer cancelled"
                        else:
                            event_text = "Transfer cancelled"
                        event_type = "warning"
                    
                    # Error events
                    elif "FAILED" in msg.upper():
                        if "Transfer completed with status FAILED" in msg:
                            # Try to extract file info
                            if "Source:" in msg:
                                try:
                                    parts = msg.split("|")
                                    source_part = [p.strip() for p in parts if "Source:" in p][0]
                                    source_file = source_part.split("Source:")[-1].strip()
                                    source_name = source_file.split("/")[-1] if "/" in source_file else source_file.split("\\")[-1]
                                    event_text = f"Transfer failed: {source_name}"
                                except:
                                    event_text = "Transfer failed"
                            else:
                                event_text = "Transfer failed"
                        else:
                            # Other failure messages
                            error_msg = msg[:80] + "..." if len(msg) > 80 else msg
                            event_text = f"Error: {error_msg}"
                        event_type = "error"
                    elif "Error" in msg and "Transfer" in msg:
                        # Transfer-related errors
                        error_msg = msg[:80] + "..." if len(msg) > 80 else msg
                        event_text = f"Error: {error_msg}"
                        event_type = "error"

                    # Add the event if it's important and not a duplicate
                    if event_text and event_text not in self._shown_activities:
                        important_events.append({
                            'text': event_text,
                            'type': event_type
                        })
                        self._shown_activities.add(event_text)
                
                # Display new important events
                if important_events:
                    # Move cursor to end
                    cursor = self.activity_view.textCursor()
                    cursor.movePosition(cursor.End)
                    self.activity_view.setTextCursor(cursor)
                    
                    # Add events
                    for event in important_events:
                        # Add some spacing if not the first event
                        if self.activity_view.toPlainText():
                            self.activity_view.insertPlainText("\n")
                        
                        # Insert the event text
                        self.activity_view.insertPlainText(event['text'])
                    
                    # Auto-scroll to bottom
                    scrollbar = self.activity_view.verticalScrollBar()
                    scrollbar.setValue(scrollbar.maximum())
                
                self._activity_log_last_pos = f.tell()
                
        except Exception as e:
            if not hasattr(self, '_error_shown'):
                self.activity_view.setPlainText(f"Activity log unavailable: {str(e)}")
                self._error_shown = True

    def show_about(self):
        """Show the about dialog"""
        CustomMessageBox.information(
            self, 
            "About FilePilot", 
            "FilePilot SFTP Client\n\n"
            "A secure and user-friendly SFTP client for file transfers.\n"
            "Features include:\n"
            "• Local to server transfers\n"
            "• Server to server transfers\n"
            "• Secure credential management\n"
            "• Progress tracking and resumable transfers\n"
            "• Modern Qt-based interface\n\n"
            "Version: 1.0.0\n"
            "Built with PyQt5 and paramiko"
        )


def run_app():
    """
    Initialize and launch the FilePilot application.
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    window.refresh_connections()
    sys.exit(app.exec_())
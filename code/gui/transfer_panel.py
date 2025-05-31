import logging
import os
import threading
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QTableWidget, QHBoxLayout, QPushButton,
                            QAbstractItemView, QHeaderView, QTableWidgetItem, QMessageBox, QProgressBar,
                            QLabel, QFrame, QPlainTextEdit, QApplication)
from PyQt5.QtCore import QTimer, Qt, QThread
from PyQt5.QtGui import QFont, QColor

from code.gui.custom_message_box import CustomMessageBox

# Ensure log directory exists
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename='logs/filepilot.log',
    filemode='a',
    format='%(asctime)s - %(message)s',
    level=logging.INFO
)

class TransferPanel(QWidget):
    """Panel for displaying and managing file transfers"""
    
    def __init__(self, parent=None, transfer_manager=None):
        super().__init__(parent)
        self.transfer_manager = transfer_manager
        
        # Add update throttling to prevent race conditions
        self._update_lock = threading.Lock()
        self._update_pending = False
        self._throttle_timer = QTimer()
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._perform_update)
        
        self.setup_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_transfers)
        self.timer.start(1000)  # Update every second
        self.last_logged_status = {}  # Track last status to avoid duplicate logs
    
    def setup_ui(self):
        """Set up the transfer panel UI with modern minimalist black/white theme"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)  # Reduced from 20
        layout.setContentsMargins(5, 5, 5, 5)  # Reduced from 20
        
        
        # Set overall widget background
        self.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                color: #2c2c2c;
                font-family: 'Segoe UI', 'San Francisco', 'Helvetica Neue', Arial, sans-serif;
            }
            
            /* Modern thin scrollbar styling */
            QScrollBar:vertical {
                border: none;
                background: #f5f5f5;
                width: 8px;
                margin: 0px;
            }
            
            QScrollBar::handle:vertical {
                background: #c1c1c1;
                min-height: 20px;
                border-radius: 4px;
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
                height: 8px;
                margin: 0px;
            }
            
            QScrollBar::handle:horizontal {
                background: #c1c1c1;
                min-width: 20px;
                border-radius: 4px;
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
        
        # Minimalist tabs with more space for content - no header
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e5e5e5;
                background-color: #ffffff;
                border-radius: 0px;
                padding: 0px;
            }
            QTabWidget::tab-bar {
                alignment: left;
            }
            QTabBar::tab {
                background-color: transparent;
                border: none;
                padding: 8px 10px;
                margin-right: 0px;
                color: #666666;
                font-size: 12px;
                font-weight: 500;
                min-width: 80px;
            }
            QTabBar::tab:selected {
                background-color: transparent;
                color: #1a1a1a;
                border-bottom: 2px solid #1a1a1a;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                color: #404040;
                background-color: #f8f8f8;
            }
        """)
        
        # Create tables with minimalist design
        self.active_table = QTableWidget()
        self.setup_transfer_table(self.active_table)
        self.tabs.addTab(self.active_table, "Active")
        
        self.queued_table = QTableWidget()
        self.setup_transfer_table(self.queued_table)
        self.tabs.addTab(self.queued_table, "Queued")
        
        self.history_table = QTableWidget()
        self.setup_transfer_table(self.history_table)
        self.tabs.addTab(self.history_table, "History")
        
        # Set minimum height for tables to show 3-4 entries
        table_min_height = 100  # Height for approximately 4 rows plus header
        self.active_table.setMinimumHeight(table_min_height)
        self.queued_table.setMinimumHeight(table_min_height)
        self.history_table.setMinimumHeight(table_min_height)
        
        layout.addWidget(self.tabs, 1)  # Give tabs stretch factor to use available space
        
        # Minimalist controls - no vertical space
        controls_frame = QFrame()
        controls_frame.setFrameStyle(QFrame.NoFrame)
        controls_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                padding: 0px;
                margin: 0px;
            }
        """)
        
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(0, 0, 0, 0)  # No margins
        controls_layout.setSpacing(8)  # Add some spacing between buttons
        
        # Minimalist button styling - more compact with equal width
        button_style = """
            QPushButton {
                background-color: transparent;
                color: #1a1a1a;
                border: 1px solid #e5e5e5;
                padding: 6px 16px;
                border-radius: 0px;
                font-weight: 500;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #f8f8f8;
                border-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
                color: #ffffff;
            }
            QPushButton:disabled {
                color: #cccccc;
                border-color: #f0f0f0;
            }
        """
        
        # Special styling for different button types
        destructive_style = button_style.replace("#1a1a1a", "#dc2626").replace("#f8f8f8", "#fef2f2")
        
        self.pause_button = QPushButton("Pause")
        self.pause_button.setStyleSheet(button_style)
        
        self.resume_button = QPushButton("Resume") 
        self.resume_button.setStyleSheet(button_style)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet(destructive_style)
        
        self.clear_button = QPushButton("Clear")
        self.clear_button.setStyleSheet(button_style)
        self.clear_button.setToolTip("Remove completed/canceled/failed transfers from history")
        self.clear_button.clicked.connect(self.clear_completed)
        
        self.pause_button.clicked.connect(self.pause_selected)
        self.resume_button.clicked.connect(self.resume_selected)
        self.cancel_button.clicked.connect(self.cancel_selected)
        self.clear_button.clicked.connect(self.clear_completed)
        
        # Add all buttons with equal stretch to occupy full horizontal space
        controls_layout.addWidget(self.pause_button, 1)
        controls_layout.addWidget(self.resume_button, 1)
        controls_layout.addWidget(self.cancel_button, 1)
        controls_layout.addWidget(self.clear_button, 1)
        
        layout.addWidget(controls_frame)
        

    def _create_stat_container(self, label_text, count_label):
        """Create a minimalist stat container"""
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
                margin: 0px;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)  # Reduced spacing
        
        # Count number (smaller)
        count_label.setStyleSheet("""
            QLabel {
                color: #1a1a1a;
                font-size: 20px;
                font-weight: 300;
                border: none;
                margin: 0;
                padding: 0;
            }
        """)
        count_label.setAlignment(Qt.AlignCenter)
        
        # Label text (smaller)
        text_label = QLabel(label_text)
        text_label.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 10px;
                font-weight: 400;
                text-transform: uppercase;
                letter-spacing: 1px;
                border: none;
                margin: 0;
                padding: 0;
            }
        """)
        text_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(count_label)
        layout.addWidget(text_label)
        
        return container
    
    def setup_transfer_table(self, table):
        """Set up a transfer table with minimalist black/white styling"""
        headers = ["ID", "Type", "Source", "Destination", "Status", 
                  "Progress", "Speed", "Size"]
        
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(False)  # Disable for clean look
        
        # Minimalist table styling
        table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: none;
                gridline-color: #f5f5f5;
                selection-background-color: #0078d4;
                selection-color: #ffffff;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 8px 6px;
                border-bottom: 1px solid #f5f5f5;
                border-right: none;
            }
            QTableWidget::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            QTableWidget::item:selected:active {
                background-color: #0078d4;
                color: #ffffff;
            }
            QTableWidget::item:selected:!active {
                background-color: #0078d4;
                color: #ffffff;
            }
            QTableWidget::item:selected:focus {
                background-color: #0078d4;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #ffffff;
                padding: 5px 3px;
                border: none;
                border-bottom: 1px solid #e5e5e5;
                font-weight: 600;
                color: #666666;
                text-transform: uppercase;
                font-size: 10px;
                letter-spacing: 1px;
            }
            QTableWidget::item:hover {
                background-color: #e6f3ff;
            }
            QTableWidget::item:hover:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
        """)
        
        # Set up columns with better proportions
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)  # Source
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)  # Destination
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Status
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)  # Progress
        table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Speed
        table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Size
        
        # Set fixed width for progress column
        table.setColumnWidth(5, 120)
        
        # Remove vertical header
        table.verticalHeader().setVisible(False)
    
    def update_transfers(self):
        """Update the transfer tables with current status using throttled updates"""
        if not self.transfer_manager:
            return
        
        # Use throttled updates to prevent race conditions during rapid transfer changes
        with self._update_lock:
            if not self._update_pending:
                self._update_pending = True
                if not self._throttle_timer.isActive():
                    self._throttle_timer.start(100)  # 100ms throttle
    
    def _perform_update(self):
        """Perform the actual update in a thread-safe manner"""
        try:
            if not QApplication.instance() or QApplication.instance().closingDown():
                return
            
            with self._update_lock:
                self._update_pending = False
            
            if not self.transfer_manager:
                return
                
            transfers = self.transfer_manager.get_all_transfers()
            
            # Update active transfers
            self._safe_update_table(self.active_table, transfers['active'])
            
            # Update queued transfers
            self._safe_update_table(self.queued_table, transfers['queued'])
            
            # Update history
            self._safe_update_table(self.history_table, transfers['history'])
            
            # Update tab counters with additional info for active transfers
            active_count = len(transfers['active'])
            queued_count = len(transfers['queued'])
            history_count = len(transfers['history'])
            
            # Show concurrent limit info for active transfers
            max_concurrent = self.transfer_manager.max_concurrent if self.transfer_manager else 3
            self.tabs.setTabText(0, f"Active ({active_count}/{max_concurrent})")
            self.tabs.setTabText(1, f"Queued ({queued_count})")
            self.tabs.setTabText(2, f"History ({history_count})")
            
        except Exception as e:
            logging.error(f"Error in transfer panel update: {str(e)}")
    
    def _safe_update_table(self, table, transfers):
        """Safely update a table with error handling"""
        try:
            if not QApplication.instance() or QApplication.instance().closingDown():
                return
            
            self.update_table(table, transfers)
        except Exception as e:
            logging.error(f"Error updating transfer table: {str(e)}")
    
    def update_table(self, table, transfers):
        """Update a table with transfer data using minimalist black/white design"""
        # Ensure we're on the main thread
        if not QApplication.instance() or QApplication.instance().closingDown():
            return
            
        # Check if we're on the main thread, if not, schedule on main thread
        from PyQt5.QtCore import QThread, QTimer
        if QThread.currentThread() != QApplication.instance().thread():
            # Schedule on main thread using QTimer
            QTimer.singleShot(0, lambda: self._update_table_on_main_thread(table, transfers))
            return
            
        self._update_table_on_main_thread(table, transfers)
    
    def _update_table_on_main_thread(self, table, transfers):
        """Perform the actual table update on the main thread"""
        try:
            # Store current selection
            current_row = table.currentRow()
            
            # Clear table but preserve structure
            table.setRowCount(0)
            table.setRowCount(len(transfers))
            
            # Pre-define styles as strings to avoid creating Qt objects repeatedly
            normal_style = "background-color: #ffffff; color: #000000; border: none;"
            completed_style = "background-color: #e8f5e8; color: #2d5a2d; border: none;"
            failed_style = "background-color: #ffe8e8; color: #8b0000; border: none;"
            progress_style = "background-color: #e8f0ff; color: #1e3a5f; border: none;"
            
            for row, transfer in enumerate(transfers):
                # Create items with text only, no styling initially
                items = [
                    QTableWidgetItem(str(transfer.get('id', ''))),
                    QTableWidgetItem(transfer.get('type', '')),
                    QTableWidgetItem(transfer.get('source', '')),
                    QTableWidgetItem(transfer.get('destination', '')),
                    QTableWidgetItem(transfer.get('status', '')),
                    QTableWidgetItem(transfer.get('progress', '')),
                    QTableWidgetItem(transfer.get('transferred', '')),
                    QTableWidgetItem(transfer.get('total', '')),
                    QTableWidgetItem(transfer.get('rate', '')),
                    QTableWidgetItem(transfer.get('elapsed_time', '')),
                    QTableWidgetItem(transfer.get('error', ''))
                ]
                
                # Set items first
                for col, item in enumerate(items):
                    table.setItem(row, col, item)
                
                # Apply styling based on status
                status = transfer.get('status', '')
                if status == 'COMPLETED':
                    style = completed_style
                elif status == 'FAILED':
                    style = failed_style
                elif status == 'IN_PROGRESS':
                    style = progress_style
                else:
                    style = normal_style
                
                # Apply style to all items in the row
                for col in range(len(items)):
                    if table.item(row, col):
                        table.item(row, col).setData(Qt.UserRole, style)
                        
            # Restore selection safely
            if 0 <= current_row < table.rowCount():
                table.selectRow(current_row)
                
            # Apply stored styles
            for row in range(table.rowCount()):
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    if item:
                        style = item.data(Qt.UserRole)
                        if style:
                            item.setData(Qt.UserRole, None)  # Clear stored style
                            # Apply style safely
                            try:
                                table.item(row, col).setBackground(QColor("#ffffff" if "ffffff" in style else "#e8f5e8" if "e8f5e8" in style else "#ffe8e8" if "ffe8e8" in style else "#e8f0ff"))
                            except:
                                pass  # Ignore styling errors
                
        except Exception as e:
            logging.error(f"Error updating table: {str(e)}")
    
    # def update_activity_view(self):
    #     """Show only new, user-friendly activity logs for the current session."""
    #     log_path = os.path.join(os.path.dirname(__file__), "..", "logs", "filepilot.log")
    #     log_path = os.path.abspath(log_path)
    #     # Track unique activities for this session
    #     if not hasattr(self, "_shown_activities"):
    #         self._shown_activities = set()
    #         self._last_activity_type = None

    #     try:
    #         with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
    #             f.seek(self._activity_log_last_pos)
    #             new_lines = f.readlines()
    #             activity_lines = []
    #             for line in new_lines:
    #                 # # Remove timestamp and dash
    #                 # if " - " in line:
    #                 #     _, msg = line.split(" - ", 1)
    #                 # else:
    #                 #     msg = line
    #                 # msg = msg.strip()

    #                 activity = None
    #                 activity_type = None

    #                 if "Connecting to" in msg:
    #                     server = msg.split("Connecting to ")[1]
    #                     activity = f"Connection Established: {server}"
    #                     activity_type = "connect"
    #                 elif "Connected successfully to" in msg:
    #                     server = msg.split("Connected successfully to ")[1]
    #                     activity = f"Connected: {server}"
    #                     activity_type = "connect"
    #                 elif "Authentication (password) successful" in msg:
    #                     activity = "Authentication Successful"
    #                     activity_type = "auth"
    #                 elif "Started transfer" in msg:
    #                     details = msg.split("Started transfer", 1)[-1].lstrip(": ")
    #                     if "->" in details:
    #                         src, dst = [s.strip() for s in details.split("->")]
    #                         direction = "Local to Server" if (":" in src and "/" in dst) else "Server to Server"
    #                         activity = f"Transfer Started ({direction}): {os.path.basename(src)} → {dst}"
    #                     else:
    #                         activity = f"Transfer Started: {details}"
    #                     activity_type = "transfer_start"
    #                 elif "File upload completed successfully" in msg or "File download completed successfully" in msg:
    #                     details = msg.split(": ", 1)[-1]
    #                     if "upload" in msg:
    #                         direction = "Local to Server"
    #                     else:
    #                         direction = "Server to Local"
    #                     if "->" in details:
    #                         src, dst = [s.strip() for s in details.split("->")]
    #                         activity = f"File Transfer Success ({direction}): {os.path.basename(src)} → {dst}"
    #                     else:
    #                         activity = f"File Transfer Success: {details}"
    #                     activity_type = "transfer_success"
    #                 elif "Transfer completed with status COMPLETED" in msg:
    #                     details = msg.split("COMPLETED: ")[-1]
    #                     if "->" in details:
    #                         src, dst = [s.strip() for s in details.split("->")]
    #                         activity = f"Transfer Completed: {os.path.basename(src)} → {dst}"
    #                     else:
    #                         activity = f"Transfer Completed: {details}"
    #                     activity_type = "transfer_success"
    #                 elif "FAILED" in msg or "Error" in msg:
    #                     activity = f"Transfer Failed/Error: {msg}"
    #                     activity_type = "transfer_fail"
    #                 elif "Successfully deleted remote file" in msg:
    #                     file_path = msg.split("Successfully deleted remote file: ")[1]
    #                     activity = f"File Deleted: {file_path}"
    #                     activity_type = "delete"
    #                 elif "Transfer paused" in msg:
    #                     activity = "Transfer Paused"
    #                     activity_type = "pause"
    #                 elif "Transfer resumed" in msg:
    #                     activity = "Transfer Resumed"
    #                     activity_type = "resume"
    #                 elif "Transfer canceled" in msg:
    #                     activity = "Transfer Cancelled"
    #                     activity_type = "cancel"
    #                 elif "Disconnected from server" in msg:
    #                     # Only show "Disconnected" if last activity was not a transfer success
    #                     if self._last_activity_type not in ("transfer_success",):
    #                         activity = "Disconnected"
    #                         activity_type = "disconnect"
    #                 elif "Detected OS from" in msg:
    #                     activity = "Remote Environment Detected"
    #                     activity_type = "env"
    #                 elif "Integrity check passed" in msg:
    #                     activity = "Integrity Check Passed"
    #                     activity_type = "integrity"
    #                 elif "Home directory determined as" in msg:
    #                     activity = f"Home Directory: {msg.split('as: ')[1]}"
    #                     activity_type = "home"
    #                 elif "Successfully renamed" in msg:
    #                     parts = msg.split("Successfully renamed ")
    #                     if len(parts) > 1:
    #                         files = parts[1].split(" to ")
    #                         if len(files) == 2:
    #                             activity = f"File Renamed: {files[0]} → {files[1]}"
    #                         else:
    #                             activity = f"File Renamed: {parts[1]}"
    #                     activity_type = "rename"

    #                 # Only show unique activities (avoid repeats)
    #                 if activity and activity not in self._shown_activities:
    #                     activity_lines.append(activity)
    #                     self._shown_activities.add(activity)
    #                     self._last_activity_type = activity_type

    #             if activity_lines:
    #                 self.activity_view.moveCursor(self.activity_view.textCursor().End)
    #                 self.activity_view.insertPlainText('\n'.join(activity_lines) + '\n')
    #                 self.activity_view.moveCursor(self.activity_view.textCursor().End)
    #             self._activity_log_last_pos = f.tell()
    #     except Exception as e:
    #         self.activity_view.setPlainText(f"Could not read log file:\n{e}")
    
    def format_size(self, num_bytes):
        """Convert bytes to a human-readable string."""
        try:
            num_bytes = float(num_bytes)
        except (ValueError, TypeError):
            return str(num_bytes)
            
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if num_bytes < 1024.0:
                return f"{num_bytes:.2f} {unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.2f} PB"

    def safe_format_size(self, value):
        """Safely format size values, handling both strings and numbers."""
        # If value is already a string with units, return as is
        if isinstance(value, str) and any(unit in value for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']):
            return value
        
        # Handle empty or None values
        if value is None or value == '' or value == 0:
            return "0 B"
            
        try:
            return self.format_size(float(value))
        except (ValueError, TypeError, AttributeError):
            return str(value)

    def _set_row_background(self, table, row, color, alpha=0.1):
        """Set background color for a row"""
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item:
                color_with_alpha = color  # In a real implementation, would set alpha
                item.setBackground(color_with_alpha)
    
    def pause_selected(self):
        """Pause the selected transfers"""
        current_table = self.tabs.currentWidget()
        selected_rows = set(index.row() for index in current_table.selectedIndexes())
        
        for row in selected_rows:
            transfer_id = int(current_table.item(row, 0).text())
            if self.transfer_manager:
                self.transfer_manager.pause_transfer(transfer_id)
    
    def resume_selected(self):
        """Resume the selected transfers"""
        current_table = self.tabs.currentWidget()
        selected_rows = set(index.row() for index in current_table.selectedIndexes())
        
        for row in selected_rows:
            transfer_id = int(current_table.item(row, 0).text())
            if self.transfer_manager:
                self.transfer_manager.resume_transfer(transfer_id)
    
    def cancel_selected(self):
        """Cancel the selected transfers"""
        current_table = self.tabs.currentWidget()
        selected_rows = set(index.row() for index in current_table.selectedIndexes())
        
        if not selected_rows:
            return
            
        result = CustomMessageBox.question(
            self, 
            "Cancel Transfers",
            "Are you sure you want to cancel the selected transfers?",
            CustomMessageBox.Yes | CustomMessageBox.No,
            CustomMessageBox.No
        )
        
        if result == CustomMessageBox.Yes:
            for row in selected_rows:
                transfer_id = int(current_table.item(row, 0).text())
                if self.transfer_manager:
                    self.transfer_manager.cancel_transfer(transfer_id)
    
    def clear_completed(self):
        """Clear completed transfers from the history"""
        # This would require adding a method to the TransferManager
        # For now, we'll just refresh the display
        result = CustomMessageBox.question(
            self,
            "Clear Completed Transfers",
            "Are you sure you want to clear your history?",
            CustomMessageBox.Yes | CustomMessageBox.No,
            CustomMessageBox.No
        )
        if result == CustomMessageBox.Yes and self.transfer_manager:
            self.transfer_manager.clear_completed_transfers()
            self.update_transfers()
    
    def _truncate_path(self, path, max_length=40):
        """Truncate long paths for clean display"""
        if len(path) <= max_length:
            return path
        
        # Split path and show beginning and end
        if '/' in path:
            parts = path.split('/')
            if len(parts) > 2:
                return f"{parts[0]}/···/{parts[-1]}"
        elif '\\' in path:
            parts = path.split('\\')
            if len(parts) > 2:
                return f"{parts[0]}\\···\\{parts[-1]}"
        
        # If no path separators, just truncate with ellipsis
        return f"{path[:max_length-3]}···"


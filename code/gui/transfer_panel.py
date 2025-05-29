import logging
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QTableWidget, QHBoxLayout, QPushButton,
                            QAbstractItemView, QHeaderView, QTableWidgetItem, QMessageBox, QProgressBar,
                            QLabel, QFrame)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QColor

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
                selection-background-color: #f8f8f8;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 8px 6px;
                border-bottom: 1px solid #f5f5f5;
                border-right: none;
            }
            QTableWidget::item:selected {
                background-color: #f8f8f8;
                color: #1a1a1a;
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
                background-color: #fafafa;
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
        """Update the transfer tables with current status"""
        if not self.transfer_manager:
            return
            
        transfers = self.transfer_manager.get_all_transfers()
        
        # Update active transfers
        self.update_table(self.active_table, transfers['active'])
        
        # Update queued transfers
        self.update_table(self.queued_table, transfers['queued'])
        
        # Update history
        self.update_table(self.history_table, transfers['history'])
        
        # Update tab counters with additional info for active transfers
        active_count = len(transfers['active'])
        queued_count = len(transfers['queued'])
        history_count = len(transfers['history'])
        
        # Show concurrent limit info for active transfers
        max_concurrent = self.transfer_manager.max_concurrent if self.transfer_manager else 3
        self.tabs.setTabText(0, f"Active ({active_count}/{max_concurrent})")
        self.tabs.setTabText(1, f"Queued ({queued_count})")
        self.tabs.setTabText(2, f"History ({history_count})")
    
    def update_table(self, table, transfers):
        """Update a table with transfer data using minimalist black/white design"""
        table.setRowCount(len(transfers))
        
        for row, transfer in enumerate(transfers):
            # Clean ID without emojis
            id_item = QTableWidgetItem(str(transfer['id']))
            table.setItem(row, 0, id_item)
            
            # Type with subtle styling
            type_item = QTableWidgetItem(transfer['type'].upper())
            table.setItem(row, 1, type_item)
            
            # Source and Destination with truncated paths
            source_text = self._truncate_path(transfer['source'])
            dest_text = self._truncate_path(transfer['destination'])
            source_item = QTableWidgetItem(source_text)
            source_item.setTextAlignment(Qt.AlignCenter)
            dest_item = QTableWidgetItem(dest_text)
            dest_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 2, source_item)
            table.setItem(row, 3, dest_item)
            
            # Status with minimalist indicators
            status_text = transfer['status']
            status_item = QTableWidgetItem(status_text)
            
            # Subtle visual cues using typography weight instead of colors
            if 'COMPLETED' in status_text:
                status_item.setText(f"✓ {status_text}")
                status_item.setForeground(QColor(0, 128, 0))  # Green tex
                font = status_item.font()
                font.setBold(True)
                status_item.setFont(font)
            elif 'FAILED' in status_text:
                status_item.setText(f"✗ {status_text}")
                font = status_item.font()
                font.setBold(True)
                status_item.setFont(font)
            elif 'PAUSED' in status_text:
                status_item.setText(f"|| {status_text}")
            elif 'IN_PROGRESS' in status_text or 'ACTIVE' in status_text or 'TRANSFERRING' in status_text:
                status_item.setText(f"→ {status_text}")
            elif 'QUEUED' in status_text:
                status_item.setText(f"⏳ {status_text}")
            elif 'CANCELED' in status_text:
                status_item.setText(f"✗ {status_text}")
            else:
                status_item.setText(f"· {status_text}")
            
            table.setItem(row, 4, status_item)
            
            # Minimalist progress bar
            progress_widget = QWidget()
            progress_layout = QVBoxLayout(progress_widget)
            progress_layout.setContentsMargins(0, 0, 0, 0)
            progress_layout.setSpacing(0)  # No spacing for compact look
            
            progress_bar = QProgressBar()
            progress_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #e5e5e5;
                    border-radius: 2px;
                    text-align: center;
                    font-size: 11px;
                    height: 14px;
                    background-color: ##00FF00;
                }
                QProgressBar::chunk {
                    background-color: #1a1a1a;
                    border-radius: 1px;
                }
            """)
            progress_bar.setTextVisible(True)
            # Parse progress percentage
            try:
                progress_text = transfer['progress']
                if '%' in progress_text:
                    # Extract numeric value from percentage string
                    progress_value = float(progress_text.replace('%', '').strip())
                    progress_bar.setValue(int(progress_value))
                    progress_bar.setFormat(f"{progress_value:.1f}%")
                else:
                    # Handle non-percentage progress values
                    try:
                        progress_value = float(progress_text)
                        progress_bar.setValue(int(progress_value))
                        progress_bar.setFormat(f"{progress_value:.1f}%")
                    except (ValueError, TypeError):
                        progress_bar.setValue(0)
                        progress_bar.setFormat(str(progress_text))
            except (ValueError, TypeError, AttributeError):
                progress_bar.setValue(0)
                progress_bar.setFormat("—")
            
            progress_layout.addWidget(progress_bar)
            table.setCellWidget(row, 5, progress_widget)
            
            # Speed and Size with clean formatting
            speed_item = QTableWidgetItem(transfer['rate'])
            table.setItem(row, 6, speed_item)
            
            size_text = f"{transfer['transferred']} / {transfer['total']}"
            size_item = QTableWidgetItem(size_text)
            table.setItem(row, 7, size_item)
            
            # Log completed transfers
            transfer_id = transfer['id']
            current_status = transfer['status']
            last_status = self.last_logged_status.get(transfer_id)

            if current_status != last_status:
                if current_status == 'COMPLETED':
                    transferred_str = self.safe_format_size(transfer['transferred'])
                    total_str = self.safe_format_size(transfer['total'])
                    log_msg = (
                        f"ID: {transfer['id']} | Type: {transfer['type']} | "
                        f"Source: {transfer['source']} | Destination: {transfer['destination']} | "
                        f"Status: {transfer['status']} | Progress: {transfer['progress']} | "
                        f"Speed: {transfer['rate']} | Size: {transferred_str} / {total_str}"
                    )
                    logging.info(log_msg)
                self.last_logged_status[transfer_id] = current_status
    
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
            
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText("Are you sure you want to cancel the selected transfers?")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        
        if msg_box.exec_() == QMessageBox.Yes:
            for row in selected_rows:
                transfer_id = int(current_table.item(row, 0).text())
                if self.transfer_manager:
                    self.transfer_manager.cancel_transfer(transfer_id)
    
    def clear_completed(self):
        """Clear completed transfers from the history"""
        # This would require adding a method to the TransferManager
        # For now, we'll just refresh the display
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


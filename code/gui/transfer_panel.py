from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QTableWidget, QHBoxLayout, QPushButton
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QTableWidgetItem, QMessageBox
from PyQt5.QtCore import QTimer, Qt


class TransferPanel(QWidget):
    """Panel for displaying and managing file transfers"""
    
    def __init__(self, parent=None, transfer_manager=None):
        super().__init__(parent)
        self.transfer_manager = transfer_manager
        self.setup_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_transfers)
        self.timer.start(1000)  # Update every second
    
    def setup_ui(self):
        """Set up the transfer panel UI"""
        layout = QVBoxLayout(self)
        
        # Tabs for different transfer views
        self.tabs = QTabWidget()
        
        # Active transfers tab
        self.active_table = QTableWidget()
        self.setup_transfer_table(self.active_table)
        self.tabs.addTab(self.active_table, "Active")
        
        # Queued transfers tab
        self.queued_table = QTableWidget()
        self.setup_transfer_table(self.queued_table)
        self.tabs.addTab(self.queued_table, "Queued")
        
        # History tab
        self.history_table = QTableWidget()
        self.setup_transfer_table(self.history_table)
        self.tabs.addTab(self.history_table, "History")
        
        layout.addWidget(self.tabs)
        
        # Transfer controls
        controls_layout = QHBoxLayout()
        self.pause_button = QPushButton("Pause")
        self.resume_button = QPushButton("Resume")
        self.cancel_button = QPushButton("Cancel")
        self.clear_button = QPushButton("Clear Completed")
        
        self.pause_button.clicked.connect(self.pause_selected)
        self.resume_button.clicked.connect(self.resume_selected)
        self.cancel_button.clicked.connect(self.cancel_selected)
        self.clear_button.clicked.connect(self.clear_completed)
        
        controls_layout.addWidget(self.pause_button)
        controls_layout.addWidget(self.resume_button)
        controls_layout.addWidget(self.cancel_button)
        controls_layout.addWidget(self.clear_button)
        
        layout.addLayout(controls_layout)
    
    def setup_transfer_table(self, table):
        """Set up a transfer table with the correct columns"""
        headers = ["ID", "Type", "Source", "Destination", "Status", 
                  "Progress", "Speed", "Size"]
        
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        
        # Set up columns
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)  # Source
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)  # Destination
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Status
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Progress
        table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Speed
        table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Size
    
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
        
        # Update tab counters
        self.tabs.setTabText(0, f"Active ({len(transfers['active'])})")
        self.tabs.setTabText(1, f"Queued ({len(transfers['queued'])})")
        self.tabs.setTabText(2, f"History ({len(transfers['history'])})")
    
    def update_table(self, table, transfers):
        """Update a table with transfer data"""
        table.setRowCount(len(transfers))
        
        for row, transfer in enumerate(transfers):
            # ID
            table.setItem(row, 0, QTableWidgetItem(str(transfer['id'])))
            
            # Type
            table.setItem(row, 1, QTableWidgetItem(transfer['type']))
            
            # Source
            table.setItem(row, 2, QTableWidgetItem(transfer['source']))
            
            # Destination
            table.setItem(row, 3, QTableWidgetItem(transfer['destination']))
            
            # Status
            status_item = QTableWidgetItem(transfer['status'])
            table.setItem(row, 4, status_item)
            
            # Progress
            progress_item = QTableWidgetItem(transfer['progress'])
            table.setItem(row, 5, progress_item)
            
            # Speed
            table.setItem(row, 6, QTableWidgetItem(transfer['rate']))
            
            # Size
            size_text = f"{transfer['transferred']} / {transfer['total']}"
            table.setItem(row, 7, QTableWidgetItem(size_text))
            
            # Set row color based on status
            if 'COMPLETED' in transfer['status']:
                self._set_row_background(table, row, Qt.green, 0.2)
            elif 'FAILED' in transfer['status']:
                self._set_row_background(table, row, Qt.red, 0.2)
            elif 'PAUSED' in transfer['status']:
                self._set_row_background(table, row, Qt.yellow, 0.2)
    
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


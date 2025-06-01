from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDialogButtonBox
)
from PyQt5.QtCore import QSettings
from code.core.transfer_manager import TransferManager
from code.gui.custom_message_box import CustomMessageBox


class FileChunkSizeDialog(QDialog):
    def __init__(self, parent=None, transfer_manager: TransferManager = None, settings: QSettings = None):
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
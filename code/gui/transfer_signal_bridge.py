from PyQt5.QtCore import QObject, pyqtSignal
from code.core.transfer_manager import TransferType


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
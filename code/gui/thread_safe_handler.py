import os
import threading
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, pyqtSignal, QThread, QTimer
from code.gui.custom_message_box import CustomMessageBox

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
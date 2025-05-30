import os
import time
import logging
import threading
import hashlib # Added for SHA-256 hash calculation
import gc
import secrets
from typing import Dict, List, Callable, Optional, Tuple
from enum import Enum
from queue import Queue, PriorityQueue
from .sftp_client import SFTPClient
from ..utils.secure_string import SecureTemporaryCredentials

class TransferType(Enum):
    """Enum for different transfer types."""
    UPLOAD = 1
    DOWNLOAD = 2
    SERVER_TO_SERVER = 3

class TransferStatus(Enum):
    """Enum for transfer status."""
    QUEUED = 1
    IN_PROGRESS = 2
    COMPLETED = 3
    FAILED = 4
    PAUSED = 5
    CANCELED = 6

class TransferItem:
    """Represents a file transfer item in the queue."""
    def __init__(self, 
                transfer_type: TransferType,
                source_path: str,
                dest_path: str,
                priority: int = 1,
                source_config: Dict = None,
                dest_config: Dict = None,
                chunks: int = 10,
                progress_callback: Callable = None,
                overwrite_callback: Callable = None): # Added overwrite_callback
        """
        Initialize a transfer item.
        
        Args:
            transfer_type: Type of transfer (upload, download, server-to-server)
            source_path: Source file path
            dest_path: Destination file path
            priority: Priority level (lower = higher priority)
            source_config: Source server configuration (for server-to-server)
            dest_config: Destination server configuration (for server-to-server)
            chunks: Number of chunks to use for transfer
            progress_callback: Callback for progress updates (transfer_id, transferred_bytes, total_bytes)
            overwrite_callback: Callback for overwrite confirmation (file_path) -> bool
        """
        self.id = int(time.time() * 1000)  # Unique ID based on timestamp
        self.transfer_type = transfer_type
        self.source_path = source_path
        self.dest_path = dest_path
        self.priority = priority
        self.source_config = source_config or {}
        self.dest_config = dest_config or {}
        self.chunks = chunks
        self.status = TransferStatus.QUEUED
        self.progress = 0.0
        self.bytes_transferred = 0
        self.total_bytes = 0
        self.start_time = None
        self.end_time = None
        self.error_message = ""
        self.transfer_rate = 0.0
        self._progress_callback = progress_callback # Stored here
        self._overwrite_callback = overwrite_callback # Stored here
        self.source_hash = None # To store source file hash
        self.destination_hash = None # To store destination file hash
        self.pause_event = threading.Event()
        self.pause_event.set()  # Start as not paused
        self.cancel_event = threading.Event()

        
    def __lt__(self, other):
        """Compare transfers based on priority for the priority queue."""
        return self.priority < other.priority
        
    def to_dict(self) -> Dict:
        """Convert the transfer item to a dictionary for UI representation."""
        elapsed_time = 0
        if self.start_time:
            if self.end_time:
                elapsed_time = self.end_time - self.start_time
            else:
                elapsed_time = time.time() - self.start_time
        
        # Safely handle division by zero for bytes
        transferred_mb = self.bytes_transferred / (1024 * 1024) if self.bytes_transferred > 0 else 0
        total_mb = self.total_bytes / (1024 * 1024) if self.total_bytes > 0 else 0
                
        return {
            'id': self.id,
            'type': self.transfer_type.name,
            'source': self.source_path,
            'destination': self.dest_path,
            'status': self.status.name,
            'progress': f"{self.progress:.1f}%",
            'transferred': f"{transferred_mb:.2f} MB",
            'total': f"{total_mb:.2f} MB",
            'rate': f"{self.transfer_rate:.2f} MB/s",
            'elapsed_time': f"{elapsed_time:.1f}s",
            'error': self.error_message,
            'source_hash': self.source_hash if self.source_hash else "N/A", # Include hashes in dict
            'destination_hash': self.destination_hash if self.destination_hash else "N/A"
        }

class TransferManager:
    """
    Manages file transfers with queue, pause, resume, and cancel operations.
    Supports local-to-server and server-to-server transfers.
    """
    def __init__(self, max_concurrent=3, logger=None):  # Changed back to 3 for parallel processing
        """
        Initialize the transfer manager.
        
        Args:
            max_concurrent: Maximum number of concurrent transfers (3 for parallel processing)
            logger: Optional logger instance
        """
        self.transfer_queue = PriorityQueue()
        self.active_transfers = {}
        self.transfer_history = []
        self.max_concurrent = max_concurrent
        self.running = True
        self.lock = threading.Lock()
        self.worker_thread = None
        # Connection pool to manage multiple SFTP connections safely
        self.connection_pool = {}
        self.pool_lock = threading.Lock()
        
        # Set up logger
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
            
    def start(self):
        """Start the transfer manager worker thread."""
        if not self.worker_thread or not self.worker_thread.is_alive():
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker, daemon=True)
            self.worker_thread.start()
            self.logger.info("Transfer manager started")
            
    def stop(self):
        """Stop the transfer manager."""
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5.0)
            self.logger.info("Transfer manager stopped")
            
    def add_transfer(self, transfer_item: TransferItem) -> int:
        """
        Add a transfer item to the queue.
        
        Args:
            transfer_item: The transfer item to queue
            
        Returns:
            int: The ID of the transfer
        """
        self.transfer_queue.put((transfer_item.priority, transfer_item))
        self.logger.info(f"Transfer queued: {transfer_item.source_path} -> {transfer_item.dest_path}")
        return transfer_item.id
        
    def queue_upload(self, 
                    local_path: str, 
                    remote_path: str, 
                    server_config: Dict,
                    priority: int = 1,
                    chunks: int = 10,
                    progress_callback: Callable = None,
                    overwrite_callback: Callable = None) -> int:
        """
        Queue a file upload.
        
        Args:
            local_path: Path to local file
            remote_path: Destination path on server
            server_config: Server connection configuration
            priority: Transfer priority (lower = higher priority)
            chunks: Number of chunks for transfer
            progress_callback: Callback function for progress updates
            overwrite_callback: Callback function for overwrite confirmation
            
        Returns:
            int: Transfer ID
        """
        transfer = TransferItem(
            TransferType.UPLOAD,
            local_path,
            remote_path,
            priority,
            dest_config=server_config,
            chunks=chunks,
            progress_callback=progress_callback,
            overwrite_callback=overwrite_callback
        )
        
        if os.path.exists(local_path):
            transfer.total_bytes = os.path.getsize(local_path)
            return self.add_transfer(transfer)
        else:
            transfer.status = TransferStatus.FAILED
            transfer.error_message = f"Local file not found: {local_path}"
            self.transfer_history.append(transfer)
            self.logger.error(f"Cannot queue upload: {transfer.error_message}")
            return transfer.id
            
    def queue_download(self,
                     remote_path: str,
                     local_path: str,
                     server_config: Dict,
                     priority: int = 1,
                     chunks: int = 10,
                     progress_callback: Callable = None,
                     overwrite_callback: Callable = None) -> int:
        """
        Queue a file download.
        
        Args:
            remote_path: Path to remote file
            local_path: Destination path on local system
            server_config: Server connection configuration
            priority: Transfer priority (lower = higher priority)
            chunks: Number of chunks for transfer
            progress_callback: Callback function for progress updates
            overwrite_callback: Callback function for overwrite confirmation
            
        Returns:
            int: Transfer ID
        """
        transfer = TransferItem(
            TransferType.DOWNLOAD,
            remote_path,
            local_path,
            priority,
            source_config=server_config,
            chunks=chunks,
            progress_callback=progress_callback,
            overwrite_callback=overwrite_callback
        )
        
        # Create directory for the download if it doesn't exist
        try:
            os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        except Exception as e:
            transfer.status = TransferStatus.FAILED
            transfer.error_message = f"Failed to create local directory: {str(e)}"
            self.transfer_history.append(transfer)
            self.logger.error(f"Cannot queue download: {transfer.error_message}")
            return transfer.id
            
        return self.add_transfer(transfer)
        
    def queue_server_to_server(self,
                             source_path: str,
                             dest_path: str,
                             source_config: Dict,
                             dest_config: Dict,
                             priority: int = 1,
                             chunks: int = 10,
                             progress_callback: Callable = None,
                             overwrite_callback: Callable = None) -> int: # Added progress_callback here
        """
        Queue a server-to-server transfer.
        
        Args:
            source_path: Path on source server
            dest_path: Path on destination server
            source_config: Source server configuration
            dest_config: Destination server configuration
            priority: Transfer priority (lower = higher priority)
            chunks: Number of chunks for transfer
            progress_callback: Callback function for progress updates (transfer_id, transferred_bytes, total_bytes)
            overwrite_callback: Callback function for overwrite confirmation
            
        Returns:
            int: Transfer ID
        """
        transfer = TransferItem(
            TransferType.SERVER_TO_SERVER,
            source_path,
            dest_path,
            priority,
            source_config=source_config,
            dest_config=dest_config,
            chunks=chunks,
            progress_callback=progress_callback,
            overwrite_callback=overwrite_callback
        )
        
        return self.add_transfer(transfer)
        
    def pause_transfer(self, transfer_id: int) -> bool:
        """
        Pause an active transfer. Note: Currently just marks for pausing on next cycle.
        
        Args:
            transfer_id: ID of the transfer to pause
            
        Returns:
            bool: True if successful, False otherwise
        """
        with self.lock:
            if transfer_id in self.active_transfers:
                transfer = self.active_transfers[transfer_id]
                transfer.status = TransferStatus.PAUSED
                transfer.pause_event.clear()
                self.logger.info(f"Transfer paused: {transfer_id}")
                return True
        
        # Also check queued transfers
        queue_list = list(self.transfer_queue.queue)
        for _, item in queue_list:
            if item.id == transfer_id:
                item.status = TransferStatus.PAUSED
                self.logger.info(f"Queued transfer marked as paused: {transfer_id}")
                return True
                
        return False
        
    def resume_transfer(self, transfer_id: int) -> bool:
        """
        Resume a paused transfer.
        
        Args:
            transfer_id: ID of the transfer to resume
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Check in active transfers (rare case but possible)
        with self.lock:
            if transfer_id in self.active_transfers:
                transfer = self.active_transfers[transfer_id]
                if transfer.status == TransferStatus.PAUSED:
                    transfer.status = TransferStatus.IN_PROGRESS
                    transfer.pause_event.set()
                    self.logger.info(f"Active transfer resumed: {transfer_id}")
                    return True
                    
        # Check in history for paused transfers
        for item in self.transfer_history:
            if item.id == transfer_id and item.status == TransferStatus.PAUSED:
                with self.lock:
                    self.transfer_history.remove(item)
                    item.status = TransferStatus.QUEUED
                    self.transfer_queue.put((item.priority, item))
                    self.logger.info(f"Transfer resumed and requeued: {transfer_id}")
                return True
                
        return False
        
    def cancel_transfer(self, transfer_id: int) -> bool:
        """
        Cancel a transfer and automatically start next queued transfer if needed.
        
        Args:
            transfer_id: ID of the transfer to cancel
            
        Returns:
            bool: True if successful, False otherwise
        """
        canceled = False
        
        # Check active transfers first
        with self.lock:
            if transfer_id in self.active_transfers:
                transfer = self.active_transfers[transfer_id]
                transfer.status = TransferStatus.CANCELED
                transfer.cancel_event.set()
                transfer.cancel_event.set()
                self.logger.info(f"Active transfer canceled: {transfer_id}")
                canceled = True
                
                # Don't remove from active_transfers here - let _process_transfer handle it
                # This ensures the worker thread can start a new transfer automatically
                
        if not canceled:
            # Check queued transfers (need to rebuild queue)
            new_queue = PriorityQueue()
            
            while not self.transfer_queue.empty():
                try:
                    priority, item = self.transfer_queue.get(block=False)
                    if item.id == transfer_id:
                        item.status = TransferStatus.CANCELED
                        self.transfer_history.append(item)
                        canceled = True
                        self.logger.info(f"Queued transfer canceled: {transfer_id}")
                    else:
                        new_queue.put((priority, item))
                except:
                    break
                    
            self.transfer_queue = new_queue
            
        return canceled
        
    def get_transfer_status(self, transfer_id: int) -> Dict:
        """
        Get the status of a transfer.
        
        Args:
            transfer_id: ID of the transfer
            
        Returns:
            Dict: Status information or empty dict if not found
        """
        # Check active transfers
        with self.lock:
            if transfer_id in self.active_transfers:
                return self.active_transfers[transfer_id].to_dict()
                
        # Check queue
        queue_list = list(self.transfer_queue.queue)
        for _, item in queue_list:
            if item.id == transfer_id:
                return item.to_dict()
                
        # Check history
        for item in self.transfer_history:
            if item.id == transfer_id:
                return item.to_dict()
                
        return {}
        
    def get_all_transfers(self) -> Dict:
        """
        Get all transfers (active, queued, and history).
        
        Returns:
            Dict: Dictionary with all transfers
        """
        active = []
        queued = []
        history = []
        
        with self.lock:
            active = [transfer.to_dict() for transfer in self.active_transfers.values()]
            
        queue_list = list(self.transfer_queue.queue)
        queued = [item.to_dict() for _, item in queue_list]
        
        history = [item.to_dict() for item in self.transfer_history]
        
        return {
            'active': active,
            'queued': queued,
            'history': history
        }
        
    def _worker(self):
        """Worker thread that processes the transfer queue and maintains max concurrent transfers."""
        while self.running:
            try:
                # Check if we can start more transfers
                with self.lock:
                    active_count = len(self.active_transfers)
                
                # Start new transfers if we have slots available and items in queue
                while active_count < self.max_concurrent and not self.transfer_queue.empty():
                    try:
                        # Get next transfer from queue
                        _, transfer_item = self.transfer_queue.get(block=False)
                        
                        # Skip if paused or canceled
                        if transfer_item.status != TransferStatus.QUEUED:
                            if transfer_item.status == TransferStatus.PAUSED:
                                self.transfer_history.append(transfer_item)
                            continue
                            
                        # Start the transfer in a completely isolated thread
                        try:
                            transfer_thread = threading.Thread(
                                target=self._process_transfer,
                                args=(transfer_item,),
                                daemon=True,
                                name=f"Transfer-{transfer_item.id}"  # Name threads for debugging
                            )
                            
                            with self.lock:
                                self.active_transfers[transfer_item.id] = transfer_item
                                active_count = len(self.active_transfers)  # Update count
                                
                            transfer_thread.start()
                            self.logger.info(f"Started transfer {transfer_item.id}: {transfer_item.source_path} -> {transfer_item.dest_path}")
                            
                        except Exception as thread_error:
                            # If we can't start the thread, mark transfer as failed and continue
                            self.logger.error(f"Failed to start thread for transfer {transfer_item.id}: {str(thread_error)}")
                            transfer_item.status = TransferStatus.FAILED
                            transfer_item.error_message = f"Failed to start transfer thread: {str(thread_error)}"
                            with self.lock:
                                if transfer_item.id in self.active_transfers:
                                    del self.active_transfers[transfer_item.id]
                                self.transfer_history.append(transfer_item)
                            continue
                        
                    except Exception as queue_error:
                        self.logger.error(f"Error processing queue item: {str(queue_error)}")
                        # Continue processing other items instead of breaking
                        continue
                        
                # Clean up any completed/failed/canceled transfers from active list
                # This ensures slots become available immediately
                try:
                    with self.lock:
                        completed_transfers = []
                        for transfer_id, transfer in self.active_transfers.items():
                            if transfer.status in [TransferStatus.COMPLETED, TransferStatus.FAILED, 
                                                 TransferStatus.CANCELED]:
                                completed_transfers.append(transfer_id)
                        
                        for transfer_id in completed_transfers:
                            transfer = self.active_transfers[transfer_id]
                            del self.active_transfers[transfer_id]
                            if transfer not in self.transfer_history:
                                self.transfer_history.append(transfer)
                            self.logger.info(f"Removed completed transfer {transfer_id} from active list")
                            
                except Exception as cleanup_error:
                    self.logger.error(f"Error during active transfers cleanup: {str(cleanup_error)}")
                        
            except Exception as worker_error:
                # Log the error but keep the worker running
                self.logger.error(f"Error in transfer worker main loop: {str(worker_error)}", exc_info=True)
                # Don't break - keep the worker running
                    
            # Sleep briefly to prevent CPU thrashing, but check frequently for new slots
            time.sleep(0.2)

    def _calculate_local_file_sha256(self, file_path: str) -> Optional[str]:
        """
        Calculates the SHA-256 hash of a local file.

        Args:
            file_path: Path to the local file.

        Returns:
            str: The SHA-256 hash of the file if successful, None otherwise.
        """
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                # Read and update hash string value in blocks of 4K
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except FileNotFoundError:
            self.logger.error(f"Local file not found for hash calculation: {file_path}")
            return None
        except Exception as e:
            self.logger.error(f"Error calculating local file SHA-256 for {file_path}: {str(e)}")
            return None
        
            
    def _process_transfer(self, transfer: TransferItem):
        """
        Process a single transfer item with proper error isolation.
        Each transfer gets its own dedicated SFTP connection.
        
        Args:
            transfer: The transfer item to process
        """

        source_client = None
        dest_client = None

        source_config = None
        dest_config = None

        # Connect based on transfer type - handle SecureString passwords
        if transfer.transfer_type == TransferType.UPLOAD or transfer.transfer_type == TransferType.SERVER_TO_SERVER:
            dest_client = SFTPClient(logger=self.logger)
            dest_config = transfer.dest_config.copy()
            dest_config.pop('name', None)
            dest_config.pop('has_password', None)
            dest_config.pop('has_passphrase', None) # Also remove has_passphrase
            # Convert SecureString to plain string for connection
            if 'password' in dest_config and hasattr(dest_config['password'], 'get_value'):
                dest_config['password'] = dest_config['password'].get_value()
            if 'passphrase' in dest_config and hasattr(dest_config['passphrase'], 'get_value'):
                dest_config['passphrase'] = dest_config['passphrase'].get_value()
            
        if transfer.transfer_type == TransferType.DOWNLOAD or transfer.transfer_type == TransferType.SERVER_TO_SERVER:
            source_client = SFTPClient(logger=self.logger)
            source_config = transfer.source_config.copy()
            source_config.pop('name', None)
            source_config.pop('has_password', None)
            source_config.pop('has_passphrase', None) # Also remove has_passphrase
            # Convert SecureString to plain string for connection
            if 'password' in source_config and hasattr(source_config['password'], 'get_value'):
                source_config['password'] = source_config['password'].get_value()
            if 'passphrase' in source_config and hasattr(source_config['passphrase'], 'get_value'):
                source_config['passphrase'] = source_config['passphrase'].get_value()

        try:
            # Mark as started
            transfer.status = TransferStatus.IN_PROGRESS
            transfer.start_time = time.time()

            # --- PAUSE/RESUME SUPPORT: Wait here if paused before starting ---
            while not transfer.pause_event.is_set():
                time.sleep(0.2)

            # --- STEP 1: Calculate Source File Hash ---
            source_hash = None
            if transfer.transfer_type == TransferType.UPLOAD:
                # Local file hash
                source_hash = self._calculate_local_file_sha256(transfer.source_path)
                if source_hash is None:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = f"Failed to calculate SHA-256 for local source file: {transfer.source_path}"
                    self.logger.error(transfer.error_message)
                    return
                transfer.source_hash = source_hash
                self.logger.info(f"Local source hash for {transfer.source_path}: {source_hash}")
                pass

            elif transfer.transfer_type == TransferType.DOWNLOAD:
                # Remote source hash
                with SecureTemporaryCredentials(source_config) as temp_params:
                    if not source_client.connect(**temp_params):
                        transfer.status = TransferStatus.FAILED
                        transfer.error_message = "Failed to connect to source server"
                        self.logger.error(transfer.error_message)
                        return
                source_hash = source_client.get_remote_file_sha256(transfer.source_path)
                if source_hash is None:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = f"Failed to calculate SHA-256 for remote source file: {transfer.source_path}"
                    self.logger.error(transfer.error_message)
                    return
                transfer.source_hash = source_hash
                self.logger.info(f"Remote source hash for {transfer.source_path}: {source_hash}")
                pass

            elif transfer.transfer_type == TransferType.SERVER_TO_SERVER:
                with SecureTemporaryCredentials(source_config) as temp_params:
                    if not source_client.connect(**temp_params):
                        transfer.status = TransferStatus.FAILED
                        transfer.error_message = "Failed to connect to source server"
                        self.logger.error(transfer.error_message)
                        return
                source_hash = source_client.get_remote_file_sha256(transfer.source_path)
                if source_hash is None:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = f"Failed to calculate SHA-256 for remote source file (S2S): {transfer.source_path}"
                    self.logger.error(transfer.error_message)
                    return
                transfer.source_hash = source_hash
                self.logger.info(f"Remote source hash for {transfer.source_path}: {source_hash}")
                pass


            # --- STEP 2: Perform the actual file transfer ---
            result = False

            # Progress callback wrapper for SFTPClient
            def sftp_progress_wrapper(bytes_transferred, total_bytes, percent):
                try:
                    # First check if transfer is being canceled or has already completed
                    if transfer.cancel_event.is_set() or transfer.status in [TransferStatus.CANCELED, TransferStatus.COMPLETED, TransferStatus.FAILED]:
                        return
                    
                    transfer.bytes_transferred = bytes_transferred
                    transfer.total_bytes = total_bytes
                    transfer.progress = percent
                    elapsed = time.time() - transfer.start_time
                    if elapsed > 0:
                        transfer.transfer_rate = bytes_transferred / elapsed / (1024 * 1024)  # MB/s
                    
                    # Call the TransferItem's stored progress callback if it exists and transfer is still active
                    if transfer._progress_callback and transfer.status == TransferStatus.IN_PROGRESS:
                        try:
                            # The stored callback expects (transfer_id, transferred_bytes, total_bytes)
                            transfer._progress_callback(transfer.id, bytes_transferred, total_bytes)
                        except Exception as e:
                            self.logger.error(f"Error in transfer {transfer.id} progress callback: {str(e)}")
                            # Disable further progress callbacks on error to prevent crashes
                            transfer._progress_callback = None
                    
                    # --- PAUSE/RESUME SUPPORT: Wait here if paused during transfer ---
                    while not transfer.pause_event.is_set():
                        time.sleep(0.2)

                    if transfer.cancel_event.is_set():
                        transfer.status = TransferStatus.CANCELED
                        self.logger.info(f"Transfer {transfer.id} canceled during progress update.")
                        return
                    # Check if transfer was canceled or paused
                    if transfer.status in [TransferStatus.CANCELED, TransferStatus.PAUSED]:
                        raise InterruptedError("Transfer was canceled or paused")
                except Exception as e:
                    self.logger.error(f"Error in progress wrapper for transfer {transfer.id}: {str(e)}")
                    # Disable progress callback on error to prevent further crashes
                    transfer._progress_callback = None
            
            # Process based on transfer type with isolated error handling
            if transfer.transfer_type == TransferType.UPLOAD:

                # Upload file with overwrite callback
                def upload_overwrite_callback(remote_path):
                    # For non-GUI transfers, we'll log and return True (allow overwrite)
                    # GUI transfers will provide their own callback
                    if hasattr(transfer, '_overwrite_callback') and transfer._overwrite_callback:
                        return transfer._overwrite_callback(remote_path)
                    else:
                        self.logger.warning(f"File exists on remote server, proceeding with overwrite: {remote_path}")
                        return True
                    
                with SecureTemporaryCredentials(dest_config) as temp_params:
                    if not dest_client.connect(**temp_params):
                        transfer.status = TransferStatus.FAILED
                        transfer.error_message = "Failed to connect to destination server for file transfer"
                        self.logger.error(transfer.error_message)
                        return
                
                # Upload file
                result = dest_client.upload_file(
                    transfer.source_path, 
                    transfer.dest_path,
                    transfer.chunks,
                    sftp_progress_wrapper,
                    upload_overwrite_callback
                )
                    
                if transfer.cancel_event.is_set():
                    transfer.status = TransferStatus.CANCELED
                    self.logger.info(f"Transfer {transfer.id} canceled after upload_file call.")
                    return
                if not result:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = "Upload failed"
                    
            elif transfer.transfer_type == TransferType.DOWNLOAD:

                # Download file with overwrite callback
                def download_overwrite_callback(local_path):
                    # For non-GUI transfers, we'll log and return True (allow overwrite)
                    # GUI transfers will provide their own callback
                    if hasattr(transfer, '_overwrite_callback') and transfer._overwrite_callback:
                        return transfer._overwrite_callback(local_path)
                    else:
                        self.logger.warning(f"File exists locally, proceeding with overwrite: {local_path}")
                        return True
                        
                # Download file
                result = source_client.download_file(
                    transfer.source_path,
                    transfer.dest_path,
                    transfer.chunks,
                    sftp_progress_wrapper,
                    download_overwrite_callback
                )

                if transfer.cancel_event.is_set():
                    transfer.status = TransferStatus.CANCELED
                    self.logger.info(f"Transfer {transfer.id} canceled after download_file call.")
                    return  
                if not result:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = "Download failed"
                    
            elif transfer.transfer_type == TransferType.SERVER_TO_SERVER:

                # Server-to-server overwrite callback
                def s2s_overwrite_callback(dest_path):
                    # For non-GUI transfers, we'll log and return True (allow overwrite)
                    # GUI transfers will provide their own callback
                    if hasattr(transfer, '_overwrite_callback') and transfer._overwrite_callback:
                        return transfer._overwrite_callback(dest_path)
                    else:
                        self.logger.warning(f"File exists on destination server, proceeding with overwrite: {dest_path}")
                        return True
                        
                with SecureTemporaryCredentials(dest_config) as temp_params:
                    if not dest_client.connect(**temp_params):
                        transfer.status = TransferStatus.FAILED
                        transfer.error_message = "Failed to connect to destination server for file transfer"
                        self.logger.error(transfer.error_message)
                        return
                
                # server to server file transfer     
                client = SFTPClient(logger=self.logger)      
                result = client.server_to_server_transfer(
                    source_config,
                    dest_config,
                    transfer.source_path,
                    transfer.dest_path,
                    chunks=transfer.chunks,
                    progress_callback=sftp_progress_wrapper,
                    overwrite_callback=s2s_overwrite_callback
                )
                if transfer.cancel_event.is_set():
                    transfer.status = TransferStatus.CANCELED
                    self.logger.info(f"Transfer {transfer.id} canceled after server_to_server_transfer call.")
                    return
                # Server to server using buffer of our machine, does not store on disk
                # result = client.stream_remote_to_remote(
                #     source_client,
                #     transfer.source_path,
                #     dest_client,
                #     transfer.dest_path,
                #     progress_callback=sftp_progress_wrapper, # Pass our wrapper
                #     overwrite_callback=s2s_overwrite_callback
                # )

                if not result:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = transfer.error_message if transfer.error_message else "Server to server file transfer failed"
                    self.logger.error(f"Failed: {transfer.error_message}")
                    return

            # --- STEP 3: Calculate Destination File Hash and Compare ---
            destination_hash = None
            if transfer.transfer_type == TransferType.UPLOAD:
                # Remote destination hash
                with SecureTemporaryCredentials(dest_config) as temp_params:
                    if not dest_client.connect(**temp_params):
                        transfer.status = TransferStatus.FAILED
                        transfer.error_message = "Failed to connect to destination server for hash verification"
                        self.logger.error(transfer.error_message)
                        return
                
                destination_hash = dest_client.get_remote_file_sha256(transfer.dest_path)
                if destination_hash is None:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = f"Failed to calculate SHA-256 for remote destination file: {transfer.dest_path}"
                    self.logger.error(transfer.error_message)
                    return
                
                transfer.destination_hash = destination_hash
                self.logger.info(f"Remote destination hash for {transfer.dest_path}: {destination_hash}")

            elif transfer.transfer_type == TransferType.DOWNLOAD:
                # Local destination hash
                destination_hash = self._calculate_local_file_sha256(transfer.dest_path)
                if destination_hash is None:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = f"Failed to calculate SHA-256 for local destination file: {transfer.dest_path}"
                    self.logger.error(transfer.error_message)
                    return
                transfer.destination_hash = destination_hash
                self.logger.info(f"Local destination hash for {transfer.dest_path}: {destination_hash}")

            elif transfer.transfer_type == TransferType.SERVER_TO_SERVER:
                # Remote destination hash (S2S)
                with SecureTemporaryCredentials(dest_config) as temp_params:
                    if not dest_client.connect(**temp_params):
                        transfer.status = TransferStatus.FAILED
                        transfer.error_message = "Failed to connect to destination server for hash verification (S2S)"
                        self.logger.error(transfer.error_message)
                        return
                
                destination_hash = dest_client.get_remote_file_sha256(transfer.dest_path)
                if destination_hash is None:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = f"Failed to calculate SHA-256 for remote destination file (S2S): {transfer.dest_path}"
                    self.logger.error(transfer.error_message)
                    return
                
                transfer.destination_hash = destination_hash
                self.logger.info(f"Remote destination hash for {transfer.dest_path}: {destination_hash}")


            # --- STEP 4: Compare Hashes ---
            # Disable progress callback EARLY to prevent threading issues during completion
            original_callback = transfer._progress_callback
            transfer._progress_callback = None
            
            # Add a small delay to ensure any in-flight progress callbacks complete
            time.sleep(0.1)
            
            if source_hash and destination_hash and source_hash == destination_hash:
                transfer.status = TransferStatus.COMPLETED
                self.logger.info(f"Integrity check passed for {transfer.source_path} -> {transfer.dest_path}")
                
                # Trigger final progress callback manually in a safe way
                if original_callback and transfer.total_bytes > 0:
                    try:
                        # Use a separate thread to avoid blocking and ensure it's the last callback
                        final_callback_thread = threading.Thread(
                            target=lambda: self._safe_final_callback(original_callback, transfer),
                            daemon=True
                        )
                        final_callback_thread.start()
                    except Exception as callback_error:
                        self.logger.error(f"Error in final progress callback for transfer {transfer.id}: {str(callback_error)}")
            else:
                transfer.status = TransferStatus.FAILED
                transfer.error_message = f"File integrity check failed for {transfer.source_path} -> {transfer.dest_path}: Source and destination file hash do not match. Source Hash: {source_hash}, Dest Hash: {destination_hash}"
                self.logger.error(transfer.error_message)

            # transfer.status = TransferStatus.COMPLETED

        except InterruptedError:
            # Transfer was canceled or paused - this is normal
            self.logger.info(f"Transfer {transfer.id} was interrupted (canceled/paused)")
            
        except Exception as e:
            # Catch any other unexpected errors to prevent worker thread from stopping
            transfer.status = TransferStatus.FAILED
            transfer.error_message = f"Unexpected error: {str(e)}"
            self.logger.error(f"Unexpected error in transfer {transfer.id}: {str(e)}", exc_info=True)
            
        finally:
            # Always disconnect the client when transfer is complete with enhanced error isolation
            try:
                # Disable any remaining progress callbacks immediately to prevent race conditions
                transfer._progress_callback = None
                
                # Add a brief delay to ensure any in-flight callbacks complete before disconnection
                time.sleep(0.05)
                
                # Disconnect clients in separate try-catch blocks to isolate failures
                if source_client:
                    try:
                        if hasattr(source_client, 'ssh') and source_client.ssh:
                            source_client.disconnect()
                            self.logger.debug(f"Source client disconnected for transfer {transfer.id}")
                    except Exception as src_disconnect_error:
                        self.logger.warning(f"Error disconnecting source client for transfer {transfer.id}: {str(src_disconnect_error)}")
                
                if dest_client:
                    try:
                        if hasattr(dest_client, 'ssh') and dest_client.ssh:
                            dest_client.disconnect()
                            self.logger.debug(f"Destination client disconnected for transfer {transfer.id}")
                    except Exception as dest_disconnect_error:
                        self.logger.warning(f"Error disconnecting destination client for transfer {transfer.id}: {str(dest_disconnect_error)}")
                
                self.logger.info(f"Disconnected SFTP client for transfer {transfer.id}")
                
            except Exception as disconnect_error:
                self.logger.warning(f"Error in client disconnection process for transfer {transfer.id}: {str(disconnect_error)}")
            
            # Record end time and cleanup with enhanced safety
            try:
                transfer.end_time = time.time()
                
                # Clear client references to help garbage collection
                source_client = None
                dest_client = None
                source_config = None
                dest_config = None
                
                # Force garbage collection to clear any lingering credential references
                gc.collect()
                
                # Move from active to history with proper synchronization
                cleanup_successful = False
                try:
                    with self.lock:
                        if transfer.id in self.active_transfers:
                            del self.active_transfers[transfer.id]
                            # Only add to history if not already there
                            if transfer not in self.transfer_history:
                                self.transfer_history.append(transfer)
                            cleanup_successful = True
                except Exception as lock_error:
                    self.logger.error(f"Error during lock-protected cleanup for transfer {transfer.id}: {str(lock_error)}")
                    # Try without lock as fallback
                    try:
                        if transfer.id in self.active_transfers:
                            del self.active_transfers[transfer.id]
                        if transfer not in self.transfer_history:
                            self.transfer_history.append(transfer)
                        cleanup_successful = True
                    except Exception as fallback_error:
                        self.logger.error(f"Fallback cleanup also failed for transfer {transfer.id}: {str(fallback_error)}")

                if cleanup_successful:
                    self.logger.info(f"Transfer {transfer.id} completed with status {transfer.status.name}: {transfer.source_path} -> {transfer.dest_path}")
                else:
                    self.logger.error(f"Transfer {transfer.id} completed but cleanup failed")
            
            except Exception as cleanup_error:
                self.logger.error(f"Error during cleanup for transfer {transfer.id}: {str(cleanup_error)}")
                # Even if cleanup fails, log the transfer completion
                try:
                    self.logger.info(f"Transfer {transfer.id} finished with status {transfer.status.name} (cleanup errors occurred)")
                except:
                    self.logger.error(f"Transfer {transfer.id} finished but status logging failed")
    
    def _safe_final_callback(self, callback, transfer):
        """Safely execute the final progress callback for a completed transfer"""
        try:
            if callback and transfer.total_bytes > 0:
                # Call with 100% completion
                callback(transfer.id, transfer.total_bytes, transfer.total_bytes)
        except Exception as e:
            self.logger.error(f"Error in safe final callback for transfer {transfer.id}: {str(e)}")

    def upload_file(self, local_path: str, remote_path: str, server_config: Dict, progress_callback: Callable = None, overwrite_callback: Callable = None) -> int:
        """
        Convenience method for uploading a file using the active connection.
        
        Args:
            local_path: Path to local file
            remote_path: Destination path on server
            server_config: active connection config
            progress_callback: Callback function for progress updates
            overwrite_callback: Callback function for overwrite confirmation
            
        Returns:
            int: Transfer ID
        """
        
        return self.queue_upload(
            local_path=local_path,
            remote_path=remote_path,
            server_config=server_config,
            progress_callback=progress_callback,
            overwrite_callback=overwrite_callback
        )
    
    def download_file(self, remote_path: str, local_path: str, server_config: Dict, progress_callback: Callable = None, overwrite_callback: Callable = None) -> int:
        """
        Convenience method for downloading a file using the active connection.
        
        Args:
            remote_path: Path to remote file
            local_path: Destination path on local system
            server_config: active connection config
            progress_callback: Callback function for progress updates
            overwrite_callback: Callback function for overwrite confirmation
            
        Returns:
            int: Transfer ID
        """
        return self.queue_download(
            remote_path=remote_path,
            local_path=local_path,
            server_config=server_config,
            progress_callback=progress_callback,
            overwrite_callback=overwrite_callback
        )


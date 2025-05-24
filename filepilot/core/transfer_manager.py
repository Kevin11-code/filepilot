import os
import time
import logging
import threading
from typing import Dict, List, Callable, Optional, Tuple
from enum import Enum
from queue import Queue, PriorityQueue
from .sftp_client import SFTPClient

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
                chunks: int = 10):
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
                
        return {
            'id': self.id,
            'type': self.transfer_type.name,
            'source': self.source_path,
            'destination': self.dest_path,
            'status': self.status.name,
            'progress': f"{self.progress:.1f}%",
            'transferred': f"{self.bytes_transferred / (1024 * 1024):.2f} MB",
            'total': f"{self.total_bytes / (1024 * 1024):.2f} MB",
            'rate': f"{self.transfer_rate:.2f} MB/s",
            'elapsed_time': f"{elapsed_time:.1f}s",
            'error': self.error_message
        }

class TransferManager:
    """
    Manages file transfers with queue, pause, resume, and cancel operations.
    Supports local-to-server and server-to-server transfers.
    """
    def __init__(self, max_concurrent=3, logger=None):
        """
        Initialize the transfer manager.
        
        Args:
            max_concurrent: Maximum number of concurrent transfers
            logger: Optional logger instance
        """
        self.transfer_queue = PriorityQueue()
        self.active_transfers = {}
        self.transfer_history = []
        self.max_concurrent = max_concurrent
        self.running = True
        self.lock = threading.Lock()
        self.worker_thread = None
        
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
                    chunks: int = 10) -> int:
        """
        Queue a file upload.
        
        Args:
            local_path: Path to local file
            remote_path: Destination path on server
            server_config: Server connection configuration
            priority: Transfer priority (lower = higher priority)
            chunks: Number of chunks for transfer
            
        Returns:
            int: Transfer ID
        """
        transfer = TransferItem(
            TransferType.UPLOAD,
            local_path,
            remote_path,
            priority,
            dest_config=server_config,
            chunks=chunks
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
                     chunks: int = 10) -> int:
        """
        Queue a file download.
        
        Args:
            remote_path: Path to remote file
            local_path: Destination path on local system
            server_config: Server connection configuration
            priority: Transfer priority (lower = higher priority)
            chunks: Number of chunks for transfer
            
        Returns:
            int: Transfer ID
        """
        transfer = TransferItem(
            TransferType.DOWNLOAD,
            remote_path,
            local_path,
            priority,
            source_config=server_config,
            chunks=chunks
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
                             chunks: int = 10) -> int:
        """
        Queue a server-to-server transfer.
        
        Args:
            source_path: Path on source server
            dest_path: Path on destination server
            source_config: Source server configuration
            dest_config: Destination server configuration
            priority: Transfer priority (lower = higher priority)
            chunks: Number of chunks for transfer
            
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
            chunks=chunks
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
        Cancel a transfer.
        
        Args:
            transfer_id: ID of the transfer to cancel
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Check active transfers
        with self.lock:
            if transfer_id in self.active_transfers:
                transfer = self.active_transfers[transfer_id]
                transfer.status = TransferStatus.CANCELED
                self.logger.info(f"Transfer canceled: {transfer_id}")
                return True
                
        # Check queued transfers (need to rebuild queue)
        new_queue = PriorityQueue()
        canceled = False
        
        while not self.transfer_queue.empty():
            priority, item = self.transfer_queue.get()
            if item.id == transfer_id:
                item.status = TransferStatus.CANCELED
                self.transfer_history.append(item)
                canceled = True
                self.logger.info(f"Queued transfer canceled: {transfer_id}")
            else:
                new_queue.put((priority, item))
                
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
        """Worker thread that processes the transfer queue."""
        while self.running:
            # Check if we can start more transfers
            with self.lock:
                active_count = len(self.active_transfers)
                
            if active_count < self.max_concurrent and not self.transfer_queue.empty():
                try:
                    # Get next transfer from queue
                    _, transfer_item = self.transfer_queue.get(block=False)
                    
                    # Skip if paused or canceled
                    if transfer_item.status != TransferStatus.QUEUED:
                        if transfer_item.status == TransferStatus.PAUSED:
                            self.transfer_history.append(transfer_item)
                        continue
                        
                    # Start the transfer
                    transfer_thread = threading.Thread(
                        target=self._process_transfer,
                        args=(transfer_item,),
                        daemon=True
                    )
                    
                    with self.lock:
                        self.active_transfers[transfer_item.id] = transfer_item
                        
                    transfer_thread.start()
                    self.logger.info(f"Started transfer: {transfer_item.source_path} -> {transfer_item.dest_path}")
                    
                except Exception as e:
                    self.logger.error(f"Error in transfer worker: {str(e)}")
                    
            # Sleep briefly to prevent CPU thrashing
            time.sleep(0.1)
            
    def _process_transfer(self, transfer: TransferItem):
        """
        Process a single transfer item.
        
        Args:
            transfer: The transfer item to process
        """
        try:
            # Mark as started
            transfer.status = TransferStatus.IN_PROGRESS
            transfer.start_time = time.time()
            
            # Create SFTP client
            client = SFTPClient(logger=self.logger)
            
            # Progress callback
            def update_progress(bytes_transferred, total_bytes, percent):
                transfer.bytes_transferred = bytes_transferred
                transfer.total_bytes = total_bytes
                transfer.progress = percent
                elapsed = time.time() - transfer.start_time
                if elapsed > 0:
                    transfer.transfer_rate = bytes_transferred / elapsed / (1024 * 1024)  # MB/s
                
                # Check if transfer was canceled or paused
                if transfer.status in [TransferStatus.CANCELED, TransferStatus.PAUSED]:
                    raise InterruptedError("Transfer was canceled or paused")
            
            # Process based on transfer type
            if transfer.transfer_type == TransferType.UPLOAD:
                # Upload file
                result = False
                if client.connect(**transfer.dest_config):
                    result = client.upload_file(
                        transfer.source_path, 
                        transfer.dest_path,
                        transfer.chunks,
                        update_progress
                    )
                    client.disconnect()
                    
                if result:
                    transfer.status = TransferStatus.COMPLETED
                else:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = "Upload failed"
                    
            elif transfer.transfer_type == TransferType.DOWNLOAD:
                # Download file
                result = False
                if client.connect(**transfer.source_config):
                    result = client.download_file(
                        transfer.source_path,
                        transfer.dest_path,
                        transfer.chunks,
                        update_progress
                    )
                    client.disconnect()
                    
                if result:
                    transfer.status = TransferStatus.COMPLETED
                else:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = "Download failed"
                    
            elif transfer.transfer_type == TransferType.SERVER_TO_SERVER:
                # Server-to-server transfer
                result = client.server_to_server_transfer(
                    transfer.source_config,
                    transfer.dest_config,
                    transfer.source_path,
                    transfer.dest_path,
                    chunks=transfer.chunks,
                    progress_callback=update_progress
                )
                
                if result:
                    transfer.status = TransferStatus.COMPLETED
                else:
                    transfer.status = TransferStatus.FAILED
                    transfer.error_message = "Server-to-server transfer failed"
                    
        except InterruptedError:
            # Transfer was canceled or paused
            pass
            
        except Exception as e:
            transfer.status = TransferStatus.FAILED
            transfer.error_message = str(e)
            self.logger.error(f"Transfer error: {str(e)}")
            
        finally:
            # Record end time and cleanup
            transfer.end_time = time.time()
            
            # Move from active to history
            with self.lock:
                if transfer.id in self.active_transfers:
                    del self.active_transfers[transfer.id]
                    self.transfer_history.append(transfer)
                    
            self.logger.info(f"Transfer completed with status {transfer.status.name}: {transfer.source_path} -> {transfer.dest_path}")
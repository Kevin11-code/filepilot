import os
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional
from code.config.path_utils import get_user_log_path

class LoggerSetup:
    """
    Utility class for setting up logging with console and file output.
    """
    @staticmethod
    def setup_logger(name: str = "filepilot", 
                    log_file: str = None, 
                    level: int = logging.INFO, 
                    max_size: int = 10 * 1024 * 1024,  # 10 MB
                    backup_count: int = 5,
                    log_to_console: bool = True) -> logging.Logger:
        """
        Set up a logger with console and file handlers.
        
        Args:
            name: Logger name
            log_file: Path to log file (None to disable file logging)
            level: Logging level
            max_size: Maximum log file size before rotation
            backup_count: Number of backup log files to keep
            log_to_console: Whether to log to console
            
        Returns:
            logging.Logger: Configured logger instance
        """
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # Clear existing handlers
        logger.handlers = []
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Console handler
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # File handler
        if log_file is None:
            log_file = get_user_log_path()
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
            
        # Create rotating file handler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_size,
            backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        return logger
"""
Centralized logging configuration for the memory system
"""
import logging
import logging.handlers
import os
import sys
from typing import Optional
from datetime import datetime


class MemorySystemLogger:
    """Centralized logging system for the memory application"""
    
    def __init__(self, 
                 log_level: str = "INFO",
                 log_file: Optional[str] = None,
                 max_file_size: int = 10 * 1024 * 1024,  # 10MB
                 backup_count: int = 5):
        
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.log_file = log_file or "logs/memory_system.log"
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        
        # Ensure log directory exists
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up the logging configuration"""
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        
        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        
        # Error file handler
        error_handler = logging.handlers.RotatingFileHandler(
            self.log_file.replace('.log', '_errors.log'),
            maxBytes=self.max_file_size,
            backupCount=self.backup_count
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        
        # Security audit handler
        security_handler = logging.handlers.RotatingFileHandler(
            self.log_file.replace('.log', '_security.log'),
            maxBytes=self.max_file_size,
            backupCount=self.backup_count
        )
        security_handler.setLevel(logging.WARNING)
        security_handler.setFormatter(detailed_formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(error_handler)
        
        # Configure security logger
        security_logger = logging.getLogger('security_audit')
        security_logger.setLevel(logging.WARNING)
        security_logger.addHandler(security_handler)
        security_logger.propagate = False  # Don't propagate to root logger
        
        # Configure application loggers
        self._configure_application_loggers()
    
    def _configure_application_loggers(self):
        """Configure specific application loggers"""
        # Database logger
        db_logger = logging.getLogger('database')
        db_logger.setLevel(logging.INFO)
        
        # API logger
        api_logger = logging.getLogger('api')
        api_logger.setLevel(logging.INFO)
        
        # Consolidation logger
        consolidation_logger = logging.getLogger('consolidation')
        consolidation_logger.setLevel(logging.INFO)
        
        # Performance logger
        perf_logger = logging.getLogger('performance')
        perf_logger.setLevel(logging.INFO)
    
    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger instance"""
        return logging.getLogger(name)
    
    def log_performance(self, operation: str, duration: float, details: dict = None):
        """Log performance metrics"""
        perf_logger = logging.getLogger('performance')
        message = f"PERF: {operation} took {duration:.3f}s"
        if details:
            message += f" - {details}"
        perf_logger.info(message)
    
    def log_database_operation(self, operation: str, table: str, duration: float = None):
        """Log database operations"""
        db_logger = logging.getLogger('database')
        message = f"DB: {operation} on {table}"
        if duration is not None:
            message += f" ({duration:.3f}s)"
        db_logger.info(message)
    
    def log_api_request(self, method: str, endpoint: str, status_code: int, duration: float = None):
        """Log API requests"""
        api_logger = logging.getLogger('api')
        message = f"API: {method} {endpoint} -> {status_code}"
        if duration is not None:
            message += f" ({duration:.3f}s)"
        api_logger.info(message)
    
    def log_consolidation_event(self, event: str, details: dict = None):
        """Log consolidation events"""
        consolidation_logger = logging.getLogger('consolidation')
        message = f"CONSOLIDATION: {event}"
        if details:
            message += f" - {details}"
        consolidation_logger.info(message)
    
    def log_security_event(self, event_type: str, details: dict = None):
        """Log security events"""
        security_logger = logging.getLogger('security_audit')
        message = f"SECURITY: {event_type}"
        if details:
            message += f" - {details}"
        security_logger.warning(message)


class PerformanceTimer:
    """Context manager for timing operations"""
    
    def __init__(self, operation_name: str, logger: MemorySystemLogger):
        self.operation_name = operation_name
        self.logger = logger
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            self.logger.log_performance(self.operation_name, duration)


# Global logger instance
def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    return logging.getLogger(name)


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> MemorySystemLogger:
    """Set up logging for the application"""
    return MemorySystemLogger(log_level=log_level, log_file=log_file)


# Initialize default logger
default_logger = setup_logging()

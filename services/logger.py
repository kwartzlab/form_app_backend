import logging
import sys
from functools import wraps
import time
import uuid
from flask import request, g

def setup_logger():
    """Configure application logger for production."""
    logger = logging.getLogger('form_app')
    logger.setLevel(logging.INFO)
    
    # Console handler (stdout for container logs)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    
    # JSON-like format for easier parsing
    formatter = logging.Formatter(
        '{"time":"%(asctime)s", "level":"%(levelname)s", "name":"%(name)s", '
        '"message":"%(message)s", "request_id":"%(request_id)s"}'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

# Create logger instance
logger = logging.getLogger('form_app')

class RequestIDFilter(logging.Filter):
    """Add request ID to all log records."""
    def filter(self, record):
        record.request_id = getattr(g, 'request_id', 'no-request')
        return True

def log_execution_time(func):
    """Decorator to log function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        func_name = func.__name__
        logger.info(f"Starting {func_name}")
        
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start
            logger.info(f"Completed {func_name}", extra={
                'duration_seconds': f"{duration:.2f}"
            })
            return result
        except Exception as e:
            duration = time.time() - start
            logger.error(f"Failed {func_name}", extra={
                'duration_seconds': f"{duration:.2f}",
                'error': str(e)
            })
            raise
    
    return wrapper
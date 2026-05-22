import logging
import json
from typing import Any, Dict
from datetime import datetime
from pythonjsonlogger import jsonlogger

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter for structured logging.
    
    Adds correlation ID and request context to all log records.
    Output format:
    {
        "timestamp": "2025-01-15T10:30:45.123456",
        "level": "INFO",
        "logger": "phr_backend.main",
        "message": "User logged in",
        "trace_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "123",
        "custom_field": "value"
    }
    """
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        
        # Add ISO timestamp
        log_record['timestamp'] = datetime.utcnow().isoformat()
        
        # Add log level
        log_record['level'] = record.levelname
        
        # Add logger name
        log_record['logger'] = record.name
        
        # Add correlation ID if available (from context)
        trace_id = getattr(record, 'trace_id', None)
        if trace_id:
            log_record['trace_id'] = trace_id

def setup_json_logging(name: str = "phr_backend"):
    """
    Configure JSON structured logging for the application.
    
    Usage:
        logger = setup_json_logging(__name__)
        logger.info("User signup", extra={"user_id": "123", "trace_id": "..."})
    """
    logger = logging.getLogger(name)
    
    # Remove default handlers
    logger.handlers = []
    
    # Set log level
    logger.setLevel(logging.DEBUG)
    
    # Console handler with JSON formatting
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(CustomJsonFormatter())
    logger.addHandler(console_handler)
    
    # File handler with JSON formatting (optional)
    try:
        file_handler = logging.FileHandler("logs/phr_backend.log")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(CustomJsonFormatter())
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Could not setup file logging: {e}")
    
    return logger

# Module-level logger
logger = setup_json_logging()

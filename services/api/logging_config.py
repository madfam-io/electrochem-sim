"""
Logging configuration for Galvana API
"""

import logging
import logging.config
import json
from datetime import datetime
from typing import Dict, Any
from services.api.config import settings

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields
        if hasattr(record, "request_id"):
            log_obj["request_id"] = record.request_id
        if hasattr(record, "user_id"):
            log_obj["user_id"] = record.user_id
        if hasattr(record, "run_id"):
            log_obj["run_id"] = record.run_id
        
        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        # Add any other extra fields
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "created", "filename", "funcName",
                          "levelname", "levelno", "lineno", "module", "msecs",
                          "pathname", "process", "processName", "relativeCreated",
                          "thread", "threadName", "exc_info", "exc_text", "stack_info",
                          "request_id", "user_id", "run_id", "getMessage"]:
                log_obj[key] = value
        
        return json.dumps(log_obj)

def setup_logging():
    """Configure logging for the application"""
    
    # Determine log format based on environment
    use_json = settings.environment == "production"
    
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": JSONFormatter
            },
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s"
            }
        },
        "filters": {
            "request_id": {
                "()": "services.api.logging_config.RequestIdFilter"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": settings.log_level,
                "formatter": "json" if use_json else "detailed",
                "filters": ["request_id"],
                "stream": "ext://sys.stdout"
            },
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "formatter": "json" if use_json else "detailed",
                "filename": "logs/error.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5
            },
            "app_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "formatter": "json" if use_json else "standard",
                "filename": "logs/app.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 10
            }
        },
        "loggers": {
            "services.api": {
                "level": settings.log_level,
                "handlers": ["console", "app_file", "error_file"],
                "propagate": False
            },
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False
            },
            "uvicorn.error": {
                "level": "INFO",
                "handlers": ["console", "error_file"],
                "propagate": False
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False
            },
            "sqlalchemy.engine": {
                "level": "WARNING" if settings.environment == "production" else "INFO",
                "handlers": ["console"],
                "propagate": False
            }
        },
        "root": {
            "level": settings.log_level,
            "handlers": ["console", "app_file"]
        }
    }
    
    # Create logs directory if it doesn't exist
    import os
    os.makedirs("logs", exist_ok=True)
    
    # Apply configuration
    logging.config.dictConfig(config)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            "environment": settings.environment,
            "log_level": settings.log_level,
            "format": "json" if use_json else "text"
        }
    )

class RequestIdFilter(logging.Filter):
    """Add request ID to log records"""
    
    def filter(self, record):
        # Try to get request ID from context
        import contextvars
        request_id_var = contextvars.ContextVar("request_id", default="no-request")
        record.request_id = request_id_var.get()
        return True

class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter to add context to logs"""
    
    def process(self, msg, kwargs):
        # Add any context from the extra dict
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        
        # Add context from adapter
        kwargs["extra"].update(self.extra)
        
        return msg, kwargs

def get_logger(name: str, **context) -> LoggerAdapter:
    """Get a logger with context"""
    logger = logging.getLogger(name)
    return LoggerAdapter(logger, context)
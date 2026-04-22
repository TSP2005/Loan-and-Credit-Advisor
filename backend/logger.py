"""
Centralized logging setup for the entire application.
Log format: [TIMESTAMP] [LEVEL] [MODULE] [ACTION] [DETAILS]
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from config import settings


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured log output."""

    def format(self, record):
        # Extract custom fields if present
        module = getattr(record, 'module_name', record.module)
        action = getattr(record, 'action', 'GENERAL')
        details = getattr(record, 'details', record.getMessage())

        timestamp = self.formatTime(record, '%Y-%m-%d %H:%M:%S')
        level = record.levelname

        formatted = f"{timestamp} | {level:8s} | {module:20s} | {action:30s} | {details}"

        if record.exc_info and record.exc_info[0]:
            formatted += f"\n{self.formatException(record.exc_info)}"

        return formatted


def get_logger(name: str) -> logging.Logger:
    """Get a structured logger for the given module name."""
    logger = logging.getLogger(f"loan_advisor.{name}")

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.DEBUG))
    logger.propagate = False

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(StructuredFormatter())
    logger.addHandler(console_handler)

    # File handler - main app log
    log_file = os.path.join(settings.LOG_DIR, "app.log")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(StructuredFormatter())
    logger.addHandler(file_handler)

    return logger


def get_frontend_logger() -> logging.Logger:
    """Get a logger specifically for frontend log ingestion."""
    logger = logging.getLogger("loan_advisor.frontend")

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    log_file = os.path.join(settings.LOG_DIR, "frontend.log")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(StructuredFormatter())
    logger.addHandler(file_handler)

    return logger


def log_action(logger: logging.Logger, level: str, module_name: str, action: str, details: str):
    """Helper to log a structured action."""
    extra = {'module_name': module_name, 'action': action, 'details': details}
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(details, extra=extra)

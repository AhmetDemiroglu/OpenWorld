"""
Structured Logging System for OpenWorld
"""
from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Logs directory - project root/data/logs
LOGS_DIR = Path(__file__).resolve().parents[3] / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


class StructuredLogFormatter(logging.Formatter):
    """JSON structured log formatter for machine parsing."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            log_entry["traceback"] = traceback.format_exception(*record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False, default=str)


class HumanReadableFormatter(logging.Formatter):
    """Colored, human-readable formatter for console output."""
    
    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
        "RESET": "\033[0m",
    }
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        msg = f"{color}[{timestamp}] [{record.levelname}]{reset} {record.getMessage()}"
        
        if record.exc_info:
            msg += f"\n{traceback.format_exception(*record.exc_info)}"
        
        return msg


def setup_logging(
    level: str = "INFO",
    structured: bool = False,
    log_to_file: bool = True
) -> logging.Logger:
    """Setup structured logging for the application."""
    
    logger = logging.getLogger("openworld")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers = []  # Clear existing handlers
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(HumanReadableFormatter())
    logger.addHandler(console_handler)
    
    # File handler with rotation
    if log_to_file:
        from logging.handlers import RotatingFileHandler
        
        # Main application log
        app_log_path = LOGS_DIR / "openworld.log"
        file_handler = RotatingFileHandler(
            app_log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(StructuredLogFormatter())
        logger.addHandler(file_handler)
        
        # Error log (only ERROR and above)
        error_log_path = LOGS_DIR / "error.log"
        error_handler = RotatingFileHandler(
            error_log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(StructuredLogFormatter())
        logger.addHandler(error_handler)
    
    return logger


# Global logger instance (will be initialized when config is loaded)
logger = logging.getLogger("openworld")


class LogContext:
    """Context manager for adding structured data to logs."""
    
    def __init__(self, **kwargs):
        self.extra = kwargs
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            logger.error(
                "Exception in context",
                exc_info=(exc_type, exc_val, exc_tb),
                extra=self.extra
            )


def log_tool_execution(
    tool_name: str,
    session_id: str,
    duration_ms: float,
    success: bool,
    error: Optional[str] = None,
    **kwargs
) -> None:
    """Log tool execution with structured data."""
    log_data = {
        "tool_name": tool_name,
        "session_id": session_id,
        "duration_ms": duration_ms,
        "success": success,
        **kwargs
    }
    if error:
        log_data["error"] = error
    
    logger.info(f"Tool execution: {tool_name}", extra={"tool_execution": log_data})


def log_llm_interaction(
    session_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
    duration_ms: float,
    **kwargs
) -> None:
    """Log LLM interaction metrics."""
    logger.info(
        f"LLM interaction: {model}",
        extra={
            "llm_interaction": {
                "session_id": session_id,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "duration_ms": duration_ms,
                **kwargs
            }
        }
    )


def log_security_event(
    event_type: str,
    severity: str,
    description: str,
    session_id: Optional[str] = None,
    **kwargs
) -> None:
    """Log security-related events."""
    log_data = {
        "security_event": {
            "event_type": event_type,
            "severity": severity,
            "description": description,
            "session_id": session_id,
            **kwargs
        }
    }
    
    if severity in ("HIGH", "CRITICAL"):
        logger.error(f"Security Event: {event_type}", extra=log_data)
    else:
        logger.warning(f"Security Event: {event_type}", extra=log_data)

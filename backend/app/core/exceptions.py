"""
Custom Exceptions for OpenWorld
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class OpenWorldException(Exception):
    """Base exception for OpenWorld application."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "INTERNAL_ERROR"
        self.details = details or {}
        self.status_code = status_code
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": True,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class ToolExecutionError(OpenWorldException):
    """Raised when a tool execution fails."""
    
    def __init__(
        self,
        tool_name: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code="TOOL_EXECUTION_ERROR",
            details={"tool_name": tool_name, **(details or {})},
            status_code=500
        )
        self.tool_name = tool_name


class PolicyViolationError(OpenWorldException):
    """Raised when a security policy is violated."""
    
    def __init__(
        self,
        policy: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code="POLICY_VIOLATION",
            details={"policy": policy, **(details or {})},
            status_code=403
        )
        self.policy = policy


class LLMError(OpenWorldException):
    """Raised when LLM interaction fails."""
    
    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code="LLM_ERROR",
            details={"provider": provider, **(details or {})},
            status_code=503
        )
        self.provider = provider


class ValidationError(OpenWorldException):
    """Raised when request validation fails."""
    
    def __init__(
        self,
        field: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details={"field": field, **(details or {})},
            status_code=400
        )
        self.field = field


class SessionNotFoundError(OpenWorldException):
    """Raised when a session is not found."""
    
    def __init__(self, session_id: str):
        super().__init__(
            message=f"Session '{session_id}' not found",
            error_code="SESSION_NOT_FOUND",
            details={"session_id": session_id},
            status_code=404
        )
        self.session_id = session_id


class DatabaseError(OpenWorldException):
    """Raised when database operation fails."""
    
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            details={"operation": operation, **(details or {})},
            status_code=500
        )
        self.operation = operation


class ConfigurationError(OpenWorldException):
    """Raised when there's a configuration error."""
    
    def __init__(self, message: str, config_key: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details={"config_key": config_key},
            status_code=500
        )
        self.config_key = config_key

"""
Custom exception classes for the memory system
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemorySystemError(Exception):
    """Base exception for all memory system errors"""

    def __init__(
        self, message: str, error_code: str = None, details: Dict[str, Any] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        self.log_error()

    def log_error(self):
        """Log the error with appropriate level"""
        logger.error(f"{self.error_code}: {self.message}", extra=self.details)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses"""
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class DatabaseError(MemorySystemError):
    """Database-related errors"""

    def __init__(
        self, message: str, operation: str = None, table: str = None, **kwargs
    ):
        details = kwargs.get("details", {})
        if operation:
            details["operation"] = operation
        if table:
            details["table"] = table
        super().__init__(message, "DATABASE_ERROR", details)


class ConnectionError(MemorySystemError):
    """Database connection errors"""

    def __init__(self, message: str, host: str = None, port: int = None, **kwargs):
        details = kwargs.get("details", {})
        if host:
            details["host"] = host
        if port:
            details["port"] = port
        super().__init__(message, "CONNECTION_ERROR", details)


class ValidationError(MemorySystemError):
    """Input validation errors"""

    def __init__(self, message: str, field: str = None, value: Any = None, **kwargs):
        details = kwargs.get("details", {})
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)
        super().__init__(message, "VALIDATION_ERROR", details)
        self.field = field
        self.value = value


class SecurityError(MemorySystemError):
    """Security-related errors"""

    def __init__(
        self, message: str, threat_type: str = None, client_id: str = None, **kwargs
    ):
        details = kwargs.get("details", {})
        if threat_type:
            details["threat_type"] = threat_type
        if client_id:
            details["client_id"] = client_id
        super().__init__(message, "SECURITY_ERROR", details)


class EmbeddingError(MemorySystemError):
    """Embedding generation errors"""

    def __init__(
        self, message: str, model: str = None, content_length: int = None, **kwargs
    ):
        details = kwargs.get("details", {})
        if model:
            details["model"] = model
        if content_length:
            details["content_length"] = content_length
        super().__init__(message, "EMBEDDING_ERROR", details)


class ConsolidationError(MemorySystemError):
    """Memory consolidation errors"""

    def __init__(
        self, message: str, domain: str = None, operation: str = None, **kwargs
    ):
        details = kwargs.get("details", {})
        if domain:
            details["domain"] = domain
        if operation:
            details["operation"] = operation
        super().__init__(message, "CONSOLIDATION_ERROR", details)


class RateLimitError(MemorySystemError):
    """Rate limiting errors"""

    def __init__(
        self, message: str, client_id: str = None, limit: int = None, **kwargs
    ):
        details = kwargs.get("details", {})
        if client_id:
            details["client_id"] = client_id
        if limit:
            details["limit"] = limit
        super().__init__(message, "RATE_LIMIT_ERROR", details)


class ConfigurationError(MemorySystemError):
    """Configuration errors"""

    def __init__(self, message: str, config_key: str = None, **kwargs):
        details = kwargs.get("details", {})
        if config_key:
            details["config_key"] = config_key
        super().__init__(message, "CONFIGURATION_ERROR", details)


class ServiceUnavailableError(MemorySystemError):
    """Service unavailable errors"""

    def __init__(
        self, message: str, service: str = None, retry_after: int = None, **kwargs
    ):
        details = kwargs.get("details", {})
        if service:
            details["service"] = service
        if retry_after:
            details["retry_after"] = retry_after
        super().__init__(message, "SERVICE_UNAVAILABLE", details)


class TimeoutError(MemorySystemError):
    """Timeout errors"""

    def __init__(
        self, message: str, operation: str = None, timeout: float = None, **kwargs
    ):
        details = kwargs.get("details", {})
        if operation:
            details["operation"] = operation
        if timeout:
            details["timeout"] = timeout
        super().__init__(message, "TIMEOUT_ERROR", details)


class InsufficientDataError(MemorySystemError):
    """Insufficient data errors"""

    def __init__(
        self, message: str, required: int = None, available: int = None, **kwargs
    ):
        details = kwargs.get("details", {})
        if required:
            details["required"] = required
        if available:
            details["available"] = available
        super().__init__(message, "INSUFFICIENT_DATA", details)


class ResourceExhaustedError(MemorySystemError):
    """Resource exhaustion errors"""

    def __init__(
        self,
        message: str,
        resource_type: str = None,
        current_usage: int = None,
        limit: int = None,
        **kwargs,
    ):
        details = kwargs.get("details", {})
        if resource_type:
            details["resource_type"] = resource_type
        if current_usage:
            details["current_usage"] = current_usage
        if limit:
            details["limit"] = limit
        super().__init__(message, "RESOURCE_EXHAUSTED", details)


# Error code mappings for HTTP status codes
ERROR_STATUS_CODES = {
    "VALIDATION_ERROR": 400,
    "SECURITY_ERROR": 403,
    "RATE_LIMIT_ERROR": 429,
    "CONFIGURATION_ERROR": 500,
    "SERVICE_UNAVAILABLE": 503,
    "TIMEOUT_ERROR": 504,
    "RESOURCE_EXHAUSTED": 507,
    "DATABASE_ERROR": 500,
    "CONNECTION_ERROR": 503,
    "EMBEDDING_ERROR": 502,
    "CONSOLIDATION_ERROR": 500,
    "INSUFFICIENT_DATA": 422,
}


def get_http_status_code(error: MemorySystemError) -> int:
    """Get HTTP status code for an error"""
    return ERROR_STATUS_CODES.get(error.error_code, 500)


def is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable"""
    retryable_errors = (
        ConnectionError,
        ServiceUnavailableError,
        TimeoutError,
    )

    # Check for specific database errors that are retryable
    if isinstance(error, DatabaseError):
        error_message = str(error).lower()
        retryable_patterns = [
            "connection",
            "timeout",
            "temporary",
            "busy",
            "locked",
            "deadlock",
        ]
        return any(pattern in error_message for pattern in retryable_patterns)

    return isinstance(error, retryable_errors)


def is_client_error(error: Exception) -> bool:
    """Check if an error is caused by client input"""
    client_errors = (
        ValidationError,
        SecurityError,
        RateLimitError,
        InsufficientDataError,
    )
    return isinstance(error, client_errors)


def is_server_error(error: Exception) -> bool:
    """Check if an error is a server-side issue"""
    server_errors = (
        DatabaseError,
        ConnectionError,
        EmbeddingError,
        ConsolidationError,
        ConfigurationError,
        ServiceUnavailableError,
        TimeoutError,
        ResourceExhaustedError,
    )
    return isinstance(error, server_errors)

"""
Error handling decorators and utilities
"""

import asyncio
import functools
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Type, Union

from exceptions import (
    ConfigurationError,
    ConnectionError,
    ConsolidationError,
    DatabaseError,
    EmbeddingError,
    InsufficientDataError,
    MemorySystemError,
    RateLimitError,
    ResourceExhaustedError,
    SecurityError,
    ServiceUnavailableError,
    TimeoutError,
    ValidationError,
    is_retryable_error,
)

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_backoff: bool = True,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_backoff = exponential_backoff
        self.jitter = jitter


def retry_on_error(
    retry_config: Optional[RetryConfig] = None,
    exceptions: Optional[Union[Type[Exception], tuple]] = None,
    on_failure: Optional[Callable] = None,
):
    """
    Decorator to retry function on specific exceptions

    Args:
        retry_config: Retry configuration
        exceptions: Exception types to retry on (default: retryable errors)
        on_failure: Callback function called on final failure
    """
    if retry_config is None:
        retry_config = RetryConfig()

    if exceptions is None:
        exceptions = (ConnectionError, ServiceUnavailableError, TimeoutError)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(retry_config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == retry_config.max_attempts - 1:
                        # Last attempt failed
                        if on_failure:
                            on_failure(e, attempt + 1)
                        raise e

                    # Calculate delay
                    delay = retry_config.base_delay
                    if retry_config.exponential_backoff:
                        delay *= 2**attempt

                    delay = min(delay, retry_config.max_delay)

                    if retry_config.jitter:
                        import random

                        delay *= 0.5 + random.random() * 0.5

                    logger.warning(
                        f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    time.sleep(delay)

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(retry_config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == retry_config.max_attempts - 1:
                        # Last attempt failed
                        if on_failure:
                            on_failure(e, attempt + 1)
                        raise e

                    # Calculate delay
                    delay = retry_config.base_delay
                    if retry_config.exponential_backoff:
                        delay *= 2**attempt

                    delay = min(delay, retry_config.max_delay)

                    if retry_config.jitter:
                        import random

                        delay *= 0.5 + random.random() * 0.5

                    logger.warning(
                        f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper

    return decorator


def handle_errors(
    default_return: Any = None,
    log_errors: bool = True,
    reraise: bool = True,
    error_mapping: Optional[Dict[Type[Exception], Type[MemorySystemError]]] = None,
):
    """
    Decorator to handle and transform exceptions

    Args:
        default_return: Value to return on error if not reraised
        log_errors: Whether to log errors
        reraise: Whether to reraise transformed exceptions
        error_mapping: Mapping from exception types to custom exceptions
    """
    if error_mapping is None:
        error_mapping = {
            ValueError: ValidationError,
            TypeError: ValidationError,
            KeyError: ValidationError,
            AttributeError: ConfigurationError,
        }

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"Error in {func.__name__}: {e}", exc_info=True)

                # Transform exception if mapping exists
                if type(e) in error_mapping:
                    transformed_error = error_mapping[type(e)](str(e))
                    if reraise:
                        raise transformed_error
                    return default_return

                # If it's already a MemorySystemError, just reraise
                if isinstance(e, MemorySystemError):
                    if reraise:
                        raise e
                    return default_return

                # For other exceptions, wrap in generic MemorySystemError
                if reraise:
                    raise MemorySystemError(f"Unexpected error in {func.__name__}: {e}")
                return default_return

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"Error in {func.__name__}: {e}", exc_info=True)

                # Transform exception if mapping exists
                if type(e) in error_mapping:
                    transformed_error = error_mapping[type(e)](str(e))
                    if reraise:
                        raise transformed_error
                    return default_return

                # If it's already a MemorySystemError, just reraise
                if isinstance(e, MemorySystemError):
                    if reraise:
                        raise e
                    return default_return

                # For other exceptions, wrap in generic MemorySystemError
                if reraise:
                    raise MemorySystemError(f"Unexpected error in {func.__name__}: {e}")
                return default_return

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper

    return decorator


def validate_inputs(**validators):
    """
    Decorator to validate function inputs

    Args:
        **validators: Mapping of parameter names to validation functions
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get function signature
            import inspect

            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            # Validate each parameter
            for param_name, validator in validators.items():
                if param_name in bound_args.arguments:
                    value = bound_args.arguments[param_name]
                    try:
                        validator(value)
                    except Exception as e:
                        raise ValidationError(
                            f"Validation failed for parameter '{param_name}': {e}",
                            field=param_name,
                            value=value,
                        )

            return func(*args, **kwargs)

        return wrapper

    return decorator


@contextmanager
def error_context(operation: str, **context):
    """
    Context manager for error handling with additional context

    Args:
        operation: Name of the operation being performed
        **context: Additional context information
    """
    start_time = time.time()
    try:
        yield
    except Exception as e:
        duration = time.time() - start_time
        error_details = {"operation": operation, "duration": duration, **context}

        if isinstance(e, ValidationError):
            # Let ValidationError pass through without wrapping
            # to ensure immediate failure for invalid input
            raise e
        elif isinstance(e, MemorySystemError):
            e.details.update(error_details)
        else:
            # Wrap in MemorySystemError with context
            raise MemorySystemError(
                f"Error in {operation}: {e}", details=error_details
            ) from e


class CircuitBreaker:
    """Circuit breaker pattern implementation"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise ServiceUnavailableError(
                    f"Circuit breaker is OPEN for {func.__name__}",
                    service=func.__name__,
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        self.state = "CLOSED"

    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    expected_exception: Type[Exception] = Exception,
):
    """Decorator to add circuit breaker pattern to functions"""
    breaker = CircuitBreaker(failure_threshold, recovery_timeout, expected_exception)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # For async functions, we need to handle them differently
            if breaker.state == "OPEN":
                if time.time() - breaker.last_failure_time > breaker.recovery_timeout:
                    breaker.state = "HALF_OPEN"
                else:
                    raise ServiceUnavailableError(
                        f"Circuit breaker is OPEN for {func.__name__}",
                        service=func.__name__,
                    )

            try:
                result = await func(*args, **kwargs)
                breaker._on_success()
                return result
            except expected_exception as e:
                breaker._on_failure()
                raise e

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper

    return decorator


class ErrorRecovery:
    """Error recovery strategies"""

    @staticmethod
    def fallback_to_cache(func: Callable, cache_key: str, cache_ttl: int = 300):
        """Fallback to cached result on error"""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(
                    f"Function {func.__name__} failed, trying cache fallback: {e}"
                )
                # Here you would implement cache retrieval logic
                # For now, just reraise the original error
                raise e

        return wrapper

    @staticmethod
    def fallback_to_default(default_value: Any):
        """Return default value on error"""

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(
                        f"Function {func.__name__} failed, using default: {e}"
                    )
                    return default_value

            return wrapper

        return decorator

    @staticmethod
    def graceful_degradation(degraded_func: Callable):
        """Use degraded function on error"""

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(
                        f"Function {func.__name__} failed, using degraded version: {e}"
                    )
                    return degraded_func(*args, **kwargs)

            return wrapper

        return decorator


def log_api_error(error, context="", request_id=None):
    """Log API error with context information.

    Args:
        error: The error that occurred
        context: Additional context about the error
        request_id: Optional request ID for tracking
    """
    import logging

    # Don't log test errors
    if context and "test" in context.lower():
        return

    # Ensure basic logging is configured
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )

    logger = logging.getLogger(__name__)

    error_msg = f"API Error: {str(error)}"
    if context:
        error_msg += f" | Context: {context}"
    if request_id:
        error_msg += f" | Request ID: {request_id}"

    logger.error(error_msg)


def handle_database_error(error, operation="unknown"):
    """Handle database errors with appropriate logging and response.

    Args:
        error: The database error that occurred
        operation: The database operation that failed

    Returns:
        Dict with error information
    """
    import logging

    # Don't log test errors
    if operation and "test" in operation.lower():
        return {
            "success": False,
            "error": f"Database operation '{operation}' failed",
            "details": str(error),
            "type": "database_error",
        }

    # Ensure basic logging is configured
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )

    logger = logging.getLogger(__name__)

    logger.error(f"Database error during {operation}: {str(error)}")

    return {
        "success": False,
        "error": f"Database operation '{operation}' failed",
        "details": str(error),
        "type": "database_error",
    }

"""
Comprehensive database error handling
"""
import functools
import logging
import time
from typing import Dict, Any, Optional, Callable, List
from contextlib import contextmanager
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from exceptions import (
    DatabaseError, ConnectionError, ValidationError, 
    TimeoutError, ResourceExhaustedError, ServiceUnavailableError
)
from error_handlers import retry_on_error, RetryConfig, error_context

logger = logging.getLogger(__name__)


class DatabaseErrorHandler:
    """Comprehensive database error handling"""
    
    # PostgreSQL error codes that are retryable
    RETRYABLE_ERROR_CODES = [
        '08000',  # connection_exception
        '08003',  # connection_does_not_exist
        '08006',  # connection_failure
        '08001',  # sqlclient_unable_to_establish_sqlconnection
        '08004',  # sqlserver_rejected_establishment_of_sqlconnection
        '08007',  # transaction_resolution_unknown
        '40001',  # serialization_failure
        '40P01',  # deadlock_detected
        '53300',  # too_many_connections
        '57P03',  # cannot_connect_now
    ]
    
    # PostgreSQL error codes that indicate resource exhaustion
    RESOURCE_EXHAUSTION_CODES = [
        '53300',  # too_many_connections
        '54000',  # program_limit_exceeded
        '54001',  # statement_too_complex
        '54011',  # too_many_columns
        '54023',  # too_many_arguments
    ]
    
    # PostgreSQL error codes that indicate timeout
    TIMEOUT_CODES = [
        '57014',  # query_canceled
        '57015',  # admin_shutdown
    ]
    
    @classmethod
    def handle_psycopg2_error(cls, error: psycopg2.Error, operation: str = None, table: str = None) -> Exception:
        """Convert psycopg2 errors to custom exceptions"""
        error_code = getattr(error, 'pgcode', None)
        error_message = str(error)
        
        # Map to custom exceptions based on error code
        if error_code in cls.RETRYABLE_ERROR_CODES:
            if 'connection' in error_message.lower():
                return ConnectionError(
                    f"Database connection failed: {error_message}",
                    operation=operation,
                    table=table,
                    details={'error_code': error_code, 'original_error': str(error)}
                )
            else:
                return ServiceUnavailableError(
                    f"Database temporarily unavailable: {error_message}",
                    service='database',
                    operation=operation,
                    details={'error_code': error_code, 'original_error': str(error)}
                )
        
        elif error_code in cls.RESOURCE_EXHAUSTION_CODES:
            return ResourceExhaustedError(
                f"Database resource exhausted: {error_message}",
                resource_type='database',
                operation=operation,
                details={'error_code': error_code, 'original_error': str(error)}
            )
        
        elif error_code in cls.TIMEOUT_CODES:
            return TimeoutError(
                f"Database operation timed out: {error_message}",
                operation=operation,
                details={'error_code': error_code, 'original_error': str(error)}
            )
        
        elif error_code == '23505':  # unique_violation
            return ValidationError(
                f"Duplicate entry: {error_message}",
                field='id',
                details={'error_code': error_code, 'original_error': str(error)}
            )
        
        elif error_code == '23503':  # foreign_key_violation
            return ValidationError(
                f"Foreign key constraint violation: {error_message}",
                details={'error_code': error_code, 'original_error': str(error)}
            )
        
        elif error_code == '23502':  # not_null_violation
            return ValidationError(
                f"Required field missing: {error_message}",
                details={'error_code': error_code, 'original_error': str(error)}
            )
        
        elif error_code == '42P01':  # undefined_table
            return DatabaseError(
                f"Table does not exist: {error_message}",
                operation=operation,
                table=table,
                details={'error_code': error_code, 'original_error': str(error)}
            )
        
        elif error_code == '42703':  # undefined_column
            return DatabaseError(
                f"Column does not exist: {error_message}",
                operation=operation,
                table=table,
                details={'error_code': error_code, 'original_error': str(error)}
            )
        
        else:
            # Generic database error
            return DatabaseError(
                f"Database error: {error_message}",
                operation=operation,
                table=table,
                details={'error_code': error_code, 'original_error': str(error)}
            )
    
    @classmethod
    def is_retryable_error(cls, error: Exception) -> bool:
        """Check if a database error is retryable"""
        if isinstance(error, psycopg2.Error):
            error_code = getattr(error, 'pgcode', None)
            return error_code in cls.RETRYABLE_ERROR_CODES
        
        # Check custom exceptions
        retryable_exceptions = (ConnectionError, ServiceUnavailableError, TimeoutError)
        return isinstance(error, retryable_exceptions)
    
    @classmethod
    def get_retry_delay(cls, attempt: int, base_delay: float = 1.0) -> float:
        """Calculate retry delay with exponential backoff"""
        delay = base_delay * (2 ** attempt)
        # Add jitter to prevent thundering herd
        import random
        jitter = random.uniform(0.1, 0.3) * delay
        return min(delay + jitter, 60.0)  # Cap at 60 seconds


@contextmanager
def database_operation(operation: str, table: str = None, connection_pool=None):
    """
    Context manager for database operations with comprehensive error handling
    
    Args:
        operation: Name of the operation (e.g., 'SELECT', 'INSERT', 'UPDATE')
        table: Table name being operated on
        connection_pool: Database connection pool
    """
    start_time = time.time()
    connection = None
    cursor = None
    
    try:
        if connection_pool:
            connection = connection_pool.get_connection()
            cursor = connection.cursor(cursor_factory=RealDictCursor)
        else:
            # Fallback to direct connection
            import psycopg2
            from postgres_memory_api import PostgresMemoryAPI
            api = PostgresMemoryAPI()
            connection = api._get_connection()
            cursor = connection.cursor(cursor_factory=RealDictCursor)
        
        yield cursor
        
        # Commit transaction
        if connection:
            connection.commit()
        
        duration = time.time() - start_time
        logger.debug(f"Database operation '{operation}' on '{table}' completed in {duration:.3f}s")
        
    except psycopg2.Error as e:
        # Rollback transaction
        if connection:
            connection.rollback()
        
        # Convert to custom exception
        custom_error = DatabaseErrorHandler.handle_psycopg2_error(e, operation, table)
        
        duration = time.time() - start_time
        custom_error.details['duration'] = duration
        
        logger.error(f"Database operation '{operation}' on '{table}' failed after {duration:.3f}s: {e}")
        raise custom_error
        
    except Exception as e:
        # Rollback transaction
        if connection:
            connection.rollback()
        
        duration = time.time() - start_time
        logger.error(f"Unexpected error in database operation '{operation}' on '{table}' after {duration:.3f}s: {e}")
        
        # Wrap in DatabaseError
        raise DatabaseError(
            f"Unexpected database error: {e}",
            operation=operation,
            table=table,
            details={'duration': duration, 'original_error': str(e)}
        )
        
    finally:
        # Clean up resources
        if cursor:
            cursor.close()
        if connection and not connection_pool:
            connection.close()


def with_database_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    operation: str = None,
    table: str = None
):
    """
    Decorator to add database retry logic to functions
    
    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay between retries
        operation: Database operation name
        table: Table name
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    # Check if error is retryable
                    if not DatabaseErrorHandler.is_retryable_error(e):
                        raise e
                    
                    if attempt == max_attempts - 1:
                        # Last attempt failed
                        logger.error(f"Database operation '{operation}' on '{table}' failed after {max_attempts} attempts")
                        raise e
                    
                    # Calculate retry delay
                    delay = DatabaseErrorHandler.get_retry_delay(attempt, base_delay)
                    
                    logger.warning(
                        f"Database operation '{operation}' on '{table}' failed (attempt {attempt + 1}/{max_attempts}): {e}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    time.sleep(delay)
            
            # This should never be reached
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


class DatabaseHealthMonitor:
    """Monitor database health and performance"""
    
    def __init__(self, connection_pool=None):
        self.connection_pool = connection_pool
        self.health_metrics = {
            'total_operations': 0,
            'failed_operations': 0,
            'average_response_time': 0.0,
            'last_health_check': None,
            'connection_pool_status': None
        }
    
    def record_operation(self, operation: str, duration: float, success: bool):
        """Record operation metrics"""
        self.health_metrics['total_operations'] += 1
        if not success:
            self.health_metrics['failed_operations'] += 1
        
        # Update average response time
        total_ops = self.health_metrics['total_operations']
        current_avg = self.health_metrics['average_response_time']
        self.health_metrics['average_response_time'] = (
            (current_avg * (total_ops - 1) + duration) / total_ops
        )
    
    def check_health(self) -> Dict[str, Any]:
        """Check database health"""
        try:
            with database_operation('HEALTH_CHECK', connection_pool=self.connection_pool) as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                
                if result and result[0] == 1:
                    self.health_metrics['last_health_check'] = time.time()
                    
                    # Get connection pool status if available
                    if self.connection_pool:
                        self.health_metrics['connection_pool_status'] = self.connection_pool.get_pool_status()
                    
                    return {
                        'healthy': True,
                        'metrics': self.health_metrics,
                        'timestamp': time.time()
                    }
                else:
                    return {
                        'healthy': False,
                        'error': 'Health check query returned unexpected result',
                        'metrics': self.health_metrics,
                        'timestamp': time.time()
                    }
                    
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'metrics': self.health_metrics,
                'timestamp': time.time()
            }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current health metrics"""
        return self.health_metrics.copy()


# Global database health monitor
_db_health_monitor = None


def get_database_health_monitor(connection_pool=None) -> DatabaseHealthMonitor:
    """Get or create global database health monitor"""
    global _db_health_monitor
    if _db_health_monitor is None:
        _db_health_monitor = DatabaseHealthMonitor(connection_pool)
    return _db_health_monitor


def monitor_database_operation(operation: str, table: str = None):
    """Decorator to monitor database operations"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            finally:
                duration = time.time() - start_time
                monitor = get_database_health_monitor()
                monitor.record_operation(operation, duration, success)
        
        return wrapper
    return decorator

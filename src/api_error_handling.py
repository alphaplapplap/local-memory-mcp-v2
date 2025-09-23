"""
API error handling and HTTP response management
"""
import json
import logging
from typing import Dict, Any, Optional, Union
from datetime import datetime
from flask import Flask, request, jsonify, Response
from werkzeug.exceptions import HTTPException

from exceptions import (
    MemorySystemError, ValidationError, DatabaseError, ConnectionError,
    SecurityError, EmbeddingError, ConsolidationError, RateLimitError,
    ConfigurationError, ServiceUnavailableError, TimeoutError,
    InsufficientDataError, ResourceExhaustedError, get_http_status_code
)

logger = logging.getLogger(__name__)


class APIErrorHandler:
    """Centralized API error handling"""
    
    def __init__(self, app: Optional[Flask] = None):
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        """Initialize error handlers for Flask app"""
        app.register_error_handler(MemorySystemError, self.handle_memory_system_error)
        app.register_error_handler(ValidationError, self.handle_validation_error)
        app.register_error_handler(DatabaseError, self.handle_database_error)
        app.register_error_handler(ConnectionError, self.handle_connection_error)
        app.register_error_handler(SecurityError, self.handle_security_error)
        app.register_error_handler(EmbeddingError, self.handle_embedding_error)
        app.register_error_handler(ConsolidationError, self.handle_consolidation_error)
        app.register_error_handler(RateLimitError, self.handle_rate_limit_error)
        app.register_error_handler(ConfigurationError, self.handle_configuration_error)
        app.register_error_handler(ServiceUnavailableError, self.handle_service_unavailable_error)
        app.register_error_handler(TimeoutError, self.handle_timeout_error)
        app.register_error_handler(InsufficientDataError, self.handle_insufficient_data_error)
        app.register_error_handler(ResourceExhaustedError, self.handle_resource_exhausted_error)
        app.register_error_handler(HTTPException, self.handle_http_exception)
        app.register_error_handler(Exception, self.handle_generic_error)
    
    def handle_memory_system_error(self, error: MemorySystemError) -> Response:
        """Handle MemorySystemError"""
        return self._create_error_response(
            error=error,
            status_code=get_http_status_code(error),
            include_details=True
        )
    
    def handle_validation_error(self, error: ValidationError) -> Response:
        """Handle ValidationError"""
        return self._create_error_response(
            error=error,
            status_code=400,
            include_details=True
        )
    
    def handle_database_error(self, error: DatabaseError) -> Response:
        """Handle DatabaseError"""
        return self._create_error_response(
            error=error,
            status_code=500,
            include_details=False  # Don't expose database details
        )
    
    def handle_connection_error(self, error: ConnectionError) -> Response:
        """Handle ConnectionError"""
        return self._create_error_response(
            error=error,
            status_code=503,
            include_details=False
        )
    
    def handle_security_error(self, error: SecurityError) -> Response:
        """Handle SecurityError"""
        return self._create_error_response(
            error=error,
            status_code=403,
            include_details=False
        )
    
    def handle_embedding_error(self, error: EmbeddingError) -> Response:
        """Handle EmbeddingError"""
        return self._create_error_response(
            error=error,
            status_code=502,
            include_details=False
        )
    
    def handle_consolidation_error(self, error: ConsolidationError) -> Response:
        """Handle ConsolidationError"""
        return self._create_error_response(
            error=error,
            status_code=500,
            include_details=False
        )
    
    def handle_rate_limit_error(self, error: RateLimitError) -> Response:
        """Handle RateLimitError"""
        response = self._create_error_response(
            error=error,
            status_code=429,
            include_details=True
        )
        
        # Add rate limit headers
        if 'limit' in error.details:
            response.headers['X-RateLimit-Limit'] = str(error.details['limit'])
        if 'retry_after' in error.details:
            response.headers['Retry-After'] = str(error.details['retry_after'])
        
        return response
    
    def handle_configuration_error(self, error: ConfigurationError) -> Response:
        """Handle ConfigurationError"""
        return self._create_error_response(
            error=error,
            status_code=500,
            include_details=False
        )
    
    def handle_service_unavailable_error(self, error: ServiceUnavailableError) -> Response:
        """Handle ServiceUnavailableError"""
        response = self._create_error_response(
            error=error,
            status_code=503,
            include_details=False
        )
        
        # Add retry-after header if specified
        if 'retry_after' in error.details:
            response.headers['Retry-After'] = str(error.details['retry_after'])
        
        return response
    
    def handle_timeout_error(self, error: TimeoutError) -> Response:
        """Handle TimeoutError"""
        return self._create_error_response(
            error=error,
            status_code=504,
            include_details=False
        )
    
    def handle_insufficient_data_error(self, error: InsufficientDataError) -> Response:
        """Handle InsufficientDataError"""
        return self._create_error_response(
            error=error,
            status_code=422,
            include_details=True
        )
    
    def handle_resource_exhausted_error(self, error: ResourceExhaustedError) -> Response:
        """Handle ResourceExhaustedError"""
        return self._create_error_response(
            error=error,
            status_code=507,
            include_details=False
        )
    
    def handle_http_exception(self, error: HTTPException) -> Response:
        """Handle Werkzeug HTTPException"""
        return self._create_error_response(
            error=error,
            status_code=error.code,
            include_details=False
        )
    
    def handle_generic_error(self, error: Exception) -> Response:
        """Handle generic exceptions"""
        logger.error(f"Unhandled exception: {error}", exc_info=True)
        
        return self._create_error_response(
            error=error,
            status_code=500,
            include_details=False,
            message="An unexpected error occurred"
        )
    
    def _create_error_response(
        self, 
        error: Union[Exception, MemorySystemError], 
        status_code: int,
        include_details: bool = False,
        message: Optional[str] = None
    ) -> Response:
        """Create standardized error response"""
        
        # Base error response
        error_response = {
            "error": True,
            "timestamp": datetime.utcnow().isoformat(),
            "status_code": status_code,
            "message": message or str(error)
        }
        
        # Add request information
        if request:
            error_response["request_id"] = getattr(request, 'id', None)
            error_response["endpoint"] = request.endpoint
            error_response["method"] = request.method
        
        # Add error details if appropriate
        if include_details and isinstance(error, MemorySystemError):
            error_response["error_code"] = error.error_code
            error_response["details"] = error.details
        
        # Log the error
        if status_code >= 500:
            logger.error(f"Server error {status_code}: {error}", extra={
                "status_code": status_code,
                "error_type": type(error).__name__,
                "request_id": error_response.get("request_id"),
                "endpoint": error_response.get("endpoint")
            })
        else:
            logger.warning(f"Client error {status_code}: {error}", extra={
                "status_code": status_code,
                "error_type": type(error).__name__,
                "request_id": error_response.get("request_id"),
                "endpoint": error_response.get("endpoint")
            })
        
        return jsonify(error_response), status_code


def create_success_response(
    data: Any = None, 
    message: str = "Success", 
    status_code: int = 200,
    metadata: Optional[Dict[str, Any]] = None
) -> Response:
    """Create standardized success response"""
    
    response = {
        "success": True,
        "timestamp": datetime.utcnow().isoformat(),
        "message": message,
        "status_code": status_code
    }
    
    if data is not None:
        response["data"] = data
    
    if metadata:
        response["metadata"] = metadata
    
    # Add request information
    if request:
        response["request_id"] = getattr(request, 'id', None)
    
    return jsonify(response), status_code


def create_paginated_response(
    data: list,
    page: int,
    per_page: int,
    total: int,
    message: str = "Success"
) -> Response:
    """Create paginated response"""
    
    total_pages = (total + per_page - 1) // per_page
    
    metadata = {
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }
    
    return create_success_response(
        data=data,
        message=message,
        metadata=metadata
    )


class APIErrorMiddleware:
    """Middleware for API error handling"""
    
    def __init__(self, app: Flask):
        self.app = app
        self.error_handler = APIErrorHandler(app)
    
    def __call__(self, environ, start_response):
        """WSGI middleware"""
        try:
            return self.app(environ, start_response)
        except Exception as e:
            # Handle uncaught exceptions
            logger.error(f"Uncaught exception in middleware: {e}", exc_info=True)
            
            # Create error response
            error_response = {
                "error": True,
                "timestamp": datetime.utcnow().isoformat(),
                "status_code": 500,
                "message": "Internal server error"
            }
            
            response = Response(
                json.dumps(error_response),
                status=500,
                mimetype='application/json'
            )
            
            return response(environ, start_response)


def setup_api_error_handling(app: Flask) -> APIErrorHandler:
    """Setup comprehensive API error handling for Flask app"""
    
    # Initialize error handler
    error_handler = APIErrorHandler(app)
    
    # Add middleware
    app.wsgi_app = APIErrorMiddleware(app)
    
    # Add health check endpoint
    @app.route('/health')
    def health_check():
        """Health check endpoint"""
        return create_success_response(
            data={"status": "healthy"},
            message="Service is healthy"
        )
    
    # Add error test endpoint (for development)
    @app.route('/test-error')
    def test_error():
        """Test error handling (development only)"""
        if app.debug:
            raise ValidationError("Test error", field="test", value="test_value")
        else:
            return create_success_response(
                data={"message": "Error testing disabled in production"},
                message="Error testing not available"
            )
    
    return error_handler


# Decorator for API endpoints with error handling
def api_endpoint(
    success_message: str = "Success",
    include_metadata: bool = False
):
    """Decorator for API endpoints with standardized error handling"""
    
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                
                # Handle different return types
                if isinstance(result, tuple):
                    data, message = result
                    return create_success_response(
                        data=data,
                        message=message or success_message,
                        metadata={"endpoint": func.__name__} if include_metadata else None
                    )
                else:
                    return create_success_response(
                        data=result,
                        message=success_message,
                        metadata={"endpoint": func.__name__} if include_metadata else None
                    )
                    
            except MemorySystemError as e:
                # Let the error handler deal with it
                raise e
            except Exception as e:
                # Wrap unexpected errors
                logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                raise MemorySystemError(f"Unexpected error in {func.__name__}: {e}")
        
        wrapper.__name__ = func.__name__
        return wrapper
    
    return decorator

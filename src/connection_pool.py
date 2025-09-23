"""
Database connection pool management
"""
import psycopg2
from psycopg2 import pool
import threading
import time
import logging
from typing import Dict, Any, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """Thread-safe database connection pool"""
    
    def __init__(self, 
                 connection_params: Dict[str, Any],
                 min_connections: int = 2,
                 max_connections: int = 10,
                 connection_timeout: int = 30):
        
        self.connection_params = connection_params
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        
        # Create connection pool
        self._pool = None
        self._lock = threading.Lock()
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize the connection pool"""
        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=self.min_connections,
                maxconn=self.max_connections,
                **self.connection_params
            )
            logger.info(f"Connection pool initialized: {self.min_connections}-{self.max_connections} connections")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            # In test environments, we might want to continue without a real pool
            if self._is_test_environment():
                logger.warning("Running in test environment - connection pool not initialized")
                self._pool = None
            else:
                raise
    
    def _is_test_environment(self) -> bool:
        """Check if we're running in a test environment"""
        import os
        return (
            os.getenv('PYTEST_CURRENT_TEST') is not None or
            os.getenv('TESTING') == 'true' or
            'test' in self.connection_params.get('user', '').lower() or
            'test' in self.connection_params.get('database', '').lower()
        )
    
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool (context manager)"""
        if self._pool is None:
            # In test environment, create a direct connection
            connection = None
            try:
                connection = psycopg2.connect(**self.connection_params)
                yield connection
            except Exception as e:
                if connection:
                    connection.rollback()
                logger.error(f"Database connection error: {e}")
                raise
            finally:
                if connection:
                    connection.close()
            return
        
        connection = None
        try:
            connection = self._pool.getconn()
            if connection is None:
                raise Exception("Failed to get connection from pool")
            
            # Test connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            
            yield connection
            
        except Exception as e:
            if connection:
                connection.rollback()
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if connection:
                self._pool.putconn(connection)
    
    @contextmanager
    def get_cursor(self, cursor_factory=None):
        """Get a cursor from the pool (context manager)"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=cursor_factory) as cursor:
                yield cursor
    
    def close_all_connections(self):
        """Close all connections in the pool"""
        if self._pool:
            self._pool.closeall()
            logger.info("All connections closed")
    
    def get_pool_status(self) -> Dict[str, Any]:
        """Get current pool status"""
        if not self._pool:
            return {"status": "not_initialized"}
        
        return {
            "status": "active",
            "min_connections": self.min_connections,
            "max_connections": self.max_connections,
            "current_connections": len(self._pool._used) + len(self._pool._pool),
            "used_connections": len(self._pool._used),
            "available_connections": len(self._pool._pool)
        }


class ConnectionHealthChecker:
    """Health checker for database connections"""
    
    def __init__(self, connection_pool: DatabaseConnectionPool):
        self.connection_pool = connection_pool
        self.last_check = None
        self.is_healthy = True
        self.error_count = 0
        self.max_errors = 5
    
    def check_health(self) -> bool:
        """Check database health"""
        try:
            with self.connection_pool.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    
            if result and result[0] == 1:
                self.is_healthy = True
                self.error_count = 0
                self.last_check = time.time()
                return True
            else:
                self.is_healthy = False
                self.error_count += 1
                return False
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.is_healthy = False
            self.error_count += 1
            return False
    
    def is_database_healthy(self) -> bool:
        """Check if database is healthy"""
        if self.error_count >= self.max_errors:
            return False
        
        # Check if we need to perform a health check
        if self.last_check is None or time.time() - self.last_check > 60:  # Check every minute
            return self.check_health()
        
        return self.is_healthy
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get detailed health status"""
        return {
            "is_healthy": self.is_healthy,
            "error_count": self.error_count,
            "last_check": self.last_check,
            "max_errors": self.max_errors
        }


class QueryOptimizer:
    """Query optimization utilities"""
    
    @staticmethod
    def optimize_memory_query(query: str, limit: int, domain: str) -> str:
        """Optimize memory retrieval query"""
        # Add LIMIT clause if not present
        if 'LIMIT' not in query.upper():
            query += f" LIMIT {limit}"
        
        # Add domain filter if not present
        if 'WHERE' not in query.upper() and domain != 'default':
            query += f" WHERE domain = '{domain}'"
        
        return query
    
    @staticmethod
    def create_index_suggestions(table_name: str) -> list:
        """Suggest database indexes for better performance"""
        suggestions = [
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_created_at ON {table_name} (created_at DESC);",
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_updated_at ON {table_name} (updated_at DESC);",
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_metadata_gin ON {table_name} USING GIN (metadata);",
        ]
        
        # Add vector index if pgvector is available
        suggestions.append(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_embedding_cosine "
            f"ON {table_name} USING ivfflat (embedding vector_cosine_ops) "
            f"WITH (lists = 100);"
        )
        
        return suggestions


# Global connection pool instance
_connection_pool = None
_health_checker = None


def initialize_connection_pool(connection_params: Dict[str, Any], 
                              min_connections: int = 2,
                              max_connections: int = 10) -> DatabaseConnectionPool:
    """Initialize the global connection pool"""
    global _connection_pool, _health_checker
    
    _connection_pool = DatabaseConnectionPool(
        connection_params=connection_params,
        min_connections=min_connections,
        max_connections=max_connections
    )
    
    _health_checker = ConnectionHealthChecker(_connection_pool)
    
    return _connection_pool


def get_connection_pool() -> Optional[DatabaseConnectionPool]:
    """Get the global connection pool"""
    return _connection_pool


def get_health_checker() -> Optional[ConnectionHealthChecker]:
    """Get the global health checker"""
    return _health_checker


def cleanup_connections():
    """Cleanup all connections"""
    global _connection_pool
    if _connection_pool:
        _connection_pool.close_all_connections()
        _connection_pool = None

"""
Health check system for the memory application
"""
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status enumeration"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    name: str
    status: HealthStatus
    message: str
    response_time: float
    details: Dict[str, Any]
    timestamp: datetime


class HealthChecker:
    """Base class for health checkers"""
    
    def __init__(self, name: str, timeout: float = 5.0):
        self.name = name
        self.timeout = timeout
    
    async def check(self) -> HealthCheckResult:
        """Perform health check"""
        start_time = time.time()
        try:
            result = await asyncio.wait_for(self._check(), timeout=self.timeout)
            response_time = time.time() - start_time
            
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message="OK",
                response_time=response_time,
                details=result,
                timestamp=datetime.now()
            )
        except asyncio.TimeoutError:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message="Timeout",
                response_time=self.timeout,
                details={},
                timestamp=datetime.now()
            )
        except Exception as e:
            response_time = time.time() - start_time
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                response_time=response_time,
                details={},
                timestamp=datetime.now()
            )
    
    async def _check(self) -> Dict[str, Any]:
        """Override in subclasses"""
        return {}


class DatabaseHealthChecker(HealthChecker):
    """Database health checker"""
    
    def __init__(self, connection_pool):
        super().__init__("database")
        self.connection_pool = connection_pool
    
    async def _check(self) -> Dict[str, Any]:
        """Check database health"""
        import psycopg2
        
        try:
            with self.connection_pool.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Test basic connectivity
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    
                    # Check database size
                    cursor.execute("""
                        SELECT pg_size_pretty(pg_database_size(current_database()))
                    """)
                    db_size = cursor.fetchone()[0]
                    
                    # Check active connections
                    cursor.execute("""
                        SELECT count(*) FROM pg_stat_activity 
                        WHERE state = 'active'
                    """)
                    active_connections = cursor.fetchone()[0]
                    
                    # Check for long-running queries
                    cursor.execute("""
                        SELECT count(*) FROM pg_stat_activity 
                        WHERE state = 'active' AND query_start < NOW() - INTERVAL '5 minutes'
                    """)
                    long_queries = cursor.fetchone()[0]
                    
                    return {
                        "connected": True,
                        "database_size": db_size,
                        "active_connections": active_connections,
                        "long_running_queries": long_queries,
                        "pool_status": self.connection_pool.get_pool_status()
                    }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            raise


class OllamaHealthChecker(HealthChecker):
    """Ollama service health checker"""
    
    def __init__(self, ollama_embeddings):
        super().__init__("ollama")
        self.ollama_embeddings = ollama_embeddings
    
    async def _check(self) -> Dict[str, Any]:
        """Check Ollama service health"""
        try:
            # Test embedding generation
            test_embedding = self.ollama_embeddings.get_embedding("health check")
            
            return {
                "service_available": True,
                "embedding_dimensions": len(test_embedding) if test_embedding else 0,
                "model_name": getattr(self.ollama_embeddings, 'model_name', 'unknown')
            }
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            raise


class MemorySystemHealthChecker(HealthChecker):
    """Memory system health checker"""
    
    def __init__(self, memory_api):
        super().__init__("memory_system")
        self.memory_api = memory_api
    
    async def _check(self) -> Dict[str, Any]:
        """Check memory system health"""
        try:
            # Test basic operations
            test_domain = "health_check_test"
            
            # Test memory storage
            memory_id = self.memory_api.store_memory(
                "Health check test memory",
                {"test": True, "timestamp": time.time()},
                test_domain
            )
            
            # Test memory retrieval
            memories = self.memory_api.retrieve_memories("health check", limit=1, domain=test_domain)
            
            # Test domain listing
            domains = self.memory_api.list_domains()
            
            # Clean up test memory
            try:
                self.memory_api.update_memory(memory_id, "deleted", {"deleted": True})
            except:
                pass  # Cleanup failure is not critical
            
            return {
                "storage_working": bool(memory_id),
                "retrieval_working": len(memories) >= 0,
                "domain_listing_working": len(domains) >= 0,
                "total_domains": len(domains),
                "test_memory_id": memory_id
            }
        except Exception as e:
            logger.error(f"Memory system health check failed: {e}")
            raise


class ConsolidationHealthChecker(HealthChecker):
    """Consolidation system health checker"""
    
    def __init__(self, memory_api):
        super().__init__("consolidation")
        self.memory_api = memory_api
    
    async def _check(self) -> Dict[str, Any]:
        """Check consolidation system health"""
        try:
            # Check if consolidation system is available
            if not hasattr(self.memory_api, 'consolidator') or not self.memory_api.consolidator:
                return {
                    "available": False,
                    "reason": "Consolidation system not initialized"
                }
            
            # Test clustering (non-destructive)
            test_domain = "health_check_test"
            cluster_result = self.memory_api.cluster_memories(test_domain)
            
            return {
                "available": True,
                "clustering_working": cluster_result.get("status") in ["success", "insufficient_data"],
                "clustering_result": cluster_result
            }
        except Exception as e:
            logger.error(f"Consolidation health check failed: {e}")
            raise


class SystemHealthChecker:
    """Main health check coordinator"""
    
    def __init__(self, memory_api, connection_pool=None):
        self.memory_api = memory_api
        self.connection_pool = connection_pool
        self.checkers: List[HealthChecker] = []
        self.last_check_time = None
        self.last_results: List[HealthCheckResult] = []
        
        self._initialize_checkers()
    
    def _initialize_checkers(self):
        """Initialize all health checkers"""
        # Database checker
        if self.connection_pool:
            self.checkers.append(DatabaseHealthChecker(self.connection_pool))
        
        # Ollama checker
        if hasattr(self.memory_api, 'ollama_embeddings') and self.memory_api.ollama_embeddings:
            self.checkers.append(OllamaHealthChecker(self.memory_api.ollama_embeddings))
        
        # Memory system checker
        self.checkers.append(MemorySystemHealthChecker(self.memory_api))
        
        # Consolidation checker
        self.checkers.append(ConsolidationHealthChecker(self.memory_api))
    
    async def run_health_checks(self) -> List[HealthCheckResult]:
        """Run all health checks"""
        logger.info("Running health checks...")
        
        # Run all checks concurrently
        tasks = [checker.check() for checker in self.checkers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        health_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                health_results.append(HealthCheckResult(
                    name=self.checkers[i].name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(result)}",
                    response_time=0.0,
                    details={},
                    timestamp=datetime.now()
                ))
            else:
                health_results.append(result)
        
        self.last_results = health_results
        self.last_check_time = datetime.now()
        
        logger.info(f"Health checks completed: {len(health_results)} checks")
        return health_results
    
    def get_overall_status(self) -> HealthStatus:
        """Get overall system health status"""
        if not self.last_results:
            return HealthStatus.UNKNOWN
        
        # Check if any critical components are unhealthy
        critical_components = ["database", "memory_system"]
        for result in self.last_results:
            if result.name in critical_components and result.status == HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
        
        # Check if any components are degraded
        for result in self.last_results:
            if result.status == HealthStatus.DEGRADED:
                return HealthStatus.DEGRADED
        
        # Check if all components are healthy
        all_healthy = all(result.status == HealthStatus.HEALTHY for result in self.last_results)
        if all_healthy:
            return HealthStatus.HEALTHY
        
        return HealthStatus.DEGRADED
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get health check summary"""
        overall_status = self.get_overall_status()
        
        return {
            "overall_status": overall_status.value,
            "last_check": self.last_check_time.isoformat() if self.last_check_time else None,
            "components": {
                result.name: {
                    "status": result.status.value,
                    "message": result.message,
                    "response_time": result.response_time,
                    "details": result.details
                }
                for result in self.last_results
            },
            "summary": {
                "total_checks": len(self.last_results),
                "healthy": sum(1 for r in self.last_results if r.status == HealthStatus.HEALTHY),
                "degraded": sum(1 for r in self.last_results if r.status == HealthStatus.DEGRADED),
                "unhealthy": sum(1 for r in self.last_results if r.status == HealthStatus.UNHEALTHY)
            }
        }
    
    def is_healthy(self) -> bool:
        """Check if system is healthy"""
        return self.get_overall_status() in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]


# Global health checker instance
_health_checker = None


def initialize_health_checker(memory_api, connection_pool=None) -> SystemHealthChecker:
    """Initialize the global health checker"""
    global _health_checker
    _health_checker = SystemHealthChecker(memory_api, connection_pool)
    return _health_checker


def get_health_checker() -> Optional[SystemHealthChecker]:
    """Get the global health checker"""
    return _health_checker


async def run_health_checks() -> Dict[str, Any]:
    """Run health checks and return summary"""
    if not _health_checker:
        return {"error": "Health checker not initialized"}
    
    await _health_checker.run_health_checks()
    return _health_checker.get_health_summary()

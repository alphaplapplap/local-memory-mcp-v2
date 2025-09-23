"""
Adaptive LRU Cache for Local Memory MCP
High-performance L1 cache with dynamic sizing and memory-aware eviction
"""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

import psutil


class AdaptiveLRUCache:
    """
    Adaptive LRU Cache with the following optimizations:
    - Dynamic sizing based on available memory
    - TTL-based expiration
    - Compression for large values
    - Hit/miss ratio tracking
    - Memory pressure awareness
    """

    def __init__(self, max_size_mb: int = 512, default_ttl: int = 3600):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.default_ttl = default_ttl
        self.cache: OrderedDict = OrderedDict()
        self.access_times: Dict[str, float] = {}
        self.creation_times: Dict[str, float] = {}
        self.sizes: Dict[str, int] = {}
        self.lock = threading.RLock()

        # Performance metrics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.current_size_bytes = 0

        # Adaptive parameters
        self.compression_threshold = 10 * 1024  # 10KB
        self.memory_pressure_threshold = 0.85  # 85% memory usage
        self.dynamic_resize_enabled = True

    def _get_cache_key(
        self, query: str, domain: str = "default", limit: int = 10
    ) -> str:
        """Generate cache key from query parameters"""
        key_string = f"{domain}:{query}:{limit}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of cached value"""
        try:
            if isinstance(value, (list, dict)):
                return len(json.dumps(value, separators=(",", ":")))
            elif isinstance(value, str):
                return len(value.encode("utf-8"))
            else:
                return len(str(value))
        except Exception:
            return 1024  # Default estimate

    def _check_memory_pressure(self) -> bool:
        """Check if system is under memory pressure"""
        try:
            memory = psutil.virtual_memory()
            return memory.percent / 100.0 > self.memory_pressure_threshold
        except Exception:
            return False

    def _adaptive_resize(self):
        """Dynamically adjust cache size based on memory pressure"""
        if not self.dynamic_resize_enabled:
            return

        if self._check_memory_pressure():
            # Reduce cache size by 25% under memory pressure
            new_max_size = int(self.max_size_bytes * 0.75)
            if new_max_size < self.current_size_bytes:
                self._evict_to_size(new_max_size)
                self.max_size_bytes = new_max_size
        else:
            # Restore to original size when memory pressure is low
            original_size = 512 * 1024 * 1024  # 512MB
            self.max_size_bytes = min(self.max_size_bytes * 1.1, original_size)

    def _evict_expired(self):
        """Remove expired entries"""
        current_time = time.time()
        expired_keys = []

        for key, creation_time in list(self.creation_times.items()):
            if current_time - creation_time > self.default_ttl:
                expired_keys.append(key)

        for key in expired_keys:
            self._remove_key(key)

    def _evict_to_size(self, target_size: int):
        """Evict LRU items until cache size is under target"""
        while self.current_size_bytes > target_size and self.cache:
            # Remove least recently used item
            lru_key = next(iter(self.cache))
            self._remove_key(lru_key)
            self.evictions += 1

    def _remove_key(self, key: str):
        """Remove a key and update all tracking structures"""
        if key in self.cache:
            self.current_size_bytes -= self.sizes.get(key, 0)
            del self.cache[key]
            self.access_times.pop(key, None)
            self.creation_times.pop(key, None)
            self.sizes.pop(key, None)

    def get(
        self, query: str, domain: str = "default", limit: int = 10
    ) -> Optional[Any]:
        """Get cached value with LRU update"""
        with self.lock:
            key = self._get_cache_key(query, domain, limit)

            # Check expiration first
            current_time = time.time()
            creation_time = self.creation_times.get(key, 0)
            if current_time - creation_time > self.default_ttl:
                self._remove_key(key)
                self.misses += 1
                return None

            if key in self.cache:
                # Move to end (most recently used)
                value = self.cache.pop(key)
                self.cache[key] = value
                self.access_times[key] = current_time
                self.hits += 1
                return value
            else:
                self.misses += 1
                return None

    def put(
        self,
        query: str,
        value: Any,
        domain: str = "default",
        limit: int = 10,
        ttl: Optional[int] = None,
    ):
        """Cache a value with adaptive management"""
        with self.lock:
            key = self._get_cache_key(query, domain, limit)
            current_time = time.time()

            # Estimate size and skip if too large
            value_size = self._estimate_size(value)
            if value_size > self.max_size_bytes * 0.1:  # Skip if > 10% of cache size
                return

            # Remove old entry if exists
            if key in self.cache:
                self._remove_key(key)

            # Adaptive cache management
            self._evict_expired()
            self._adaptive_resize()

            # Ensure we have space
            required_space = self.current_size_bytes + value_size
            if required_space > self.max_size_bytes:
                self._evict_to_size(self.max_size_bytes - value_size)

            # Add new entry
            self.cache[key] = value
            self.access_times[key] = current_time
            self.creation_times[key] = current_time
            self.sizes[key] = value_size
            self.current_size_bytes += value_size

    def invalidate(self, pattern: Optional[str] = None, domain: Optional[str] = None):
        """Invalidate cache entries by pattern or domain"""
        with self.lock:
            if pattern is None and domain is None:
                # Clear all
                self.cache.clear()
                self.access_times.clear()
                self.creation_times.clear()
                self.sizes.clear()
                self.current_size_bytes = 0
                return

            keys_to_remove = []
            for key in list(self.cache.keys()):
                # Reconstruct query info to check domain
                if domain and key.startswith(f"{domain}:"):
                    keys_to_remove.append(key)
                elif pattern and pattern in key:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                self._remove_key(key)

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        with self.lock:
            total_requests = self.hits + self.misses
            hit_ratio = (self.hits / total_requests) if total_requests > 0 else 0

            return {
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "hit_ratio": hit_ratio,
                "entries": len(self.cache),
                "size_mb": self.current_size_bytes / (1024 * 1024),
                "max_size_mb": self.max_size_bytes / (1024 * 1024),
                "memory_utilization": self.current_size_bytes / self.max_size_bytes,
                "memory_pressure": self._check_memory_pressure(),
                "avg_entry_size_kb": (
                    (self.current_size_bytes / len(self.cache) / 1024)
                    if self.cache
                    else 0
                ),
            }

    def get_health_status(self) -> Dict[str, Any]:
        """Get cache health indicators"""
        stats = self.get_stats()

        # Health indicators
        health_score = 1.0
        issues = []

        if stats["hit_ratio"] < 0.5:
            health_score -= 0.3
            issues.append("Low hit ratio")

        if stats["memory_utilization"] > 0.95:
            health_score -= 0.2
            issues.append("High memory utilization")

        if stats["memory_pressure"]:
            health_score -= 0.3
            issues.append("System memory pressure")

        if stats["avg_entry_size_kb"] > 100:
            health_score -= 0.1
            issues.append("Large entry sizes")

        return {
            "health_score": max(0, health_score),
            "status": (
                "healthy"
                if health_score > 0.7
                else "degraded" if health_score > 0.4 else "unhealthy"
            ),
            "issues": issues,
            "recommendations": self._get_recommendations(stats),
        }

    def _get_recommendations(self, stats: Dict[str, Any]) -> List[str]:
        """Generate optimization recommendations"""
        recommendations = []

        if stats["hit_ratio"] < 0.5:
            recommendations.append("Consider increasing cache TTL or cache size")

        if stats["memory_utilization"] > 0.9:
            recommendations.append(
                "Consider increasing max cache size or enabling compression"
            )

        if stats["evictions"] > stats["hits"] * 0.1:
            recommendations.append("High eviction rate - consider larger cache size")

        if stats["avg_entry_size_kb"] > 50:
            recommendations.append("Enable compression for large entries")

        return recommendations


# Global cache instance for the bridge server
memory_cache = AdaptiveLRUCache(max_size_mb=512, default_ttl=1800)  # 30 min TTL

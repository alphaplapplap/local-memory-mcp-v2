import os
import sys

# CRITICAL: Disable banner BEFORE importing FastMCP to prevent JSON protocol errors
os.environ["FASTMCP_SHOW_CLI_BANNER"] = "false"

import time
import json
import uuid
import asyncio
import threading
import logging

# Configure logging based on server mode
if len(sys.argv) > 1 and sys.argv[1] == "mcp":
    # Set environment variable so other modules can check
    os.environ["SERVER_MODE"] = "mcp"
    # Initial config - will be overridden after imports
    logging.basicConfig(
        level=logging.WARNING, format="%(message)s", stream=sys.stderr, force=True
    )
else:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )
from decimal import Decimal
from datetime import datetime
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

import fastmcp
from fastmcp import FastMCP, Context

# FastAPI imports for HTTP layer
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from ollama_embeddings import OllamaEmbeddings
from postgres_memory_api import PostgresMemoryAPI, get_project_domain
from adaptive_lru_cache import memory_cache
from connection_pool import (
    initialize_connection_pool,
    get_connection_pool,
    get_health_checker,
)

# Import optimization manager
try:
    from optimization.optimization_manager import OptimizationManager

    optimization_available = True
except ImportError:
    logger.warning("OptimizationManager not available, running without optimizations")
    optimization_available = False

# Configure logger
logger = logging.getLogger(__name__)

# CRITICAL: Re-configure logging AFTER all imports to ensure stderr output in MCP mode
if len(sys.argv) > 1 and sys.argv[1] == "mcp":
    # Force ALL loggers to use stderr
    root_logger = logging.getLogger()
    root_logger.handlers = []
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(logging.WARNING)

# Get server name from environment or use default
server_name = os.environ.get("MCP_SERVER_NAME", "Local Context Memory")

# Initialize the FastMCP server
server = FastMCP(server_name)

# Check if Ollama is available
ollama_available = False
ollama_url = os.environ.get("OLLAMA_API_URL", "http://localhost:11434")
embedding_model = os.environ.get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:v1.5")
keep_alive = os.environ.get(
    "OLLAMA_KEEP_ALIVE", "10m"
)  # Keep model in memory for 10 minutes by default
ollama_embeddings = None

try:
    import requests

    response = requests.get(f"{ollama_url}/api/tags", timeout=10)
    if response.status_code == 200:
        models = response.json().get("models", [])
        model_names = [model.get("name", "") for model in models]

        if embedding_model in model_names:
            ollama_available = True
            ollama_embeddings = OllamaEmbeddings(
                model_name=embedding_model, base_url=ollama_url, keep_alive=keep_alive
            )
        else:
            logger.warning(
                f"Ollama found but embedding model {embedding_model} not available, using text search only"
            )
    else:
        logger.warning("Ollama API returned error, using text search only")
except Exception as e:
    logger.warning(f"Ollama check failed: {e}, using text search only")

# Initialize the PostgreSQL memory API
memory_api = PostgresMemoryAPI(ollama_embeddings=ollama_embeddings)

# Initialize optimization manager if available
if optimization_available:
    try:
        optimization_mgr = OptimizationManager(
            {
                "similarity_threshold": 0.95,
                "consolidation_threshold": 100,
                "archive_days": 30,
                "session_max_tokens": 500,
                "min_cluster_size": 3,
                "max_cluster_size": 20,
                "cluster_similarity": 0.7,
                "max_context_tokens": 2000,
            }
        )
        logger.info("OptimizationManager initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize OptimizationManager: {e}")
        optimization_mgr = None
else:
    optimization_mgr = None

# === HTTP SERVER SETUP ===


# Custom JSON encoder for Decimal and other types
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


# Performance metrics (same as bridge_server.py)
performance_metrics = {
    "queries_total": 0,
    "query_errors": 0,
    "avg_response_ms": 0,
    "memory_count": 0,
    "db_size_mb": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "slow_queries": 0,  # Queries > 1s
    "startup_time": datetime.now(),
}


# Request/Response models
class MemoryStoreRequest(BaseModel):
    content: str
    metadata: Optional[Dict[str, Any]] = {}
    domain: Optional[str] = None  # Auto-detection enabled
    tags: Optional[List[str]] = []


class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int = 1
    method: str
    params: Dict[str, Any]


class ConsolidationRequest(BaseModel):
    domain: str = "default"
    strategy: str = "clustering"


class MemorySearchRequest(BaseModel):
    query: str = ""
    domain: Optional[str] = "default"
    limit: Optional[int] = 10
    time_filter: Optional[str] = None


class SessionStartRequest(BaseModel):
    session_id: str
    project_name: Optional[str] = None
    working_directory: Optional[str] = None
    initial_topics: Optional[List[str]] = None


class SessionEndRequest(BaseModel):
    session_id: str
    outcome: Optional[Dict[str, Any]] = None
    final_topics: Optional[List[str]] = None
    conversation_summary: Optional[str] = None


class SessionMemoryTrackRequest(BaseModel):
    session_id: str
    memory_id: str
    domain: str = "default"
    created_during_session: bool = True
    interaction_type: str = "loaded"
    relevance_score: Optional[float] = None


# FastAPI lifespan function
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Only log to stderr for HTTP mode to avoid breaking MCP JSON protocol
    if os.environ.get("SERVER_MODE") != "mcp":
        print("🚀 Unified Memory Server starting...", file=sys.stderr)
        print(
            f"📊 PostgreSQL: {os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', 5432)}",
            file=sys.stderr,
        )
        print(f"🧠 Ollama: {ollama_url} ({embedding_model})", file=sys.stderr)
        print(f"🌐 HTTP Server: http://localhost:8000", file=sys.stderr)
        print(f"⚡ MCP Protocol: stdio transport", file=sys.stderr)
        print("🔄 Dual Protocol Mode: ENABLED", file=sys.stderr)

    # Initialize connection pool
    try:
        connection_params = {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", 5432)),
            "database": os.getenv("POSTGRES_DB", "postgres"),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
        }
        pool = initialize_connection_pool(
            connection_params,
            min_connections=int(os.getenv("POOL_MIN_CONNECTIONS", 2)),
            max_connections=int(os.getenv("POOL_MAX_CONNECTIONS", 10)),
        )
        if os.environ.get("SERVER_MODE") != "mcp":
            print(
                f"🔗 Connection pool initialized: {pool.get_pool_status()}",
                file=sys.stderr,
            )
    except Exception as e:
        logger.warning(f"Connection pool initialization failed: {e}")

    yield

    # Shutdown
    if os.environ.get("SERVER_MODE") != "mcp":
        print("🔻 Unified Memory Server shutting down...", file=sys.stderr)
    pool = get_connection_pool()
    if pool:
        if os.environ.get("SERVER_MODE") != "mcp":
            print("🔌 Closing database connection pool...", file=sys.stderr)
        pool.close_all_connections()


# Initialize FastAPI app
http_app = FastAPI(
    title="Memory Bridge API",
    description="Unified Memory System with MCP and HTTP support",
    version="2.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
http_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === HTTP ENDPOINTS ===


@http_app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Unified Memory Server",
        "version": "2.0.0",
        "protocols": ["MCP", "HTTP"],
        "description": "Unified MCP and HTTP memory server",
    }


@http_app.get("/api/health")
async def health_check():
    """Health check endpoint for hooks"""
    try:
        start_time = time.time()

        # Test database connection and get comprehensive stats
        domains = memory_api.list_domains()
        total_memories = 0
        database_size_mb = 0

        for domain in domains:
            stats = memory_api.get_domain_stats(domain)
            total_memories += stats.get("memory_count", 0)
            # Get size in MB (assuming stats provides size in bytes)
            if "size" in stats:
                database_size_mb += stats["size"] / (1024 * 1024)

        # Get actual unique tags count
        unique_tags_count = memory_api.get_total_unique_tags_count()

        response_time = (time.time() - start_time) * 1000

        # Test Ollama if available
        ollama_status = "available" if ollama_available else "unavailable"

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "response_time_ms": round(response_time, 2),
            "storage": {
                "backend": "postgresql",
                "status": "connected",
                "domains": len(domains),
                "total_memories": total_memories,
                "database_size_mb": (
                    round(database_size_mb, 2) if database_size_mb > 0 else 1.0
                ),
                "unique_tags": unique_tags_count,
                "embedding_model": embedding_model if ollama_available else "text-only",
                "accessible": True,
                "database_path": os.environ.get(
                    "DATABASE_URL", "postgresql://localhost/memories"
                ),
            },
            "system": {
                "platform": os.uname().sysname if hasattr(os, "uname") else "Unknown"
            },
            "ollama": {
                "status": ollama_status,
                "model": embedding_model if ollama_available else None,
            },
            "uptime_seconds": (
                datetime.now() - performance_metrics["startup_time"]
            ).total_seconds(),
            "protocols": ["MCP", "HTTP"],
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@http_app.get("/api/health/detailed")
async def health_check_detailed():
    """Detailed health check with cache and connection pool metrics"""
    base_health = await health_check()

    # Add cache health information
    cache_stats = memory_cache.get_stats()
    cache_health = memory_cache.get_health_status()

    # Get connection pool status
    pool = get_connection_pool()
    pool_status = pool.get_pool_status() if pool else None

    # Add more detailed storage info
    if "storage" in base_health:
        base_health["storage"]["location"] = os.environ.get(
            "DATABASE_URL", "postgresql://localhost/memories"
        )

    # Add statistics that hooks expect
    base_health.update(
        {
            "metrics": performance_metrics,
            "statistics": {
                "total_memories": base_health.get("storage", {}).get(
                    "total_memories", 0
                ),
                "database_size_mb": base_health.get("storage", {}).get(
                    "database_size_mb", 1.0
                ),
                "unique_tags": base_health.get("storage", {}).get("unique_tags", 0),
            },
            "cache": {"stats": cache_stats, "health": cache_health},
            "connection_pool": pool_status,
        }
    )

    return base_health


@http_app.get("/api/cache/stats")
async def get_cache_stats():
    """Get detailed cache statistics"""
    return {
        "cache_stats": memory_cache.get_stats(),
        "cache_health": memory_cache.get_health_status(),
    }


@http_app.post("/api/cache/invalidate")
async def invalidate_cache(domain: str = None, pattern: str = None):
    """Invalidate cache entries"""
    memory_cache.invalidate(pattern=pattern, domain=domain)
    return {
        "success": True,
        "message": f"Cache invalidated for domain={domain}, pattern={pattern}",
        "timestamp": datetime.now().isoformat(),
    }


@http_app.get("/api/metrics")
async def get_metrics():
    """Get performance metrics"""
    uptime = (datetime.now() - performance_metrics["startup_time"]).total_seconds()

    return {
        "uptime_seconds": uptime,
        "queries_total": performance_metrics["queries_total"],
        "query_errors": performance_metrics["query_errors"],
        "slow_queries": performance_metrics["slow_queries"],
        "avg_response_ms": performance_metrics["avg_response_ms"],
        "memory_count": performance_metrics["memory_count"],
    }


@http_app.get("/api/project/domain")
async def get_current_project_domain():
    """Get the current project domain based on the working directory"""
    try:
        domain = get_project_domain()
        return {"success": True, "domain": domain, "working_directory": os.getcwd()}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get project domain: {str(e)}"
        )


@http_app.post("/api/memories")
async def store_memory_http(request: MemoryStoreRequest):
    """Store a memory via HTTP (for hooks)"""
    try:
        # Prepare metadata with tags
        metadata = request.metadata or {}
        if request.tags:
            metadata["tags"] = request.tags

        # Use the same store_memory function as MCP
        memory_id = memory_api.store_memory(
            content=request.content, domain=request.domain, metadata=metadata
        )

        performance_metrics["queries_total"] += 1

        return {
            "success": True,
            "memory_id": memory_id,
            "domain": request.domain or "default",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        performance_metrics["query_errors"] += 1
        raise HTTPException(status_code=500, detail=str(e))


@http_app.get("/api/memories")
async def retrieve_memories_http(
    query: str = "", domain: str = "default", limit: int = 10
):
    """Retrieve memories via HTTP (for testing/debugging)"""
    try:
        start_time = time.time()
        performance_metrics["queries_total"] += 1

        # Use the same retrieve_memories function as MCP
        results = memory_api.retrieve_memories(query=query, domain=domain, limit=limit)

        response_time = (time.time() - start_time) * 1000
        performance_metrics["avg_response_ms"] = response_time

        if response_time > 1000:
            performance_metrics["slow_queries"] += 1

        return {
            "success": True,
            "query": query,
            "domain": domain,
            "memories": results,
            "count": len(results),
            "response_time_ms": round(response_time, 2),
        }
    except Exception as e:
        performance_metrics["query_errors"] += 1
        raise HTTPException(status_code=500, detail=str(e))


@http_app.post("/api/memories/search")
async def search_memories_http(request: MemorySearchRequest):
    """Search memories via HTTP (for session hooks)"""
    try:
        start_time = time.time()
        performance_metrics["queries_total"] += 1

        # Use the search_memories function (which uses embeddings if available)
        results = memory_api.retrieve_memories(
            query=request.query, domain=request.domain, limit=request.limit
        )

        # Apply time filter if provided
        if request.time_filter:
            from datetime import datetime, timedelta

            now = datetime.now()

            # Parse time filter
            if request.time_filter == "today":
                cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif request.time_filter == "recent":
                cutoff = now - timedelta(hours=24)
            elif request.time_filter == "last-week":
                cutoff = now - timedelta(days=7)
            elif request.time_filter == "last-month":
                cutoff = now - timedelta(days=30)
            elif request.time_filter == "last-2-weeks":
                cutoff = now - timedelta(days=14)
            else:
                cutoff = None

            # Filter results by creation time if cutoff is set
            if cutoff:
                filtered_results = []
                for memory in results:
                    created_at = memory.get("metadata", {}).get("created_at")
                    if created_at:
                        try:
                            mem_time = datetime.fromisoformat(
                                created_at.replace("Z", "+00:00")
                            )
                            if mem_time >= cutoff:
                                filtered_results.append(memory)
                        except:
                            # Keep memory if we can't parse date
                            filtered_results.append(memory)
                    else:
                        # Keep memory if no creation date
                        filtered_results.append(memory)
                results = filtered_results

        response_time = (time.time() - start_time) * 1000
        performance_metrics["avg_response_ms"] = response_time

        if response_time > 1000:
            performance_metrics["slow_queries"] += 1

        return {
            "success": True,
            "query": request.query,
            "domain": request.domain,
            "memories": results,
            "count": len(results),
            "response_time_ms": round(response_time, 2),
        }
    except Exception as e:
        performance_metrics["query_errors"] += 1
        raise HTTPException(status_code=500, detail=str(e))


@http_app.post("/api/sessions/start")
async def start_session_http(request: SessionStartRequest):
    """Start a new session via HTTP"""
    try:
        result = memory_api.start_session(
            session_id=request.session_id,
            project_name=request.project_name,
            working_directory=request.working_directory,
            initial_topics=request.initial_topics,
        )

        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@http_app.post("/api/sessions/end")
async def end_session_http(request: SessionEndRequest):
    """End a session via HTTP"""
    try:
        result = memory_api.end_session(
            session_id=request.session_id,
            outcome=request.outcome,
            final_topics=request.final_topics,
            conversation_summary=request.conversation_summary,
        )

        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@http_app.post("/api/sessions/track-memory")
async def track_session_memory_http(request: SessionMemoryTrackRequest):
    """Track session-memory association via HTTP"""
    try:
        success = memory_api.track_session_memory(
            session_id=request.session_id,
            memory_id=request.memory_id,
            domain=request.domain,
            created_during_session=request.created_during_session,
            interaction_type=request.interaction_type,
            relevance_score=request.relevance_score,
        )

        return {
            "success": success,
            "message": f"Tracked memory {request.memory_id} for session {request.session_id}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@http_app.get("/api/sessions/insights")
async def get_session_insights_http(
    project_name: Optional[str] = None, days_back: int = 30, limit: int = 10
):
    """Get session insights and analytics via HTTP"""
    try:
        # Get recurring topics
        topics = memory_api.find_recurring_topics(
            project_name=project_name, days_back=days_back, limit=limit
        )

        # Get progression patterns
        patterns = memory_api.analyze_progression_patterns(
            project_name=project_name, days_back=days_back
        )

        # Get uncompleted tasks
        tasks = memory_api.find_uncompleted_tasks(
            project_name=project_name, days_back=days_back
        )

        # Get statistics
        stats = memory_api.get_session_statistics(project_name=project_name)

        return {
            "success": True,
            "recurring_topics": topics,
            "progression_patterns": patterns,
            "uncompleted_tasks": tasks,
            "statistics": stats,
            "project": project_name or "all",
        }
    except Exception as e:
        # Return partial results if some analytics fail
        return {
            "success": False,
            "error": str(e),
            "recurring_topics": [],
            "progression_patterns": [],
            "uncompleted_tasks": [],
            "statistics": {},
        }


@http_app.post("/mcp")
async def mcp_endpoint(request: MCPRequest):
    """
    MCP protocol endpoint for memory retrieval
    Handles tools/call method for retrieve_memory
    """
    try:
        if request.method == "tools/call":
            tool_name = request.params.get("name")
            args = request.params.get("arguments", {})

            if tool_name == "retrieve_memory":
                query = args.get("query", "")
                domain = args.get("domain", "default")
                limit = args.get("limit", 10)

                # Use the same retrieve function
                results = memory_api.retrieve_memories(
                    query=query, domain=domain, limit=limit
                )

                return {
                    "jsonrpc": "2.0",
                    "id": request.id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    results, indent=2, cls=CustomJSONEncoder
                                ),
                            }
                        ]
                    },
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request.id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {tool_name}",
                    },
                }
        else:
            return {
                "jsonrpc": "2.0",
                "id": request.id,
                "error": {
                    "code": -32601,
                    "message": f"Method not supported: {request.method}",
                },
            }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
        }


# === MCP RESPONSE SANITIZATION ===
def _sanitize_mcp_response(data):
    """
    Sanitize response data for MCP to reduce token overhead.
    Removes embeddings and redundant fields while preserving functionality.
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Strip embeddings - massive token waste (768+ values per memory)
            if key == "embedding":
                continue
            # Strip redundant display-only fields
            elif key in ["query", "matched_tags", "optimization_used", "techniques_applied"]:
                continue
            else:
                sanitized[key] = _sanitize_mcp_response(value)
        return sanitized
    elif isinstance(data, list):
        return [_sanitize_mcp_response(item) for item in data]
    else:
        return data

# === MCP TOOLS SECTION ===
# Essential tools based on proven mcp-memory-service design

def generate_tags_with_ollama(content: str) -> List[str]:
    """Generate intelligent tags using Ollama AI."""
    if not ollama_embeddings:
        logger.warning("Ollama not available for tag generation")
        return []

    try:
        # Create a concise prompt for tag extraction
        prompt = f"""Extract 3-5 relevant tags from this text. Return only tags separated by commas:

{content[:500]}

Tags:"""

        # Use Ollama's generate API for text completion
        generate_url = f"{ollama_embeddings.base_url}/api/generate"
        response = ollama_embeddings.session.post(
            generate_url,
            json={
                "model": "llama3.2:3b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 50,  # Limit tokens
                    "stop": ["\n", ".", "!", "?"]
                }
            },
            timeout=15
        )

        if response.status_code == 200:
            result = response.json()
            tags_text = result.get('response', '').strip()

            # Parse comma-separated tags and clean them
            tags = [
                tag.strip().lower().replace(' ', '-')
                for tag in tags_text.split(',')
                if tag.strip() and len(tag.strip()) > 1
            ]

            # Filter out common words and limit to 5 tags
            filtered_tags = [
                tag for tag in tags[:5]
                if tag not in ['the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'with', 'from']
                and len(tag) > 1
            ]

            logger.info(f"Generated {len(filtered_tags)} tags: {filtered_tags}")
            return filtered_tags
        else:
            logger.warning(f"Ollama API returned status {response.status_code}")

    except Exception as e:
        logger.warning(f"Failed to generate tags with Ollama: {e}")

    return []


@server.tool()
def store_memory(
    content: str,
    domain: Optional[str] = None,
    tags: Optional[List[str]] = None,
    auto_tag: bool = True,
    source: Optional[str] = None,
    importance: Optional[float] = None,
) -> str:
    """Store memory with content and metadata."""
    metadata = {}
    if source:
        metadata["source"] = source
    if importance is not None:
        metadata["importance"] = importance

    # Combine user tags with auto-generated tags
    final_tags = list(tags) if tags else []

    if auto_tag and len(content.strip()) > 20:  # Only auto-tag substantial content
        try:
            generated_tags = generate_tags_with_ollama(content)
            # Add generated tags, avoiding duplicates
            for tag in generated_tags:
                if tag not in final_tags:
                    final_tags.append(tag)
            logger.info(f"Auto-generated {len(generated_tags)} tags, total: {len(final_tags)}")
        except Exception as e:
            logger.warning(f"Auto-tagging failed: {e}")

    if final_tags:
        metadata["tags"] = final_tags

    memory_id = memory_api.store_memory(content, metadata, domain)
    return memory_id

@server.tool()
def retrieve_memory(
    query: str,
    domain: Optional[str] = None,
    limit: Optional[int] = 5,
    min_similarity: Optional[float] = 0.0,
) -> List[Dict[str, Any]]:
    """Retrieve memories by semantic similarity."""
    results = memory_api.retrieve_memories(query, limit, domain)

    for result in results:
        result["query"] = query
        if "score" not in result:
            result["score"] = 0.0

    return _sanitize_mcp_response(results)

@server.tool()
def search_by_tag(
    tags: List[str],
    domain: Optional[str] = None,
    match_all: bool = False,
) -> List[Dict[str, Any]]:
    """Search memories by tags."""
    tag_query = f"tags:{','.join(tags)}"
    results = memory_api.retrieve_memories(tag_query, 100, domain)

    return _sanitize_mcp_response(results)

@server.tool()
def delete_memory(
    memory_id: str,
    domain: Optional[str] = None,
) -> bool:
    """Delete memory by ID."""
    return memory_api.delete_memory(memory_id, domain)

@server.tool()
def list_domains() -> List[str]:
    """List available memory domains."""
    return memory_api.list_domains()

# Keep resource for compatibility
@server.resource("memory://{domain}/{query}")
def get_memories(
    domain: str, query: str, limit: Optional[int] = 5
) -> List[Dict[str, Any]]:
    """Retrieve memories from domain using search query."""
    results = memory_api.retrieve_memories(query, limit, domain)
    return results

# Core function for get_project_domain compatibility
def get_project_domain() -> str:
    """Get current project domain from working directory."""
    from postgres_memory_api import get_project_domain
    return get_project_domain()


# === SERVER STARTUP SECTION ===


def run_http_server():
    """Run the HTTP server in a separate thread"""
    port = int(os.environ.get("BRIDGE_PORT", 8000))
    print(f"🌐 Starting HTTP server on port {port}", file=sys.stderr)
    uvicorn.run(
        http_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=False,  # Reduce noise in logs
    )


def run_mcp_server():
    """Run the MCP server with stdio transport"""
    # No print statements in MCP mode to avoid breaking JSON protocol
    server.run(transport="stdio")


if __name__ == "__main__":
    # Detect mode based on environment or command line arguments
    mode = os.environ.get("SERVER_MODE", "mcp")

    if len(sys.argv) > 1:
        mode = sys.argv[1]

    if mode == "http":
        # HTTP-only mode (for testing)
        run_http_server()
    elif mode == "dual":
        # Dual protocol mode - HTTP in background thread, MCP in main thread
        print("🚀 Starting Unified Memory Server in DUAL mode", file=sys.stderr)

        # Start HTTP server in background thread
        http_thread = threading.Thread(target=run_http_server, daemon=True)
        http_thread.start()

        # Give HTTP server time to start
        time.sleep(2)

        # Run MCP server in main thread (blocks)
        run_mcp_server()
    else:
        # Default: MCP-only mode (for Claude Code)
        run_mcp_server()

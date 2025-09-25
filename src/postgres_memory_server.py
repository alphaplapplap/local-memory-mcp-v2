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
        level=logging.WARNING,
        format='%(message)s',
        stream=sys.stderr,
        force=True
    )
else:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
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
from connection_pool import initialize_connection_pool, get_connection_pool, get_health_checker

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
    stderr_handler.setFormatter(logging.Formatter('%(message)s'))
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
        optimization_mgr = OptimizationManager({
            'similarity_threshold': 0.95,
            'consolidation_threshold': 100,
            'archive_days': 30,
            'session_max_tokens': 500,
            'min_cluster_size': 3,
            'max_cluster_size': 20,
            'cluster_similarity': 0.7,
            'max_context_tokens': 2000
        })
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
    "startup_time": datetime.now()
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
        print(f"📊 PostgreSQL: {os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', 5432)}", file=sys.stderr)
        print(f"🧠 Ollama: {ollama_url} ({embedding_model})", file=sys.stderr)
        print(f"🌐 HTTP Server: http://localhost:8000", file=sys.stderr)
        print(f"⚡ MCP Protocol: stdio transport", file=sys.stderr)
        print("🔄 Dual Protocol Mode: ENABLED", file=sys.stderr)

    # Initialize connection pool
    try:
        connection_params = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'postgres'),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', 'postgres')
        }
        pool = initialize_connection_pool(
            connection_params,
            min_connections=int(os.getenv('POOL_MIN_CONNECTIONS', 2)),
            max_connections=int(os.getenv('POOL_MAX_CONNECTIONS', 10))
        )
        if os.environ.get("SERVER_MODE") != "mcp":
            print(f"🔗 Connection pool initialized: {pool.get_pool_status()}", file=sys.stderr)
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
    lifespan=lifespan
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
        "description": "Unified MCP and HTTP memory server"
    }

@http_app.get("/api/health")
async def health_check():
    """Health check endpoint for hooks"""
    try:
        start_time = time.time()

        # Test database connection and get comprehensive stats
        domains = memory_api.list_domains()
        total_memories = 0
        unique_tags = set()
        database_size_mb = 0

        for domain in domains:
            stats = memory_api.get_domain_stats(domain)
            total_memories += stats.get("memory_count", 0)
            # Get size in MB (assuming stats provides size in bytes)
            if "size" in stats:
                database_size_mb += stats["size"] / (1024 * 1024)
            # Collect unique tags (would need API method for this)

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
                "database_size_mb": round(database_size_mb, 2) if database_size_mb > 0 else 1.0,
                "unique_tags": len(unique_tags) if unique_tags else 10,  # Default for now
                "embedding_model": embedding_model if ollama_available else "text-only",
                "accessible": True,
                "database_path": os.environ.get("DATABASE_URL", "postgresql://localhost/memories")
            },
            "system": {
                "platform": os.uname().sysname if hasattr(os, 'uname') else "Unknown"
            },
            "ollama": {
                "status": ollama_status,
                "model": embedding_model if ollama_available else None
            },
            "uptime_seconds": (datetime.now() - performance_metrics["startup_time"]).total_seconds(),
            "protocols": ["MCP", "HTTP"]
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
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
        base_health["storage"]["location"] = os.environ.get("DATABASE_URL", "postgresql://localhost/memories")

    # Add statistics that hooks expect
    base_health.update({
        "metrics": performance_metrics,
        "statistics": {
            "total_memories": base_health.get("storage", {}).get("total_memories", 0),
            "database_size_mb": base_health.get("storage", {}).get("database_size_mb", 1.0),
            "unique_tags": base_health.get("storage", {}).get("unique_tags", 10)
        },
        "cache": {
            "stats": cache_stats,
            "health": cache_health
        },
        "connection_pool": pool_status
    })

    return base_health

@http_app.get("/api/cache/stats")
async def get_cache_stats():
    """Get detailed cache statistics"""
    return {
        "cache_stats": memory_cache.get_stats(),
        "cache_health": memory_cache.get_health_status()
    }

@http_app.post("/api/cache/invalidate")
async def invalidate_cache(domain: str = None, pattern: str = None):
    """Invalidate cache entries"""
    memory_cache.invalidate(pattern=pattern, domain=domain)
    return {
        "success": True,
        "message": f"Cache invalidated for domain={domain}, pattern={pattern}",
        "timestamp": datetime.now().isoformat()
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
        "memory_count": performance_metrics["memory_count"]
    }

@http_app.get("/api/project/domain")
async def get_current_project_domain():
    """Get the current project domain based on the working directory"""
    try:
        domain = get_project_domain()
        return {
            "success": True,
            "domain": domain,
            "working_directory": os.getcwd()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get project domain: {str(e)}")

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
            content=request.content,
            domain=request.domain,
            metadata=metadata
        )

        performance_metrics["queries_total"] += 1

        return {
            "success": True,
            "memory_id": memory_id,
            "domain": request.domain or "default",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        performance_metrics["query_errors"] += 1
        raise HTTPException(status_code=500, detail=str(e))

@http_app.get("/api/memories")
async def retrieve_memories_http(query: str = "", domain: str = "default", limit: int = 10):
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
            "response_time_ms": round(response_time, 2)
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
            query=request.query,
            domain=request.domain,
            limit=request.limit
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
                            mem_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
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
            "response_time_ms": round(response_time, 2)
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
            initial_topics=request.initial_topics
        )

        return {
            "success": True,
            **result
        }
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
            conversation_summary=request.conversation_summary
        )

        return {
            "success": True,
            **result
        }
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
            relevance_score=request.relevance_score
        )

        return {
            "success": success,
            "message": f"Tracked memory {request.memory_id} for session {request.session_id}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@http_app.get("/api/sessions/insights")
async def get_session_insights_http(
    project_name: Optional[str] = None,
    days_back: int = 30,
    limit: int = 10
):
    """Get session insights and analytics via HTTP"""
    try:
        # Get recurring topics
        topics = memory_api.find_recurring_topics(
            project_name=project_name,
            days_back=days_back,
            limit=limit
        )

        # Get progression patterns
        patterns = memory_api.analyze_progression_patterns(
            project_name=project_name,
            days_back=days_back
        )

        # Get uncompleted tasks
        tasks = memory_api.find_uncompleted_tasks(
            project_name=project_name,
            days_back=days_back
        )

        # Get statistics
        stats = memory_api.get_session_statistics(project_name=project_name)

        return {
            "success": True,
            "recurring_topics": topics,
            "progression_patterns": patterns,
            "uncompleted_tasks": tasks,
            "statistics": stats,
            "project": project_name or "all"
        }
    except Exception as e:
        # Return partial results if some analytics fail
        return {
            "success": False,
            "error": str(e),
            "recurring_topics": [],
            "progression_patterns": [],
            "uncompleted_tasks": [],
            "statistics": {}
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
                results = memory_api.retrieve_memories(query=query, domain=domain, limit=limit)

                return {
                    "jsonrpc": "2.0",
                    "id": request.id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(results, indent=2, cls=CustomJSONEncoder)
                            }
                        ]
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request.id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {tool_name}"
                    }
                }
        else:
            return {
                "jsonrpc": "2.0",
                "id": request.id,
                "error": {
                    "code": -32601,
                    "message": f"Method not supported: {request.method}"
                }
            }
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }

# === MCP TOOLS SECTION ===
# (All existing MCP tools remain unchanged below)


@server.tool()
def store_memory(
    content: str,
    domain: Optional[str] = None,
    source: Optional[str] = None,
    importance: Optional[float] = None,
    tags: Optional[List[str]] = None,
) -> str:
    """
    Store new information with optional tags and metadata.

    This tool allows you to save important information that should be remembered across conversations.
    The content will be automatically indexed for semantic search (if Ollama is available) or text search.
    Supports both domain-based segmentation and tag-based categorization.

    Parameters:
    - content (str): The memory content to store, such as a fact, note, or piece of information.
                    Examples:
                    * "User prefers Python over JavaScript for backend development"
                    * "Meeting scheduled for Tuesday at 3pm about project planning"
                    * "User's favorite color is blue and they work in San Francisco"

    - domain (str, optional): The domain/context for this memory. Memories are segmented by domain
                             for better retrieval accuracy. Defaults to 'default'. Examples:
                             * "startup" - for business-related memories
                             * "health" - for health-related information
                             * "personal" - for personal preferences
                             * "work" - for work-related context
                             * "learning" - for educational content

    - source (str, optional): Where this memory originated from. Examples:
                              * "conversation"
                              * "document"
                              * "email"
                              * "meeting_notes"
                              * "web_search"
                              * "user_input"

    - importance (float, optional): Importance score from 0.0 to 1.0 where:
                                   * 0.0-0.3 = Low importance (casual mentions, trivia)
                                   * 0.4-0.7 = Medium importance (useful context, preferences)
                                   * 0.8-1.0 = High importance (critical information, decisions)

    - tags (List[str], optional): Tags to categorize the memory as an array of strings.
                                 Examples: ["important", "reference", "work", "personal"]
                                 If you have a comma-separated string, convert it to an array before calling.

    Returns:
    str: A unique memory ID that can be used to update or reference this memory later.

    Example usage:
    - store_memory("User loves hiking in the mountains", "personal", "conversation", 0.7, ["hobbies", "outdoor"])
    - store_memory("Series A funding closed at $10M", "startup", "meeting", 0.9, ["funding", "milestone"])
    - store_memory("Python is preferred for data science projects", "work", "conversation", 0.8, ["programming", "preference"])
    """
    # Pre-validate inputs before calling memory_api
    if not content or not isinstance(content, str):
        raise ValueError("Content must be a non-empty string")

    if content.strip() == "":
        raise ValueError("Content cannot be empty or whitespace only")

    # Use optimization manager if available
    if optimization_mgr:
        should_store, reason, optimized_data = optimization_mgr.optimize_memory_storage(
            content=content,
            domain=domain,
            metadata={'tags': tags, 'importance': importance, 'source': source},
            project_name=domain  # Use domain as project name for now
        )

        if not should_store:
            raise ValueError(f"Memory rejected: {reason}")
    else:
        # Fallback to basic size validation
        max_content_size = 5_000  # 5KB limit
        if len(content) > max_content_size:
            raise ValueError(f"Content too long (max {max_content_size:,} characters, got {len(content):,})")

        # Check byte size for unicode content
        content_bytes = content.encode('utf-8')
        max_bytes = 5 * 1024  # 5KB
        if len(content_bytes) > max_bytes:
            raise ValueError(f"Content too large (max {max_bytes:,} bytes, got {len(content_bytes):,} bytes)")

    # Domain validation
    if domain is not None:
        if not isinstance(domain, str):
            raise ValueError("Domain must be a string or None")

        import re
        if not re.match(r"^[a-zA-Z0-9_-]+$", domain):
            raise ValueError("Domain must contain only alphanumeric characters, underscores, and hyphens")

        if len(domain) < 1:
            raise ValueError("Domain cannot be empty")
        elif len(domain) > 50:
            raise ValueError(f"Domain too long (max 50 characters, got {len(domain)})")

        # Reserved names validation
        reserved_names = {'system', 'admin', 'root', 'user', 'test', 'temp', 'public', 'private'}
        if domain.lower() in reserved_names:
            raise ValueError(f"Domain name '{domain}' is reserved")

    metadata = {}
    if source:
        metadata["source"] = source
    if importance is not None:
        metadata["importance"] = importance
    if tags:
        metadata["tags"] = tags

    # Metadata size validation
    if metadata:
        import json
        metadata_json = json.dumps(metadata, ensure_ascii=False)
        metadata_bytes = metadata_json.encode('utf-8')
        max_metadata_bytes = 2 * 1024  # 2KB (optimized from 10KB)
        if len(metadata_bytes) > max_metadata_bytes:
            raise ValueError(f"Metadata too large (max {max_metadata_bytes:,} bytes, got {len(metadata_bytes):,} bytes)")

    memory_id = memory_api.store_memory(content, metadata, domain)
    return memory_id


@server.tool()
def update_memory(
    memory_id: str,
    content: Optional[str] = None,
    importance: Optional[float] = None,
    domain: Optional[str] = None,
) -> bool:
    """
    Update an existing memory chunk with new information.

    This tool allows you to modify previously stored memories. You can update the content,
    change the importance level. If updating content, the memory will be
    re-indexed for search.

    Parameters:
    - memory_id (str): The unique ID of the memory to update (returned from store_memory).
                      Example: "mem_1234567890123"

    - content (str, optional): New content to replace the existing memory content.
                              If provided, this completely replaces the old content.
                              Example: "User prefers React over Vue for frontend projects"

    - importance (float, optional): New importance score from 0.0 to 1.0.
                                   * 0.0-0.3 = Low importance
                                   * 0.4-0.7 = Medium importance
                                   * 0.8-1.0 = High importance

    - domain (str, optional): The domain where this memory is stored.
                             If not specified, uses the default domain.

    Returns:
    bool: True if the update was successful, False if the memory_id was not found.

    Example usage:
    - update_memory("mem_1234567890123", content="User now prefers TypeScript over JavaScript")
    - update_memory("mem_1234567890123", importance=0.9)
    """
    metadata = {}
    if importance is not None:
        metadata["importance"] = importance

    success = memory_api.update_memory(memory_id, content, metadata, domain)
    return success


@server.resource("memory://{domain}/{query}")
def get_memories(
    domain: str, query: str, limit: Optional[int] = 5
) -> List[Dict[str, Any]]:
    """
    Retrieve memories from a specific domain using semantic or text search.

    This resource performs intelligent search within a specific domain,
    finding relevant content based on the query. Uses vector embeddings if available,
    falls back to text search otherwise.

    URI Pattern: memory://{domain}/{query}

    Parameters:
    - domain (str): The domain to search within. Examples:
                   * "default" - general memories
                   * "startup" - business context
                   * "health" - health information
                   * "personal" - personal preferences

    - query (str): The search query to find relevant memories. This can be:
                  * Natural language questions: "What does the user like to do?"
                  * Keywords: "python programming preferences"
                  * Concepts: "work schedule" or "personal information"
                  * Specific topics: "machine learning projects"

    - limit (int, optional): Maximum number of memories to return (default: 5).
                            Higher values return more results but may include less relevant ones.
                            Recommended range: 3-10.

    Returns:
    List[Dict[str, Any]]: A list of memory objects, each containing:
        - id (str): Unique memory identifier
        - content (str): The stored memory content
        - metadata (dict): Associated metadata including source, importance, timestamps
        - score (float): Relevance score (higher = more relevant)

    Example URIs:
    - memory://startup/funding%20strategy
    - memory://health/blood%20pressure
    - memory://default/programming%20preferences
    """
    results = memory_api.retrieve_memories(query, limit, domain)
    return results


@server.tool()
def search_memories(
    query: str, domain: Optional[str] = None, limit: Optional[int] = 5, time_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Find relevant memories based on query using semantic or text search.

    This tool provides intelligent search across memories in the specified domain.
    Uses vector embeddings for semantic similarity if available, falls back to text search.
    Domain segmentation ensures queries return contextually relevant results.

    Parameters:
    - query (str): Search query to find relevant memories based on content.
                  Examples:
                  * "What does the user like for breakfast?"
                  * "programming projects and preferences"
                  * "work meetings this week"
                  * "personal goals and aspirations"
                  * "python programming techniques"
                  * "user's favorite restaurants"

    - domain (str, optional): The domain to search within. If not specified,
                             searches the default domain. Examples:
                             * "startup" - business memories
                             * "health" - health information
                             * "personal" - personal data
                             * "work" - work-related context
                             * "learning" - educational content

    - limit (int, optional): Maximum number of results to return (default: 5).
                            Range: 1-20. Higher values may include less relevant results.
    - time_filter (str, optional): Filter memories by creation time. Examples:
                                   * "last-week" - memories from last 7 days
                                   * "last-month" - memories from last 30 days
                                   * "recent" - memories from last 24 hours
                                   * "today" - memories created today

    Returns:
    List[Dict[str, Any]]: A list of memory objects with search metadata:
        - id (str): Unique memory identifier
        - content (str): The stored memory content
        - metadata (dict): Memory metadata (source, importance, timestamps, tags)
        - score (float): Relevance/similarity score (higher = more relevant)
        - query (str): The original search query (for reference)

    Example usage:
    - search_memories("user preferences", "personal", 3)
    - search_memories("python programming", limit=10)  # searches default domain
    - search_memories("recent meetings", "startup", 5)
    - search_memories("machine learning projects", "work", 8)
    """
    # Use optimization manager if available
    if optimization_mgr:
        # Get more raw results for optimization to work with
        raw_limit = min(limit * 3, 30) if limit else 15  # Get 3x for clustering
        results = memory_api.retrieve_memories(query, raw_limit, domain, time_filter)

        # Optimize retrieved memories
        optimized_results, optimization_meta = optimization_mgr.optimize_memory_retrieval(
            query=query,
            memories=results,
            domain=domain or "default",
            project_name=domain,  # Use domain as project name
            token_budget=1000  # Default budget
        )

        # Limit to requested count and add metadata
        final_results = optimized_results[:limit] if limit else optimized_results
        for result in final_results:
            result["query"] = query
            if "score" not in result:
                result["score"] = 0.0
            result["optimization_applied"] = True
            result["optimization_meta"] = optimization_meta

        return final_results
    else:
        # Fallback to standard retrieval
        results = memory_api.retrieve_memories(query, limit, domain, time_filter)

        # Add search information
        for result in results:
            result["query"] = query
            if "score" not in result:
                result["score"] = 0.0

        return results


@server.tool()
def recall_memory(
    query: str, n_results: Optional[int] = 5
) -> List[Dict[str, Any]]:
    """
    Retrieve memories using natural language time expressions and optional semantic search.
    
    This tool supports various time-related expressions and can find memories based on
    when they were stored or when events occurred. Uses semantic search to understand
    temporal context and content relevance.

    Parameters:
    - query (str): Natural language query specifying the time frame or content to recall.
                  Supports various time-related expressions such as:
                  * "yesterday", "last week", "2 days ago"
                  * "last summer", "this month", "last January"
                  * "spring", "winter", "Christmas", "Thanksgiving"
                  * "morning", "evening", "yesterday afternoon"
                  * "recall what I stored last week"
                  * "find information about databases from two months ago"
                  * "what did we discuss yesterday about the project"

    - n_results (int, optional): Maximum number of results to return (default: 5).
                                Range: 1-20. Higher values may include less relevant results.

    Returns:
    List[Dict[str, Any]]: A list of memory objects with temporal context:
        - id (str): Unique memory identifier
        - content (str): The stored memory content
        - metadata (dict): Memory metadata including timestamps
        - score (float): Relevance/similarity score
        - query (str): The original recall query

    Example usage:
    - recall_memory("recall what I stored last week")
    - recall_memory("find information about databases from two months ago", 5)
    - recall_memory("what did we discuss yesterday about the project", 3)
    - recall_memory("memories from last summer", 10)
    """
    results = memory_api.retrieve_memories(query, n_results)
    
    # Add search information
    for result in results:
        result["query"] = query
        if "score" not in result:
            result["score"] = 0.0
    
    return results


@server.tool()
def search_by_tag(
    tags: List[str], domain: Optional[str] = None, limit: Optional[int] = 5
) -> List[Dict[str, Any]]:
    """
    Search memories by tags. Returns memories matching ANY of the specified tags.

    This tool allows you to find memories based on their tag categorization.
    It returns memories that contain any of the specified tags, making it useful
    for finding related content across different topics.

    Parameters:
    - tags (List[str]): List of tags to search for. Returns memories matching ANY of these tags.
                       Examples:
                       * ["important", "reference"]
                       * ["work", "meeting"]
                       * ["personal", "hobby"]
                       * ["learning", "python", "programming"]

    - domain (str, optional): The domain to search within. If not specified,
                             searches the default domain.

    - limit (int, optional): Maximum number of results to return (default: 5).
                            Range: 1-20.

    Returns:
    List[Dict[str, Any]]: A list of memory objects matching the tags:
        - id (str): Unique memory identifier
        - content (str): The stored memory content
        - metadata (dict): Memory metadata including tags
        - score (float): Relevance score
        - matched_tags (List[str]): Tags that matched the search

    Example usage:
    - search_by_tag(["important", "reference"])
    - search_by_tag(["work", "meeting"], "startup", 10)
    - search_by_tag(["personal", "hobby"], "personal", 3)
    """
    # Convert tags to a search query
    tag_query = f"tags:{','.join(tags)}"
    results = memory_api.retrieve_memories(tag_query, limit, domain)
    
    # Add tag matching information
    for result in results:
        # Tags are stored in metadata
        metadata = result.get('metadata', {})
        result_tags = metadata.get('tags', [])
        result["matched_tags"] = [tag for tag in tags if tag in result_tags]
        if "score" not in result:
            result["score"] = 0.0
    
    return results


@server.tool()
def list_memory_domains() -> List[str]:
    """
    List all available memory domains in the database.

    This tool returns a list of all domain tables that have been created in the database.
    Each domain represents a separate context for storing memories (e.g., 'default', 'startup', 'health').

    Returns:
    List[str]: A list of domain names that can be used with store_memory and search_memories.

    Example usage:
    - list_memory_domains() might return: ["default", "startup", "health", "personal"]

    This is useful for:
    - Discovering what domains are available before storing/searching
    - Understanding the organization of stored memories
    - Validating domain names before use
    """
    return memory_api.list_domains()


@server.tool()
def delete_memory(
    memory_id: str, domain: Optional[str] = None
) -> bool:
    """
    Delete a specific memory by its ID.

    This tool allows you to remove a specific memory from the system.
    Use with caution as this action cannot be undone.

    Parameters:
    - memory_id (str): The unique ID of the memory to delete.
                      Example: "mem_1234567890123"

    - domain (str, optional): The domain where this memory is stored.
                             If not specified, uses the default domain.

    Returns:
    bool: True if the deletion was successful, False if the memory_id was not found.

    Example usage:
    - delete_memory("mem_1234567890123")
    - delete_memory("mem_1234567890123", "startup")
    """
    try:
        success = memory_api.delete_memory(memory_id, domain)
        return success
    except Exception as e:
        logger.error(f"Error deleting memory {memory_id}: {e}")
        return False


@server.tool()
def delete_by_tag(
    tags: List[str], domain: Optional[str] = None
) -> int:
    """
    Delete all memories with specific tags.
    WARNING: Deletes ALL memories containing any of the specified tags.

    This tool allows you to remove multiple memories at once based on their tags.
    Use with extreme caution as this action cannot be undone.

    Parameters:
    - tags (List[str]): Array of tag labels. Memories containing any of these tags will be deleted.
                       Examples:
                       * ["temporary", "outdated"]
                       * ["test", "debug"]
                       * ["old", "archived"]

    - domain (str, optional): The domain to search within. If not specified,
                             searches the default domain.

    Returns:
    int: Number of memories that were deleted.

    Example usage:
    - delete_by_tag(["temporary", "outdated"])
    - delete_by_tag(["test", "debug"], "startup")
    - delete_by_tag(["old", "archived"], "personal")
    """
    try:
        # Find memories with these tags
        tag_query = f"tags:{','.join(tags)}"
        memories = memory_api.retrieve_memories(tag_query, limit=1000, domain=domain)
        
        deleted_count = 0
        for memory in memories:
            if memory_api.delete_memory(memory['id'], domain):
                deleted_count += 1
        
        return deleted_count
    except Exception as e:
        logger.error(f"Error deleting memories by tags {tags}: {e}")
        return 0


@server.tool()
def get_current_project_domain() -> str:
    """
    Get the current project domain based on the working directory.

    This tool automatically detects the project domain by analyzing the current working directory
    for Git repository information, project files, and other context clues. The domain name
    is sanitized for use as a database table name.

    Returns:
    str: The detected project domain name (e.g., "local-memory-mcp-v2", "my-startup-project")

    Example usage:
    - get_current_project_domain() might return: "local-memory-mcp-v2"

    This is useful for:
    - Automatically routing memories to the correct project context
    - Understanding which domain memories will be stored in by default
    - Setting up project-specific memory organization
    """
    from postgres_memory_api import get_project_domain

    return get_project_domain()


@server.tool()
def create_domain(domain_name: str) -> bool:
    """
    Create a new memory domain.

    This tool creates a new domain table in the database for organizing memories.
    Domains provide logical separation of memories by context, project, or topic.

    Parameters:
    - domain_name (str): The name of the domain to create. Must be a valid identifier:
                        * Use lowercase letters, numbers, underscores, and hyphens
                        * Avoid special characters and spaces
                        * Examples: "startup", "health", "project-alpha", "user_preferences"

    Returns:
    bool: True if the domain was created successfully, False if it already exists or creation failed.

    Example usage:
    - create_domain("startup") -> True (new domain created)
    - create_domain("health") -> True (new domain created)
    - create_domain("startup") -> False (already exists)

    This is useful for:
    - Setting up new project contexts
    - Organizing memories by topic or category
    - Preparing domains before storing memories
    """
    try:
        # Check if domain already exists
        existing_domains = memory_api.list_domains()
        if domain_name in existing_domains:
            return False

        # Create the domain by storing a test memory (which creates the table)
        test_memory_id = memory_api.store_memory(
            content="Domain initialization memory",
            metadata={"source": "domain_creation", "temporary": True},
            domain=domain_name,
        )

        # Remove the test memory
        memory_api.delete_memory(test_memory_id, domain_name)

        return True
    except Exception as e:
        logger.error(f"Error creating domain {domain_name}: {e}")
        return False


@server.tool()
def get_domain_info(domain_name: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific memory domain.

    This tool provides comprehensive information about a domain including memory count,
    storage size, and other metadata.

    Parameters:
    - domain_name (str): The name of the domain to get information about.

    Returns:
    Dict[str, Any]: Domain information including:
        - domain (str): The domain name
        - memory_count (int): Number of memories in this domain
        - table_size (str): Approximate size of the domain table
        - exists (bool): Whether the domain exists
        - last_activity (str): Timestamp of the most recent memory (if any)

    Example usage:
    - get_domain_info("startup") -> {"domain": "startup", "memory_count": 15, "table_size": "2.1 MB", "exists": True, "last_activity": "2024-01-15 10:30:00"}
    - get_domain_info("nonexistent") -> {"domain": "nonexistent", "memory_count": 0, "table_size": "0 B", "exists": False, "last_activity": None}

    This is useful for:
    - Understanding domain usage and size
    - Monitoring memory storage across domains
    - Validating domain existence before operations
    """
    try:
        # Check if domain exists
        existing_domains = memory_api.list_domains()
        if domain_name not in existing_domains:
            return {
                "domain": domain_name,
                "memory_count": 0,
                "table_size": "0 B",
                "exists": False,
                "last_activity": None,
            }

        # Get domain statistics
        stats = memory_api.get_domain_stats(domain_name)

        return {
            "domain": domain_name,
            "memory_count": stats.get("memory_count", 0),
            "table_size": stats.get("table_size", "0 B"),
            "exists": True,
            "last_activity": stats.get("last_activity", None),
        }
    except Exception as e:
        logger.error(f"Error getting domain info for {domain_name}: {e}")
        return {
            "domain": domain_name,
            "memory_count": 0,
            "table_size": "0 B",
            "exists": False,
            "last_activity": None,
            "error": str(e),
        }


@server.tool()
def switch_to_domain(domain_name: str) -> Dict[str, Any]:
    """
    Switch the current working domain context.

    This tool sets the default domain for subsequent memory operations.
    After switching, store_memory and search_memories operations will use this domain
    unless explicitly overridden.

    Parameters:
    - domain_name (str): The domain to switch to. If the domain doesn't exist, it will be created.

    Returns:
    Dict[str, Any]: Information about the domain switch:
        - success (bool): Whether the switch was successful
        - domain (str): The domain that was switched to
        - created (bool): Whether the domain was created (True) or already existed (False)
        - memory_count (int): Number of memories in this domain
        - message (str): Human-readable status message

    Example usage:
    - switch_to_domain("startup") -> {"success": True, "domain": "startup", "created": False, "memory_count": 15, "message": "Switched to existing domain 'startup' with 15 memories"}
    - switch_to_domain("new-project") -> {"success": True, "domain": "new-project", "created": True, "memory_count": 0, "message": "Created and switched to new domain 'new-project'"}

    This is useful for:
    - Changing context between different projects or topics
    - Setting up new project domains
    - Organizing memory operations by context
    """
    try:
        # Check if domain exists
        existing_domains = memory_api.list_domains()
        created = False

        if domain_name not in existing_domains:
            # Create the domain
            success = create_domain(domain_name)
            if not success:
                return {
                    "success": False,
                    "domain": domain_name,
                    "created": False,
                    "memory_count": 0,
                    "message": f"Failed to create domain '{domain_name}'",
                }
            created = True

        # Get domain info
        domain_info = get_domain_info(domain_name)

        # Update the default domain in the memory API
        memory_api.default_domain = domain_name

        return {
            "success": True,
            "domain": domain_name,
            "created": created,
            "memory_count": domain_info["memory_count"],
            "message": f"{'Created and switched to' if created else 'Switched to existing'} domain '{domain_name}' with {domain_info['memory_count']} memories",
        }
    except Exception as e:
        logger.error(f"Error switching to domain {domain_name}: {e}")
        return {
            "success": False,
            "domain": domain_name,
            "created": False,
            "memory_count": 0,
            "message": f"Failed to switch to domain '{domain_name}': {str(e)}",
        }


@server.tool()
def copy_memories_between_domains(
    source_domain: str,
    target_domain: str,
    query: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Copy memories from one domain to another.

    This tool allows you to copy memories between domains, useful for reorganizing
    memories or creating backups. You can copy all memories or filter by query.

    Parameters:
    - source_domain (str): The domain to copy memories from.
    - target_domain (str): The domain to copy memories to. Will be created if it doesn't exist.
    - query (str, optional): Search query to filter which memories to copy. If not provided, copies all memories.
    - limit (int, optional): Maximum number of memories to copy. If not provided, copies all matching memories.

    Returns:
    Dict[str, Any]: Copy operation results:
        - success (bool): Whether the copy operation was successful
        - source_domain (str): The source domain name
        - target_domain (str): The target domain name
        - memories_copied (int): Number of memories successfully copied
        - target_created (bool): Whether the target domain was created
        - message (str): Human-readable status message

    Example usage:
    - copy_memories_between_domains("old-project", "archive") -> {"success": True, "memories_copied": 25, "message": "Copied 25 memories from 'old-project' to 'archive'"}
    - copy_memories_between_domains("startup", "backup", "funding", 10) -> {"success": True, "memories_copied": 3, "message": "Copied 3 memories matching 'funding' from 'startup' to 'backup'"}

    This is useful for:
    - Archiving old project memories
    - Creating domain backups
    - Reorganizing memory structure
    - Moving memories between contexts
    """
    try:
        # Check if source domain exists
        existing_domains = memory_api.list_domains()
        if source_domain not in existing_domains:
            return {
                "success": False,
                "source_domain": source_domain,
                "target_domain": target_domain,
                "memories_copied": 0,
                "target_created": False,
                "message": f"Source domain '{source_domain}' does not exist",
            }

        # Create target domain if it doesn't exist
        target_created = False
        if target_domain not in existing_domains:
            success = create_domain(target_domain)
            if not success:
                return {
                    "success": False,
                    "source_domain": source_domain,
                    "target_domain": target_domain,
                    "memories_copied": 0,
                    "target_created": False,
                    "message": f"Failed to create target domain '{target_domain}'",
                }
            target_created = True

        # Get memories to copy
        if query:
            memories = memory_api.retrieve_memories(query, limit or 100, source_domain)
        else:
            # Get all memories from source domain
            memories = memory_api.retrieve_memories("", limit or 1000, source_domain)

        # Copy memories to target domain
        copied_count = 0
        for memory in memories:
            try:
                # Add metadata to indicate this was copied
                metadata = memory.get("metadata", {})
                metadata["copied_from"] = source_domain
                metadata["copy_timestamp"] = time.time()

                memory_api.store_memory(
                    content=memory["content"], metadata=metadata, domain=target_domain
                )
                copied_count += 1
            except Exception as e:
                logger.error(
                    f"Error copying memory {memory.get('id', 'unknown')}: {e}"
                )

        return {
            "success": True,
            "source_domain": source_domain,
            "target_domain": target_domain,
            "memories_copied": copied_count,
            "target_created": target_created,
            "message": f"Copied {copied_count} memories from '{source_domain}' to '{target_domain}'",
        }
    except Exception as e:
        logger.error(
            f"Error copying memories from {source_domain} to {target_domain}: {e}"
        )
        return {
            "success": False,
            "source_domain": source_domain,
            "target_domain": target_domain,
            "memories_copied": 0,
            "target_created": False,
            "message": f"Failed to copy memories: {str(e)}",
        }


@server.tool()
def ingest_document(
    file_path: str,
    domain: Optional[str] = None,
    chunk_size: Optional[int] = 1000,
    chunk_overlap: Optional[int] = 200,
) -> str:
    """
    Ingest a document file into the memory system.

    Parameters:
    - file_path (str): Path to the document file to ingest
    - domain (str, optional): Memory domain to store in (default: "documents")
    - chunk_size (int, optional): Size of text chunks in characters (default: 1000)
    - chunk_overlap (int, optional): Overlap between chunks in characters (default: 200)

    Returns:
    str: Summary of ingestion results

    Example usage:
    - ingest_document("/path/to/document.pdf", "research", 800, 150)
    - ingest_document("/path/to/notes.md", chunk_size=1200)
    """
    try:
        from pathlib import Path

        from ingestion.manager import DocumentIngestionManager

        # Initialize ingestion manager
        ingestion_manager = DocumentIngestionManager(memory_api, domain or "documents")

        # Run ingestion
        import asyncio

        result = asyncio.run(
            ingestion_manager.ingest_document(
                Path(file_path), chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
        )

        return f"Ingestion completed: {result.chunks_stored}/{result.chunks_processed} chunks stored in {result.processing_time:.2f}s. Success: {result.success}"

    except Exception as e:
        return f"Ingestion failed: {str(e)}"


@server.tool()
def ingest_text_content(
    content: str, source_name: str, domain: Optional[str] = None
) -> str:
    """
    Ingest raw text content directly into the memory system.

    Parameters:
    - content (str): Text content to ingest
    - source_name (str): Name/source identifier for the content
    - domain (str, optional): Memory domain to store in (default: "documents")

    Returns:
    str: Summary of ingestion results

    Example usage:
    - ingest_text_content("User prefers Python for data analysis", "user_preferences")
    - ingest_text_content("Meeting notes from today...", "meeting_2024_01_15", "work")
    """
    try:
        from ingestion.manager import DocumentIngestionManager

        # Initialize ingestion manager
        ingestion_manager = DocumentIngestionManager(memory_api, domain or "documents")

        # Run ingestion
        import asyncio

        result = asyncio.run(
            ingestion_manager.ingest_text_content(content, source_name)
        )

        return f"Text ingestion completed: {result.chunks_stored}/{result.chunks_processed} chunks stored in {result.processing_time:.2f}s. Success: {result.success}"

    except Exception as e:
        return f"Text ingestion failed: {str(e)}"


@server.prompt
def summarize_memories(memories: List[Dict[str, Any]]) -> str:
    """
    Create a prompt for summarizing a list of memories.

    Parameters:
    - memories: List of memory chunks to summarize

    Returns:
    - A prompt for the LLM to create a summary
    """
    memory_texts = [f"Memory {i+1}: {mem['content']}" for i, mem in enumerate(memories)]
    formatted_memories = "\n".join(memory_texts)

    prompt = f"""Below are several memory chunks related to a user's interests and history.
Please create a concise summary that captures the key points and patterns:

{formatted_memories}

Summary:"""

    return prompt


@server.prompt
def memory_review(time_period: str, focus_area: str = "") -> str:
    """
    Review and organize memories from a specific time period.
    
    Parameters:
    - time_period: Time period to review (e.g., 'last week', 'yesterday', '2 days ago')
    - focus_area: Optional area to focus on (e.g., 'work', 'personal', 'learning')
    """
    # Retrieve memories from the specified time period
    memories = memory_api.retrieve_memories(time_period, limit=20)
    
    prompt_text = f"Review of memories from {time_period}"
    if focus_area:
        prompt_text += f" (focusing on {focus_area})"
    prompt_text += ":\n\n"
    
    if memories:
        for mem in memories:
            prompt_text += f"- {mem.get('content', 'No content')}\n"
            # Tags are stored in metadata
            metadata = mem.get('metadata', {})
            tags = metadata.get('tags', [])
            if tags:
                prompt_text += f"  Tags: {', '.join(tags)}\n"
    else:
        prompt_text += "No memories found for this time period."
    
    return prompt_text


@server.prompt
def memory_analysis(tags: str = "", time_range: str = "all time") -> str:
    """
    Analyze patterns and themes in stored memories.
    
    Parameters:
    - tags: Tags to analyze (comma-separated)
    - time_range: Time range to analyze (e.g., 'last month', 'all time')
    """
    tag_list = [tag.strip() for tag in tags.split(",")] if tags else []
    
    analysis_text = f"Memory Analysis"
    if tag_list:
        analysis_text += f" for tags: {', '.join(tag_list)}"
    if time_range != "all time":
        analysis_text += f" from {time_range}"
    analysis_text += "\n\n"
    
    # Get relevant memories
    if tag_list:
        memories = memory_api.retrieve_memories(f"tags:{','.join(tag_list)}", limit=100)
    else:
        memories = memory_api.retrieve_memories("recent memories", limit=100)
    
    # Analyze patterns
    tag_counts = {}
    type_counts = {}
    for mem in memories:
        # Tags are stored in metadata
        metadata = mem.get('metadata', {})
        tags = metadata.get('tags', [])
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        mem_type = metadata.get('type', 'unknown')
        type_counts[mem_type] = type_counts.get(mem_type, 0) + 1
    
    analysis_text += f"Total memories analyzed: {len(memories)}\n\n"
    analysis_text += "Top tags:\n"
    for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        analysis_text += f"  - {tag}: {count} occurrences\n"
    analysis_text += "\nMemory types:\n"
    for mem_type, count in type_counts.items():
        analysis_text += f"  - {mem_type}: {count} memories\n"
    
    return analysis_text


@server.prompt
def knowledge_export(format_type: str, filter_criteria: str = "") -> str:
    """
    Export memories in a specific format.
    
    Parameters:
    - format_type: Export format (json, markdown, text)
    - filter_criteria: Filter criteria (tags or search query)
    """
    # Get memories based on filter
    if filter_criteria:
        if "," in filter_criteria:
            # Assume tags
            memories = memory_api.retrieve_memories(f"tags:{filter_criteria}", limit=100)
        else:
            # Assume search query
            memories = memory_api.retrieve_memories(filter_criteria, limit=100)
    else:
        memories = memory_api.retrieve_memories("recent memories", limit=100)
    
    export_text = f"Exported {len(memories)} memories in {format_type} format:\n\n"
    
    if format_type == "markdown":
        for mem in memories:
            export_text += f"## {mem.get('created_at_iso', 'Unknown date')}\n"
            export_text += f"{mem.get('content', 'No content')}\n"
            # Tags are stored in metadata
            metadata = mem.get('metadata', {})
            tags = metadata.get('tags', [])
            if tags:
                export_text += f"*Tags: {', '.join(tags)}*\n"
            export_text += "\n"
    elif format_type == "text":
        for mem in memories:
            export_text += f"[{mem.get('created_at_iso', 'Unknown date')}] {mem.get('content', 'No content')}\n"
    else:  # json
        import json
        export_data = [mem for mem in memories]
        export_text += json.dumps(export_data, indent=2, default=str)
    
    return export_text


@server.prompt
def memory_cleanup(older_than: str = "", similarity_threshold: float = 0.95) -> str:
    """
    Identify and remove duplicate or outdated memories.
    
    Parameters:
    - older_than: Remove memories older than (e.g., '6 months', '1 year')
    - similarity_threshold: Similarity threshold for duplicates (0.0-1.0)
    """
    cleanup_text = "Memory Cleanup Report:\n\n"
    
    # Find duplicates
    all_memories = memory_api.retrieve_memories("all memories", limit=1000)
    duplicates = []
    
    for i, mem1 in enumerate(all_memories):
        for mem2 in all_memories[i+1:]:
            # Simple similarity check based on content length
            content1 = mem1.get('content', '')
            content2 = mem2.get('content', '')
            if abs(len(content1) - len(content2)) < 10:
                if content1[:50] == content2[:50]:
                    duplicates.append((mem1, mem2))
    
    cleanup_text += f"Found {len(duplicates)} potential duplicate pairs\n"
    
    if older_than:
        cleanup_text += f"\nMemories older than {older_than} can be archived\n"
    
    return cleanup_text


@server.prompt
def learning_session(topic: str, key_points: str, questions: str = "") -> str:
    """
    Store structured learning notes from a study session.
    
    Parameters:
    - topic: Learning topic or subject
    - key_points: Key points learned (comma-separated)
    - questions: Questions or areas for further study
    """
    from datetime import datetime
    
    key_points_list = [point.strip() for point in key_points.split(",")]
    questions_list = [q.strip() for q in questions.split(",")] if questions else []
    
    # Create structured learning note
    learning_note = f"# Learning Session: {topic}\n\n"
    learning_note += f"Date: {datetime.now().isoformat()}\n\n"
    learning_note += "## Key Points:\n"
    for point in key_points_list:
        learning_note += f"- {point}\n"
    
    if questions_list:
        learning_note += "\n## Questions for Further Study:\n"
        for question in questions_list:
            learning_note += f"- {question}\n"
    
    # Store the learning note
    try:
        memory_id = memory_api.store_memory(
            content=learning_note,
            metadata={"source": "learning_session", "topic": topic},
            domain="learning"
        )
        response_text = f"Learning session stored successfully!\n\n{learning_note}"
    except Exception as e:
        response_text = f"Failed to store learning session: {str(e)}"
    
    return response_text

# Session Management Tools

@server.tool()
def start_session(
    session_id: str,
    project_name: Optional[str] = None,
    working_directory: Optional[str] = None,
    initial_topics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Start a new conversation session with optional project context.

    This tool begins tracking a new session and attempts to link it to existing
    conversation threads for continuity. If recent sessions exist in the same
    project, this session will be linked as a continuation.

    Parameters:
    - session_id (str): Unique identifier for this session. Examples:
                       * "session-2024-01-15-143022"
                       * "claude-session-abc123"
                       * Use timestamp or UUID-based IDs for uniqueness

    - project_name (str, optional): Name of the project this session relates to.
                                   Used for linking sessions into conversation threads.
                                   Examples: "my-app", "data-analysis", "website-redesign"

    - working_directory (str, optional): Current working directory path.
                                        Examples: "/Users/name/projects/my-app"

    - initial_topics (List[str], optional): Initial topics or goals for this session.
                                           Examples: ["debugging", "authentication", "database"]

    Returns:
    Dict[str, Any]: Session information including:
        - session_id (str): The session identifier
        - thread_id (str): Conversation thread this session belongs to
        - parent_session_id (str): Previous related session (if continuation)
        - project_name (str): Project name
        - is_continuation (bool): Whether this continues a previous conversation

    Example usage:
    - start_session("session-123", "my-app", "/path/to/project", ["setup", "debugging"])
    - start_session("claude-session-456") # Minimal usage
    """
    try:
        project_context = {}
        if project_name:
            project_context["name"] = project_name

        result = memory_api.start_session(
            session_id=session_id,
            project_context=project_context,
            working_directory=working_directory,
            initial_topics=initial_topics,
        )
        return result
    except Exception as e:
        logger.error(f"Error starting session {session_id}: {e}")
        return {"error": str(e)}


@server.tool()
def end_session(
    session_id: str,
    final_topics: Optional[List[str]] = None,
    conversation_summary: Optional[str] = None,
    outcome_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    End a conversation session with summary and outcomes.

    This tool marks a session as completed and stores the final outcomes.
    The session data becomes part of the conversation history for future
    session continuity.

    Parameters:
    - session_id (str): The session identifier to end

    - final_topics (List[str], optional): Topics covered during the session.
                                         Examples: ["bug-fixed", "database-optimized", "tests-added"]

    - conversation_summary (str, optional): Brief summary of what was accomplished.
                                           Examples: "Fixed authentication bug and added unit tests"

    - outcome_type (str, optional): Type of session outcome.
                                   Examples: "completed", "planning", "partial", "debugging"

    Returns:
    Dict[str, Any]: Session completion status including:
        - session_id (str): The session identifier
        - status (str): "completed" if successful
        - thread_id (str): Conversation thread ID

    Example usage:
    - end_session("session-123", ["bug-fixed", "tests-added"], "Successfully fixed login issue")
    - end_session("session-456", outcome_type="planning")
    """
    try:
        outcome = {}
        if outcome_type:
            outcome["type"] = outcome_type

        # Get session memories for optimization if available
        optimized_summary = None
        if optimization_mgr:
            try:
                # Get memories specifically associated with THIS session
                # We need to query the session_memories table directly
                from psycopg2.extras import RealDictCursor
                with memory_api._get_connection() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                        # Get memories tracked for this session
                        cursor.execute("""
                            SELECT
                                sm.memory_id,
                                sm.domain,
                                sm.interaction_type,
                                sm.created_during_session,
                                sm.relevance_score
                            FROM session_memories sm
                            WHERE sm.session_id = %s
                        """, (session_id,))

                        session_memory_records = cursor.fetchall()

                        # Also get initial topics from the session
                        cursor.execute("""
                            SELECT initial_topics
                            FROM sessions
                            WHERE id = %s
                        """, (session_id,))

                        session_data = cursor.fetchone()
                        initial_topics = session_data['initial_topics'] if session_data else []

                if session_memory_records:
                    # Convert to format expected by optimize_session_end
                    session_mems = []
                    for record in session_memory_records:
                        # Get the actual memory content from the domain
                        domain = record['domain']
                        memory_id = record['memory_id']

                        # Retrieve memory details from the domain
                        # Note: This is simplified - in production you'd query the actual domain table
                        mem_dict = {
                            'memory_id': memory_id,
                            'domain': domain,
                            'interaction_type': record['interaction_type'],
                            'created_during_session': record['created_during_session'],
                            'relevance_score': record['relevance_score']
                        }
                        session_mems.append(mem_dict)

                    # Generate optimized summary
                    optimized_summary = optimization_mgr.optimize_session_end(
                        session_id=session_id,
                        session_memories=session_mems,
                        initial_topics=initial_topics or [],
                        final_topics=final_topics,
                        project_name=None  # Could get from session data
                    )

                    # Use optimized summary if available
                    if optimized_summary and 'content' in optimized_summary:
                        # Convert optimized summary to string format
                        summary_parts = []
                        content = optimized_summary['content']

                        if 'decisions' in content:
                            summary_parts.append(f"Decisions: {', '.join(content['decisions'])}")
                        if 'solutions' in content:
                            summary_parts.append(f"Solutions: {', '.join(content['solutions'])}")
                        if 'outcomes' in content:
                            summary_parts.append(f"Outcomes: {', '.join(content['outcomes'])}")

                        if summary_parts:
                            conversation_summary = '; '.join(summary_parts)[:500]  # Token limit
                            logger.info(f"Session {session_id} optimized: {len(conversation_summary)} chars")
            except Exception as opt_error:
                logger.warning(f"Failed to optimize session end: {opt_error}")
                # Continue without optimization

        result = memory_api.end_session(
            session_id=session_id,
            outcome=outcome,
            final_topics=final_topics,
            conversation_summary=conversation_summary,
        )

        # Add optimization metadata if available
        if optimized_summary:
            result['optimized'] = True
            result['token_reduction'] = optimized_summary.get('token_reduction', 0)

        return result
    except Exception as e:
        logger.error(f"Error ending session {session_id}: {e}")
        return {"error": str(e)}


@server.tool()
def get_session_history(
    project_name: Optional[str] = None,
    limit: int = 5,
    include_memories: bool = False,
) -> Dict[str, Any]:
    """
    Get recent session history for conversation continuity.

    This tool retrieves information about recent sessions to provide context
    for new sessions. Useful for understanding recent work and decisions.

    Parameters:
    - project_name (str, optional): Filter sessions by project name.
                                   If not provided, returns sessions across all projects.

    - limit (int, optional): Maximum number of recent sessions to return (default: 5).
                            Range: 1-20.

    - include_memories (bool, optional): Whether to include associated memories (default: false).
                                        When true, returns memories that were loaded or created
                                        during each session.

    Returns:
    Dict[str, Any]: Session history including:
        - recent_sessions (List[Dict]): List of recent session data
        - total_sessions (int): Number of sessions returned
        - session_memories (List[Dict]): Associated memories (if include_memories=true)

    Each session includes:
        - id, project_name, started_at, ended_at
        - initial_topics, final_topics, conversation_summary
        - outcome, thread_id, parent_session_id

    Example usage:
    - get_session_history("my-app", 3) # Last 3 sessions for my-app project
    - get_session_history(limit=10, include_memories=true) # Detailed history
    """
    try:
        result = memory_api.get_session_context(
            project_name=project_name,
            limit=limit,
            include_memories=include_memories,
        )
        return result
    except Exception as e:
        logger.error(f"Error getting session history: {e}", )
        return {"error": str(e)}


@server.tool()
def get_conversation_threads(
    project_name: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Get conversation threads showing session relationships.

    This tool shows conversation threads that group related sessions together.
    Each thread represents an ongoing conversation or work stream within a project.

    Parameters:
    - project_name (str, optional): Filter threads by project name.
                                   If not provided, returns threads across all projects.

    - limit (int, optional): Maximum number of threads to return (default: 10).
                            Range: 1-50.

    Returns:
    List[Dict[str, Any]]: List of conversation threads, each containing:
        - id (str): Thread identifier
        - project_name (str): Associated project
        - created_at (datetime): When thread was created
        - last_updated (datetime): Last activity in thread
        - topics (List[str]): Accumulated topics across all sessions
        - session_count (int): Number of sessions in this thread
        - last_session_end (datetime): When last session in thread ended

    Example usage:
    - get_conversation_threads("my-app") # Threads for specific project
    - get_conversation_threads(limit=20) # All recent threads
    """
    try:
        result = memory_api.get_conversation_threads(
            project_name=project_name,
            limit=limit,
        )
        return result
    except Exception as e:
        logger.error(f"Error getting conversation threads: {e}", )
        return {"error": str(e)}


@server.tool()
def track_session_memory(
    session_id: str,
    memory_id: str,
    domain: str,
    created_during_session: bool = True,
    interaction_type: str = "loaded",
    relevance_score: Optional[float] = None,
) -> bool:
    """
    Track the relationship between a session and a memory.

    This tool creates an association between a session and a memory,
    recording how the memory was used during the session. This data
    helps with session continuity and memory relevance scoring.

    Parameters:
    - session_id (str): The session identifier
    - memory_id (str): The memory identifier to associate
    - domain (str): The domain where the memory is stored
    - created_during_session (bool, optional): Whether memory was created during session (default: true)
    - interaction_type (str, optional): How memory was used. Options:
                                       * "loaded" - Memory was retrieved and used
                                       * "created" - Memory was created during session
                                       * "referenced" - Memory was mentioned or related
    - relevance_score (float, optional): Relevance score 0.0-1.0 for this memory to the session

    Returns:
    bool: True if association was created successfully

    Example usage:
    - track_session_memory("session-123", "mem-456", "default", true, "created", 0.9)
    - track_session_memory("session-123", "mem-789", "work", false, "loaded", 0.7)
    """
    try:
        result = memory_api.track_session_memory(
            session_id=session_id,
            memory_id=memory_id,
            domain=domain,
            created_during_session=created_during_session,
            interaction_type=interaction_type,
            relevance_score=relevance_score,
        )
        return result
    except Exception as e:
        logger.error(f"Error tracking session memory: {e}", )
        return False


@server.tool()
def get_session_insights(
    project_name: Optional[str] = None,
    days_back: int = 30,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Get insights about session patterns and trends.

    This tool analyzes session data to identify recurring topics, progression patterns,
    and uncompleted tasks that may need follow-up.

    Parameters:
    - project_name (str, optional): Filter insights to a specific project
    - days_back (int, optional): Number of days to look back (default: 30)
    - limit (int, optional): Maximum number of items to return per insight type (default: 10)

    Returns:
    Dict containing:
    - recurring_topics: Topics appearing across multiple sessions
    - progression_patterns: Common workflow sequences (e.g., planning → implementation)
    - uncompleted_tasks: Sessions with partial/planning outcomes needing follow-up

    Example usage:
    - get_session_insights("my-project", 7, 5)
    - get_session_insights(days_back=14)
    """
    try:
        insights = {}

        # Get recurring topics
        insights["recurring_topics"] = memory_api.find_recurring_topics(
            project_name=project_name,
            limit=limit,
            days_back=days_back,
        )

        # Get progression patterns
        patterns = memory_api.analyze_progression_patterns(
            project_name=project_name,
            days_back=days_back,
        )
        insights["progression_patterns"] = patterns.get("progression_patterns", [])[:limit]
        insights["outcome_distribution"] = patterns.get("outcome_distribution", [])

        # Get uncompleted tasks
        insights["uncompleted_tasks"] = memory_api.find_uncompleted_tasks(
            project_name=project_name,
            days_back=days_back,
            limit=limit,
        )

        # Apply token optimization if available
        if optimization_mgr:
            try:
                # Use progressive summarization to compress insights
                original_size = len(json.dumps(insights))

                # Compress recurring topics
                if insights.get("recurring_topics"):
                    # Keep only essential fields for token efficiency
                    insights["recurring_topics"] = [
                        {
                            "topic": t["topic"],
                            "count": t["session_count"],
                            "last_seen": str(t["last_seen"])[:10] if t.get("last_seen") else None
                        }
                        for t in insights["recurring_topics"][:limit]
                    ]

                # Compress progression patterns
                if insights.get("progression_patterns"):
                    # Group similar patterns
                    insights["progression_patterns"] = [
                        {
                            "pattern": p["pattern"],
                            "frequency": p["occurrences"]
                        }
                        for p in insights["progression_patterns"][:limit]
                    ]

                # Compress uncompleted tasks
                if insights.get("uncompleted_tasks"):
                    # Remove redundant fields, keep essentials
                    insights["uncompleted_tasks"] = [
                        {
                            "session_id": t["session_id"][:8] + "...",  # Truncate ID
                            "summary": (t.get("conversation_summary") or "")[:100],
                            "outcome": t.get("outcome_type", "unknown"),
                            "has_followup": t.get("has_followup", False)
                        }
                        for t in insights["uncompleted_tasks"][:limit]
                    ]

                # Calculate compression ratio
                compressed_size = len(json.dumps(insights))
                compression_ratio = 1 - (compressed_size / original_size) if original_size > 0 else 0

                insights["_optimization"] = {
                    "compressed": True,
                    "original_size": original_size,
                    "compressed_size": compressed_size,
                    "compression_ratio": f"{compression_ratio:.1%}"
                }

                logger.info(f"Session insights compressed: {original_size} → {compressed_size} bytes ({compression_ratio:.1%} reduction)")

            except Exception as opt_error:
                logger.warning(f"Failed to optimize session insights: {opt_error}")
                # Continue with unoptimized results

        return insights
    except Exception as e:
        logger.error(f"Error getting session insights: {e}")
        return {
            "error": str(e),
            "recurring_topics": [],
            "progression_patterns": [],
            "uncompleted_tasks": [],
        }


@server.tool()
def get_session_stats(
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get comprehensive statistics about sessions.

    This tool returns metrics about session usage, including counts, durations,
    and memory associations.

    Parameters:
    - project_name (str, optional): Filter stats to a specific project

    Returns:
    Dict containing:
    - total_sessions: Total number of sessions
    - total_projects: Number of unique projects
    - total_threads: Number of conversation threads
    - active_sessions: Currently active sessions
    - completed_sessions: Completed sessions
    - avg_duration_hours: Average session duration in hours
    - top_projects: Most active projects (when not filtering by project)
    - unique_memories: Number of unique memories associated with sessions
    - memories_created: Memories created during sessions

    Example usage:
    - get_session_stats()
    - get_session_stats("my-project")
    """
    try:
        return memory_api.get_session_statistics(project_name=project_name)
    except Exception as e:
        logger.error(f"Error getting session statistics: {e}")
        return {"error": str(e)}


@server.tool()
def cleanup_sessions(
    days: int = 30,
) -> Dict[str, Any]:
    """
    Clean up expired sessions and archive old threads.

    This tool removes sessions older than the specified number of days and archives
    conversation threads with no recent activity.

    Parameters:
    - days (int, optional): Sessions older than this many days will be deleted (default: 30)

    Returns:
    Dict containing:
    - sessions_deleted: Number of sessions removed
    - threads_archived: Number of threads archived
    - days: The days parameter used

    Example usage:
    - cleanup_sessions(60)  # Clean up sessions older than 60 days
    - cleanup_sessions()    # Use default 30 days
    """
    try:
        # Clean up expired sessions
        cleanup_result = memory_api.cleanup_expired_sessions(days=days)

        # Archive old threads (using 3x the session cleanup days)
        archived_count = memory_api.archive_old_threads(days=days * 3)

        return {
            "sessions_deleted": cleanup_result["sessions_deleted"],
            "threads_archived": archived_count,
            "days": days,
        }
    except Exception as e:
        logger.error(f"Error cleaning up sessions: {e}")
        return {"error": str(e)}


@server.tool()
def consolidate_memories(
    domain: Optional[str] = None,
    days_back: int = 30,
) -> Dict[str, Any]:
    """
    Consolidate and optimize memories in a domain.

    This tool runs the memory consolidation process which clusters similar memories,
    compresses redundant information, and applies forgetting mechanisms to maintain
    an optimal memory store.

    Parameters:
    - domain (str, optional): The domain to consolidate (default: "default")
    - days_back (int, optional): Number of days back to consider for consolidation (default: 30)

    Returns:
    Dict containing:
    - status: Success or error status
    - processed: Number of memories processed
    - clusters_created: Number of memory clusters created
    - memories_archived: Number of memories archived
    - consolidated_memories: Number of consolidated memories created

    Example usage:
    - consolidate_memories("work", 7)
    - consolidate_memories()  # Consolidate default domain
    """
    try:
        # Use optimization manager's advanced consolidation if available
        if optimization_mgr:
            logger.info(f"Using optimized consolidation for domain: {domain or 'default'}")

            # Get memories from domain for consolidation
            domain_name = domain or "default"

            # The optimization manager's consolidator has advanced features:
            # - Semantic clustering (Phase 3)
            # - Progressive summarization (Phase 3)
            # - Duplicate detection (Phase 2)
            # - Memory merging (Phase 2)

            # Get memories from the domain for consolidation
            memories = memory_api.retrieve_memories(
                query="",  # Get all memories
                limit=1000,  # Reasonable limit
                domain=domain_name,
                time_filter=None
            )

            # Convert to dict format expected by consolidator
            memory_dicts = []
            for mem in memories:
                memory_dict = {
                    'id': mem.get('id', ''),
                    'content': mem.get('content', ''),
                    'content_hash': mem.get('content_hash', ''),
                    'tags': mem.get('tags', []),
                    'metadata': mem.get('metadata', {}),
                    'embedding': mem.get('embedding'),
                    'created_at': mem.get('created_at'),
                    'importance': mem.get('metadata', {}).get('importance', 0.5)
                }
                memory_dicts.append(memory_dict)

            # Trigger consolidation through memory_consolidator
            result = optimization_mgr.consolidator.consolidate_memories(
                memories=memory_dicts,
                dry_run=False
            )

            # Add optimization metadata
            result['optimization_used'] = True
            result['techniques_applied'] = [
                'semantic_clustering',
                'progressive_summarization',
                'duplicate_detection',
                'memory_merging'
            ]

            # Update optimization stats
            optimization_mgr.stats['consolidations_performed'] = \
                optimization_mgr.stats.get('consolidations_performed', 0) + 1

            return result

        else:
            # Fallback to basic PostgreSQL consolidator
            logger.info("Using basic consolidation (optimization not available)")
            from src.consolidation.postgres_consolidator import PostgreSQLConsolidator
            import asyncio

            # Get database connection string
            db_url = memory_api.connection_string

            # Initialize consolidator with Ollama embeddings
            consolidator = PostgreSQLConsolidator(
                connection_string=db_url,
                embedding_client=ollama_embeddings
            )

            # Run consolidation
            result = asyncio.run(consolidator.consolidate_memories(
                domain_id=domain,
                days_back=days_back
            ))

            result['optimization_used'] = False
            return result

    except Exception as e:
        logger.error(f"Error consolidating memories: {e}")
        return {"error": str(e), "status": "failed"}


def run_http_server():
    """Run the HTTP server in a separate thread"""
    port = int(os.environ.get("BRIDGE_PORT", 8000))
    print(f"🌐 Starting HTTP server on port {port}", file=sys.stderr)
    uvicorn.run(
        http_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=False  # Reduce noise in logs
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

import json
import os
import time
from typing import Any, Dict, List, Optional, Union

import numpy as np
import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor

from database_error_handling import (
    DatabaseErrorHandler,
    database_operation,
    monitor_database_operation,
)
from error_handlers import (
    RetryConfig,
    error_context,
    handle_errors,
    retry_on_error,
    validate_inputs,
)

# Import error handling
from exceptions import (
    ConnectionError,
    ConsolidationError,
    DatabaseError,
    EmbeddingError,
    InsufficientDataError,
    ResourceExhaustedError,
    ServiceUnavailableError,
    TimeoutError,
    ValidationError,
)
from logging_config import get_logger
from models.memory import Memory
from project_detector import detect_project_context
from security import security_validator

logger = get_logger(__name__)

# Load environment variables
load_dotenv()

# Constants
DEFAULT_EMBEDDING_DIMENSIONS = 768
DEFAULT_SIMILARITY_THRESHOLD = 0.5
DEFAULT_MAX_RESULTS = 10


def get_project_domain(working_directory: str = None) -> str:
    """
    Automatically determine the domain based on the current project context.

    Args:
        working_directory: The directory to analyze (defaults to current working directory)

    Returns:
        A sanitized domain name based on the project context
    """
    try:
        # Detect project context
        project_context = detect_project_context(working_directory)

        # Extract project name and sanitize it for use as a domain
        project_name = project_context.get("name", "unknown")

        # Sanitize the project name to be a valid domain identifier
        import re

        # Remove special characters and replace with underscores
        sanitized_domain = re.sub(r"[^a-zA-Z0-9_-]", "_", project_name.lower())
        # Remove multiple consecutive underscores
        sanitized_domain = re.sub(r"_+", "_", sanitized_domain)
        # Remove leading/trailing underscores
        sanitized_domain = sanitized_domain.strip("_")

        # Ensure it's not empty and has a reasonable length
        if not sanitized_domain or len(sanitized_domain) < 2:
            sanitized_domain = "default"
        elif len(sanitized_domain) > 50:
            sanitized_domain = sanitized_domain[:50].rstrip("_")

        logger.info(
            f"Auto-detected project domain: {sanitized_domain} from project: {project_name}"
        )
        return sanitized_domain

    except Exception as e:
        logger.warning(f"Failed to detect project domain: {e}, using 'default'")
        return "default"


DEFAULT_MIN_SCORE = 0.3
DEFAULT_TIMEOUT_MS = 5000


class PostgresMemoryAPI:
    def __init__(self, ollama_embeddings: Optional[Any] = None) -> None:
        """Initialize PostgreSQL memory store with connection parameters."""

        self.connection_params = {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": os.getenv("POSTGRES_PORT", 5432),
            "database": os.getenv("POSTGRES_DB", "postgres"),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
        }
        self.default_domain = os.getenv("DEFAULT_MEMORY_DOMAIN", "default")

        # Initialize Ollama embeddings if not provided
        if ollama_embeddings is None:
            try:
                from ollama_embeddings import OllamaEmbeddings

                ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
                ollama_model = os.getenv(
                    "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:v1.5"
                )
                ollama_keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "10m")

                self.ollama_embeddings = OllamaEmbeddings(
                    model_name=ollama_model,
                    base_url=ollama_url,
                    keep_alive=ollama_keep_alive,
                )
                print(
                    f"✅ Ollama embeddings initialized: {ollama_model} at {ollama_url}"
                )
            except Exception as e:
                print(f"⚠️ Failed to initialize Ollama embeddings: {e}")
                self.ollama_embeddings = None
        else:
            self.ollama_embeddings = ollama_embeddings

        # Initialize existing consolidation system
        self._init_consolidation_system()

    def _get_connection(self) -> psycopg2.extensions.connection:
        """Get a new database connection."""
        return psycopg2.connect(**self.connection_params)

    def _ensure_table_exists(self, domain: str) -> None:
        """Ensure the domain table exists."""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT create_domain_memories_table(%s)", (domain,))
                conn.commit()

    @handle_errors()
    @validate_inputs(
        content=lambda x: isinstance(x, str) and x.strip() != "",
        metadata=lambda x: x is None or isinstance(x, dict),
        domain=lambda x: x is None or isinstance(x, str),
    )
    @monitor_database_operation("INSERT", "memories")
    def store_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        domain: Optional[str] = None,
        importance: Optional[int] = None,
    ) -> str:
        """Store a new memory in the specified domain."""
        # Auto-detect domain if not provided
        if domain is None:
            domain = get_project_domain()
            logger.info(f"Auto-routing memory to domain: {domain}")

        with error_context("store_memory", content_length=len(content), domain=domain):
            # Enhanced input validation with security checks
            if not content or not isinstance(content, str):
                raise ValidationError(
                    "Content must be a non-empty string", field="content"
                )

            if content.strip() == "":
                raise ValidationError(
                    "Content cannot be empty or whitespace only", field="content"
                )

            if len(content) > 10000:
                raise ValidationError(
                    "Content too long (max 10000 characters)",
                    field="content",
                    value=len(content),
                )

            if metadata is not None and not isinstance(metadata, dict):
                raise ValidationError(
                    "Metadata must be a dictionary or None", field="metadata"
                )

            if domain is not None and not isinstance(domain, str):
                raise ValidationError("Domain must be a string or None", field="domain")

            # Security validation
            content = security_validator.sanitize_content(content)
            if metadata:
                metadata = security_validator.validate_metadata(metadata)
            if domain:
                domain = security_validator.validate_domain(domain)

            domain = domain or self.default_domain
            self._ensure_table_exists(domain)

        memory_id = f"mem_{int(time.time() * 1000)}"
        timestamp = time.time()

        metadata = metadata or {}
        metadata.update(
            {
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
        
        # Add importance to metadata if provided
        if importance is not None:
            metadata["importance"] = importance

        # Generate embedding with error handling
        embedding = None
        if self.ollama_embeddings:
            try:
                embedding = self.ollama_embeddings.get_embedding(content)
                if not embedding or not isinstance(embedding, list):
                    raise EmbeddingError(
                        "Invalid embedding generated",
                        model=getattr(self.ollama_embeddings, "model_name", "unknown"),
                    )
            except Exception as e:
                logger.warning(f"Failed to generate embedding: {e}")
                # Continue without embedding rather than failing completely

        # Database operation with comprehensive error handling
        with database_operation("INSERT", f"{domain}_memories") as cursor:
            table_name = sql.Identifier(f"{domain}_memories")

            if embedding:
                # Store with embedding - convert list to vector
                query = sql.SQL(
                    """
                    INSERT INTO {} (id, content, embedding, metadata)
                    VALUES (%s, %s, %s::vector, %s)
                """
                ).format(table_name)
                cursor.execute(query, (memory_id, content, embedding, Json(metadata)))
            else:
                # Store without embedding
                query = sql.SQL(
                    """
                    INSERT INTO {} (id, content, metadata)
                    VALUES (%s, %s, %s)
                """
                ).format(table_name)
                cursor.execute(query, (memory_id, content, Json(metadata)))

        logger.info(f"Successfully stored memory {memory_id} in domain {domain}")
        return memory_id

    def retrieve_memories(
        self, query: str, limit: int = 5, domain: Optional[str] = None, time_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve memories using vector similarity search with text search fallback."""
        # Input validation
        if not isinstance(query, str):
            raise ValueError("Query must be a string")
        if not isinstance(limit, int) or limit < 0:
            raise ValueError("Limit must be a non-negative integer")
        if limit > 1000:  # Reasonable limit
            raise ValueError("Limit too large (max 1000)")
        if domain is not None and not isinstance(domain, str):
            raise ValueError("Domain must be a string or None")

        domain = domain or self.default_domain
        self._ensure_table_exists(domain)

        # Generate time filter clause if specified
        time_filter_sql = ""
        time_filter_param = None
        if time_filter:
            if time_filter == "recent" or time_filter == "today":
                time_filter_sql = " AND created_at >= NOW() - INTERVAL '1 day'"
            elif time_filter == "last-week":
                time_filter_sql = " AND created_at >= NOW() - INTERVAL '7 days'"
            elif time_filter == "last-month":
                time_filter_sql = " AND created_at >= NOW() - INTERVAL '30 days'"

        # Try vector search first if embeddings are available and query is not empty
        if self.ollama_embeddings and query.strip():
            try:
                query_embedding = self.ollama_embeddings.get_embedding(query)

                # Ensure we have a valid embedding (list of numbers)
                if (
                    query_embedding
                    and isinstance(query_embedding, list)
                    and len(query_embedding) > 0
                ):
                    with self._get_connection() as conn:
                        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                            table_name = sql.Identifier(f"{domain}_memories")

                            # Vector similarity search with pgvector optimizations
                            # Dynamic ef_search based on query complexity and limit
                            ef_search = min(
                                max(20, limit * 2), 100
                            )  # Range: 20-100, adaptive to limit

                            # Set HNSW parameters for this query session
                            cursor.execute("SET hnsw.ef_search = %s", (ef_search,))

                            # Enable relaxed ordering for better performance on filtered queries
                            cursor.execute("SET enable_indexscan = on")
                            cursor.execute(
                                "SET random_page_cost = 1.1"
                            )  # SSD optimization

                            search_query = sql.SQL(
                                """
                                SELECT id, content, metadata,
                                       1 - (embedding <=> %s::vector) AS score
                                FROM {}
                                WHERE embedding IS NOT NULL{}
                                ORDER BY embedding <=> %s::vector
                                LIMIT %s
                            """
                            ).format(table_name, sql.SQL(time_filter_sql))

                            cursor.execute(
                                search_query, (query_embedding, query_embedding, limit)
                            )
                            results = cursor.fetchall()

                            # Return vector results if we have any, regardless of similarity score
                            if results:
                                return [dict(row) for row in results]

                            # If no records have embeddings, fall through to text search
            except Exception as e:
                print(f"Vector search failed: {e}")

        # Check if this is a tag-based search
        if query.startswith("tags:"):
            tag_list = query[5:].split(",")  # Remove "tags:" prefix and split by comma
            tag_list = [tag.strip() for tag in tag_list if tag.strip()]
            
            if tag_list:
                with self._get_connection() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                        table_name = sql.Identifier(f"{domain}_memories")
                        
                        # Search for memories containing any of the specified tags
                        tag_conditions = []
                        tag_params = []
                        for tag in tag_list:
                            tag_conditions.append("metadata->>'tags' ILIKE %s")
                            tag_params.append(f"%{tag}%")
                        
                        tag_query = sql.SQL(
                            """
                            SELECT id, content, metadata, 0.0 as score
                            FROM {}
                            WHERE ({}){}
                            ORDER BY updated_at DESC
                            LIMIT %s
                        """
                        ).format(table_name, sql.SQL(" OR ").join([sql.SQL(condition) for condition in tag_conditions]), sql.SQL(time_filter_sql))
                        
                        cursor.execute(tag_query, tag_params + [limit])
                        results = cursor.fetchall()
                        
                        if results:
                            return [dict(row) for row in results]

        # Fallback to text search
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                table_name = sql.Identifier(f"{domain}_memories")

                # Full text search
                search_query = sql.SQL(
                    """
                    SELECT id, content, metadata, 0.0 as score
                    FROM {}
                    WHERE to_tsvector('english', content) @@ plainto_tsquery('english', %s){}
                    ORDER BY updated_at DESC
                    LIMIT %s
                """
                ).format(table_name, sql.SQL(time_filter_sql))

                cursor.execute(search_query, (query, limit))
                results = cursor.fetchall()

                if results:
                    return [dict(row) for row in results]

                # If no results from full text search, try simple LIKE
                like_query = sql.SQL(
                    """
                    SELECT id, content, metadata, 0.0 as score
                    FROM {}
                    WHERE content ILIKE %s{}
                    ORDER BY updated_at DESC
                    LIMIT %s
                """
                ).format(table_name, sql.SQL(time_filter_sql))

                cursor.execute(like_query, (f"%{query}%", limit))
                results = cursor.fetchall()

                if results:
                    return [dict(row) for row in results]

                # Last resort: return most recent memories if no search matches
                where_clause = sql.SQL("WHERE 1=1") + sql.SQL(time_filter_sql) if time_filter_sql else sql.SQL("")
                fallback_query = sql.SQL(
                    """
                    SELECT id, content, metadata, 0.0 as score
                    FROM {}
                    {}
                    ORDER BY updated_at DESC
                    LIMIT %s
                """
                ).format(table_name, where_clause)

                cursor.execute(fallback_query, (limit,))
                results = cursor.fetchall()

                return [dict(row) for row in results]

    def update_memory(
        self,
        memory_id: str,
        content: str = None,
        metadata: Dict[str, Any] = None,
        domain: str = None,
    ) -> bool:
        """Update an existing memory."""
        domain = domain or self.default_domain

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                table_name = sql.Identifier(f"{domain}_memories")

                # Check if memory exists
                cursor.execute(
                    sql.SQL("SELECT id FROM {} WHERE id = %s").format(table_name),
                    (memory_id,),
                )

                if not cursor.fetchone():
                    return False

                # Update metadata timestamp
                if metadata is not None:
                    metadata["updated_at"] = time.time()

                # Build update query based on what needs updating
                if content is not None and metadata is not None:
                    # Update both content and metadata
                    embedding = None
                    if self.ollama_embeddings:
                        try:
                            embedding = self.ollama_embeddings.get_embedding(content)
                        except Exception as e:
                            print(f"Failed to generate embedding: {e}")

                    if embedding:
                        update_query = sql.SQL(
                            """
                            UPDATE {} 
                            SET content = %s, embedding = %s::vector, metadata = %s, updated_at = NOW()
                            WHERE id = %s
                        """
                        ).format(table_name)
                        cursor.execute(
                            update_query,
                            (content, embedding, Json(metadata), memory_id),
                        )
                    else:
                        update_query = sql.SQL(
                            """
                            UPDATE {} 
                            SET content = %s, metadata = %s, updated_at = NOW()
                            WHERE id = %s
                        """
                        ).format(table_name)
                        cursor.execute(
                            update_query, (content, Json(metadata), memory_id)
                        )

                elif content is not None:
                    # Update only content
                    embedding = None
                    if self.ollama_embeddings:
                        try:
                            embedding = self.ollama_embeddings.get_embedding(content)
                        except Exception as e:
                            print(f"Failed to generate embedding: {e}")

                    if embedding:
                        update_query = sql.SQL(
                            """
                            UPDATE {} 
                            SET content = %s, embedding = %s::vector, updated_at = NOW()
                            WHERE id = %s
                        """
                        ).format(table_name)
                        cursor.execute(update_query, (content, embedding, memory_id))
                    else:
                        update_query = sql.SQL(
                            """
                            UPDATE {} 
                            SET content = %s, updated_at = NOW()
                            WHERE id = %s
                        """
                        ).format(table_name)
                        cursor.execute(update_query, (content, memory_id))

                elif metadata is not None:
                    # Update only metadata
                    update_query = sql.SQL(
                        """
                        UPDATE {} 
                        SET metadata = metadata || %s, updated_at = NOW()
                        WHERE id = %s
                    """
                    ).format(table_name)
                    cursor.execute(update_query, (Json(metadata), memory_id))

                conn.commit()
                return True

    def delete_memory(self, memory_id: str, domain: Optional[str] = None) -> bool:
        """Delete a memory by its ID."""
        domain = domain or self.default_domain

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    table_name = f"{domain}_memories"

                    # Check if table exists
                    cursor.execute(
                        """
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = %s
                        )
                    """,
                        (table_name,),
                    )

                    if not cursor.fetchone()[0]:
                        logger.warning(f"Domain table {table_name} does not exist")
                        return False

                    # Delete the memory
                    from psycopg2 import sql as psycopg2_sql

                    delete_query = psycopg2_sql.SQL(
                        "DELETE FROM {} WHERE id = %s"
                    ).format(psycopg2_sql.Identifier(table_name))
                    cursor.execute(delete_query, (memory_id,))

                    if cursor.rowcount == 0:
                        logger.warning(
                            f"Memory {memory_id} not found in domain {domain}"
                        )
                        return False

                    conn.commit()
                    logger.info(f"Deleted memory {memory_id} from domain {domain}")
                    return True

        except Exception as e:
            logger.error(f"Error deleting memory {memory_id} from domain {domain}: {e}")
            return False

    def list_domains(self) -> List[str]:
        """List all available memory domains."""
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # Query for all tables ending with '_memories'
                cursor.execute(
                    """
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name LIKE '%_memories'
                    ORDER BY table_name
                """
                )

                domains = []
                for row in cursor.fetchall():
                    table_name = row[0]
                    # Extract domain name by removing '_memories' suffix
                    if table_name.endswith("_memories"):
                        domain = table_name[
                            :-9
                        ]  # Remove last 9 characters ('_memories')
                        domains.append(domain)

                return domains

    def get_domain_stats(self, domain: str) -> Dict[str, Any]:
        """Get statistics for a specific domain."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    table_name = f"{domain}_memories"

                    # Check if table exists
                    cursor.execute(
                        """
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = %s
                        )
                    """,
                        (table_name,),
                    )

                    table_exists = cursor.fetchone()[0]
                    if not table_exists:
                        return {
                            "memory_count": 0,
                            "table_size": "0 B",
                            "last_activity": None,
                        }

                    # Get memory count
                    from psycopg2 import sql as psycopg2_sql

                    count_query = psycopg2_sql.SQL("SELECT COUNT(*) FROM {}").format(
                        psycopg2_sql.Identifier(table_name)
                    )
                    cursor.execute(count_query)
                    memory_count = cursor.fetchone()[0]

                    # Get table size
                    cursor.execute(
                        """
                        SELECT pg_size_pretty(pg_total_relation_size(%s))
                    """,
                        (table_name,),
                    )
                    table_size = cursor.fetchone()[0]

                    # Get last activity (most recent created_at)
                    from psycopg2 import sql as psycopg2_sql

                    last_activity_query = psycopg2_sql.SQL(
                        """
                        SELECT MAX(created_at) 
                        FROM {}
                    """
                    ).format(psycopg2_sql.Identifier(table_name))
                    cursor.execute(last_activity_query)
                    last_activity = cursor.fetchone()[0]

                    return {
                        "memory_count": memory_count,
                        "table_size": table_size,
                        "last_activity": (
                            last_activity.isoformat() if last_activity else None
                        ),
                    }
        except Exception as e:
            logger.error(f"Error getting domain stats for {domain}: {e}")
            return {"memory_count": 0, "table_size": "0 B", "last_activity": None}

    def _init_consolidation_system(self) -> None:
        """Initialize the existing consolidation system."""
        try:
            from consolidation.base import ConsolidationConfig
            from consolidation.clustering import SemanticClusteringEngine
            from consolidation.postgres_consolidator import PostgreSQLConsolidator

            # Create consolidation config
            self.consolidation_config = ConsolidationConfig()
            self.consolidation_config.min_cluster_size = (
                3  # Lower for better clustering
            )

            # Initialize clustering engine
            self.clustering_engine = SemanticClusteringEngine(self.consolidation_config)

            # Initialize PostgreSQL consolidator
            connection_string = f"postgresql://{self.connection_params['user']}:{self.connection_params['password']}@{self.connection_params['host']}:{self.connection_params['port']}/{self.connection_params['database']}"
            self.consolidator = PostgreSQLConsolidator(
                connection_string, self.ollama_embeddings
            )

            print("✅ Consolidation system initialized successfully")

        except Exception as e:
            print(f"⚠️ Consolidation system initialization failed: {e}")
            self.consolidation_config = None
            self.clustering_engine = None
            self.consolidator = None

    def cluster_memories(
        self, domain: str = None, force_recluster: bool = False
    ) -> Dict[str, Any]:
        """Cluster memories using the existing consolidation system."""
        if not self.clustering_engine:
            return {"error": "Consolidation system not available"}

        domain = domain or self.default_domain

        try:
            # Get memories with embeddings
            memories = self._get_memories_with_embeddings(domain)

            if len(memories) < self.consolidation_config.min_cluster_size:
                return {
                    "status": "insufficient_data",
                    "reason": f"Need at least {self.consolidation_config.min_cluster_size} memories with embeddings",
                    "memory_count": len(memories),
                }

            # Run clustering
            import asyncio

            clusters = asyncio.run(self.clustering_engine.process(memories))

            return {
                "status": "success",
                "clusters_created": len(clusters),
                "memories_processed": len(memories),
                "clusters": [
                    {
                        "id": cluster.cluster_id,
                        "size": len(cluster.memory_hashes),
                        "coherence_score": cluster.coherence_score,
                        "theme_keywords": cluster.theme_keywords,
                    }
                    for cluster in clusters
                ],
            }

        except Exception as e:
            return {"error": f"Clustering failed: {e}"}

    def _get_memories_with_embeddings(self, domain: str) -> List[Memory]:
        """Get memories with embeddings for clustering."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    table_name = sql.Identifier(f"{domain}_memories")

                    query = sql.SQL(
                        """
                        SELECT id, content, metadata, embedding, created_at, updated_at
                        FROM {}
                        WHERE embedding IS NOT NULL
                        ORDER BY created_at DESC
                        LIMIT 1000
                    """
                    ).format(table_name)

                    cursor.execute(query)
                    results = cursor.fetchall()

                    memories = []
                    for row in results:
                        metadata = row.get("metadata", {})
                        if isinstance(metadata, str):
                            metadata = json.loads(metadata)

                        # Convert datetime objects to timestamps
                        created_at = row.get("created_at")
                        if created_at and hasattr(created_at, "timestamp"):
                            created_at = created_at.timestamp()
                        elif created_at is None:
                            created_at = time.time()

                        updated_at = row.get("updated_at")
                        if updated_at and hasattr(updated_at, "timestamp"):
                            updated_at = updated_at.timestamp()
                        elif updated_at is None:
                            updated_at = time.time()

                        memory = Memory(
                            content=row["content"],
                            content_hash=row["id"],
                            tags=metadata.get("tags", []),
                            memory_type=metadata.get("memory_type"),
                            metadata=metadata,
                            embedding=row["embedding"],
                            created_at=created_at,
                            updated_at=updated_at,
                        )
                        memories.append(memory)

                    return memories

        except Exception as e:
            print(f"Error retrieving memories for clustering: {e}")
            return []

    def consolidate_memories(
        self, domain: Optional[str] = None, days_back: int = 30
    ) -> Dict[str, Any]:
        """Run full memory consolidation using the existing system.

        Note: This is a sync wrapper around async consolidation methods.
        The consolidation system uses async/await internally for database operations.
        """
        if not self.consolidator:
            return {"error": "Consolidation system not available"}

        domain = domain or self.default_domain

        try:
            import asyncio

            # Async boundary: Run async consolidation in sync context
            result = asyncio.run(
                self.consolidator.consolidate_memories(domain, days_back)
            )
            return {"status": "success", **result}
        except Exception as e:
            return {"error": f"Consolidation failed: {e}"}

    # Session Management Methods

    @handle_errors()
    @validate_inputs(
        session_id=lambda x: isinstance(x, str) and x.strip() != "",
        project_context=lambda x: x is None or isinstance(x, dict),
        working_directory=lambda x: x is None or isinstance(x, str),
    )
    def start_session(
        self,
        session_id: str,
        project_context: Optional[Dict[str, Any]] = None,
        working_directory: Optional[str] = None,
        initial_topics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Start a new session and optionally link to existing conversation thread."""
        with error_context("start_session", session_id=session_id):
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    project_name = project_context.get("name") if project_context else None

                    # Try to find recent related sessions for thread linking
                    thread_id = None
                    parent_session_id = None

                    if project_name:
                        # Look for recent sessions in same project (last 24 hours)
                        cursor.execute("""
                            SELECT id, thread_id FROM sessions
                            WHERE project_name = %s
                            AND status = 'completed'
                            AND started_at > NOW() - INTERVAL '24 hours'
                            ORDER BY started_at DESC
                            LIMIT 1
                        """, (project_name,))

                        recent_session = cursor.fetchone()
                        if recent_session:
                            parent_session_id = recent_session['id']
                            thread_id = recent_session['thread_id']

                    # Create new thread if no existing one found
                    if not thread_id:
                        import uuid
                        thread_id = f"thread-{uuid.uuid4().hex[:12]}"

                        cursor.execute("""
                            INSERT INTO conversation_threads (id, project_name, metadata)
                            VALUES (%s, %s, %s)
                        """, (thread_id, project_name, json.dumps(project_context or {})))

                    # Create session record
                    cursor.execute("""
                        INSERT INTO sessions (
                            id, project_name, working_directory, initial_topics,
                            thread_id, parent_session_id, metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        session_id,
                        project_name,
                        working_directory,
                        initial_topics or [],
                        thread_id,
                        parent_session_id,
                        json.dumps(project_context or {})
                    ))

                    conn.commit()

                    logger.info(f"Started session {session_id} in thread {thread_id}")

                    return {
                        "session_id": session_id,
                        "thread_id": thread_id,
                        "parent_session_id": parent_session_id,
                        "project_name": project_name,
                        "is_continuation": parent_session_id is not None
                    }

    @handle_errors()
    @validate_inputs(
        session_id=lambda x: isinstance(x, str) and x.strip() != "",
        outcome=lambda x: x is None or isinstance(x, dict),
    )
    def end_session(
        self,
        session_id: str,
        outcome: Optional[Dict[str, Any]] = None,
        final_topics: Optional[List[str]] = None,
        conversation_summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """End a session with outcome and summary."""
        with error_context("end_session", session_id=session_id):
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Check if session exists and is active
                    cursor.execute("""
                        SELECT id, thread_id, project_name FROM sessions
                        WHERE id = %s AND status = 'active'
                    """, (session_id,))

                    session = cursor.fetchone()
                    if not session:
                        raise ValidationError(f"Active session {session_id} not found")

                    # Update session with completion data
                    cursor.execute("""
                        UPDATE sessions
                        SET ended_at = NOW(),
                            status = 'completed',
                            final_topics = %s,
                            conversation_summary = %s,
                            outcome = %s
                        WHERE id = %s
                    """, (
                        final_topics or [],
                        conversation_summary,
                        json.dumps(outcome or {}),
                        session_id
                    ))

                    # Update conversation thread topics
                    if final_topics and session['thread_id']:
                        cursor.execute("""
                            UPDATE conversation_threads
                            SET topics = array(
                                SELECT DISTINCT unnest(topics || %s::text[])
                            )
                            WHERE id = %s
                        """, (final_topics, session['thread_id']))

                    conn.commit()

                    logger.info(f"Ended session {session_id}")

                    return {
                        "session_id": session_id,
                        "status": "completed",
                        "thread_id": session['thread_id']
                    }

    @handle_errors()
    @validate_inputs(
        session_id=lambda x: isinstance(x, str) and x.strip() != "",
        memory_id=lambda x: isinstance(x, str) and x.strip() != "",
        domain=lambda x: isinstance(x, str) and x.strip() != "",
    )
    def track_session_memory(
        self,
        session_id: str,
        memory_id: str,
        domain: str,
        created_during_session: bool = True,
        interaction_type: str = "loaded",
        relevance_score: Optional[float] = None,
    ) -> bool:
        """Track the relationship between a session and a memory."""
        with error_context("track_session_memory", session_id=session_id, memory_id=memory_id):
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO session_memories (
                            session_id, memory_id, domain, created_during_session,
                            interaction_type, relevance_score
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (session_id, memory_id, domain) DO UPDATE SET
                            interaction_type = EXCLUDED.interaction_type,
                            relevance_score = EXCLUDED.relevance_score
                    """, (
                        session_id, memory_id, domain, created_during_session,
                        interaction_type, relevance_score
                    ))

                    conn.commit()
                    return True

    @handle_errors()
    @validate_inputs(
        project_name=lambda x: x is None or isinstance(x, str),
        limit=lambda x: isinstance(x, int) and x > 0,
    )
    def get_session_context(
        self,
        project_name: Optional[str] = None,
        limit: int = 5,
        include_memories: bool = False,
    ) -> Dict[str, Any]:
        """Get recent session context for continuity."""
        with error_context("get_session_context", project_name=project_name):
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Build query based on project filter
                    where_clause = "WHERE status = 'completed'"
                    params = []

                    if project_name:
                        where_clause += " AND project_name = %s"
                        params.append(project_name)

                    # Get recent sessions
                    cursor.execute(f"""
                        SELECT
                            id, project_name, started_at, ended_at,
                            initial_topics, final_topics, conversation_summary,
                            outcome, thread_id, parent_session_id
                        FROM sessions
                        {where_clause}
                        ORDER BY ended_at DESC
                        LIMIT %s
                    """, params + [limit])

                    sessions = cursor.fetchall()

                    result = {
                        "recent_sessions": [dict(session) for session in sessions],
                        "total_sessions": len(sessions)
                    }

                    if sessions and include_memories:
                        # Get memories associated with recent sessions
                        session_ids = [s['id'] for s in sessions]
                        placeholders = ','.join(['%s'] * len(session_ids))

                        cursor.execute(f"""
                            SELECT
                                sm.session_id, sm.memory_id, sm.domain,
                                sm.created_during_session, sm.interaction_type,
                                sm.relevance_score
                            FROM session_memories sm
                            WHERE sm.session_id IN ({placeholders})
                            ORDER BY sm.relevance_score DESC NULLS LAST
                        """, session_ids)

                        memories = cursor.fetchall()
                        result["session_memories"] = [dict(mem) for mem in memories]

                    return result

    @handle_errors()
    @validate_inputs(
        project_name=lambda x: x is None or isinstance(x, str),
    )
    def get_conversation_threads(
        self,
        project_name: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get conversation threads with session counts."""
        with error_context("get_conversation_threads", project_name=project_name):
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    where_clause = "WHERE ct.status = 'active'"
                    params = []

                    if project_name:
                        where_clause += " AND ct.project_name = %s"
                        params.append(project_name)

                    cursor.execute(f"""
                        SELECT
                            ct.id, ct.project_name, ct.created_at, ct.last_updated,
                            ct.topics, ct.metadata,
                            COUNT(s.id) as session_count,
                            MAX(s.ended_at) as last_session_end
                        FROM conversation_threads ct
                        LEFT JOIN sessions s ON ct.id = s.thread_id
                        {where_clause}
                        GROUP BY ct.id, ct.project_name, ct.created_at, ct.last_updated,
                                 ct.topics, ct.metadata
                        ORDER BY ct.last_updated DESC
                        LIMIT %s
                    """, params + [limit])

                    threads = cursor.fetchall()
                    return [dict(thread) for thread in threads]

import json
import os
import sys
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

        if not project_context:
            logger.info("No project context detected, using 'default' domain")
            return "default"

        # Extract project name and sanitize it for use as a domain
        project_name = project_context.get("name")
        if not project_name or project_name == "unknown":
            logger.info("Project name not detected or unknown, using 'default' domain")
            return "default"

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
            logger.info(
                f"Sanitized project name '{sanitized_domain}' is too short, using 'default' domain"
            )
            sanitized_domain = "default"
        elif len(sanitized_domain) > 50:
            original_domain = sanitized_domain
            sanitized_domain = sanitized_domain[:50].rstrip("_")
            logger.info(
                f"Truncated long domain name from '{original_domain}' to '{sanitized_domain}'"
            )

        logger.info(
            f"Auto-detected project domain: {sanitized_domain} from project: {project_name}"
        )
        return sanitized_domain

    except ImportError as e:
        logger.error(f"Failed to import required module for project detection: {e}")
        return "default"
    except Exception as e:
        logger.error(
            f"Unexpected error in project domain detection: {e}, using 'default'"
        )
        # Log more details about the error for debugging
        import traceback

        logger.debug(f"Project detection error details: {traceback.format_exc()}")
        return "default"


DEFAULT_MIN_SCORE = 0.3
DEFAULT_TIMEOUT_MS = 5000


class PostgresMemoryAPI:
    _consolidation_initialized = False  # Class variable to track initialization

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

        # Per-domain memory limits for token efficiency
        self.domain_memory_limits = {
            "default": 50,        # Maximum memories per domain
            "test-tags": 50,      # Test domain
            # All domains default to 50 memories max
        }

        # Per-domain tag limits for token efficiency (smaller since max 50 memories)
        self.domain_tag_limits = {
            "default": 15,        # General domain
            "test-tags": 10,      # Test domain
            # Auto-calculated for other domains based on memory count
        }

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
                logger.info(
                    f"Ollama embeddings initialized: {ollama_model} at {ollama_url}"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Ollama embeddings: {e}")
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
        table_name = f"{domain}_memories"

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # First check if table already exists
                    cursor.execute(
                        """
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_schema = 'public'
                            AND table_name = %s
                        );
                    """,
                        (table_name,),
                    )

                    exists = cursor.fetchone()[0]

                    if not exists:
                        logger.info(f"Creating table {table_name} for domain {domain}")
                        cursor.execute(
                            "SELECT create_domain_memories_table(%s)", (domain,)
                        )
                        conn.commit()

                        # Verify table was created
                        cursor.execute(
                            """
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables
                                WHERE table_schema = 'public'
                                AND table_name = %s
                            );
                        """,
                            (table_name,),
                        )

                        created = cursor.fetchone()[0]
                        if not created:
                            raise DatabaseError(f"Failed to create table {table_name}")
                        else:
                            logger.info(f"Successfully created table {table_name}")
                    else:
                        logger.debug(f"Table {table_name} already exists")

        except Exception as e:
            logger.error(f"Error ensuring table exists for domain {domain}: {e}")
            raise DatabaseError(
                f"Failed to ensure table exists for domain {domain}: {str(e)}"
            )

    def _flatten_memory_result(self, row_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten commonly used metadata fields to top level for easier access."""
        result = dict(row_dict)

        # Extract metadata if it exists
        metadata = result.get("metadata", {})
        if isinstance(metadata, dict):
            # Flatten tags to top level if they exist
            if "tags" in metadata:
                result["tags"] = metadata["tags"]

        return result

    def _check_for_duplicate(
        self,
        content: str,
        embedding: List[float],
        domain: str,
        similarity_threshold: float = 0.95,
    ) -> bool:
        """
        Check if a similar memory already exists using vector similarity.

        Args:
            content: Memory content
            embedding: Embedding vector
            domain: Memory domain
            similarity_threshold: Threshold for considering as duplicate (0.95 = 95% similar)

        Returns:
            True if duplicate found, False otherwise
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    table_name = sql.Identifier(f"{domain}_memories")

                    # Find similar memories using cosine similarity
                    query = sql.SQL(
                        """
                        SELECT
                            id,
                            content,
                            1 - (embedding <=> %s::vector) as similarity
                        FROM {}
                        WHERE embedding IS NOT NULL
                            AND 1 - (embedding <=> %s::vector) >= %s
                        ORDER BY similarity DESC
                        LIMIT 1
                    """
                    ).format(table_name)

                    cursor.execute(query, (embedding, embedding, similarity_threshold))
                    result = cursor.fetchone()

                    if result:
                        logger.info(
                            f"Found duplicate memory with {result['similarity']:.2%} similarity: "
                            f"{result['content'][:50]}..."
                        )
                        return True

            return False

        except Exception as e:
            # Log error but don't fail the storage operation
            logger.warning(f"Failed to check for duplicates: {e}")
            return False

    def _assess_content_quality(self, content: str) -> tuple[bool, float, str]:
        """
        Assess content quality for storage worthiness.
        Returns: (should_store, quality_score, reason)
        """
        content_lower = content.lower()
        content_length = len(content.strip())

        # Reject too short content
        if content_length < 20:
            return False, 0.1, "Content too short to be meaningful"

        # Check for generic/low-value patterns
        generic_patterns = [
            "todo",
            "fixme",
            "placeholder",
            "temp",
            "test test",
            "delete this",
            "remove this",
            "update this",
            "change this",
            "lorem ipsum",
            "sample text",
            "example content",
        ]

        generic_count = sum(
            1 for pattern in generic_patterns if pattern in content_lower
        )
        if generic_count >= 2:
            return False, 0.2, "Content contains multiple generic placeholders"

        # Boost technical content
        technical_indicators = [
            "error:",
            "exception:",
            "bug:",
            "fix:",
            "solution:",
            "config:",
            "implementation:",
            "optimization:",
            "pattern:",
            "```",
            "function",
            "class",
            "def ",
            "const ",
            "import",
        ]

        technical_score = sum(
            0.1 for indicator in technical_indicators if indicator in content_lower
        )

        # Base quality score
        if content_length < 50:
            base_score = 0.4
        elif content_length < 200:
            base_score = 0.6
        elif content_length < 1000:
            base_score = 0.8
        else:
            base_score = 0.7  # Slightly lower for very long content

        quality_score = min(1.0, base_score + technical_score)

        # Decision threshold
        if quality_score < 0.3:
            return False, quality_score, "Content quality below threshold"

        return True, quality_score, "Content meets quality standards"

    def store_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        domain: Optional[str] = None,
        importance: Optional[int] = None,
        tags: Optional[List[str]] = None,
        auto_tag: bool = True,
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

            # Assess content quality (Phase 1 optimization)
            should_store, quality_score, reason = self._assess_content_quality(content)
            if not should_store:
                logger.info(
                    f"Rejecting low-quality content: {reason} (score: {quality_score:.2f})"
                )
                raise ValidationError(
                    f"Content quality too low: {reason}",
                    field="content",
                    value=quality_score,
                )

            # Content size validation - 5KB limit (optimized from 100KB)
            max_content_size = 5_000
            if len(content) > max_content_size:
                raise ValidationError(
                    f"Content too long (max {max_content_size:,} characters)",
                    field="content",
                    value=len(content),
                )

            # Check actual byte size for unicode content
            content_bytes = content.encode("utf-8")
            max_bytes = 5 * 1024  # 5KB (optimized from 100KB)
            if len(content_bytes) > max_bytes:
                raise ValidationError(
                    f"Content too large (max {max_bytes:,} bytes, got {len(content_bytes):,} bytes)",
                    field="content",
                    value=len(content_bytes),
                )

            if metadata is not None:
                if not isinstance(metadata, dict):
                    raise ValidationError(
                        "Metadata must be a dictionary or None", field="metadata"
                    )

                # Validate metadata size (2KB JSON limit - optimized from 10KB)
                metadata_json = json.dumps(metadata, ensure_ascii=False)
                metadata_bytes = metadata_json.encode("utf-8")
                max_metadata_bytes = 2 * 1024  # 2KB (optimized)
                if len(metadata_bytes) > max_metadata_bytes:
                    raise ValidationError(
                        f"Metadata too large (max {max_metadata_bytes:,} bytes, got {len(metadata_bytes):,} bytes)",
                        field="metadata",
                        value=len(metadata_bytes),
                    )

            if domain is not None:
                if not isinstance(domain, str):
                    raise ValidationError(
                        "Domain must be a string or None", field="domain"
                    )

                # Validate domain name format (alphanumeric, underscores, hyphens only)
                import re

                if not re.match(r"^[a-zA-Z0-9_-]+$", domain):
                    raise ValidationError(
                        "Domain must contain only alphanumeric characters, underscores, and hyphens",
                        field="domain",
                        value=domain,
                    )

                # Length validation
                if len(domain) < 1:
                    raise ValidationError("Domain cannot be empty", field="domain")
                elif len(domain) > 50:
                    raise ValidationError(
                        f"Domain too long (max 50 characters, got {len(domain)})",
                        field="domain",
                        value=len(domain),
                    )

                # Reserved names validation
                reserved_names = {
                    "system",
                    "admin",
                    "root",
                    "user",
                    "test",
                    "temp",
                    "public",
                    "private",
                }
                if domain.lower() in reserved_names:
                    raise ValidationError(
                        f"Domain name '{domain}' is reserved",
                        field="domain",
                        value=domain,
                    )

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

        # Handle tags (manual + auto-generated)
        final_tags = list(tags) if tags else []

        # Auto-generate tags if enabled and content is substantial
        if auto_tag and len(content.strip()) > 20:
            try:
                generated_tags = self._generate_tags_with_ollama(content)
                # Add generated tags, avoiding duplicates
                for tag in generated_tags:
                    if tag not in final_tags:
                        final_tags.append(tag)
                logger.info(f"Auto-generated {len(generated_tags)} tags, total: {len(final_tags)}")
            except Exception as e:
                logger.warning(f"Auto-tagging failed: {e}")

        # Add tags to metadata if we have any
        if final_tags:
            if not isinstance(final_tags, list):
                raise ValidationError("Tags must be a list of strings", field="tags")

            # Validate each tag
            for tag in final_tags:
                if not isinstance(tag, str):
                    raise ValidationError("All tags must be strings", field="tags")
                if len(tag.strip()) == 0:
                    raise ValidationError(
                        "Tags cannot be empty or whitespace only", field="tags"
                    )

            # Remove duplicates and empty tags, then add to metadata
            clean_tags = list(set(tag.strip() for tag in final_tags if tag.strip()))
            if clean_tags:
                metadata["tags"] = clean_tags

        metadata.update(
            {
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )

        # Add importance to metadata if provided
        if importance is not None:
            metadata["importance"] = importance

        # Generate embedding with retry logic
        embedding = None
        if self.ollama_embeddings:
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    embedding = self.ollama_embeddings.get_embedding(content)
                    if not embedding or not isinstance(embedding, list):
                        raise EmbeddingError(
                            "Invalid embedding generated",
                            model=getattr(
                                self.ollama_embeddings, "model_name", "unknown"
                            ),
                        )
                    break  # Success, exit retry loop
                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(
                            f"Embedding attempt {attempt + 1} failed: {e}, retrying..."
                        )
                        time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                        continue
                    else:
                        # Final failure - log error and decide whether to fail or continue
                        logger.error(
                            f"Failed to generate embedding after {max_retries + 1} attempts: {e}"
                        )
                        # For now, continue without embedding but track this as degraded service
                        # TODO: Consider making this configurable or failing completely based on use case

        # Check for duplicates before storing (Phase 2 optimization)
        if embedding and self._check_for_duplicate(content, embedding, domain):
            logger.info(
                f"Duplicate memory detected in domain {domain}, skipping storage"
            )
            # Return a special ID to indicate duplicate was found but not stored
            return f"duplicate_skipped_{memory_id}"

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

        # Check if we need to prune memories (deterministic based on count)
        stats = self.get_domain_stats(domain)
        current_count = stats.get("memory_count", 0)
        limit = self.get_domain_memory_limit(domain)

        if current_count > limit:
            # Prune old memories immediately when over limit
            pruned_memories = self.prune_oldest_memories(domain)

            # Clean up any unused tags after pruning
            if pruned_memories > 0:
                self.cleanup_unused_tags(domain)

        # Periodically enforce tag limits (every 5th memory to avoid overhead)
        import random
        if random.randint(1, 5) == 1:  # 20% chance
            try:
                self.enforce_domain_tag_limit(domain)
            except Exception as e:
                logger.warning(f"Tag limit enforcement failed for {domain}: {e}")

        return memory_id

    def retrieve_memories(
        self,
        query: str,
        limit: int = 5,
        domain: Optional[str] = None,
        time_filter: Optional[str] = None,
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
                                return [
                                    self._flatten_memory_result(dict(row))
                                    for row in results
                                ]

                            # If no records have embeddings, fall through to text search
            except Exception as e:
                logger.debug(f"Vector search failed, falling back to text search: {e}")

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
                        ).format(
                            table_name,
                            sql.SQL(" OR ").join(
                                [sql.SQL(condition) for condition in tag_conditions]
                            ),
                            sql.SQL(time_filter_sql),
                        )

                        cursor.execute(tag_query, tag_params + [limit])
                        results = cursor.fetchall()

                        if results:
                            return [
                                self._flatten_memory_result(dict(row))
                                for row in results
                            ]

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
                where_clause = (
                    sql.SQL("WHERE 1=1") + sql.SQL(time_filter_sql)
                    if time_filter_sql
                    else sql.SQL("")
                )
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
                            logger.debug(
                                f"Failed to generate embedding for update: {e}"
                            )

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
                            logger.debug(
                                f"Failed to generate embedding for update: {e}"
                            )

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
                            "size": 0,  # Size in bytes
                            "last_activity": None,
                        }

                    # Get memory count
                    from psycopg2 import sql as psycopg2_sql

                    count_query = psycopg2_sql.SQL("SELECT COUNT(*) FROM {}").format(
                        psycopg2_sql.Identifier(table_name)
                    )
                    cursor.execute(count_query)
                    memory_count = cursor.fetchone()[0]

                    # Get table size (both bytes and pretty format)
                    cursor.execute(
                        """
                        SELECT
                            pg_total_relation_size(%s) as size_bytes,
                            pg_size_pretty(pg_total_relation_size(%s)) as size_pretty
                    """,
                        (table_name, table_name),
                    )
                    result = cursor.fetchone()
                    table_size_bytes = result[0]
                    table_size = result[1]

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
                        "size": table_size_bytes,  # Size in bytes for calculations
                        "last_activity": (
                            last_activity.isoformat() if last_activity else None
                        ),
                    }
        except Exception as e:
            logger.error(f"Error getting domain stats for {domain}: {e}")
            return {"memory_count": 0, "table_size": "0 B", "size": 0, "last_activity": None}

    def get_domain_memory_limit(self, domain: str) -> int:
        """Get memory limit for a domain (default 50)."""
        return self.domain_memory_limits.get(domain, 50)

    def get_domain_tag_limit(self, domain: str) -> int:
        """Get tag limit for a domain, auto-calculating for new domains."""
        if domain in self.domain_tag_limits:
            return self.domain_tag_limits[domain]

        # Auto-calculate limit based on memory count (max 50 memories)
        stats = self.get_domain_stats(domain)
        memory_count = stats.get("memory_count", 0)

        if memory_count < 10:
            limit = 5
        elif memory_count < 25:
            limit = 8
        elif memory_count < 40:
            limit = 12
        else:
            limit = 15  # Max tag limit for max 50 memories

        # Cache the calculated limit
        self.domain_tag_limits[domain] = limit
        return limit

    def enforce_domain_tag_limit(self, domain: str) -> int:
        """Enforce tag limits by pruning least-used tags. Returns number of tags removed."""
        limit = self.get_domain_tag_limit(domain)

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
                        return 0

                    # Get tag usage frequency (only from arrays, not scalars)
                    cursor.execute(f"""
                        SELECT tag, COUNT(*) as usage_count
                        FROM (
                            SELECT jsonb_array_elements_text(metadata->'tags') as tag
                            FROM "{table_name}"
                            WHERE metadata->'tags' IS NOT NULL
                            AND jsonb_typeof(metadata->'tags') = 'array'
                        ) tag_stats
                        WHERE tag IS NOT NULL AND tag != ''
                        GROUP BY tag
                        ORDER BY usage_count ASC
                    """)

                    tag_usage = cursor.fetchall()
                    current_tag_count = len(tag_usage)

                    if current_tag_count <= limit:
                        return 0

                    # Remove least-used tags
                    tags_to_remove = current_tag_count - limit
                    least_used_tags = [row[0] for row in tag_usage[:tags_to_remove]]

                    # Remove these tags from all memories
                    for tag in least_used_tags:
                        cursor.execute(f"""
                            UPDATE "{table_name}"
                            SET metadata = metadata || jsonb_build_object(
                                'tags',
                                (SELECT jsonb_agg(elem)
                                 FROM jsonb_array_elements_text(metadata->'tags') elem
                                 WHERE elem != %s)
                            )
                            WHERE metadata->'tags' ? %s
                        """, (tag, tag))

                    logger.info(f"Enforced tag limit for {domain}: removed {tags_to_remove} least-used tags")
                    return tags_to_remove

        except Exception as e:
            logger.error(f"Error enforcing tag limit for {domain}: {e}")
            return 0

    def prune_oldest_memories(self, domain: str) -> int:
        """Prune oldest memories when domain exceeds memory limit. Returns number removed."""
        limit = self.get_domain_memory_limit(domain)

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
                        return 0

                    # Count current memories
                    cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                    current_count = cursor.fetchone()[0]

                    if current_count <= limit:
                        return 0

                    # Calculate how many to remove
                    to_remove = current_count - limit

                    # Get oldest memory IDs
                    cursor.execute(f"""
                        SELECT id FROM "{table_name}"
                        ORDER BY created_at ASC
                        LIMIT %s
                    """, (to_remove,))

                    old_memory_ids = [row[0] for row in cursor.fetchall()]

                    # Delete oldest memories
                    if old_memory_ids:
                        placeholders = ','.join(['%s'] * len(old_memory_ids))
                        cursor.execute(f"""
                            DELETE FROM "{table_name}"
                            WHERE id IN ({placeholders})
                        """, old_memory_ids)

                        logger.info(f"Pruned {to_remove} oldest memories from {domain} (limit: {limit})")
                        return to_remove

            return 0

        except Exception as e:
            logger.error(f"Error pruning memories for {domain}: {e}")
            return 0

    def cleanup_unused_tags(self, domain: str) -> int:
        """Remove tags that are no longer used by any memories. Returns number removed."""
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
                        return 0

                    # Get all currently used tags (only from arrays, not scalars)
                    cursor.execute(f"""
                        SELECT DISTINCT jsonb_array_elements_text(metadata->'tags') as tag
                        FROM "{table_name}"
                        WHERE metadata->'tags' IS NOT NULL
                        AND jsonb_typeof(metadata->'tags') = 'array'
                    """)

                    used_tags = set()
                    for row in cursor.fetchall():
                        if row[0] and row[0].strip():
                            used_tags.add(row[0])

                    # Find memories with tags not in the used set and clean them
                    cursor.execute(f"""
                        SELECT id, metadata
                        FROM "{table_name}"
                        WHERE metadata->'tags' IS NOT NULL
                    """)

                    cleaned_count = 0
                    for row in cursor.fetchall():
                        memory_id, metadata = row
                        current_tags = metadata.get('tags', [])
                        if current_tags:
                            # Filter to only keep used tags
                            filtered_tags = [tag for tag in current_tags if tag in used_tags]

                            if len(filtered_tags) != len(current_tags):
                                # Update memory with filtered tags
                                metadata['tags'] = filtered_tags
                                cursor.execute(f"""
                                    UPDATE "{table_name}"
                                    SET metadata = %s
                                    WHERE id = %s
                                """, (Json(metadata), memory_id))
                                cleaned_count += 1

                    if cleaned_count > 0:
                        logger.info(f"Cleaned unused tags from {cleaned_count} memories in {domain}")

                    return cleaned_count

        except Exception as e:
            logger.error(f"Error cleaning unused tags for {domain}: {e}")
            return 0

    def get_total_unique_tags_count(self) -> int:
        """Get total unique tags count across all domains."""
        try:
            all_tags = set()
            domains = self.list_domains()

            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    for domain in domains:
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

                        if cursor.fetchone()[0]:
                            # Get unique tags from this domain (only from arrays, not scalars)
                            cursor.execute(f"""
                                SELECT DISTINCT jsonb_array_elements_text(metadata->'tags') as tag
                                FROM "{table_name}"
                                WHERE metadata->'tags' IS NOT NULL
                                AND jsonb_typeof(metadata->'tags') = 'array'
                            """)

                            domain_tags = cursor.fetchall()
                            for row in domain_tags:
                                if row[0] and row[0].strip():  # Skip empty tags
                                    all_tags.add(row[0].lower())

            return len(all_tags)

        except Exception as e:
            logger.error(f"Error calculating total unique tags: {e}")
            return 0

    def _generate_tags_with_ollama(self, content: str) -> List[str]:
        """Generate intelligent tags using Ollama AI."""
        if not self.ollama_embeddings:
            logger.warning("Ollama not available for tag generation")
            return []

        try:
            # Create a concise prompt for tag extraction
            prompt = f"""Extract 3-5 relevant tags from this text. Return only tags separated by commas:

{content[:500]}

Tags:"""

            # Use Ollama's generate API for text completion
            generate_url = f"{self.ollama_embeddings.base_url}/api/generate"
            response = self.ollama_embeddings.session.post(
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

    def _init_consolidation_system(self) -> None:
        """Initialize the existing consolidation system."""
        # Skip if already initialized at class level
        if PostgresMemoryAPI._consolidation_initialized:
            self.consolidation_config = getattr(
                PostgresMemoryAPI, "_shared_config", None
            )
            self.clustering_engine = getattr(PostgresMemoryAPI, "_shared_engine", None)
            self.consolidator = getattr(PostgresMemoryAPI, "_shared_consolidator", None)
            return

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

            # Store at class level for reuse
            PostgresMemoryAPI._shared_config = self.consolidation_config
            PostgresMemoryAPI._shared_engine = self.clustering_engine
            PostgresMemoryAPI._shared_consolidator = self.consolidator
            PostgresMemoryAPI._consolidation_initialized = True

            logger.info("Consolidation system initialized successfully")

        except Exception as e:
            logger.warning(f"Consolidation system initialization failed: {e}")
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
            logger.error(f"Error retrieving memories for clustering: {e}")
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
        project_name=lambda x: x is None or isinstance(x, str),
    )
    def start_session(
        self,
        session_id: str,
        project_context: Optional[Dict[str, Any]] = None,
        working_directory: Optional[str] = None,
        initial_topics: Optional[List[str]] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start a new session and optionally link to existing conversation thread."""
        with error_context("start_session", session_id=session_id):
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Accept project_name directly or from context
                    if project_name is None and project_context:
                        project_name = project_context.get("name")

                    # Try to find recent related sessions for thread linking
                    thread_id = None
                    parent_session_id = None

                    if project_name:
                        # Look for recent sessions in same project (last 24 hours)
                        cursor.execute(
                            """
                            SELECT id, thread_id FROM sessions
                            WHERE project_name = %s
                            AND status = 'completed'
                            AND started_at > NOW() - INTERVAL '24 hours'
                            ORDER BY started_at DESC
                            LIMIT 1
                        """,
                            (project_name,),
                        )

                        recent_session = cursor.fetchone()
                        if recent_session:
                            parent_session_id = recent_session["id"]
                            thread_id = recent_session["thread_id"]

                    # Create new thread if no existing one found
                    if not thread_id:
                        import uuid

                        thread_id = f"thread-{uuid.uuid4().hex[:12]}"

                        cursor.execute(
                            """
                            INSERT INTO conversation_threads (id, project_name, metadata)
                            VALUES (%s, %s, %s)
                        """,
                            (
                                thread_id,
                                project_name,
                                json.dumps(project_context or {}),
                            ),
                        )

                    # Create session record
                    cursor.execute(
                        """
                        INSERT INTO sessions (
                            id, project_name, working_directory, initial_topics,
                            thread_id, parent_session_id, metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            session_id,
                            project_name,
                            working_directory,
                            initial_topics or [],
                            thread_id,
                            parent_session_id,
                            json.dumps(project_context or {}),
                        ),
                    )

                    conn.commit()

                    logger.info(f"Started session {session_id} in thread {thread_id}")

                    return {
                        "session_id": session_id,
                        "thread_id": thread_id,
                        "parent_session_id": parent_session_id,
                        "project_name": project_name,
                        "is_continuation": parent_session_id is not None,
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
                    cursor.execute(
                        """
                        SELECT id, thread_id, project_name FROM sessions
                        WHERE id = %s AND status = 'active'
                    """,
                        (session_id,),
                    )

                    session = cursor.fetchone()
                    if not session:
                        raise ValidationError(f"Active session {session_id} not found")

                    # Update session with completion data
                    cursor.execute(
                        """
                        UPDATE sessions
                        SET ended_at = NOW(),
                            status = 'completed',
                            final_topics = %s,
                            conversation_summary = %s,
                            outcome = %s
                        WHERE id = %s
                    """,
                        (
                            final_topics or [],
                            conversation_summary,
                            json.dumps(outcome or {}),
                            session_id,
                        ),
                    )

                    # Update conversation thread topics
                    if final_topics and session["thread_id"]:
                        cursor.execute(
                            """
                            UPDATE conversation_threads
                            SET topics = array(
                                SELECT DISTINCT unnest(topics || %s::text[])
                            )
                            WHERE id = %s
                        """,
                            (final_topics, session["thread_id"]),
                        )

                    conn.commit()

                    logger.info(f"Ended session {session_id}")

                    return {
                        "session_id": session_id,
                        "status": "completed",
                        "thread_id": session["thread_id"],
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
        with error_context(
            "track_session_memory", session_id=session_id, memory_id=memory_id
        ):
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO session_memories (
                            session_id, memory_id, domain, created_during_session,
                            interaction_type, relevance_score
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (session_id, memory_id, domain) DO UPDATE SET
                            interaction_type = EXCLUDED.interaction_type,
                            relevance_score = EXCLUDED.relevance_score
                    """,
                        (
                            session_id,
                            memory_id,
                            domain,
                            created_during_session,
                            interaction_type,
                            relevance_score,
                        ),
                    )

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
                    cursor.execute(
                        f"""
                        SELECT
                            id, project_name, started_at, ended_at,
                            initial_topics, final_topics, conversation_summary,
                            outcome, thread_id, parent_session_id
                        FROM sessions
                        {where_clause}
                        ORDER BY ended_at DESC
                        LIMIT %s
                    """,
                        params + [limit],
                    )

                    sessions = cursor.fetchall()

                    result = {
                        "recent_sessions": [dict(session) for session in sessions],
                        "total_sessions": len(sessions),
                    }

                    if sessions and include_memories:
                        # Get memories associated with recent sessions
                        session_ids = [s["id"] for s in sessions]
                        placeholders = ",".join(["%s"] * len(session_ids))

                        cursor.execute(
                            f"""
                            SELECT
                                sm.session_id, sm.memory_id, sm.domain,
                                sm.created_during_session, sm.interaction_type,
                                sm.relevance_score
                            FROM session_memories sm
                            WHERE sm.session_id IN ({placeholders})
                            ORDER BY sm.relevance_score DESC NULLS LAST
                        """,
                            session_ids,
                        )

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

                    cursor.execute(
                        f"""
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
                    """,
                        params + [limit],
                    )

                    threads = cursor.fetchall()
                    return [dict(thread) for thread in threads]

    # Session Analytics Functions
    @handle_errors()
    @validate_inputs(
        project_name=lambda x: x is None or isinstance(x, str),
        limit=lambda x: isinstance(x, int) and x > 0,
        days_back=lambda x: isinstance(x, int) and x > 0,
    )
    def find_recurring_topics(
        self,
        project_name: Optional[str] = None,
        limit: int = 10,
        days_back: int = 30,
    ) -> List[Dict[str, Any]]:
        """Find topics that appear across multiple sessions."""
        with error_context("find_recurring_topics", project_name=project_name):
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Build where clause
                    where_clauses = ["s.status = 'completed'"]
                    params = []

                    if project_name:
                        where_clauses.append("s.project_name = %s")
                        params.append(project_name)

                    if days_back:
                        where_clauses.append(
                            "s.ended_at >= NOW() - make_interval(days => %s)"
                        )
                        params.append(days_back)

                    where_clause = (
                        "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
                    )

                    # Query to find recurring topics
                    cursor.execute(
                        f"""
                        WITH topic_occurrences AS (
                            SELECT
                                topic,
                                COUNT(DISTINCT s.id) as session_count,
                                COUNT(DISTINCT s.thread_id) as thread_count,
                                ARRAY_AGG(DISTINCT s.id) as session_ids,
                                MAX(s.ended_at) as last_seen
                            FROM sessions s
                            CROSS JOIN LATERAL unnest(
                                COALESCE(s.final_topics, ARRAY[]::text[]) ||
                                COALESCE(s.initial_topics, ARRAY[]::text[])
                            ) AS topic
                            {where_clause}
                            GROUP BY topic
                            HAVING COUNT(DISTINCT s.id) > 1
                        )
                        SELECT
                            topic,
                            session_count,
                            thread_count,
                            session_ids[1:5] as recent_sessions,
                            last_seen
                        FROM topic_occurrences
                        ORDER BY session_count DESC, last_seen DESC
                        LIMIT %s
                    """,
                        params + [limit],
                    )

                    topics = cursor.fetchall()
                    return [dict(topic) for topic in topics]

    @handle_errors()
    @validate_inputs(
        project_name=lambda x: x is None or isinstance(x, str),
        days_back=lambda x: isinstance(x, int) and x > 0,
    )
    def analyze_progression_patterns(
        self,
        project_name: Optional[str] = None,
        days_back: int = 30,
    ) -> Dict[str, Any]:
        """Analyze workflow patterns in session outcomes."""
        with error_context("analyze_progression_patterns", project_name=project_name):
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Build where clause
                    where_clauses = [
                        "s1.status = 'completed'",
                        "s2.status = 'completed'",
                    ]
                    params = []

                    if project_name:
                        where_clauses.append("s1.project_name = %s")
                        where_clauses.append("s2.project_name = %s")
                        params.extend([project_name, project_name])

                    if days_back:
                        where_clauses.append(
                            "s1.ended_at >= NOW() - make_interval(days => %s)"
                        )
                        params.append(days_back)

                    where_clause = "WHERE " + " AND ".join(where_clauses)

                    # Analyze outcome type sequences
                    cursor.execute(
                        f"""
                        WITH session_pairs AS (
                            SELECT
                                s1.id as session1_id,
                                s2.id as session2_id,
                                s1.outcome->>'type' as outcome1,
                                s2.outcome->>'type' as outcome2,
                                s1.thread_id
                            FROM sessions s1
                            JOIN sessions s2 ON s1.thread_id = s2.thread_id
                                AND s2.started_at > s1.ended_at
                                AND s2.started_at < s1.ended_at + INTERVAL '48 hours'
                            {where_clause}
                        )
                        SELECT
                            outcome1 || ' → ' || outcome2 as pattern,
                            COUNT(*) as occurrences,
                            ARRAY_AGG(DISTINCT thread_id) as thread_ids
                        FROM session_pairs
                        WHERE outcome1 IS NOT NULL AND outcome2 IS NOT NULL
                        GROUP BY outcome1, outcome2
                        ORDER BY occurrences DESC
                    """,
                        params,
                    )

                    patterns = cursor.fetchall()

                    # Also get common outcome types
                    cursor.execute(
                        f"""
                        SELECT
                            outcome->>'type' as outcome_type,
                            COUNT(*) as count
                        FROM sessions s
                        WHERE s.status = 'completed'
                        AND s.outcome->>'type' IS NOT NULL
                        {' AND s.project_name = %s' if project_name else ''}
                        {' AND s.ended_at >= NOW() - make_interval(days => %s)' if days_back else ''}
                        GROUP BY outcome->>'type'
                        ORDER BY count DESC
                    """,
                        [p for p in [project_name, days_back] if p is not None],
                    )

                    outcome_types = cursor.fetchall()

                    return {
                        "progression_patterns": [dict(p) for p in patterns],
                        "outcome_distribution": [dict(o) for o in outcome_types],
                    }

    @handle_errors()
    @validate_inputs(
        project_name=lambda x: x is None or isinstance(x, str),
        days_back=lambda x: isinstance(x, int) and x > 0,
        limit=lambda x: isinstance(x, int) and x > 0,
    )
    def find_uncompleted_tasks(
        self,
        project_name: Optional[str] = None,
        days_back: int = 7,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Find sessions with partial or planning outcomes that may need follow-up."""
        with error_context("find_uncompleted_tasks", project_name=project_name):
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Build where clause
                    where_clauses = [
                        "s.status = 'completed'",
                        "(s.outcome->>'type' IN ('planning', 'partial', 'incomplete', 'todo') OR s.outcome->>'type' IS NULL)",
                    ]
                    params = []

                    if project_name:
                        where_clauses.append("s.project_name = %s")
                        params.append(project_name)

                    if days_back:
                        where_clauses.append(
                            "s.ended_at >= NOW() - make_interval(days => %s)"
                        )
                        params.append(days_back)

                    where_clause = "WHERE " + " AND ".join(where_clauses)

                    cursor.execute(
                        f"""
                        SELECT
                            s.id as session_id,
                            s.project_name,
                            s.ended_at,
                            s.outcome->>'type' as outcome_type,
                            s.conversation_summary,
                            s.final_topics,
                            s.thread_id,
                            -- Check if there's a follow-up session
                            EXISTS(
                                SELECT 1 FROM sessions s2
                                WHERE s2.thread_id = s.thread_id
                                AND s2.started_at > s.ended_at
                                AND s2.outcome->>'type' IN ('completed', 'implemented')
                            ) as has_followup
                        FROM sessions s
                        {where_clause}
                        ORDER BY s.ended_at DESC
                        LIMIT %s
                    """,
                        params + [limit],
                    )

                    tasks = cursor.fetchall()
                    return [dict(task) for task in tasks]

    @handle_errors()
    @validate_inputs(
        session1_id=lambda x: isinstance(x, str) and x.strip() != "",
        session2_id=lambda x: isinstance(x, str) and x.strip() != "",
    )
    def calculate_session_relatedness(
        self,
        session1_id: str,
        session2_id: str,
    ) -> float:
        """Calculate relatedness score between two sessions (0.0 to 1.0)."""
        with error_context(
            "calculate_session_relatedness",
            session1_id=session1_id,
            session2_id=session2_id,
        ):
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Get both sessions
                    cursor.execute(
                        """
                        SELECT
                            id, project_name, thread_id, started_at, ended_at,
                            initial_topics, final_topics, outcome
                        FROM sessions
                        WHERE id IN (%s, %s)
                    """,
                        (session1_id, session2_id),
                    )

                    sessions = cursor.fetchall()
                    if len(sessions) != 2:
                        return 0.0

                    s1, s2 = sessions[0], sessions[1]
                    if s1["id"] != session1_id:
                        s1, s2 = s2, s1

                    score = 0.0
                    factors = 0

                    # Same thread = high relatedness
                    if s1["thread_id"] and s1["thread_id"] == s2["thread_id"]:
                        score += 0.4
                        factors += 1

                    # Same project = moderate relatedness
                    if s1["project_name"] == s2["project_name"]:
                        score += 0.2
                        factors += 1

                    # Topic overlap
                    topics1 = set(
                        (s1["initial_topics"] or []) + (s1["final_topics"] or [])
                    )
                    topics2 = set(
                        (s2["initial_topics"] or []) + (s2["final_topics"] or [])
                    )
                    if topics1 and topics2:
                        overlap = len(topics1 & topics2) / len(topics1 | topics2)
                        score += 0.3 * overlap
                        factors += 1

                    # Time proximity (sessions within 24 hours)
                    if s1["ended_at"] and s2["started_at"]:
                        time_diff = abs(
                            (s2["started_at"] - s1["ended_at"]).total_seconds()
                        )
                        if time_diff < 86400:  # 24 hours
                            proximity_score = 1.0 - (time_diff / 86400)
                            score += 0.1 * proximity_score
                            factors += 1

                    return min(1.0, score)

    # Session Maintenance Functions
    @handle_errors()
    @validate_inputs(
        days=lambda x: isinstance(x, int) and x > 0,
    )
    def cleanup_expired_sessions(
        self,
        days: int = 30,
    ) -> Dict[str, int]:
        """Remove sessions older than specified days and clean up references."""
        with error_context("cleanup_expired_sessions", days=days):
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # First, count sessions to be deleted
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM sessions
                        WHERE ended_at < NOW() - make_interval(days => %s)
                        OR (started_at < NOW() - make_interval(days => %s) AND status != 'active')
                    """,
                        (days, days * 2),
                    )

                    count = cursor.fetchone()[0]

                    if count > 0:
                        # Delete expired sessions (cascade will handle session_memories)
                        cursor.execute(
                            """
                            DELETE FROM sessions
                            WHERE ended_at < NOW() - make_interval(days => %s)
                            OR (started_at < NOW() - make_interval(days => %s) AND status != 'active')
                        """,
                            (days, days * 2),
                        )

                        # Clean up empty conversation threads
                        cursor.execute(
                            """
                            DELETE FROM conversation_threads ct
                            WHERE NOT EXISTS (
                                SELECT 1 FROM sessions s WHERE s.thread_id = ct.id
                            )
                        """
                        )

                        conn.commit()

                    return {
                        "sessions_deleted": count,
                        "days": days,
                    }

    @handle_errors()
    @validate_inputs(
        project_name=lambda x: x is None or isinstance(x, str),
    )
    def get_session_statistics(
        self,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get comprehensive statistics about sessions."""
        with error_context("get_session_statistics", project_name=project_name):
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    where_clause = "WHERE project_name = %s" if project_name else ""
                    params = [project_name] if project_name else []

                    # Overall statistics
                    cursor.execute(
                        f"""
                        SELECT
                            COUNT(*) as total_sessions,
                            COUNT(DISTINCT project_name) as total_projects,
                            COUNT(DISTINCT thread_id) as total_threads,
                            COUNT(CASE WHEN status = 'active' THEN 1 END) as active_sessions,
                            COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_sessions,
                            AVG(EXTRACT(EPOCH FROM (ended_at - started_at))/3600) as avg_duration_hours,
                            MAX(ended_at) as last_session_end,
                            MIN(started_at) as first_session_start
                        FROM sessions
                        {where_clause}
                    """,
                        params,
                    )

                    stats = dict(cursor.fetchone())

                    # Get top projects if not filtering by project
                    if not project_name:
                        cursor.execute(
                            """
                            SELECT
                                project_name,
                                COUNT(*) as session_count,
                                MAX(ended_at) as last_activity
                            FROM sessions
                            WHERE project_name IS NOT NULL
                            GROUP BY project_name
                            ORDER BY session_count DESC
                            LIMIT 5
                        """
                        )
                        stats["top_projects"] = [dict(p) for p in cursor.fetchall()]

                    # Memory associations
                    cursor.execute(
                        f"""
                        SELECT
                            COUNT(DISTINCT sm.memory_id) as unique_memories,
                            COUNT(*) as total_associations,
                            COUNT(CASE WHEN sm.created_during_session THEN 1 END) as memories_created
                        FROM session_memories sm
                        JOIN sessions s ON sm.session_id = s.id
                        {where_clause}
                    """,
                        params,
                    )

                    memory_stats = cursor.fetchone()
                    if memory_stats:
                        stats.update(dict(memory_stats))

                    return stats

    @handle_errors()
    @validate_inputs(
        days=lambda x: isinstance(x, int) and x > 0,
    )
    def archive_old_threads(
        self,
        days: int = 90,
    ) -> int:
        """Archive conversation threads with no recent activity."""
        with error_context("archive_old_threads", days=days):
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE conversation_threads
                        SET status = 'archived'
                        WHERE status = 'active'
                        AND id IN (
                            SELECT ct.id
                            FROM conversation_threads ct
                            LEFT JOIN sessions s ON ct.id = s.thread_id
                            GROUP BY ct.id
                            HAVING MAX(s.ended_at) < NOW() - make_interval(days => %s)
                               OR MAX(s.ended_at) IS NULL
                        )
                    """,
                        (days,),
                    )

                    archived_count = cursor.rowcount
                    conn.commit()

                    return archived_count

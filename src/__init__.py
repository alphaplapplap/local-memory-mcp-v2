"""
Local Memory MCP Service
A PostgreSQL + pgvector based memory system with MCP protocol support
"""

__version__ = "2.0.0"

# Try relative imports first (when used as a package),
# fall back to absolute imports (when run directly)
try:
    # When imported as a package
    from .postgres_memory_api import PostgresMemoryAPI, get_project_domain
    from .memory_scorer import score_memory_relevance
    from .ollama_embeddings import OllamaEmbeddings
except ImportError:
    # When run directly from src directory
    from postgres_memory_api import PostgresMemoryAPI, get_project_domain
    from memory_scorer import score_memory_relevance
    from ollama_embeddings import OllamaEmbeddings

__all__ = [
    "PostgresMemoryAPI",
    "get_project_domain",
    "score_memory_relevance",
    "OllamaEmbeddings",
]
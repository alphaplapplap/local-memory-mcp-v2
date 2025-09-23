#!/usr/bin/env python3
"""
Python API for Local Memory MCP System

This module provides a clean, high-level Python interface for the memory system.
It wraps the core PostgresMemoryAPI and DocumentIngestionManager to provide
a user-friendly API for Python applications, scripts, and notebooks.

Usage:
    from src.python_api import MemorySystem

    # Initialize the memory system
    memory = MemorySystem()

    # Store a memory
    memory_id = memory.store("User prefers Python over JavaScript", "personal")

    # Search memories
    results = memory.search("programming preferences", domain="personal")

    # Ingest documents
    result = memory.ingest_document("document.pdf", domain="research")
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Dict, List, Optional, Union

from dotenv import load_dotenv

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ingestion.manager import DocumentIngestionManager
from ollama_embeddings import OllamaEmbeddings
from postgres_memory_api import PostgresMemoryAPI

# Load environment variables
load_dotenv()


class MemorySystem:
    """
    High-level Python API for the Local Memory MCP System.

    This class provides a clean, synchronous interface for memory operations,
    document ingestion, and domain management. It automatically handles
    Ollama embeddings setup and provides both sync and async methods.
    """

    def __init__(
        self,
        ollama_url: Optional[str] = None,
        embedding_model: Optional[str] = None,
        keep_alive: Optional[str] = None,
        auto_setup_ollama: bool = True,
    ):
        """
        Initialize the Memory System.

        Args:
            ollama_url: Ollama API URL (defaults to env var or localhost:11434)
            embedding_model: Embedding model name (defaults to env var or nomic-embed-text:v1.5)
            keep_alive: Model keep-alive duration (defaults to env var or 10m)
            auto_setup_ollama: Whether to automatically check and setup Ollama
        """
        # Initialize Ollama embeddings if available
        self.ollama_embeddings = None
        if auto_setup_ollama:
            self.ollama_embeddings = self._setup_ollama_embeddings(
                ollama_url, embedding_model, keep_alive
            )

        # Initialize the core memory API
        self.memory_api = PostgresMemoryAPI(ollama_embeddings=self.ollama_embeddings)

        # Initialize document ingestion manager
        self.ingestion_manager = DocumentIngestionManager(
            self.memory_api, domain="documents"
        )

    def _setup_ollama_embeddings(
        self,
        ollama_url: Optional[str] = None,
        embedding_model: Optional[str] = None,
        keep_alive: Optional[str] = None,
    ) -> Optional[OllamaEmbeddings]:
        """Setup Ollama embeddings if available."""
        ollama_url = ollama_url or os.getenv("OLLAMA_API_URL", "http://localhost:11434")
        embedding_model = embedding_model or os.getenv(
            "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:v1.5"
        )
        keep_alive = keep_alive or os.getenv("OLLAMA_KEEP_ALIVE", "10m")

        try:
            import requests

            response = requests.get(f"{ollama_url}/api/tags", timeout=2)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [model.get("name", "") for model in models]
                if embedding_model in model_names:
                    return OllamaEmbeddings(
                        model_name=embedding_model,
                        base_url=ollama_url,
                        keep_alive=keep_alive,
                    )
                else:
                    print(
                        f"⚠️ Embedding model {embedding_model} not found, using text search"
                    )
            else:
                print("⚠️ Ollama not available, using text search")
        except Exception as e:
            print(f"⚠️ Ollama check failed: {e}, using text search")

        return None

    def store(
        self,
        content: str,
        domain: Optional[str] = None,
        source: Optional[str] = None,
        importance: Optional[float] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Store a new memory.

        Args:
            content: The text content to remember
            domain: Memory domain (defaults to 'default')
            source: Source of the memory (e.g., 'conversation', 'document')
            importance: Importance score 0.0-1.0
            tags: List of tags for categorization
            metadata: Additional metadata dictionary

        Returns:
            str: Memory ID
        """
        # Build metadata
        mem_metadata = metadata or {}
        if source:
            mem_metadata["source"] = source
        if importance is not None:
            mem_metadata["importance"] = importance
        if tags:
            mem_metadata["tags"] = tags

        return self.memory_api.store_memory(content, mem_metadata, domain)

    def search(
        self, query: str, domain: Optional[str] = None, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for memories.

        Args:
            query: Search query
            domain: Domain to search in (defaults to 'default')
            limit: Maximum number of results

        Returns:
            List of memory dictionaries
        """
        return self.memory_api.retrieve_memories(query, limit, domain)

    def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        domain: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Update an existing memory.

        Args:
            memory_id: ID of memory to update
            content: New content (optional)
            importance: New importance score (optional)
            domain: Memory domain
            metadata: Additional metadata to merge

        Returns:
            bool: True if successful
        """
        return self.memory_api.update_memory(memory_id, content, metadata, domain)

    def delete(self, memory_id: str, domain: Optional[str] = None) -> bool:
        """
        Delete a memory.

        Args:
            memory_id: ID of memory to delete
            domain: Memory domain

        Returns:
            bool: True if successful
        """
        # Note: This would need to be implemented in PostgresMemoryAPI
        # For now, we'll raise NotImplementedError
        raise NotImplementedError(
            "Delete functionality not yet implemented in PostgresMemoryAPI"
        )

    def list_domains(self) -> List[str]:
        """
        List all available memory domains.

        Returns:
            List of domain names
        """
        return self.memory_api.list_domains()

    def ingest_document(
        self,
        file_path: Union[str, Path],
        domain: Optional[str] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> Dict[str, Any]:
        """
        Ingest a document into the memory system.

        Args:
            file_path: Path to document file
            domain: Target domain (defaults to 'documents')
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks

        Returns:
            Dictionary with ingestion results
        """
        # Set domain-specific ingestion manager
        ingestion_manager = DocumentIngestionManager(
            self.memory_api, domain or "documents"
        )

        # Run ingestion
        result = asyncio.run(
            ingestion_manager.ingest_document(
                Path(file_path), chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
        )

        return {
            "success": result.success,
            "chunks_stored": result.chunks_stored,
            "chunks_processed": result.chunks_processed,
            "processing_time": result.processing_time,
            "domain": domain or "documents",
        }

    def ingest_text(
        self, content: str, source_name: str, domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ingest raw text content into the memory system.

        Args:
            content: Text content to ingest
            source_name: Name/source identifier
            domain: Target domain (defaults to 'documents')

        Returns:
            Dictionary with ingestion results
        """
        # Set domain-specific ingestion manager
        ingestion_manager = DocumentIngestionManager(
            self.memory_api, domain or "documents"
        )

        # Run ingestion
        result = asyncio.run(
            ingestion_manager.ingest_text_content(content, source_name)
        )

        return {
            "success": result.success,
            "chunks_stored": result.chunks_stored,
            "chunks_processed": result.chunks_processed,
            "processing_time": result.processing_time,
            "domain": domain or "documents",
        }

    def get_memory(
        self, memory_id: str, domain: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific memory by ID.

        Args:
            memory_id: Memory ID
            domain: Memory domain

        Returns:
            Memory dictionary or None if not found
        """
        # This would need to be implemented in PostgresMemoryAPI
        # For now, we'll search for it (inefficient but functional)
        results = self.search("", domain=domain, limit=1000)
        for memory in results:
            if memory.get("id") == memory_id:
                return memory
        return None

    def get_stats(self) -> Dict[str, Any]:
        """
        Get system statistics.

        Returns:
            Dictionary with system stats
        """
        domains = self.list_domains()
        stats = {
            "domains": domains,
            "total_domains": len(domains),
            "ollama_available": self.ollama_embeddings is not None,
            "embedding_model": None,
        }

        if self.ollama_embeddings:
            stats["embedding_model"] = getattr(
                self.ollama_embeddings, "model_name", "unknown"
            )

        return stats


class AsyncMemorySystem:
    """
    Async version of MemorySystem for modern Python applications.

    This class provides async/await support for all memory operations,
    making it suitable for async applications and better performance.
    """

    def __init__(
        self,
        ollama_url: Optional[str] = None,
        embedding_model: Optional[str] = None,
        keep_alive: Optional[str] = None,
        auto_setup_ollama: bool = True,
    ):
        """Initialize the Async Memory System."""
        # Initialize Ollama embeddings if available
        self.ollama_embeddings = None
        if auto_setup_ollama:
            self.ollama_embeddings = self._setup_ollama_embeddings(
                ollama_url, embedding_model, keep_alive
            )

        # Initialize the core memory API
        self.memory_api = PostgresMemoryAPI(ollama_embeddings=self.ollama_embeddings)

        # Initialize document ingestion manager
        self.ingestion_manager = DocumentIngestionManager(
            self.memory_api, domain="documents"
        )

    def _setup_ollama_embeddings(
        self,
        ollama_url: Optional[str] = None,
        embedding_model: Optional[str] = None,
        keep_alive: Optional[str] = None,
    ) -> Optional[OllamaEmbeddings]:
        """Setup Ollama embeddings if available."""
        ollama_url = ollama_url or os.getenv("OLLAMA_API_URL", "http://localhost:11434")
        embedding_model = embedding_model or os.getenv(
            "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:v1.5"
        )
        keep_alive = keep_alive or os.getenv("OLLAMA_KEEP_ALIVE", "10m")

        try:
            import requests

            response = requests.get(f"{ollama_url}/api/tags", timeout=2)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [model.get("name", "") for model in models]
                if embedding_model in model_names:
                    return OllamaEmbeddings(
                        model_name=embedding_model,
                        base_url=ollama_url,
                        keep_alive=keep_alive,
                    )
                else:
                    print(
                        f"⚠️ Embedding model {embedding_model} not found, using text search"
                    )
            else:
                print("⚠️ Ollama not available, using text search")
        except Exception as e:
            print(f"⚠️ Ollama check failed: {e}, using text search")

        return None

    async def store(
        self,
        content: str,
        domain: Optional[str] = None,
        source: Optional[str] = None,
        importance: Optional[float] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Async version of store."""
        # Build metadata
        mem_metadata = metadata or {}
        if source:
            mem_metadata["source"] = source
        if importance is not None:
            mem_metadata["importance"] = importance
        if tags:
            mem_metadata["tags"] = tags

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.memory_api.store_memory, content, mem_metadata, domain
        )

    async def search(
        self, query: str, domain: Optional[str] = None, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Async version of search."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.memory_api.retrieve_memories, query, limit, domain
        )

    async def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        domain: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Async version of update."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.memory_api.update_memory, memory_id, content, metadata, domain
        )

    async def list_domains(self) -> List[str]:
        """Async version of list_domains."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.memory_api.list_domains)

    async def ingest_document(
        self,
        file_path: Union[str, Path],
        domain: Optional[str] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> Dict[str, Any]:
        """Async version of ingest_document."""
        # Set domain-specific ingestion manager
        ingestion_manager = DocumentIngestionManager(
            self.memory_api, domain or "documents"
        )

        # Run ingestion (already async)
        result = await ingestion_manager.ingest_document(
            Path(file_path), chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

        return {
            "success": result.success,
            "chunks_stored": result.chunks_stored,
            "chunks_processed": result.chunks_processed,
            "processing_time": result.processing_time,
            "domain": domain or "documents",
        }

    async def ingest_text(
        self, content: str, source_name: str, domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """Async version of ingest_text."""
        # Set domain-specific ingestion manager
        ingestion_manager = DocumentIngestionManager(
            self.memory_api, domain or "documents"
        )

        # Run ingestion (already async)
        result = await ingestion_manager.ingest_text_content(content, source_name)

        return {
            "success": result.success,
            "chunks_stored": result.chunks_stored,
            "chunks_processed": result.chunks_processed,
            "processing_time": result.processing_time,
            "domain": domain or "documents",
        }

    async def get_stats(self) -> Dict[str, Any]:
        """Async version of get_stats."""
        domains = await self.list_domains()
        stats = {
            "domains": domains,
            "total_domains": len(domains),
            "ollama_available": self.ollama_embeddings is not None,
            "embedding_model": None,
        }

        if self.ollama_embeddings:
            stats["embedding_model"] = getattr(
                self.ollama_embeddings, "model_name", "unknown"
            )

        return stats


# Convenience functions for quick usage
def quick_store(content: str, domain: str = "default", **kwargs) -> str:
    """Quick function to store a memory."""
    memory = MemorySystem()
    return memory.store(content, domain, **kwargs)


def quick_search(
    query: str, domain: str = "default", limit: int = 5
) -> List[Dict[str, Any]]:
    """Quick function to search memories."""
    memory = MemorySystem()
    return memory.search(query, domain, limit)


def quick_ingest(
    file_path: Union[str, Path], domain: str = "documents"
) -> Dict[str, Any]:
    """Quick function to ingest a document."""
    memory = MemorySystem()
    return memory.ingest_document(file_path, domain)


# Async convenience functions
async def async_quick_store(content: str, domain: str = "default", **kwargs) -> str:
    """Quick async function to store a memory."""
    memory = AsyncMemorySystem()
    return await memory.store(content, domain, **kwargs)


async def async_quick_search(
    query: str, domain: str = "default", limit: int = 5
) -> List[Dict[str, Any]]:
    """Quick async function to search memories."""
    memory = AsyncMemorySystem()
    return await memory.search(query, domain, limit)


async def async_quick_ingest(
    file_path: Union[str, Path], domain: str = "documents"
) -> Dict[str, Any]:
    """Quick async function to ingest a document."""
    memory = AsyncMemorySystem()
    return await memory.ingest_document(file_path, domain)


# Example usage
if __name__ == "__main__":

    async def async_example():
        """Example of async usage."""
        print("\n🚀 Async Example:")
        print("-" * 30)

        # Initialize async memory system
        memory = AsyncMemorySystem()

        # Store memories asynchronously
        mem1 = await memory.store(
            "User loves async programming", "personal", importance=0.9
        )
        mem2 = await memory.store(
            "Async operations are faster", "technical", source="learning"
        )
        print(f"Async stored memories: {mem1}, {mem2}")

        # Search asynchronously
        results = await memory.search("async programming", limit=2)
        for i, result in enumerate(results, 1):
            print(
                f"{i}. {result['content'][:40]}... (score: {result.get('score', 0):.3f})"
            )

        # Get stats asynchronously
        stats = await memory.get_stats()
        print(f"Async stats: {stats}")

    def sync_example():
        """Example of sync usage."""
        print("🧠 Local Memory MCP - Python API Example")
        print("=" * 50)

        # Initialize memory system
        memory = MemorySystem()

        # Store some memories
        print("\n📝 Storing memories...")
        mem1 = memory.store(
            "User prefers Python for data analysis", "personal", importance=0.8
        )
        mem2 = memory.store(
            "Meeting scheduled for Tuesday at 3pm", "work", source="calendar"
        )
        print(f"Stored memories: {mem1}, {mem2}")

        # Search memories
        print("\n🔍 Searching memories...")
        results = memory.search("python programming", limit=3)
        for i, result in enumerate(results, 1):
            print(
                f"{i}. {result['content'][:50]}... (score: {result.get('score', 0):.3f})"
            )

        # List domains
        print(f"\n📂 Available domains: {memory.list_domains()}")

        # Get stats
        stats = memory.get_stats()
        print(f"\n📊 System stats: {stats}")

    # Run sync example
    sync_example()

    # Run async example
    asyncio.run(async_example())

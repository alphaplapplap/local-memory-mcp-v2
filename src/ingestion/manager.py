#!/usr/bin/env python3
"""
Document Ingestion Manager for PostgreSQL Memory System
Integrates with postgres_memory_api.py for storing document chunks
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime

from .base import DocumentLoader, DocumentChunk, IngestionResult
from .chunker import TextChunker, ChunkingStrategy
from .registry import get_loader_for_file, is_supported_file

# Import your existing memory API
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from postgres_memory_api import PostgresMemoryAPI
from ollama_embeddings import OllamaEmbeddings

logger = logging.getLogger(__name__)


class DocumentIngestionManager:
    """
    Manages document ingestion into the PostgreSQL memory system.

    Features:
    - Automatic format detection
    - Intelligent chunking
    - Batch processing
    - Progress tracking
    - Error handling and recovery
    """

    def __init__(self, memory_api: PostgresMemoryAPI, domain: str = "documents"):
        """
        Initialize document ingestion manager.

        Args:
            memory_api: PostgreSQL memory API instance
            domain: Memory domain to store documents in
        """
        self.memory_api = memory_api
        self.domain = domain
        self.chunker = TextChunker(ChunkingStrategy(
            chunk_size=1000,
            chunk_overlap=200,
            respect_paragraph_boundaries=True,
            respect_sentence_boundaries=True
        ))

    async def ingest_document(
        self,
        file_path: Path,
        **kwargs
    ) -> IngestionResult:
        """
        Ingest a single document into the memory system.

        Args:
            file_path: Path to the document to ingest
            **kwargs: Additional options:
                - chunk_size: Override default chunk size
                - chunk_overlap: Override default chunk overlap
                - preserve_structure: Whether to preserve document structure
                - extract_links: Whether to extract links (for Markdown)
                - encoding: Text encoding to use

        Returns:
            IngestionResult with processing statistics
        """
        start_time = time.time()
        errors = []
        chunks_processed = 0
        chunks_stored = 0

        try:
            # Validate file
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            if not is_supported_file(file_path):
                raise ValueError(f"Unsupported file format: {file_path.suffix}")

            # Get appropriate loader
            loader = get_loader_for_file(file_path)
            if not loader:
                raise ValueError(f"No loader available for: {file_path}")

            logger.info(f"Starting ingestion of {file_path}")

            # Process document chunks
            async for chunk in loader.extract_chunks(file_path, **kwargs):
                chunks_processed += 1

                try:
                    # Store chunk in memory system
                    memory_id = self.memory_api.store_memory(
                        content=chunk.content,
                        metadata=chunk.metadata,
                        domain=self.domain
                    )
                    chunks_stored += 1

                    logger.debug(f"Stored chunk {chunks_processed} as memory {memory_id}")

                except Exception as e:
                    error_msg = f"Failed to store chunk {chunks_processed}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            processing_time = time.time() - start_time
            success = len(errors) == 0 and chunks_stored > 0

            result = IngestionResult(
                success=success,
                chunks_processed=chunks_processed,
                chunks_stored=chunks_stored,
                errors=errors,
                source_file=file_path,
                processing_time=processing_time
            )

            logger.info(f"Ingestion completed: {chunks_stored}/{chunks_processed} chunks stored in {processing_time:.2f}s")
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Document ingestion failed: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)

            return IngestionResult(
                success=False,
                chunks_processed=chunks_processed,
                chunks_stored=chunks_stored,
                errors=errors,
                source_file=file_path,
                processing_time=processing_time
            )

    async def ingest_directory(
        self,
        directory_path: Path,
        recursive: bool = True,
        **kwargs
    ) -> List[IngestionResult]:
        """
        Ingest all supported documents in a directory.

        Args:
            directory_path: Path to directory containing documents
            recursive: Whether to process subdirectories
            **kwargs: Additional options passed to ingest_document

        Returns:
            List of IngestionResult objects for each processed file
        """
        if not directory_path.exists() or not directory_path.is_dir():
            raise ValueError(f"Directory not found: {directory_path}")

        # Find all supported files
        pattern = "**/*" if recursive else "*"
        all_files = list(directory_path.glob(pattern))
        supported_files = [f for f in all_files if f.is_file() and is_supported_file(f)]

        logger.info(f"Found {len(supported_files)} supported files in {directory_path}")

        # Process files
        results = []
        for file_path in supported_files:
            try:
                result = await self.ingest_document(file_path, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {str(e)}")
                results.append(IngestionResult(
                    success=False,
                    chunks_processed=0,
                    chunks_stored=0,
                    errors=[str(e)],
                    source_file=file_path,
                    processing_time=0.0
                ))

        return results

    async def ingest_text_content(
        self,
        content: str,
        source_name: str,
        **kwargs
    ) -> IngestionResult:
        """
        Ingest raw text content directly.

        Args:
            content: Text content to ingest
            source_name: Name/source identifier for the content
            **kwargs: Additional options

        Returns:
            IngestionResult with processing statistics
        """
        start_time = time.time()
        errors = []
        chunks_processed = 0
        chunks_stored = 0

        try:
            # Create metadata
            metadata = {
                'source': source_name,
                'content_type': 'raw_text',
                'total_characters': len(content),
                'ingested_at': datetime.now().isoformat()
            }

            # Chunk the content
            chunks = self.chunker.chunk_text(content, metadata)

            for i, (chunk_text, chunk_metadata) in enumerate(chunks):
                chunks_processed += 1

                try:
                    # Store chunk in memory system
                    memory_id = self.memory_api.store_memory(
                        content=chunk_text,
                        metadata=chunk_metadata,
                        domain=self.domain
                    )
                    chunks_stored += 1

                except Exception as e:
                    error_msg = f"Failed to store chunk {chunks_processed}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            processing_time = time.time() - start_time
            success = len(errors) == 0 and chunks_stored > 0

            return IngestionResult(
                success=success,
                chunks_processed=chunks_processed,
                chunks_stored=chunks_stored,
                errors=errors,
                source_file=Path(source_name),
                processing_time=processing_time
            )

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Text ingestion failed: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)

            return IngestionResult(
                success=False,
                chunks_processed=chunks_processed,
                chunks_stored=chunks_stored,
                errors=errors,
                source_file=Path(source_name),
                processing_time=processing_time
            )
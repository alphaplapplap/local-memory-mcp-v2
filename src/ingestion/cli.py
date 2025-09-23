#!/usr/bin/env python3
"""
Command-line interface for document ingestion
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.ingestion.manager import DocumentIngestionManager
from src.ingestion.registry import get_supported_extensions
from src.ollama_embeddings import OllamaEmbeddings
from src.postgres_memory_api import PostgresMemoryAPI

logger = logging.getLogger(__name__)


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Ingest documents into PostgreSQL memory system"
    )
    parser.add_argument("path", help="File or directory path to ingest")
    parser.add_argument(
        "--domain", default="documents", help="Memory domain to store in"
    )
    parser.add_argument(
        "--recursive", action="store_true", help="Process directories recursively"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=1000, help="Chunk size in characters"
    )
    parser.add_argument(
        "--chunk-overlap", type=int, default=200, help="Chunk overlap in characters"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Set up logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s")

    # Initialize memory API
    try:
        ollama_embeddings = OllamaEmbeddings()
        memory_api = PostgresMemoryAPI(ollama_embeddings=ollama_embeddings)
        ingestion_manager = DocumentIngestionManager(memory_api, domain=args.domain)

        logger.info(f"Initialized ingestion manager for domain: {args.domain}")

    except Exception as e:
        logger.error(f"Failed to initialize memory API: {e}")
        return 1

    # Process path
    path = Path(args.path)

    if path.is_file():
        # Single file
        logger.info(f"Ingesting file: {path}")
        result = await ingestion_manager.ingest_document(
            path, chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap
        )

        print(f"\n📄 File Ingestion Results:")
        print(f"   File: {result.source_file}")
        print(f"   Success: {result.success}")
        print(f"   Chunks: {result.chunks_stored}/{result.chunks_processed}")
        print(f"   Time: {result.processing_time:.2f}s")
        print(f"   Success Rate: {result.success_rate:.1f}%")

        if result.errors:
            print(f"   Errors: {len(result.errors)}")
            for error in result.errors:
                print(f"     - {error}")

    elif path.is_dir():
        # Directory
        logger.info(f"Ingesting directory: {path}")
        results = await ingestion_manager.ingest_directory(
            path,
            recursive=args.recursive,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )

        # Summary
        total_files = len(results)
        successful_files = sum(1 for r in results if r.success)
        total_chunks = sum(r.chunks_stored for r in results)
        total_time = sum(r.processing_time for r in results)

        print(f"\n📁 Directory Ingestion Results:")
        print(f"   Files: {successful_files}/{total_files} successful")
        print(f"   Total Chunks: {total_chunks}")
        print(f"   Total Time: {total_time:.2f}s")

        # Show failed files
        failed_files = [r for r in results if not r.success]
        if failed_files:
            print(f"   Failed Files: {len(failed_files)}")
            for result in failed_files:
                print(
                    f"     - {result.source_file}: {result.errors[0] if result.errors else 'Unknown error'}"
                )

    else:
        logger.error(f"Path not found: {path}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

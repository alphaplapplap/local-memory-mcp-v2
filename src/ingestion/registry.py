#!/usr/bin/env python3
"""
Document loader registry for the ingestion system.
"""

from pathlib import Path
from typing import Dict, Optional, Type

from .base import DocumentLoader

# Registry of file extensions to loader classes
_LOADER_REGISTRY: Dict[str, Type[DocumentLoader]] = {}


def register_loader(file_extension: str, loader_class: Type[DocumentLoader]) -> None:
    """
    Register a document loader for a specific file extension.

    Args:
        file_extension: File extension (e.g., '.txt', '.pdf')
        loader_class: DocumentLoader subclass
    """
    _LOADER_REGISTRY[file_extension.lower()] = loader_class


def get_loader_for_file(file_path: Path) -> Optional[Type[DocumentLoader]]:
    """
    Get the appropriate loader class for a file.

    Args:
        file_path: Path to the file

    Returns:
        DocumentLoader class or None if no loader found
    """
    extension = file_path.suffix.lower()
    return _LOADER_REGISTRY.get(extension)


def is_supported_file(file_path: Path) -> bool:
    """
    Check if a file type is supported.

    Args:
        file_path: Path to the file

    Returns:
        True if file type is supported
    """
    return get_loader_for_file(file_path) is not None


def get_supported_extensions() -> list[str]:
    """
    Get list of supported file extensions.

    Returns:
        List of supported file extensions
    """
    return list(_LOADER_REGISTRY.keys())


# Register default loaders
def _register_default_loaders():
    """Register default document loaders."""
    try:
        from .loaders import MarkdownLoader, TextLoader

        # Register text-based loaders
        register_loader(".txt", TextLoader)
        register_loader(".md", MarkdownLoader)
        register_loader(".markdown", MarkdownLoader)

        # Try to register PDF loader if available
        try:
            from .loaders import PDFLoader

            register_loader(".pdf", PDFLoader)
        except ImportError:
            pass  # PDF loader not available

        # Try to register other loaders if available
        try:
            from .loaders import DOCXLoader

            register_loader(".docx", DOCXLoader)
        except ImportError:
            pass  # DOCX loader not available

    except ImportError:
        # Fallback: create a simple text loader
        from .base import DocumentLoader

        class SimpleTextLoader(DocumentLoader):
            """Simple text file loader."""

            def load_document(self, file_path: Path) -> str:
                """Load text content from file."""
                return file_path.read_text(encoding="utf-8")

        register_loader(".txt", SimpleTextLoader)


# Initialize default loaders
_register_default_loaders()

#!/usr/bin/env python3
"""
Document loaders for various file formats.
"""

from pathlib import Path
from typing import List, Dict, Any
from .base import DocumentLoader


class TextLoader(DocumentLoader):
    """Loader for plain text files."""
    
    def load_document(self, file_path: Path) -> str:
        """Load text content from file."""
        try:
            return file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            # Try with different encodings
            for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    return file_path.read_text(encoding=encoding)
                except UnicodeDecodeError:
                    continue
            raise ValueError(f"Could not decode file {file_path} with any supported encoding")


class MarkdownLoader(DocumentLoader):
    """Loader for Markdown files."""
    
    def load_document(self, file_path: Path) -> str:
        """Load Markdown content from file."""
        return file_path.read_text(encoding='utf-8')


# Optional loaders that require additional dependencies
try:
    import PyPDF2
    
    class PDFLoader(DocumentLoader):
        """Loader for PDF files using PyPDF2."""
        
        def load_document(self, file_path: Path) -> str:
            """Extract text from PDF file."""
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text

except ImportError:
    # PyPDF2 not available
    pass


try:
    from docx import Document
    
    class DOCXLoader(DocumentLoader):
        """Loader for DOCX files using python-docx."""
        
        def load_document(self, file_path: Path) -> str:
            """Extract text from DOCX file."""
            doc = Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text

except ImportError:
    # python-docx not available
    pass

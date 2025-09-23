#!/usr/bin/env python3
"""
Development server with hot reloading support
Automatically restarts when source files change
"""

import os
import sys
import uvicorn
from pathlib import Path

# Add src to path
sys.path.insert(0, 'src')

def main():
    """Start the development server with hot reloading"""
    
    # Set environment variables for development
    os.environ.setdefault('POSTGRES_DB', 'memory_db')
    os.environ.setdefault('POSTGRES_USER', 'postgres')
    os.environ.setdefault('POSTGRES_PASSWORD', 'postgres')
    os.environ.setdefault('POSTGRES_HOST', 'localhost')
    os.environ.setdefault('POSTGRES_PORT', '5432')
    os.environ.setdefault('OLLAMA_API_URL', 'http://localhost:11434')
    os.environ.setdefault('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text:v1.5')
    os.environ.setdefault('LOG_LEVEL', 'DEBUG')
    
    # Development-specific settings
    os.environ.setdefault('ENVIRONMENT', 'development')
    os.environ.setdefault('DEBUG', 'true')
    
    print("🚀 Starting Memory System Development Server")
    print("📁 Working directory:", os.getcwd())
    print("🔄 Hot reloading: ENABLED")
    print("🌐 Server will be available at: http://localhost:8000")
    print("📊 API docs will be available at: http://localhost:8000/docs")
    print("=" * 60)
    
    # Configure uvicorn for development
    config = uvicorn.Config(
        "bridge_server:app",  # Import the FastAPI app
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable hot reloading
        reload_dirs=["src", "."],  # Watch these directories for changes
        reload_excludes=["*.pyc", "__pycache__", "*.log", "logs/*", "venv/*", ".git/*"],
        log_level="info",
        access_log=True,
        use_colors=True,
        reload_delay=0.5,  # Small delay to avoid rapid restarts
    )
    
    # Start the server
    server = uvicorn.Server(config)
    server.run()

if __name__ == "__main__":
    main()

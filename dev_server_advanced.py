#!/usr/bin/env python3
"""
Advanced Development Server with Enhanced Hot Reloading
Includes file watching, better logging, and development utilities
"""

import os
import sys
import uvicorn
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add src to path
sys.path.insert(0, 'src')

class DevFileHandler(FileSystemEventHandler):
    """Custom file handler for development server"""
    
    def __init__(self):
        self.last_reload = 0
        self.reload_delay = 1.0  # Minimum delay between reloads
    
    def on_modified(self, event):
        if event.is_directory:
            return
            
        # Only watch Python files
        if not event.src_path.endswith('.py'):
            return
            
        # Avoid rapid reloads
        current_time = time.time()
        if current_time - self.last_reload < self.reload_delay:
            return
            
        self.last_reload = current_time
        print(f"🔄 File changed: {event.src_path}")
        print("   Server will reload automatically...")

def setup_development_environment():
    """Set up development environment variables"""
    
    # Database configuration
    os.environ.setdefault('POSTGRES_DB', 'memory_db')
    os.environ.setdefault('POSTGRES_USER', 'postgres')
    os.environ.setdefault('POSTGRES_PASSWORD', 'postgres')
    os.environ.setdefault('POSTGRES_HOST', 'localhost')
    os.environ.setdefault('POSTGRES_PORT', '5432')
    
    # Ollama configuration
    os.environ.setdefault('OLLAMA_API_URL', 'http://localhost:11434')
    os.environ.setdefault('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text:v1.5')
    
    # Development settings
    os.environ.setdefault('ENVIRONMENT', 'development')
    os.environ.setdefault('DEBUG', 'true')
    os.environ.setdefault('LOG_LEVEL', 'DEBUG')
    
    # Performance settings for development
    os.environ.setdefault('DB_MIN_CONNECTIONS', '1')
    os.environ.setdefault('DB_MAX_CONNECTIONS', '5')
    os.environ.setdefault('ENABLE_QUERY_CACHING', 'false')  # Disable caching in dev

def print_development_info():
    """Print development server information"""
    
    print("🚀 Memory System Development Server (Advanced)")
    print("=" * 60)
    print(f"📁 Working directory: {os.getcwd()}")
    print(f"🐍 Python version: {sys.version.split()[0]}")
    print(f"🔄 Hot reloading: ENABLED")
    print(f"👀 File watching: ENABLED")
    print(f"🌐 Server URL: http://localhost:8000")
    print(f"📊 API Documentation: http://localhost:8000/docs")
    print(f"🔍 Health Check: http://localhost:8000/api/health")
    print(f"📋 Project Domain: http://localhost:8000/api/project/domain")
    print("=" * 60)
    print("💡 Development Tips:")
    print("   • Edit Python files in src/ to see changes instantly")
    print("   • Check logs for detailed debugging information")
    print("   • Use Ctrl+C to stop the server")
    print("   • API changes will be reflected immediately")
    print("=" * 60)

def main():
    """Start the advanced development server"""
    
    # Set up development environment
    setup_development_environment()
    
    # Print development information
    print_development_info()
    
    # Set up file watching
    event_handler = DevFileHandler()
    observer = Observer()
    
    # Watch relevant directories
    watch_dirs = ['src', '.']
    for watch_dir in watch_dirs:
        if os.path.exists(watch_dir):
            observer.schedule(event_handler, watch_dir, recursive=True)
            print(f"👀 Watching directory: {watch_dir}")
    
    # Start file observer
    observer.start()
    print("✅ File watcher started")
    
    try:
        # Configure uvicorn for development
        config = uvicorn.Config(
            "bridge_server:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            reload_dirs=["src", "."],
            reload_excludes=[
                "*.pyc", "__pycache__", "*.log", "logs/*", 
                "venv/*", ".git/*", "*.tmp", "*.swp"
            ],
            log_level="info",
            access_log=True,
            use_colors=True,
            reload_delay=0.5,
            # Development-specific settings
            workers=1,  # Single worker for development
            loop="asyncio",
        )
        
        # Start the server
        server = uvicorn.Server(config)
        print("🚀 Starting server...")
        server.run()
        
    except KeyboardInterrupt:
        print("\n🛑 Shutting down development server...")
    finally:
        observer.stop()
        observer.join()
        print("✅ Development server stopped")

if __name__ == "__main__":
    main()

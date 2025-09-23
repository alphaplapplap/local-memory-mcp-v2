#!/usr/bin/env python3
"""
Memory Server Daemon
Runs the memory server as a background daemon process
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path

# Add src to path for other modules
sys.path.insert(0, 'src')

def setup_logging():
    """Set up logging for daemon"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # Only log to file for daemon mode - no console output
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/memory-daemon.log')
        ]
    )
    return logging.getLogger(__name__)

def setup_environment():
    """Set up environment variables"""
    os.environ.setdefault('POSTGRES_DB', 'memory_db')
    os.environ.setdefault('POSTGRES_USER', 'postgres')
    os.environ.setdefault('POSTGRES_PASSWORD', 'postgres')
    os.environ.setdefault('POSTGRES_HOST', 'localhost')
    os.environ.setdefault('POSTGRES_PORT', '5432')
    os.environ.setdefault('OLLAMA_API_URL', 'http://localhost:11434')
    os.environ.setdefault('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text:v1.5')
    os.environ.setdefault('ENVIRONMENT', 'production')
    os.environ.setdefault('LOG_LEVEL', 'INFO')

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)

def main():
    """Main daemon function"""
    logger = setup_logging()
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("🚀 Memory Server Daemon starting...")
    
    # Set up environment
    setup_environment()
    
    # Write PID file
    with open('memory-daemon.pid', 'w') as f:
        f.write(str(os.getpid()))
    
    logger.info(f"📋 Daemon PID: {os.getpid()}")
    logger.info("🌐 Starting memory server...")
    
    try:
        # Import and start the server
        import uvicorn
        from bridge_server import app
        
        # Configure uvicorn for daemon mode
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="warning",  # Reduce verbosity
            access_log=False,     # Disable access logs to console
            use_colors=False,     # Disable colors for daemon
            log_config=None       # Disable default logging to console
        )
        
        server = uvicorn.Server(config)
        server.run()
        
    except Exception as e:
        logger.error(f"❌ Daemon error: {e}")
        sys.exit(1)
    finally:
        # Clean up PID file
        try:
            os.remove('memory-daemon.pid')
        except:
            pass
        logger.info("👋 Memory Server Daemon stopped")

if __name__ == "__main__":
    main()

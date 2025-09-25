# Local Memory MCP Server - Project Setup Guide

## Overview

This is a Model Context Protocol (MCP) server that provides intelligent memory management for Claude Code (and Claude Desktop), featuring semantic search, session continuity, and context-aware memory retrieval.

## Prerequisites

### 1. PostgreSQL with pgvector Extension

```bash
# macOS (using Homebrew)
brew install postgresql@17
brew services start postgresql@17

# Install pgvector extension
brew install pgvector

# Connect to PostgreSQL and enable pgvector
psql -U postgres -d postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. Ollama for Embeddings

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
ollama serve

# Pull the required embedding model
ollama pull nomic-embed-text:v1.5

# Verify model is available
ollama list
```

### 3. Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate     # On Windows

# Install dependencies
pip install -r requirements.txt
```

## Configuration

### 1. Environment Variables

Copy the example environment file and configure:

```bash
cp .env.example .env
```

Edit `.env` with your settings:
```bash
# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres  # Change in production!

# Ollama Configuration
OLLAMA_API_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text:v1.5
```

### 2. Database Setup

Initialize the database schema:

```bash
# The server will auto-create tables on first run
python3 src/postgres_memory_server.py mcp

# Or manually create tables
psql -U postgres -d postgres < schema/init.sql  # If schema file exists
```

### 3. Hook Configuration (for Claude Code)

The memory system integrates with Claude Code through hooks. Configure them:

```bash
# Copy hook configuration
cp hooks/config.json ~/.claude/hooks/config.json

# Symlink or copy the hook files
cp -r hooks/* ~/.claude/hooks/
```

Edit `~/.claude/hooks/config.json` to point to your local server:

```json
{
  "memoryService": {
    "endpoint": "http://localhost:8000",
    "apiKey": "test-key-123"
  }
}
```

## Running the Server

### Standalone MCP Mode (for Claude Code)

```bash
# Activate virtual environment
source venv/bin/activate

# Run MCP server
python3 src/postgres_memory_server.py mcp
```

### HTTP API Mode (for testing)

```bash
# Run HTTP server
python3 src/postgres_memory_server.py http
```

### Dual Protocol Mode

```bash
# Run both MCP and HTTP
python3 src/postgres_memory_server.py dual
```

### Using the Startup Script

```bash
# Make script executable
chmod +x start_memory_services.sh

# Run all services
./start_memory_services.sh
```

## Claude Code Integration

### 1. Add to Claude Code Settings

Edit `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "local-memory": {
      "command": "python3",
      "args": [
        "/path/to/local-memory-mcp/src/postgres_memory_server.py",
        "mcp"
      ],
      "env": {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "postgres",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",
        "OLLAMA_API_URL": "http://localhost:11434",
        "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text:v1.5"
      }
    }
  }
}
```

### 2. Verify Integration

Start a new Claude Code session and you should see:
```
🧠 Memory Hook → Initializing session awareness...
📂 Project Detector → Analyzing [your-project]
💾 Storage → 💾 Local MCP Service (http://localhost:8000)
```

## Testing

### Run Tests

```bash
# Unit tests
pytest tests/

# Integration tests
pytest tests/integration/

# Performance tests
python3 /tmp/memory-performance-tester.py

# Stress tests
python3 /tmp/comprehensive-memory-stress-test.py
```

### Manual Testing

Test memory storage and retrieval:

```bash
# Store a memory
curl -X POST http://localhost:8000/api/store \
  -H "Content-Type: application/json" \
  -d '{"content": "Test memory", "domain": "test"}'

# Search memories
curl "http://localhost:8000/api/search?query=test&domain=test"
```

## Troubleshooting

### Common Issues

1. **PostgreSQL Connection Error**
   - Ensure PostgreSQL is running: `brew services list`
   - Check credentials in `.env`
   - Verify database exists: `psql -U postgres -l`

2. **Ollama Embedding Errors**
   - Check Ollama is running: `ps aux | grep ollama`
   - Verify model installed: `ollama list`
   - Test embeddings: `curl http://localhost:11434/api/embeddings -d '{"model":"nomic-embed-text:v1.5","prompt":"test"}'`

3. **MCP Protocol Errors**
   - Check for print statements breaking JSON protocol
   - Verify FastMCP version: `pip show fastmcp`
   - Check server logs in stderr

4. **Memory Not Loading in Claude Code**
   - Verify hook configuration in `~/.claude/hooks/`
   - Check hook execution logs
   - Ensure server is accessible at configured endpoint

### Debug Mode

Enable debug logging:

```bash
# Set in environment
export DEBUG=true
export LOG_LEVEL=debug

# Or in .env
DEBUG=true
LOG_LEVEL=debug
```

## Performance Tuning

### Memory Limits (Optimized for Context Efficiency)

Edit `src/postgres_memory_server.py`:
```python
MAX_CONTENT_SIZE = 5_000  # Characters per memory
MAX_METADATA_SIZE = 2_048  # Metadata JSON size
```

### Retrieval Tuning

Edit `hooks/config.json`:
```json
{
  "memoryService": {
    "maxMemoriesPerSession": 8,  # Total memories loaded
    "recentMemoryRatio": 0.6,    # Ratio of recent vs important
    "minScore": 0.3              # Minimum relevance score
  }
}
```

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│           Claude Code / Desktop             │
├─────────────────────────────────────────────┤
│              MCP Protocol                   │
├─────────────────────────────────────────────┤
│         FastMCP Server Framework            │
├─────────────────────────────────────────────┤
│          Memory Management Layer            │
│  ┌──────────┬──────────┬──────────────┐   │
│  │ Storage  │ Retrieval │ Session Mgmt │   │
│  └──────────┴──────────┴──────────────┘   │
├─────────────────────────────────────────────┤
│     PostgreSQL + pgvector + Ollama         │
└─────────────────────────────────────────────┘
```

## License

This project is licensed under the terms specified in the LICENSE file.

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs in `src/logs/`
3. Open an issue on GitHub with:
   - Error messages
   - Environment details
   - Steps to reproduce
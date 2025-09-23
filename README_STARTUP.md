# Local Memory MCP - Startup Guide

## Quick Start

To start all services:
```bash
./start_memory_services.sh
```

To stop all services:
```bash
./stop_memory_services.sh
```

To check service status:
```bash
./status_memory_services.sh
```

## Service Architecture

- **PostgreSQL**: Database with pgvector extension (port 5432)
- **Ollama**: Embedding service with nomic-embed-text:v1.5 (port 11434)  
- **Bridge Server**: FastAPI server for memory operations (port 8000)

## Testing

Run comprehensive tests:
```bash
./run_tests.sh all
```

Test specific components:
```bash
./run_tests.sh unit        # Database connectivity
./run_tests.sh integration # Memory operations
./run_tests.sh api         # API endpoints
```

## API Usage

Health check:
```bash
curl http://localhost:8000/api/health
```

Store memory:
```bash
curl -X POST http://localhost:8000/api/memories \
  -H "Content-Type: application/json" \
  -d '{"content": "Test memory", "domain": "test", "tags": ["example"]}'
```

Search memories:
```bash
curl "http://localhost:8000/api/memories?query=test&domain=test&limit=5"
```

## Python API

```python
from src.python_api import quick_store, quick_search

# Store a memory
memory_id = quick_store("Important information", domain="work")

# Search memories  
results = quick_search("information", domain="work")
```
# Python API Guide for Local Memory MCP System

## Overview

The Python API provides a clean, high-level interface for the Local Memory MCP System, allowing Python applications, scripts, and notebooks to easily interact with the memory system. It sits above the core `PostgresMemoryAPI` and provides both synchronous and asynchronous interfaces.

## Architecture Placement

The Python API is located at **`src/python_api.py`** and fits into the system architecture as follows:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL INTERFACES                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Claude Desktop                    Web Dashboard                Python Apps   │
│        ↓                                 ↓                          ↓        │
│    [MCP/STDIO]                    [HTTP:8000]                  [Python API]  │
│        ↓                                 ↓                          ↓        │
└────────┬─────────────────────────────────┬─────────────────────────┬────────┘
         │                                 │                         │
         ↓                                 ↓                         ↓
┌────────────────────────────────────────────────────────────────────────────┐
│                            MAIN SERVER LAYER                                │
├────────────────────────────────────────────────────────────────────────────┤
│  MCP Server (FastMCP)              HTTP Bridge (FastAPI)    Python API     │
│  src/postgres_memory_server.py     bridge_server.py         src/python_api.py │
└────────────────────────────────────────────────────────────────────────────┘
         │                                 │                         │
         ↓                                 ↓                         ↓
┌────────────────────────────────────────────────────────────────────────────┐
│                              CORE API LAYER                                 │
├────────────────────────────────────────────────────────────────────────────┤
│                    PostgresMemoryAPI + OllamaEmbeddings                     │
│                         src/postgres_memory_api.py                          │
└────────────────────────────────────────────────────────────────────────────┘
```

## Features

### Core Features
- **Synchronous Interface**: `MemorySystem` class for simple, blocking operations
- **Asynchronous Interface**: `AsyncMemorySystem` class for modern async/await patterns
- **Quick Functions**: Convenience functions for one-off operations
- **Document Ingestion**: Support for ingesting documents and text content
- **Domain Management**: Organize memories into logical domains
- **Metadata Support**: Rich metadata with tags, importance scores, and custom fields
- **Ollama Integration**: Automatic setup and fallback for embedding generation

### Memory Operations
- **Store**: Save new memories with metadata
- **Search**: Semantic and text-based search across domains
- **Update**: Modify existing memories
- **List Domains**: Discover available memory domains
- **Statistics**: Get system information and stats

## Quick Start

### Basic Synchronous Usage

```python
from src.python_api import MemorySystem

# Initialize the memory system
memory = MemorySystem()

# Store a memory
memory_id = memory.store(
    "User prefers Python for data analysis",
    domain="personal",
    importance=0.8,
    tags=["programming", "preferences"]
)

# Search memories
results = memory.search("programming preferences", limit=3)
for result in results:
    print(f"Found: {result['content']} (score: {result['score']:.3f})")

# List available domains
domains = memory.list_domains()
print(f"Available domains: {domains}")
```

### Asynchronous Usage

```python
import asyncio
from src.python_api import AsyncMemorySystem

async def main():
    # Initialize async memory system
    memory = AsyncMemorySystem()
    
    # Store memories concurrently
    tasks = [
        memory.store("User loves async programming", "technical", importance=0.9),
        memory.store("User works remotely", "work", importance=0.7),
        memory.store("User enjoys cooking", "personal", importance=0.6)
    ]
    
    memory_ids = await asyncio.gather(*tasks)
    print(f"Stored memories: {memory_ids}")
    
    # Search concurrently
    search_tasks = [
        memory.search("programming", limit=2),
        memory.search("work", domain="work", limit=2),
        memory.search("cooking", domain="personal", limit=2)
    ]
    
    results = await asyncio.gather(*search_tasks)
    for i, search_results in enumerate(results):
        print(f"Search {i+1}: {len(search_results)} results")

asyncio.run(main())
```

### Quick Functions

```python
from src.python_api import quick_store, quick_search, quick_ingest

# Quick operations for simple use cases
mem_id = quick_store("User loves quick APIs", "personal", importance=0.7)
results = quick_search("quick APIs", limit=2)
result = quick_ingest("document.pdf", domain="research")
```

## API Reference

### MemorySystem Class

The main synchronous interface for memory operations.

#### Constructor
```python
MemorySystem(
    ollama_url: Optional[str] = None,
    embedding_model: Optional[str] = None,
    keep_alive: Optional[str] = None,
    auto_setup_ollama: bool = True
)
```

#### Methods

##### `store(content, domain=None, source=None, importance=None, tags=None, metadata=None) -> str`
Store a new memory.

**Parameters:**
- `content` (str): The text content to remember
- `domain` (str, optional): Memory domain (defaults to 'default')
- `source` (str, optional): Source of the memory
- `importance` (float, optional): Importance score 0.0-1.0
- `tags` (List[str], optional): List of tags
- `metadata` (Dict[str, Any], optional): Additional metadata

**Returns:** Memory ID string

##### `search(query, domain=None, limit=5) -> List[Dict[str, Any]]`
Search for memories.

**Parameters:**
- `query` (str): Search query
- `domain` (str, optional): Domain to search in
- `limit` (int): Maximum number of results

**Returns:** List of memory dictionaries

##### `update(memory_id, content=None, importance=None, domain=None, metadata=None) -> bool`
Update an existing memory.

##### `list_domains() -> List[str]`
List all available memory domains.

##### `get_stats() -> Dict[str, Any]`
Get system statistics.

### AsyncMemorySystem Class

Async version of MemorySystem with the same interface but async methods.

### Document Ingestion

```python
# Ingest a document file
result = memory.ingest_document(
    "document.pdf",
    domain="research",
    chunk_size=1000,
    chunk_overlap=200
)

# Ingest raw text content
result = memory.ingest_text(
    "This is some text content to ingest",
    source_name="meeting_notes",
    domain="work"
)
```

## Examples

### Complete Example Script

See `examples/python_api_examples.py` for comprehensive examples including:
- Basic synchronous and asynchronous usage
- Document ingestion
- Memory updates
- Batch operations
- Error handling
- Advanced async patterns

### Running Examples

```bash
# Activate virtual environment
source venv/bin/activate

# Run comprehensive examples
python examples/python_api_examples.py

# Run simple test
python test_simple_python_api.py
```

## Integration with Existing System

The Python API integrates seamlessly with the existing memory system:

1. **Uses Same Database**: All operations use the same PostgreSQL database and tables
2. **Compatible with MCP**: Memories stored via Python API are accessible via MCP tools
3. **HTTP Bridge Compatible**: Works alongside the HTTP bridge server
4. **Ollama Integration**: Uses the same Ollama embeddings system
5. **Domain Support**: Full support for domain-based memory organization

## Environment Variables

The Python API respects the same environment variables as the rest of the system:

```bash
# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Ollama Configuration
OLLAMA_API_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text:v1.5
OLLAMA_KEEP_ALIVE=10m

# Memory System
DEFAULT_MEMORY_DOMAIN=default
```

## Error Handling

The Python API includes comprehensive error handling:

```python
try:
    memory = MemorySystem()
    mem_id = memory.store("Important information", "personal")
    results = memory.search("important", domain="personal")
except Exception as e:
    print(f"Error: {e}")
    # Handle error appropriately
```

## Performance Considerations

- **Async Interface**: Use `AsyncMemorySystem` for better performance in async applications
- **Batch Operations**: Use `asyncio.gather()` for concurrent operations
- **Domain Organization**: Use meaningful domains for better search performance
- **Importance Scores**: Set appropriate importance scores for better retrieval
- **Chunk Size**: Adjust document chunk sizes based on your use case

## Troubleshooting

### Common Issues

1. **Import Errors**: Make sure you're running from the project root and have activated the virtual environment
2. **Database Connection**: Ensure PostgreSQL is running and accessible
3. **Ollama Issues**: The system will fall back to text search if Ollama is unavailable
4. **Memory Limits**: Large documents may need to be chunked appropriately

### Testing

Run the test suite to verify everything is working:

```bash
# Simple test (recommended)
python test_simple_python_api.py

# Full test (requires ingestion system)
python test_python_api.py
```

## Future Enhancements

Planned improvements include:
- Enhanced document ingestion with more file format support
- Memory consolidation and cleanup tools
- Advanced search filters and sorting
- Memory relationship tracking
- Export/import functionality
- Performance monitoring and metrics

## Contributing

The Python API is designed to be extensible. Key areas for contribution:
- Additional document loaders
- Enhanced search capabilities
- Performance optimizations
- New convenience functions
- Better error handling and logging

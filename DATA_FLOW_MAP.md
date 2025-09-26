# Local Memory MCP Data Flow Map

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                   │
├─────────────────────────────┬───────────────────────────────────────────────┤
│      Claude Desktop         │              AI Agent                         │
│   (Primary Interface)       │        (Programmatic Access)                 │
└─────────────┬───────────────┴───────────────┬───────────────────────────────┘
              │                               │
              │ MCP Protocol / HTTP JSON-RPC  │
              │                               │
┌─────────────▼───────────────────────────────▼───────────────────────────────┐
│                           MCP SERVER LAYER                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                    PostgreSQL Memory Server                                 │
│              (Core MCP Implementation)                                      │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              │ Internal API Calls
                              │
┌─────────────────────────────▼───────────────────────────────────────────────┐
│                             API LAYER                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                    PostgreSQL Memory API                                    │
│              (Core Memory Operations Handler)                               │
│                                                                             │
│                      SQL + Vector Operations                                │
└─────────┬───────────────────────────────────────────────────┬───────────────┘
          │                                                   │
          │ Embedding Requests                                │ Database Ops
          │                                                   │
┌─────────▼───────────────────────┐                 ┌─────────▼───────────────┐
│     EXTERNAL SERVICES           │                 │    DATABASE LAYER       │
├─────────────────────────────────┤                 ├─────────────────────────┤
│        Ollama Service           │                 │   PostgreSQL Database   │
│                                 │                 │                         │
│  ┌─────────────────────────┐    │                 │  ┌─────────────────────┐│
│  │     Ollama API          │    │                 │  │   pgvector Extension│││
│  │                         │    │                 │  │                     ││
│  │ ┌─────────────────────┐ │    │                 │  │ ┌─────────────────┐ ││
│  │ │  nomic-embed-text   │ │    │                 │  │ │  Domain Tables  │ ││
│  │ │     (Model)         │ │    │                 │  │ │                 │ ││
│  │ └─────────────────────┘ │    │                 │  │ │ default_memories│ ││
│  └─────────────────────────┘    │                 │  │ │ startup_memories│ ││
└─────────────────────────────────┘                 │  │ │ health_memories │ ││
                                                    │  │ │      ...        │ ││
                                                    │  │ └─────────────────┘ ││
                                                    │  └─────────────────────┘│
                                                    └─────────────────────────┘
```

## Data Flow Processes

### Memory Storage Flow

```
Client Input
    │
    │ 1. Send memory content
    ▼
┌─────────────────────┐
│   MCP Server        │ ◄── 2. Receive content
│                     │
└─────────┬───────────┘
          │ 3. Forward to API
          ▼
┌─────────────────────┐
│ PostgreSQL Memory   │ ◄── 4. Process memory request
│      API            │
└─────────┬───────────┘
          │ 5. Generate embedding
          ▼
┌─────────────────────┐     ┌─────────────────────┐
│   Ollama Service    │ ◄── │  Send text content  │
│                     │     │                     │
│ ┌─────────────────┐ │     │ ┌─────────────────┐ │
│ │ nomic-embed-    │ │ ──► │ │ Return embedding│ │
│ │     text        │ │     │ │    vector       │ │
│ └─────────────────┘ │     │ └─────────────────┘ │
└─────────────────────┘     └─────────────────────┘
          │                           │
          └───────────6. Embedding────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│         PostgreSQL Database                 │
│                                             │
│  7. Store memory + embedding in domain table│
│                                             │
│ ┌─────────────────────────────────────────┐ │
│ │          Domain Table                   │ │
│ │  ┌─────────┬──────────┬──────────────┐  │ │
│ │  │   ID    │ Content  │  Embedding   │  │ │
│ │  │ (UUID)  │ (Text)   │  (Vector)    │  │ │
│ │  └─────────┴──────────┴──────────────┘  │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

### Memory Retrieval Flow

```
Client Query
    │
    │ 1. Send search query
    ▼
┌─────────────────────┐
│   MCP Server        │ ◄── 2. Receive query
│                     │
└─────────┬───────────┘
          │ 3. Forward to API
          ▼
┌─────────────────────┐
│ PostgreSQL Memory   │ ◄── 4. Process search request
│      API            │
└─────────┬───────────┘
          │ 5. Convert query to embedding
          ▼
┌─────────────────────┐     ┌─────────────────────┐
│   Ollama Service    │ ◄── │  Send query text    │
│                     │     │                     │
│ ┌─────────────────┐ │     │ ┌─────────────────┐ │
│ │ nomic-embed-    │ │ ──► │ │ Return query    │ │
│ │     text        │ │     │ │   embedding     │ │
│ └─────────────────┘ │     │ └─────────────────┘ │
└─────────────────────┘     └─────────────────────┘
          │                           │
          └───────────6. Query Embedding────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│         PostgreSQL Database                 │
│                                             │
│  7. Vector similarity search using pgvector │
│                                             │
│ ┌─────────────────────────────────────────┐ │
│ │          Domain Table                   │ │
│ │                                         │ │
│ │  SELECT * FROM memories                 │ │
│ │  ORDER BY embedding <-> query_vector    │ │
│ │  LIMIT n;                               │ │
│ │                                         │ │
│ └─────────┬───────────────────────────────┘ │
└───────────┼─────────────────────────────────┘
            │ 8. Return matching memories
            ▼
┌─────────────────────┐
│ PostgreSQL Memory   │ ◄── 9. Format results
│      API            │
└─────────┬───────────┘
          │ 10. Return to server
          ▼
┌─────────────────────┐
│   MCP Server        │ ◄── 11. Process response
│                     │
└─────────┬───────────┘
          │ 12. Send to client
          ▼
    Client Results
```

## Communication Protocols

### MCP Protocol Flow
```
Client ◄──► MCP Server
   │              │
   │ JSON-RPC     │
   │ Messages     │
   │              │
   ▼              ▼
┌─────────────────────┐
│  Standard MCP       │
│  Operations:        │
│  - store_memory     │
│  - retrieve_memory  │
│  - search_by_tag    │
│  - delete_memory    │
│  - list_domains     │
└─────────────────────┘
```

### HTTP/JSON-RPC Alternative
```
Client ◄──► HTTP API
   │              │
   │ HTTP POST    │
   │ JSON Payload │
   │              │
   ▼              ▼
┌─────────────────────┐
│  Alternative        │
│  Communication      │
│  Channel            │
└─────────────────────┘
```

## Domain Isolation Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                PostgreSQL Database                          │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ default_memories│  │ startup_memories│  │health_memor.│  │
│  │                 │  │                 │  │             │  │
│  │ ID   │ Content  │  │ ID   │ Content  │  │ ID │ Content│  │
│  │ UUID │ Text     │  │ UUID │ Text     │  │ UUID│ Text  │  │
│  │ Vec  │ Metadata │  │ Vec  │ Metadata │  │ Vec │ Meta  │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
│           │                     │                   │       │
│           ▼                     ▼                   ▼       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │   pgvector      │  │   pgvector      │  │  pgvector   │  │
│  │   Index         │  │   Index         │  │   Index     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Key Data Transformations

1. **Text → Vector Embedding**
   - Input: Raw text content
   - Process: Ollama nomic-embed-text model
   - Output: 768-dimensional vector

2. **Query → Similarity Search**
   - Input: Search query text
   - Process: Convert to embedding + pgvector cosine similarity
   - Output: Ranked relevant memories

3. **Domain Routing**
   - Input: Domain parameter
   - Process: Table selection logic
   - Output: Isolated memory context

## Performance Considerations

- **Embedding Generation**: External Ollama service call (potential bottleneck)
- **Vector Search**: pgvector indexing for fast similarity search
- **Domain Isolation**: Separate tables prevent cross-contamination
- **Connection Pooling**: PostgreSQL handles concurrent requests
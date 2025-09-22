# Local Memory MCP - Architecture Map

## 🗺️ System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL INTERFACES                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Claude Desktop                    Web Dashboard                k6 Tests     │
│        ↓                                 ↓                          ↓        │
│    [MCP/STDIO]                    [HTTP:8000]                  [HTTP Load]   │
│        ↓                                 ↓                          ↓        │
└────────┬─────────────────────────────────┬─────────────────────────┬────────┘
         │                                 │                         │
         ↓                                 ↓                         ↓
┌────────────────────────────────────────────────────────────────────────────┐
│                            MAIN SERVER LAYER                                │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────┐         ┌─────────────────────┐                  │
│  │ postgres_memory_     │         │   web_dashboard/    │                  │
│  │    server.py         │         │      app.py         │                  │
│  │  [FastMCP Server]    │         │  [FastAPI Server]   │                  │
│  └──────────┬───────────┘         └──────────┬──────────┘                  │
│             │                                 │                             │
│             ↓                                 ↓                             │
└─────────────────────────────────────────────────────────────────────────────┘
              │                                 │
              ↓                                 ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────┐         ┌─────────────────────┐                  │
│  │ postgres_memory_     │         │   web_dashboard/    │                  │
│  │     api.py           │←--------│ postgres_adapter.py │                  │
│  │  [psycopg2 sync]     │         │   [asyncpg async]   │                  │
│  └──────────┬───────────┘         └──────────┬──────────┘                  │
│             │                                 │                             │
└─────────────────────────────────────────────────────────────────────────────┘
              │                                 │
              ↓                                 ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EMBEDDINGS LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────┐                                                   │
│  │ ollama_embeddings.py │ ←------ Uses Ollama API                           │
│  │  [Vector Generation] │         (nomic-embed-text)                        │
│  └──────────┬───────────┘                                                   │
│             │                                                                │
└─────────────────────────────────────────────────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DATABASE LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────┐                    │
│  │            PostgreSQL Database                      │                    │
│  │  ┌──────────────────────────────────────────────┐  │                    │
│  │  │  Tables:                                     │  │                    │
│  │  │  • default_memories                          │  │                    │
│  │  │  • sentient-library-universal_memories       │  │                    │
│  │  │                                              │  │                    │
│  │  │  Extensions:                                 │  │                    │
│  │  │  • pgvector (768-dimensional embeddings)     │  │                    │
│  │  └──────────────────────────────────────────────┘  │                    │
│  └────────────────────────────────────────────────────┘                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

```

## 🔗 Component Connections

### ✅ **CONNECTED Components**

```
postgres_memory_server.py
    ├──→ postgres_memory_api.py [imports]
    ├──→ ollama_embeddings.py [imports]
    └──→ PostgreSQL Database [psycopg2]

postgres_memory_api.py
    ├──→ ollama_embeddings.py [uses for vectors]
    └──→ PostgreSQL Database [psycopg2 connection]

web_dashboard/app.py
    └──→ web_dashboard/postgres_adapter.py [imports]

web_dashboard/postgres_adapter.py
    └──→ PostgreSQL Database [asyncpg connection]

ollama_embeddings.py
    └──→ Ollama Service [HTTP API at localhost:11434]
```

### ⚠️ **PARTIALLY Connected Components**

```
consolidation/ (Directory)
    ├── postgres_consolidator.py
    │   └──→ PostgreSQL [asyncpg] ✅ Connected
    │
    ├── consolidator.py
    ├── clustering.py
    ├── associations.py
    ├── compression.py
    ├── decay.py
    ├── forgetting.py
    ├── health.py
    └── scheduler.py
        ⚠️ These modules import each other but NOT connected to main server
```

### ❌ **DISCONNECTED Components**

```
❌ enhanced_cli/
    ├── cli.py [Uses asyncpg, Click CLI]
    └── memory_scoring.py
    ⚠️ Standalone CLI tool - NOT connected to main server

❌ models/
    └── memory.py
    ⚠️ Defines data models but NOT imported anywhere

❌ memory_scorer.py
    ⚠️ Standalone module - NOT imported by any active component

❌ memory_scoring.py
    ⚠️ Duplicate of enhanced_cli/memory_scoring.py - NOT used

❌ context_formatter.py
    ⚠️ Standalone utility - NOT imported anywhere

❌ project_detector.py
    ⚠️ Standalone utility - NOT imported anywhere

❌ time_parsing.py
    ⚠️ Standalone utility - NOT imported anywhere

❌ Hooks Directory (hooks/)
    ├── core/
    └── utilities/
    ⚠️ JavaScript files - separate from Python system

❌ SQL files (sql/)
    ⚠️ Schema definitions - manually executed, not imported

❌ Test Files
    ├── k6_demo.js
    ├── k6_memory_test.js
    └── test_queries.sql
    ⚠️ Test scripts - not part of runtime system
```

## 📊 Data Flow Paths

### **Main Memory Storage Path:**
```
Claude Desktop
    ↓ (MCP Protocol)
postgres_memory_server.py
    ↓ (Function call)
postgres_memory_api.py
    ↓ (Generate embedding)
ollama_embeddings.py
    ↓ (HTTP to Ollama)
Ollama Service
    ↓ (Return vector)
postgres_memory_api.py
    ↓ (Store with vector)
PostgreSQL + pgvector
```

### **Web Dashboard Path:**
```
Browser
    ↓ (HTTP Request)
web_dashboard/app.py
    ↓ (FastAPI route)
web_dashboard/postgres_adapter.py
    ↓ (asyncpg query)
PostgreSQL
    ↓ (Return data)
Browser (JSON response)
```

## 🚨 Issues Identified

1. **Consolidation System Disconnected**: The entire consolidation system is implemented but not integrated with the main server
2. **Duplicate Files**: Multiple scoring implementations (memory_scoring.py vs enhanced_cli/memory_scoring.py)
3. **Unused Models**: models/memory.py defines structures but isn't used
4. **Orphaned Utilities**: Several utility modules have no consumers
5. **Two Database Clients**: Using both psycopg2 (sync) and asyncpg (async) for the same database

## 💡 Recommendations

1. **Integrate Consolidation**: Connect consolidation system to main server for automatic memory management
2. **Remove Duplicates**: Clean up duplicate scoring implementations
3. **Use Models**: Import and use the defined models in models/memory.py
4. **Connect Utilities**: Wire up useful utilities like time_parsing.py where needed
5. **Standardize DB Access**: Choose either sync (psycopg2) or async (asyncpg) consistently
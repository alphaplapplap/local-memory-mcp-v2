# Local Memory MCP Architecture

## System Overview

This document describes the architecture of the Local Memory MCP (Model Context Protocol) system, which provides semantic memory storage and retrieval capabilities using PostgreSQL with pgvector extension.

## Architecture Layers

### Client Layer
- **Claude Desktop**: Primary client interface for interacting with the memory system
- **AI Agent**: Secondary client interface for programmatic access

Both clients communicate with the MCP Server Layer through:
- **MCP Protocol**: Standard Model Context Protocol communication
- **HTTP/JSON-RPC**: Alternative communication protocol

### MCP Server Layer
- **PostgreSQL Memory Server**: Core MCP server implementation that handles memory operations and provides the MCP interface

### API Layer
- **PostgreSQL Memory API**: Core API that handles all memory operations including storage, retrieval, and management
- **SQL + Vector Ops**: Database operations combining traditional SQL with vector similarity operations

### External Services
- **Ollama Embeddings**: External service for generating text embeddings
- **Ollama API**: API interface to the Ollama service
- **nomic-embed-text**: Specific embedding model used for text vectorization

### Database Layer
- **PostgreSQL Database**: Primary data storage with pgvector extension for vector operations
- **pgvector Extension**: Enables vector similarity search capabilities

#### Domain Tables
The system supports multiple isolated memory domains:
- **default_memories**: Default domain for general memories
- **startup_memories**: Domain for startup-related information
- **health_memories**: Domain for health-related data

## Data Flow

1. **Memory Storage**:
   - Client sends memory content to MCP Server
   - Content is processed through PostgreSQL Memory API
   - Text is sent to Ollama for embedding generation
   - Memory and embedding are stored in appropriate domain table

2. **Memory Retrieval**:
   - Client sends query to MCP Server
   - Query is converted to embedding via Ollama
   - Vector similarity search performed using pgvector
   - Relevant memories returned to client

## Key Features

- **Semantic Search**: Uses vector embeddings for intelligent memory retrieval
- **Domain Isolation**: Separate tables for different contexts/domains
- **Scalable Storage**: PostgreSQL backend with vector indexing
- **Multiple Clients**: Supports both desktop and programmatic access
- **Standardized Protocol**: Uses MCP for consistent client-server communication
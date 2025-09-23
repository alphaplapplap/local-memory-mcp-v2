# Development Guide

## Hot Reloading Setup

The memory system now supports hot reloading for development. This means you can edit Python files and see changes immediately without manually restarting the server.

## Quick Start

### Option 1: Simple Development Server
```bash
# Start with basic hot reloading
./start_dev.sh
```

### Option 2: Advanced Development Server
```bash
# Start with enhanced file watching and logging
python dev_server_advanced.py
```

### Option 3: Manual Uvicorn
```bash
# Direct uvicorn command with reload
source venv/bin/activate
uvicorn bridge_server:app --reload --host 0.0.0.0 --port 8000
```

## Development Features

### 🔄 Hot Reloading
- Automatically restarts server when Python files change
- Watches `src/` directory and root directory
- Excludes cache files, logs, and virtual environment

### 👀 File Watching
- Monitors file system changes
- Provides visual feedback when files are modified
- Prevents rapid reloads with debouncing

### 🐛 Enhanced Logging
- Debug-level logging in development
- Colored console output
- Detailed error information

### 📊 Development Endpoints
- `http://localhost:8000/docs` - Interactive API documentation
- `http://localhost:8000/api/health` - Health check
- `http://localhost:8000/api/project/domain` - Current project domain

## Development Environment Variables

The development server automatically sets these environment variables:

```bash
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
DB_MIN_CONNECTIONS=1
DB_MAX_CONNECTIONS=5
ENABLE_QUERY_CACHING=false
```

## File Structure

```
├── dev_server.py              # Simple development server
├── dev_server_advanced.py     # Advanced development server with file watching
├── start_dev.sh              # Development startup script
├── bridge_server.py          # Main FastAPI application
└── src/                      # Source code (watched for changes)
    ├── postgres_memory_api.py
    ├── project_detector.py
    └── ...
```

## Troubleshooting

### Server Won't Start
1. Check if PostgreSQL is running: `brew services start postgresql@17`
2. Verify database connection: `psql -h localhost -p 5432 -U postgres -d memory_db`
3. Check if port 8000 is available: `lsof -i :8000`

### Hot Reloading Not Working
1. Ensure you're using the development server scripts
2. Check that files are being saved (not just modified in memory)
3. Verify the file is in a watched directory (`src/` or root)

### Performance Issues
1. Development server uses single worker (intentional)
2. Caching is disabled in development
3. Connection pool is minimized for development

## Production vs Development

| Feature | Development | Production |
|---------|-------------|------------|
| Hot Reloading | ✅ Enabled | ❌ Disabled |
| Debug Logging | ✅ Enabled | ❌ Disabled |
| Caching | ❌ Disabled | ✅ Enabled |
| Workers | 1 | Multiple |
| File Watching | ✅ Enabled | ❌ Disabled |

## Auto-Domain Routing

The development server automatically detects the current project and routes memories to project-specific domains:

- **Git Repository Name**: `local-memory-mcp-v2` → domain: `local-memory-mcp-v2`
- **Fallback**: If detection fails → domain: `default`

This ensures memories are automatically organized by project during development.

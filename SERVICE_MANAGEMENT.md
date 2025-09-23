# Local Memory MCP Service Management

This directory contains scripts for managing the Local Memory MCP services as persistent background processes.

## Service Scripts

### `start_memory_services.sh`
Starts all required services for the memory system:
- **PostgreSQL** (if not already running)
- **Ollama** (if available and not running)
- **Bridge Server** (on port 8000)

```bash
./start_memory_services.sh
```

### `stop_memory_services.sh`
Stops all memory system services that were started by the start script:

```bash
./stop_memory_services.sh
```

### `restart_memory_services.sh`
Cleanly restarts all services by:
1. Killing any stuck processes
2. Cleaning up PID files
3. Stopping services cleanly
4. Starting services fresh

```bash
./restart_memory_services.sh
```

### `status_memory_services.sh`
Shows the current status of all services:

```bash
./status_memory_services.sh
```

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL | 5432 | Database storage |
| Ollama | 11434 | Embedding generation |
| Bridge Server | 8000 | HTTP API for hooks |

## Files and Directories

### `.pids/`
Contains PID files for services started by the scripts:
- `bridge_server.pid`
- `ollama.pid` (if started by script)

### `logs/`
Contains service logs:
- `bridge_server.log`
- `ollama.log` (if started by script)

## Usage Patterns

### Development Workflow
```bash
# Start services when working on the project
./start_memory_services.sh

# Check status
./status_memory_services.sh

# Stop when done
./stop_memory_services.sh
```

### Troubleshooting
```bash
# If services seem stuck or unresponsive
./restart_memory_services.sh

# Check logs if issues persist
tail -f logs/bridge_server.log
```

### Port Conflicts
If port 8000 is already in use:
1. Find what's using it: `lsof -i :8000`
2. Stop the conflicting process
3. Restart services: `./restart_memory_services.sh`

## Integration with Claude Code Hooks

The bridge server on port 8000 provides the MCP tools that the Claude Code hooks use:
- `search_memories`
- `store_memory`
- `list_memory_domains`

The hooks are configured in `hooks/config.json` to use `http://localhost:8000`.

## Service Dependencies

1. **PostgreSQL** must be running (managed externally via Homebrew)
2. **Ollama** is optional (enables semantic search, falls back to text search)
3. **Bridge Server** requires PostgreSQL to be accessible

## Automatic Startup

For automatic startup on boot, you can:

### macOS (launchd)
Create a user launch agent or add to your shell profile:

```bash
# Add to ~/.zshrc or ~/.bash_profile
cd /path/to/local-memory-mcp && ./start_memory_services.sh
```

### Linux (systemd)
Create systemd user services (see systemd documentation).

## Security Notes

- Services run on localhost only
- API key authentication is basic (for local development)
- PostgreSQL should be configured with proper access controls
- Bridge server logs may contain sensitive memory content
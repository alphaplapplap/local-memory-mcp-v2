# MCP Server Automatic Recovery Solution

## Overview
Comprehensive automatic recovery infrastructure for MCP Memory Server to ensure high availability and resilience against crashes.

## Components Implemented

### 1. Database Error Handling (src/database_error_handling.py)
- **Automatic Table Recreation**: Detects missing tables (error 42P01) and recreates them automatically
- **Connection Pool Recovery**: Reinitializes database connections after failures
- **Retry Logic**: Implements exponential backoff for retryable database errors

### 2. Server-Level Recovery (src/postgres_memory_server.py)
- **In-Process Retry**: `run_server_with_recovery()` function with automatic restart
- **Global Declaration Fix**: Fixed syntax error with global memory_api declaration
- **Graceful Degradation**: Handles connection failures and attempts reconnection

### 3. Wrapper Script (scripts/run_with_restart.sh)
- **Process Supervision**: Monitors server process and restarts on crash
- **Exponential Backoff**: Prevents rapid restart loops with increasing delays
- **Intelligent Restart**: Resets failure counter if server runs > 5 minutes
- **Signal Handling**: Proper cleanup on SIGINT/SIGTERM
- **Max Retry Limit**: Configurable maximum retry attempts (default: 10)

### 4. System Service Management

#### macOS (launchd)
- **com.localmemory.mcp.http.plist**: HTTP server with KeepAlive directives
- **com.localmemory.mcp.stdio.plist**: MCP stdio server configuration
- **Features**:
  - Automatic restart on crash (KeepAlive)
  - Throttle interval to prevent rapid restarts
  - Resource limits configuration
  - Centralized logging

#### Linux (systemd)
- **localmemory-mcp.service**: Systemd unit file
- **Features**:
  - Restart=always policy
  - StartLimitBurst for restart throttling
  - Security hardening options
  - Resource limits

### 5. Management Scripts

#### install-service.sh
- Cross-platform installation (macOS/Linux)
- Dependency checking
- Python virtual environment setup
- Service registration

#### manage-service.sh
- Unified interface for service management
- Commands: start, stop, restart, status, logs, test, health, clean
- Platform detection and appropriate tool usage
- Built-in crash recovery testing

## Recovery Layers

1. **Application Layer**: Table recreation, connection pool recovery
2. **Process Layer**: In-process retry with exponential backoff
3. **Wrapper Layer**: External process supervision
4. **System Layer**: OS-level service management (launchd/systemd)

## Test Results

### Crash Recovery Tests ✅
1. **Graceful Shutdown (SIGTERM)**: Server successfully restarts
2. **Simulated Crash (SIGKILL)**: Server recovers from hard crash
3. **Database Table Drop**: Tables are automatically recreated

## Usage

### Quick Start
```bash
# Install service
./scripts/install-service.sh

# Start with auto-restart
./scripts/run_with_restart.sh http

# Manage service
./scripts/manage-service.sh start
./scripts/manage-service.sh status
./scripts/manage-service.sh test  # Test crash recovery
```

### macOS Service Management
```bash
# Load service
launchctl load ~/Library/LaunchAgents/com.localmemory.mcp.http.plist

# Check status
launchctl list | grep localmemory

# View logs
tail -f logs/mcp-http.log
```

### Linux Service Management
```bash
# Start service
sudo systemctl start localmemory-mcp

# Enable on boot
sudo systemctl enable localmemory-mcp

# Check status
sudo systemctl status localmemory-mcp

# View logs
sudo journalctl -u localmemory-mcp -f
```

## Configuration

### Environment Variables
- `MAX_RETRIES`: Maximum retry attempts (default: 5 in-process, 10 wrapper)
- `RESTART_DELAY`: Initial restart delay in seconds (default: 5)
- `BACKOFF_MULTIPLIER`: Exponential backoff multiplier (default: 2)
- `MAX_DELAY`: Maximum delay between restarts (default: 60)

### Log Files
- HTTP server: `logs/mcp-http.log`
- Error logs: `logs/mcp-http.error.log`
- Daily logs: `logs/mcp-server-YYYYMMDD.log`

## Benefits

1. **High Availability**: Multiple recovery layers ensure service continuity
2. **Automatic Recovery**: No manual intervention required for common failures
3. **Graceful Degradation**: Service continues with reduced functionality if needed
4. **Prevention of Data Loss**: Tables recreated automatically when dropped
5. **Resource Protection**: Prevents rapid restart loops and resource exhaustion
6. **Monitoring**: Health checks and status reporting built-in
7. **Cross-Platform**: Works on both macOS and Linux

## Monitoring

The solution includes comprehensive monitoring capabilities:
- Health endpoint: `http://localhost:8000/health`
- Process status checking
- Database connectivity testing
- Automatic log rotation and cleanup

This implementation ensures the MCP Memory Server remains available and automatically recovers from various failure scenarios without manual intervention.
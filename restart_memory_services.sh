#!/bin/bash

# Local Memory MCP Service Restarter
# Cleanly stops and restarts all memory system services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

main() {
    log "Restarting Local Memory MCP Services..."
    echo

    # Force kill any processes that might be stuck
    log "Cleaning up any stuck processes..."

    # Kill any python bridge server processes
    pkill -f "python.*bridge_server.py" 2>/dev/null || true

    # Kill any HTTP servers on port 8000
    lsof -ti :8000 | xargs kill -9 2>/dev/null || true

    sleep 2

    # Clean up PID files
    log "Cleaning PID files..."
    rm -rf "$SCRIPT_DIR/.pids"

    echo

    # Stop services cleanly
    log "Stopping services..."
    "$SCRIPT_DIR/stop_memory_services.sh" || true

    echo

    # Start services
    log "Starting services..."
    "$SCRIPT_DIR/start_memory_services.sh"
}

# Handle signals
trap 'echo; error "Restart interrupted"; exit 1' INT TERM

main "$@"
#!/bin/bash

# Local Memory MCP Service Stopper
# Stops all memory system services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"

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

# Stop a service by PID file
stop_service() {
    local service_name="$1"
    local pid_file="$PID_DIR/${service_name}.pid"

    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log "Stopping $service_name (PID: $pid)..."
            kill "$pid"

            # Wait for process to stop
            for i in {1..5}; do
                if ! kill -0 "$pid" 2>/dev/null; then
                    success "$service_name stopped"
                    rm -f "$pid_file"
                    return 0
                fi
                sleep 1
            done

            # Force kill if still running
            warning "Force killing $service_name..."
            kill -9 "$pid" 2>/dev/null || true
            rm -f "$pid_file"
            success "$service_name force stopped"
        else
            warning "$service_name PID file exists but process not running"
            rm -f "$pid_file"
        fi
    else
        log "$service_name not running (no PID file)"
    fi
}

# Stop all running processes
stop_all() {
    log "Stopping Local Memory MCP Services..."
    echo

    # Stop bridge server
    stop_service "bridge_server"

    # Stop Ollama if we started it
    stop_service "ollama"

    # Note about PostgreSQL
    if pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
        warning "PostgreSQL is still running (managed externally)"
        echo "  To stop PostgreSQL: brew services stop postgresql"
    fi

    echo
    success "Memory services stopped"
}

# Handle signals
trap 'echo; error "Stop interrupted"; exit 1' INT TERM

stop_all "$@"
#!/bin/bash

# Local Memory MCP Service Starter
# Starts all required services for the memory system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"
LOG_DIR="$SCRIPT_DIR/logs"

# Create directories
mkdir -p "$PID_DIR" "$LOG_DIR"

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

# Check if service is already running
check_service() {
    local service_name="$1"
    local pid_file="$PID_DIR/${service_name}.pid"

    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0  # Running
        else
            warning "Cleaning stale PID file for $service_name"
            rm -f "$pid_file"
            return 1  # Not running
        fi
    fi
    return 1  # Not running
}

# Start PostgreSQL if not running
start_postgres() {
    log "Checking PostgreSQL..."

    if pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
        success "PostgreSQL is already running"
        return 0
    fi

    log "Starting PostgreSQL..."
    if command -v brew >/dev/null 2>&1; then
        if brew services list | grep postgresql | grep started >/dev/null; then
            success "PostgreSQL is managed by Homebrew and running"
        else
            brew services start postgresql@17 || brew services start postgresql
            sleep 2
            if pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
                success "PostgreSQL started via Homebrew"
            else
                error "Failed to start PostgreSQL via Homebrew"
                return 1
            fi
        fi
    else
        error "PostgreSQL not running and Homebrew not found"
        return 1
    fi
}

# Start Ollama if not running
start_ollama() {
    log "Checking Ollama..."

    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        success "Ollama is already running"
        return 0
    fi

    log "Starting Ollama..."
    if command -v ollama >/dev/null 2>&1; then
        ollama serve >"$LOG_DIR/ollama.log" 2>&1 &
        local ollama_pid=$!
        echo "$ollama_pid" > "$PID_DIR/ollama.pid"

        # Wait for Ollama to start
        for i in {1..10}; do
            if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
                success "Ollama started (PID: $ollama_pid)"
                return 0
            fi
            sleep 1
        done
        error "Ollama failed to start"
        return 1
    else
        warning "Ollama not found, memory system will use text search only"
        return 0
    fi
}

# Start Bridge Server
start_bridge_server() {
    log "Checking Bridge Server..."

    if check_service "bridge_server"; then
        local pid=$(cat "$PID_DIR/bridge_server.pid")
        success "Bridge Server is already running (PID: $pid)"
        return 0
    fi

    # Check if port 8000 is already in use by another process
    if lsof -i :8000 >/dev/null 2>&1; then
        error "Port 8000 is already in use by another process"
        log "Use 'lsof -i :8000' to see what's using it"
        return 1
    fi

    log "Starting Bridge Server..."
    cd "$SCRIPT_DIR"

    # Use fixed port 8000 for bridge server
    BRIDGE_PORT=8000 python3 bridge_server.py >"$LOG_DIR/bridge_server.log" 2>&1 &
    local bridge_pid=$!
    echo "$bridge_pid" > "$PID_DIR/bridge_server.pid"

    # Wait for bridge server to start
    for i in {1..10}; do
        if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
            success "Bridge Server started on port 8000 (PID: $bridge_pid)"
            return 0
        fi
        sleep 1
    done

    # If startup failed, clean up PID file
    rm -f "$PID_DIR/bridge_server.pid"
    error "Bridge Server failed to start"
    log "Check logs: $LOG_DIR/bridge_server.log"
    return 1
}

# Main startup sequence
main() {
    log "Starting Local Memory MCP Services..."
    echo

    # Start services in order
    start_postgres || exit 1
    start_ollama || true  # Continue even if Ollama fails
    start_bridge_server || exit 1

    echo
    success "All services started successfully!"
    echo
    echo "Services running:"
    echo "  • PostgreSQL: localhost:5432"
    echo "  • Bridge Server: http://localhost:8000"
    if check_service "ollama" || curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "  • Ollama: http://localhost:11434"
    fi
    echo
    echo "Logs available in: $LOG_DIR/"
    echo "PIDs stored in: $PID_DIR/"
    echo
    echo "To stop services: ./stop_memory_services.sh"
}

# Handle signals
trap 'echo; error "Startup interrupted"; exit 1' INT TERM

main "$@"
#!/bin/bash

# Local Memory MCP Service Status Checker
# Shows status of all memory system services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

status_icon() {
    if [[ "$1" == "running" ]]; then
        echo -e "${GREEN}●${NC}"
    elif [[ "$1" == "stopped" ]]; then
        echo -e "${RED}●${NC}"
    else
        echo -e "${YELLOW}●${NC}"
    fi
}

check_postgres() {
    if pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
        echo "running"
    else
        echo "stopped"
    fi
}

check_ollama() {
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "running"
    else
        echo "stopped"
    fi
}

check_bridge_server() {
    if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
        echo "running"
    else
        echo "stopped"
    fi
}

get_pid() {
    local service_name="$1"
    local pid_file="$PID_DIR/${service_name}.pid"

    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
        else
            echo "stale"
        fi
    else
        echo "none"
    fi
}

# Main status display
echo -e "${BLUE}Local Memory MCP Services Status${NC}"
echo "================================="
echo

# PostgreSQL
postgres_status=$(check_postgres)
postgres_pid=$(pgrep -f postgres | head -1 || echo "none")
echo -e "$(status_icon "$postgres_status") PostgreSQL       $postgres_status"
if [[ "$postgres_status" == "running" ]]; then
    echo "    Port: 5432"
    echo "    PID: $postgres_pid"
fi
echo

# Ollama
ollama_status=$(check_ollama)
ollama_pid=$(get_pid "ollama")
echo -e "$(status_icon "$ollama_status") Ollama           $ollama_status"
if [[ "$ollama_status" == "running" ]]; then
    echo "    Port: 11434"
    if [[ "$ollama_pid" != "none" && "$ollama_pid" != "stale" ]]; then
        echo "    PID: $ollama_pid"
    fi
fi
echo

# Bridge Server
bridge_status=$(check_bridge_server)
bridge_pid=$(get_pid "bridge_server")
echo -e "$(status_icon "$bridge_status") Bridge Server    $bridge_status"
if [[ "$bridge_status" == "running" ]]; then
    echo "    Port: 8000"
    if [[ "$bridge_pid" != "none" && "$bridge_pid" != "stale" ]]; then
        echo "    PID: $bridge_pid"
    fi
fi
echo

# Summary
all_running=true
[[ "$postgres_status" != "running" ]] && all_running=false
[[ "$bridge_status" != "running" ]] && all_running=false

if [[ "$all_running" == "true" ]]; then
    echo -e "${GREEN}✓ All core services are running${NC}"
    if [[ "$ollama_status" == "running" ]]; then
        echo -e "${GREEN}✓ Ollama is running (semantic search enabled)${NC}"
    else
        echo -e "${YELLOW}⚠ Ollama not running (text search only)${NC}"
    fi
else
    echo -e "${RED}✗ Some services are not running${NC}"
    echo "  Run: ./start_memory_services.sh"
fi

echo
echo "Logs: $SCRIPT_DIR/logs/"
echo "PIDs: $PID_DIR/"
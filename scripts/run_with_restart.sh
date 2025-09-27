#!/bin/bash
# Runs MCP server with automatic restart on crash
# Usage: ./scripts/run_with_restart.sh [mode]
# Modes: http, mcp, unified (default: mcp)

set -e

# Configuration
MAX_RETRIES=10
RESTART_DELAY=5
BACKOFF_MULTIPLIER=2
MAX_DELAY=60
LOG_DIR="logs"
PID_FILE="memory-server.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Get server mode from argument
MODE="${1:-mcp}"

# Detect Python executable
if [ -f "/opt/homebrew/Cellar/python@3.11/3.11.13/Frameworks/Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python" ]; then
    PYTHON="/opt/homebrew/Cellar/python@3.11/3.11.13/Frameworks/Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python"
elif command -v python3 &> /dev/null; then
    PYTHON="python3"
elif command -v python &> /dev/null; then
    PYTHON="python"
else
    echo -e "${RED}❌ Python not found. Please install Python 3.${NC}"
    exit 1
fi

echo -e "${GREEN}🚀 Starting MCP Server with Auto-Restart${NC}"
echo -e "Mode: ${YELLOW}$MODE${NC}"
echo -e "Python: $PYTHON"
echo -e "Restart Policy: Max ${MAX_RETRIES} retries with exponential backoff"
echo "----------------------------------------"

# Function to cleanup on exit
cleanup() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo -e "\n${YELLOW}Stopping server (PID: $PID)...${NC}"
            kill $PID 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
    fi
}

# Set up signal handlers
trap cleanup EXIT INT TERM

# Initialize variables
retry_count=0
consecutive_failures=0
delay=$RESTART_DELAY

# Main restart loop
while true; do
    # Start timestamp
    START_TIME=$(date +%s)

    echo -e "${GREEN}Starting server (attempt $((retry_count + 1)))...${NC}"

    # Run the server
    $PYTHON src/postgres_memory_server.py "$MODE" 2>&1 | tee -a "$LOG_DIR/mcp-server-$(date +%Y%m%d).log" &
    SERVER_PID=$!
    echo $SERVER_PID > "$PID_FILE"

    # Wait for the server process
    wait $SERVER_PID
    EXIT_CODE=$?

    # Calculate run duration
    END_TIME=$(date +%s)
    RUN_DURATION=$((END_TIME - START_TIME))

    # Remove PID file
    rm -f "$PID_FILE"

    # Check exit code
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}✅ Server exited cleanly${NC}"
        break
    elif [ $EXIT_CODE -eq 130 ] || [ $EXIT_CODE -eq 143 ]; then
        # 130 = SIGINT (Ctrl+C), 143 = SIGTERM
        echo -e "${YELLOW}Server stopped by signal${NC}"
        break
    else
        echo -e "${RED}❌ Server crashed with exit code $EXIT_CODE${NC}"

        # If server ran for more than 5 minutes, reset the failure counter
        if [ $RUN_DURATION -gt 300 ]; then
            echo -e "${GREEN}Server ran for $(($RUN_DURATION / 60)) minutes, resetting failure counter${NC}"
            consecutive_failures=0
            delay=$RESTART_DELAY
        else
            consecutive_failures=$((consecutive_failures + 1))
        fi

        # Check if we've exceeded max retries
        retry_count=$((retry_count + 1))
        if [ $retry_count -ge $MAX_RETRIES ]; then
            echo -e "${RED}❌ Maximum retry limit ($MAX_RETRIES) reached. Giving up.${NC}"
            exit 1
        fi

        # Check for rapid consecutive failures
        if [ $consecutive_failures -ge 3 ]; then
            echo -e "${YELLOW}⚠️  Multiple rapid failures detected, increasing delay${NC}"
            delay=$((delay * BACKOFF_MULTIPLIER))
            if [ $delay -gt $MAX_DELAY ]; then
                delay=$MAX_DELAY
            fi
        fi

        echo -e "${YELLOW}Restarting in $delay seconds... (retry $retry_count/$MAX_RETRIES)${NC}"
        sleep $delay
    fi
done

echo -e "${GREEN}✅ Server shutdown complete${NC}"
#!/bin/bash
# Management script for MCP Memory Server
# Provides unified interface for macOS and Linux

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Get the script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Detect OS
OS_TYPE="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS_TYPE="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS_TYPE="linux"
fi

# Service names
HTTP_SERVICE="com.localmemory.mcp.http"
STDIO_SERVICE="com.localmemory.mcp.stdio"
SYSTEMD_SERVICE="localmemory-mcp"

# Function to show usage
usage() {
    echo -e "${BLUE}MCP Memory Server Management${NC}"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  start      Start the MCP server"
    echo "  stop       Stop the MCP server"
    echo "  restart    Restart the MCP server"
    echo "  status     Show server status"
    echo "  logs       Tail server logs"
    echo "  test       Test crash recovery"
    echo "  health     Check server health"
    echo "  clean      Clean logs and temp files"
    echo ""
    echo "Options:"
    echo "  --http     Operate on HTTP server only"
    echo "  --stdio    Operate on stdio server only"
    echo "  --all      Operate on all servers (default)"
    echo ""
    echo "Examples:"
    echo "  $0 start               # Start all servers"
    echo "  $0 status --http       # Check HTTP server status"
    echo "  $0 logs                # Tail all logs"
    echo "  $0 test                # Test crash recovery"
}

# macOS functions
macos_start() {
    local service=$1
    echo -e "${YELLOW}Starting $service...${NC}"
    launchctl load "$HOME/Library/LaunchAgents/${service}.plist" 2>/dev/null || {
        echo -e "${YELLOW}Service might already be running${NC}"
    }
}

macos_stop() {
    local service=$1
    echo -e "${YELLOW}Stopping $service...${NC}"
    launchctl unload "$HOME/Library/LaunchAgents/${service}.plist" 2>/dev/null || {
        echo -e "${YELLOW}Service might not be running${NC}"
    }
}

macos_status() {
    echo -e "${BLUE}macOS Service Status:${NC}"
    launchctl list | grep -E "localmemory|PID" || echo "No services found"

    # Check if processes are running
    echo ""
    echo -e "${BLUE}Running Processes:${NC}"
    ps aux | grep -E "postgres_memory_server|PID" | grep -v grep || echo "No processes found"
}

# Linux functions
linux_start() {
    echo -e "${YELLOW}Starting systemd service...${NC}"
    sudo systemctl start $SYSTEMD_SERVICE
}

linux_stop() {
    echo -e "${YELLOW}Stopping systemd service...${NC}"
    sudo systemctl stop $SYSTEMD_SERVICE
}

linux_status() {
    echo -e "${BLUE}Linux Service Status:${NC}"
    sudo systemctl status $SYSTEMD_SERVICE --no-pager || true
}

# Start command
cmd_start() {
    echo -e "${GREEN}🚀 Starting MCP Memory Server${NC}"

    if [ "$OS_TYPE" == "macos" ]; then
        if [ "$SERVER_TYPE" == "http" ] || [ "$SERVER_TYPE" == "all" ]; then
            macos_start "$HTTP_SERVICE"
        fi
        if [ "$SERVER_TYPE" == "stdio" ] || [ "$SERVER_TYPE" == "all" ]; then
            echo -e "${BLUE}ℹ️  stdio server is started by Claude Code${NC}"
        fi
    elif [ "$OS_TYPE" == "linux" ]; then
        linux_start
    else
        # Fallback to direct execution
        echo -e "${YELLOW}Starting with wrapper script...${NC}"
        "$PROJECT_ROOT/scripts/run_with_restart.sh" http &
        echo $! > "$PROJECT_ROOT/memory-server.pid"
        echo -e "${GREEN}✅ Server started (PID: $(cat "$PROJECT_ROOT/memory-server.pid"))${NC}"
    fi
}

# Stop command
cmd_stop() {
    echo -e "${RED}🛑 Stopping MCP Memory Server${NC}"

    if [ "$OS_TYPE" == "macos" ]; then
        if [ "$SERVER_TYPE" == "http" ] || [ "$SERVER_TYPE" == "all" ]; then
            macos_stop "$HTTP_SERVICE"
        fi
        if [ "$SERVER_TYPE" == "stdio" ] || [ "$SERVER_TYPE" == "all" ]; then
            macos_stop "$STDIO_SERVICE"
        fi
    elif [ "$OS_TYPE" == "linux" ]; then
        linux_stop
    else
        # Fallback to kill process
        if [ -f "$PROJECT_ROOT/memory-server.pid" ]; then
            PID=$(cat "$PROJECT_ROOT/memory-server.pid")
            kill $PID 2>/dev/null || true
            rm -f "$PROJECT_ROOT/memory-server.pid"
            echo -e "${GREEN}✅ Server stopped${NC}"
        else
            pkill -f "postgres_memory_server" || echo "No running server found"
        fi
    fi
}

# Restart command
cmd_restart() {
    echo -e "${YELLOW}🔄 Restarting MCP Memory Server${NC}"
    cmd_stop
    sleep 2
    cmd_start
}

# Status command
cmd_status() {
    echo -e "${BLUE}📊 MCP Memory Server Status${NC}"
    echo "----------------------------------------"

    if [ "$OS_TYPE" == "macos" ]; then
        macos_status
    elif [ "$OS_TYPE" == "linux" ]; then
        linux_status
    else
        # Generic status check
        echo -e "${BLUE}Processes:${NC}"
        ps aux | grep postgres_memory_server | grep -v grep || echo "No processes found"
    fi

    # Check HTTP endpoint
    echo ""
    echo -e "${BLUE}HTTP Endpoint Test:${NC}"
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ HTTP server is responding${NC}"
        curl -s http://localhost:8000/health | python3 -m json.tool
    else
        echo -e "${RED}❌ HTTP server is not responding${NC}"
    fi
}

# Logs command
cmd_logs() {
    echo -e "${BLUE}📝 Tailing MCP Memory Server Logs${NC}"
    echo "----------------------------------------"

    LOG_DIR="$PROJECT_ROOT/logs"

    if [ "$OS_TYPE" == "linux" ] && [ -f /etc/systemd/system/$SYSTEMD_SERVICE.service ]; then
        # Use journalctl for systemd
        sudo journalctl -u $SYSTEMD_SERVICE -f
    else
        # Tail log files
        if [ -f "$LOG_DIR/mcp-http.log" ] || [ -f "$LOG_DIR/mcp-server-$(date +%Y%m%d).log" ]; then
            echo -e "${YELLOW}Press Ctrl+C to stop tailing logs${NC}"
            tail -f "$LOG_DIR"/*.log 2>/dev/null || tail -f "$LOG_DIR"/*.log
        else
            echo -e "${YELLOW}No log files found in $LOG_DIR${NC}"
        fi
    fi
}

# Test crash recovery
cmd_test() {
    echo -e "${MAGENTA}🧪 Testing Crash Recovery${NC}"
    echo "----------------------------------------"

    # Start the server if not running
    echo -e "${YELLOW}Ensuring server is running...${NC}"
    cmd_start
    sleep 3

    # Get current PID
    CURRENT_PID=$(pgrep -f "postgres_memory_server" | head -n 1)
    if [ -z "$CURRENT_PID" ]; then
        echo -e "${RED}❌ No server process found${NC}"
        exit 1
    fi

    echo -e "${BLUE}Current server PID: $CURRENT_PID${NC}"

    # Test 1: Kill with SIGTERM (graceful)
    echo ""
    echo -e "${YELLOW}Test 1: Graceful shutdown (SIGTERM)${NC}"
    kill -TERM $CURRENT_PID
    sleep 2

    # Check if restarted
    NEW_PID=$(pgrep -f "postgres_memory_server" | head -n 1)
    if [ -n "$NEW_PID" ] && [ "$NEW_PID" != "$CURRENT_PID" ]; then
        echo -e "${GREEN}✅ Server restarted (new PID: $NEW_PID)${NC}"
    else
        echo -e "${RED}❌ Server did not restart${NC}"
    fi

    # Test 2: Kill with SIGKILL (crash)
    echo ""
    echo -e "${YELLOW}Test 2: Simulated crash (SIGKILL)${NC}"
    CURRENT_PID=$(pgrep -f "postgres_memory_server" | head -n 1)
    if [ -n "$CURRENT_PID" ]; then
        kill -9 $CURRENT_PID
        sleep 5

        NEW_PID=$(pgrep -f "postgres_memory_server" | head -n 1)
        if [ -n "$NEW_PID" ] && [ "$NEW_PID" != "$CURRENT_PID" ]; then
            echo -e "${GREEN}✅ Server recovered from crash (new PID: $NEW_PID)${NC}"
        else
            echo -e "${RED}❌ Server did not recover from crash${NC}"
        fi
    fi

    # Test 3: Database table drop recovery
    echo ""
    echo -e "${YELLOW}Test 3: Database table drop recovery${NC}"
    python3 <<EOF
import psycopg2
import time

try:
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="postgres",
        user="postgres",
        password="postgres"
    )
    cur = conn.cursor()

    # Drop a table
    cur.execute("DROP TABLE IF EXISTS test_memories CASCADE")
    conn.commit()
    print("Table dropped")

    # Wait a moment
    time.sleep(2)

    # Try to use the server (it should recreate the table)
    import requests
    response = requests.post(
        "http://localhost:8000/remember",
        json={
            "domain": "test",
            "content": "Test memory after table drop",
            "metadata": {"test": True}
        }
    )

    if response.status_code == 200:
        print("✅ Server successfully handled table recreation")
    else:
        print(f"❌ Server failed: {response.status_code}")

except Exception as e:
    print(f"Test error: {e}")
EOF

    echo ""
    echo -e "${GREEN}🎉 Crash recovery tests complete${NC}"
}

# Health check command
cmd_health() {
    echo -e "${BLUE}🏥 Server Health Check${NC}"
    echo "----------------------------------------"

    # Check HTTP health endpoint
    echo -e "${YELLOW}Checking HTTP health endpoint...${NC}"
    HEALTH_RESPONSE=$(curl -s http://localhost:8000/health 2>/dev/null)

    if [ $? -eq 0 ] && [ -n "$HEALTH_RESPONSE" ]; then
        echo -e "${GREEN}✅ Server is healthy${NC}"
        echo "$HEALTH_RESPONSE" | python3 -m json.tool

        # Check database connectivity
        echo ""
        echo -e "${YELLOW}Testing database operation...${NC}"
        TEST_RESPONSE=$(curl -s -X POST http://localhost:8000/search \
            -H "Content-Type: application/json" \
            -d '{"domain": "health_check", "limit": 1}' 2>/dev/null)

        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ Database operations working${NC}"
        else
            echo -e "${RED}❌ Database operations failed${NC}"
        fi
    else
        echo -e "${RED}❌ Server is not responding${NC}"

        # Check if process exists
        if pgrep -f "postgres_memory_server" > /dev/null; then
            echo -e "${YELLOW}Process is running but not responding on HTTP${NC}"
        else
            echo -e "${RED}No server process found${NC}"
        fi
    fi
}

# Clean command
cmd_clean() {
    echo -e "${YELLOW}🧹 Cleaning logs and temporary files${NC}"

    # Clean old logs (keep last 7 days)
    if [ -d "$PROJECT_ROOT/logs" ]; then
        find "$PROJECT_ROOT/logs" -type f -name "*.log" -mtime +7 -delete
        echo -e "${GREEN}✅ Old logs cleaned${NC}"
    fi

    # Clean Python cache
    find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$PROJECT_ROOT" -type f -name "*.pyc" -delete 2>/dev/null || true
    echo -e "${GREEN}✅ Python cache cleaned${NC}"

    # Clean PID files
    rm -f "$PROJECT_ROOT"/*.pid
    echo -e "${GREEN}✅ PID files cleaned${NC}"
}

# Parse arguments
COMMAND=${1:-}
SERVER_TYPE="all"

# Parse options
shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --http)
            SERVER_TYPE="http"
            shift
            ;;
        --stdio)
            SERVER_TYPE="stdio"
            shift
            ;;
        --all)
            SERVER_TYPE="all"
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

# Execute command
case "$COMMAND" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    status)
        cmd_status
        ;;
    logs)
        cmd_logs
        ;;
    test)
        cmd_test
        ;;
    health)
        cmd_health
        ;;
    clean)
        cmd_clean
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        usage
        exit 1
        ;;
esac
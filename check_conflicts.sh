#!/bin/bash
# Simple conflict checker for memory servers

echo "🔍 Checking for Memory Server Conflicts"
echo "======================================="

# Check for running processes
echo "🔄 Checking running processes..."
RUNNING_PROCESSES=$(ps aux | grep -E "(bridge_server|dev_server|daemon_server)" | grep -v grep)

if [ -n "$RUNNING_PROCESSES" ]; then
    echo "⚠️  Found running memory servers:"
    echo "$RUNNING_PROCESSES" | while read line; do
        echo "   $line"
    done
else
    echo "✅ No memory servers currently running"
fi

# Check port usage
echo ""
echo "🌐 Checking port 8000..."
PORT_USERS=$(lsof -i :8000 2>/dev/null)

if [ -n "$PORT_USERS" ]; then
    echo "⚠️  Port 8000 is in use:"
    echo "$PORT_USERS" | while read line; do
        echo "   $line"
    done
else
    echo "✅ Port 8000 is available"
fi

# Check PID files
echo ""
echo "📄 Checking PID files..."
PID_FILES=("memory-server.pid" "memory-daemon.pid")
STALE_FILES=()

for pid_file in "${PID_FILES[@]}"; do
    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$PID" ] && ps -p "$PID" > /dev/null 2>&1; then
            echo "✅ $pid_file: PID $PID is running"
        else
            echo "🧹 $pid_file: PID $PID is stale (will be cleaned up)"
            STALE_FILES+=("$pid_file")
        fi
    else
        echo "ℹ️  $pid_file: Not found"
    fi
done

# Check server response
echo ""
echo "🔍 Checking server response..."
if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "✅ Server is responding at http://localhost:8000"
else
    echo "❌ No server responding at http://localhost:8000"
fi

# Summary
echo ""
echo "📊 Summary:"
SERVER_COUNT=$(echo "$RUNNING_PROCESSES" | wc -l | tr -d ' ')

if [ "$SERVER_COUNT" -gt 1 ]; then
    echo "⚠️  CONFLICT DETECTED: Multiple servers running ($SERVER_COUNT)"
    echo "   Run './stop_all_servers.sh' to stop all servers"
elif [ "$SERVER_COUNT" -eq 1 ]; then
    echo "✅ One server running (no conflicts)"
elif [ -n "$PORT_USERS" ]; then
    echo "⚠️  Port 8000 in use but no memory server processes found"
    echo "   Another application may be using the port"
else
    echo "✅ No conflicts - ready to start server"
fi

# Clean up stale PID files
if [ ${#STALE_FILES[@]} -gt 0 ]; then
    echo ""
    echo "🧹 Cleaning up stale PID files..."
    for file in "${STALE_FILES[@]}"; do
        rm -f "$file"
        echo "   Removed: $file"
    done
fi

#!/bin/bash
# Stop memory server daemon

echo "🛑 Stopping Memory Server Daemon"
echo "================================="

# Check if PID file exists
if [ -f "memory-daemon.pid" ]; then
    PID=$(cat memory-daemon.pid)
    
    # Check if process is still running
    if ps -p $PID > /dev/null 2>&1; then
        echo "🔄 Stopping daemon (PID: $PID)..."
        kill $PID
        
        # Wait for graceful shutdown
        sleep 3
        
        # Force kill if still running
        if ps -p $PID > /dev/null 2>&1; then
            echo "⚡ Force stopping daemon..."
            kill -9 $PID
        fi
        
        echo "✅ Daemon stopped"
    else
        echo "ℹ️  Daemon was not running"
    fi
    
    # Remove PID file
    rm -f memory-daemon.pid
else
    echo "ℹ️  No PID file found. Checking for running daemons..."
    
    # Find and kill any running daemon processes
    PIDS=$(ps aux | grep "daemon_server.py" | grep -v grep | awk '{print $2}')
    
    if [ -n "$PIDS" ]; then
        echo "🔄 Found running daemons, stopping..."
        echo $PIDS | xargs kill
        sleep 2
        echo "✅ Daemons stopped"
    else
        echo "ℹ️  No daemon processes found"
    fi
fi

# Verify server is stopped
if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "⚠️  Server may still be running. Check manually:"
    echo "   ps aux | grep daemon_server"
else
    echo "✅ Server is stopped"
fi

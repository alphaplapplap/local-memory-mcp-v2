#!/bin/bash
# Stop persistent memory server

echo "🛑 Stopping Memory Server"
echo "========================="

# Check if PID file exists
if [ -f "memory-server.pid" ]; then
    PID=$(cat memory-server.pid)
    
    # Check if process is still running
    if ps -p $PID > /dev/null 2>&1; then
        echo "🔄 Stopping server (PID: $PID)..."
        kill $PID
        
        # Wait for graceful shutdown
        sleep 2
        
        # Force kill if still running
        if ps -p $PID > /dev/null 2>&1; then
            echo "⚡ Force stopping server..."
            kill -9 $PID
        fi
        
        echo "✅ Server stopped"
    else
        echo "ℹ️  Server was not running"
    fi
    
    # Remove PID file
    rm -f memory-server.pid
else
    echo "ℹ️  No PID file found. Checking for running processes..."
    
    # Find and kill any running memory servers
    PIDS=$(ps aux | grep -E "(bridge_server|dev_server)" | grep -v grep | awk '{print $2}')
    
    if [ -n "$PIDS" ]; then
        echo "🔄 Found running servers, stopping..."
        echo $PIDS | xargs kill
        sleep 2
        echo "✅ Servers stopped"
    else
        echo "ℹ️  No memory servers found running"
    fi
fi

# Verify server is stopped
if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "⚠️  Server may still be running. Check manually:"
    echo "   ps aux | grep bridge_server"
else
    echo "✅ Server is stopped"
fi

#!/bin/bash
# Stop all memory servers and clean up

echo "🛑 Stopping All Memory Servers"
echo "=============================="

# Stop daemon server
if [ -f "stop_daemon.sh" ]; then
    echo "🔄 Stopping daemon server..."
    ./stop_daemon.sh
fi

# Stop persistent server
if [ -f "stop_persistent.sh" ]; then
    echo "🔄 Stopping persistent server..."
    ./stop_persistent.sh
fi

# Kill any remaining memory server processes
echo "🔄 Checking for remaining processes..."
REMAINING_PIDS=$(ps aux | grep -E "(bridge_server|dev_server|daemon_server)" | grep -v grep | awk '{print $2}')

if [ -n "$REMAINING_PIDS" ]; then
    echo "⚡ Force stopping remaining processes..."
    echo $REMAINING_PIDS | xargs kill -9
    sleep 1
    echo "✅ All processes stopped"
else
    echo "✅ No remaining processes found"
fi

# Clean up PID files
echo "🧹 Cleaning up PID files..."
rm -f memory-server.pid memory-daemon.pid

# Verify everything is stopped
echo "🔍 Verifying all servers are stopped..."
if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "⚠️  Server may still be responding. Check manually:"
    echo "   ps aux | grep -E '(bridge_server|dev_server|daemon_server)'"
else
    echo "✅ All servers stopped successfully"
fi

#!/bin/bash
# Start memory server as a background daemon

echo "🚀 Starting Memory Server Daemon"
echo "================================="

# Check for conflicts first
echo "🔍 Checking for conflicts..."
./check_conflicts.sh > /dev/null 2>&1
CONFLICT_STATUS=$?

if [ $CONFLICT_STATUS -ne 0 ]; then
    echo "⚠️  Conflicts detected. Run './check_conflicts.sh' for details."
    echo "   Or run './stop_all_servers.sh' to stop all servers first."
    exit 1
fi

# Check if daemon is already running
if [ -f "memory-daemon.pid" ]; then
    PID=$(cat memory-daemon.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ Memory server daemon is already running (PID: $PID)"
        echo "🌐 Server URL: http://localhost:8000"
        exit 0
    else
        echo "🧹 Cleaning up stale PID file..."
        rm -f memory-daemon.pid
    fi
fi

# Check if server is responding
if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "✅ Memory server is already running at http://localhost:8000"
    exit 0
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please run setup first."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if database is running
echo "🔍 Checking database connection..."
if ! psql -h localhost -p 5432 -U postgres -d memory_db -c "SELECT 1;" >/dev/null 2>&1; then
    echo "❌ Database connection failed. Please ensure PostgreSQL is running."
    echo "   You can start it with: brew services start postgresql@17"
    exit 1
fi

echo "✅ Database connection successful"

# Start the daemon completely detached
echo "🔄 Starting daemon in background..."

# Create a script that properly daemonizes with venv
cat > /tmp/start_memory_daemon.sh << EOF
#!/bin/bash
cd "$1"
# Activate virtual environment if it exists
if [ -d "venv/bin" ]; then
    source venv/bin/activate
fi
exec python3 daemon_server.py > logs/daemon-startup.log 2>&1 < /dev/null
EOF
chmod +x /tmp/start_memory_daemon.sh

# Start daemon with nohup and setsid for complete detachment
nohup setsid /tmp/start_memory_daemon.sh "$(pwd)" >/dev/null 2>&1 &
DAEMON_PID=$!
disown

# Clean up temp script after a brief delay
(sleep 2; rm -f /tmp/start_memory_daemon.sh) &

# Give it a moment to start
sleep 5

# Quick verification without long wait
echo "⏳ Verifying daemon startup..."
if [ -f "memory-daemon.pid" ]; then
    PID=$(cat memory-daemon.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ Memory server daemon started successfully!"
        echo "🌐 Server URL: http://localhost:8000"
        echo "📋 Daemon PID: $PID"
        echo "📄 Logs: tail -f logs/memory-daemon.log"
        echo ""
        echo "🛑 To stop: ./stop_daemon.sh"
        exit 0
    fi
fi

# If no PID file yet, still exit successfully - daemon is starting
echo "🔄 Daemon is starting in background..."
echo "📄 Check status: curl http://localhost:8000/api/health"
echo "📄 View logs: tail -f logs/daemon-startup.log"
echo "🛑 To stop: ./stop_daemon.sh"
exit 0

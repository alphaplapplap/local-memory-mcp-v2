#!/bin/bash
# Start memory server persistently (survives terminal closure)

echo "🚀 Starting Memory Server (Persistent Mode)"
echo "==========================================="

# Check if server is already running
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

# Set environment variables
export POSTGRES_DB=memory_db
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=postgres
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export OLLAMA_API_URL=http://localhost:11434
export OLLAMA_EMBEDDING_MODEL=nomic-embed-text:v1.5
export ENVIRONMENT=production
export LOG_LEVEL=INFO

# Start the server in background with nohup
echo "🔄 Starting server in background..."
nohup python bridge_server.py > logs/memory-server-persistent.log 2>&1 &

# Get the process ID
SERVER_PID=$!
echo $SERVER_PID > memory-server.pid

echo "⏳ Waiting for server to start..."

# Wait for server to start with progress indicator
for i in {1..10}; do
    if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
        break
    fi
    echo -n "."
    sleep 1
done
echo ""

# Check if server started successfully
if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "✅ Memory server started successfully!"
    echo "🌐 Server URL: http://localhost:8000"
    echo "📊 Health Check: http://localhost:8000/api/health"
    echo "📋 Process ID: $SERVER_PID"
    echo "📄 Logs: tail -f logs/memory-server-persistent.log"
    echo ""
    echo "🛑 To stop the server:"
    echo "   ./stop_persistent.sh"
    echo "   or: kill $SERVER_PID"
else
    echo "❌ Failed to start memory server"
    echo "📄 Check logs: cat logs/memory-server-persistent.log"
    exit 1
fi

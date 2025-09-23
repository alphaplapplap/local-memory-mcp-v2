#!/bin/bash
# Development server startup script

echo "🚀 Starting Memory System Development Server"
echo "=============================================="

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
export ENVIRONMENT=development
export DEBUG=true
export LOG_LEVEL=DEBUG

# Start the development server
echo "🔄 Starting server with hot reloading..."
python dev_server.py

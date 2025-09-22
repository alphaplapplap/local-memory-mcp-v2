#!/bin/bash
set -e

echo "🧠 Setting up Local Memory MCP System..."
echo "========================================"

# Check if running as script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 1. Check prerequisites
echo "📋 Checking prerequisites..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

if ! command -v psql &> /dev/null; then
    echo "❌ PostgreSQL is required but not installed"
    exit 1
fi

if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is required but not installed"
    echo "   Install from: https://ollama.ai"
    exit 1
fi
echo "✅ All prerequisites found"

# 2. Create virtual environment
echo ""
echo "🐍 Setting up Python environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Created virtual environment"
fi
source venv/bin/activate
pip install -q -r requirements.txt
echo "✅ Python packages installed"

# 3. Start Ollama and pull model
echo ""
echo "🤖 Setting up Ollama..."
# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Starting Ollama service..."
    ollama serve > /dev/null 2>&1 &
    sleep 5
fi

# Pull embedding model
echo "Pulling nomic-embed-text:v1.5 model (this may take a few minutes)..."
ollama pull nomic-embed-text:v1.5
echo "✅ Ollama model ready"

# 4. Setup PostgreSQL with pgvector
echo ""
echo "🗄️  Setting up PostgreSQL..."

# Check if PostgreSQL is running
if ! pg_isready -q; then
    echo "❌ PostgreSQL is not running. Please start it first."
    exit 1
fi

# Create pgvector extension
echo "Creating pgvector extension..."
psql -U postgres -d postgres -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || {
    echo "⚠️  Could not create pgvector extension. It may already exist."
}

# Create memory tables
echo "Creating memory tables..."
python3 -c "
import sys
sys.path.insert(0, 'src')
from postgres_memory_api import PostgresMemoryAPI
from ollama_embeddings import OllamaEmbeddings
from dotenv import load_dotenv
import os

load_dotenv()

try:
    # Initialize without embeddings first to create tables
    memory_api = PostgresMemoryAPI(ollama_embeddings=None)

    # Create default domains
    domains = ['default', 'system', 'startup', 'health', 'personal', 'sentient-library-universal']
    for domain in domains:
        memory_api._ensure_table_exists(domain)
        print(f'  ✅ Created {domain}_memories table')

except Exception as e:
    print(f'  ⚠️  Tables may already exist: {e}')
"
echo "✅ PostgreSQL configured"

# 5. Initialize system memories
echo ""
echo "📚 Creating system memories..."
python3 setup_system_memories.py

# 6. Add test memories for demonstration
echo ""
echo "📝 Adding test memories..."
python3 add_test_memories.py

# 7. Setup Claude hooks (if Claude directory exists)
if [ -d "$HOME/.claude" ]; then
    echo ""
    echo "🪝 Setting up Claude hooks..."

    # Create hooks directory structure
    mkdir -p "$HOME/.claude/hooks/core"
    mkdir -p "$HOME/.claude/hooks/utilities"

    # Copy hook files if they don't exist
    if [ ! -f "$HOME/.claude/hooks/config.json" ]; then
        cp hooks/config.json "$HOME/.claude/hooks/config.json"
        echo "  ✅ Copied hooks configuration"
    else
        echo "  ⚠️  Hooks config already exists, skipping"
    fi

    # Copy core hooks
    for hook in session-start.js session-end.js memory-retrieval.js topic-change.js; do
        if [ -f "hooks/core/$hook" ]; then
            cp "hooks/core/$hook" "$HOME/.claude/hooks/core/$hook"
            echo "  ✅ Installed $hook"
        fi
    done

    # Copy utilities
    for util in http-adapter.js memory-scorer.js context-formatter.js project-detector.js git-analyzer.js; do
        if [ -f "hooks/utilities/$util" ]; then
            cp "hooks/utilities/$util" "$HOME/.claude/hooks/utilities/$util"
            echo "  ✅ Installed $util"
        fi
    done

    echo "✅ Claude hooks installed"
else
    echo ""
    echo "⚠️  Claude directory not found, skipping hooks installation"
fi

# 8. Start bridge server
echo ""
echo "🌉 Starting bridge server..."
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "  ⚠️  Port 8000 already in use, skipping bridge server"
else
    nohup python3 bridge_server.py > bridge_server.log 2>&1 &
    BRIDGE_PID=$!
    sleep 3

    # Check if bridge server started successfully
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "  ✅ Bridge server running on port 8000 (PID: $BRIDGE_PID)"
        echo "  📄 Logs: tail -f bridge_server.log"
    else
        echo "  ❌ Bridge server failed to start"
        echo "  Check bridge_server.log for details"
    fi
fi

# 9. Run comprehensive test
echo ""
echo "🧪 Running system test..."
python3 test_memory_config.py

# 10. Create management scripts
echo ""
echo "📝 Creating management scripts..."

# Create start script
cat > start_memory_system.sh << 'EOF'
#!/bin/bash
echo "Starting memory system services..."

# Start Ollama if not running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Starting Ollama..."
    ollama serve > /dev/null 2>&1 &
    sleep 3
fi

# Start bridge server if not running
if ! lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null; then
    echo "Starting bridge server..."
    source venv/bin/activate
    nohup python bridge_server.py > bridge_server.log 2>&1 &
    echo "Bridge server started (PID: $!)"
else
    echo "Bridge server already running"
fi

echo "✅ Memory system started"
EOF
chmod +x start_memory_system.sh

# Create stop script
cat > stop_memory_system.sh << 'EOF'
#!/bin/bash
echo "Stopping memory system services..."

# Stop bridge server
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null; then
    PID=$(lsof -Pi :8000 -sTCP:LISTEN -t)
    kill $PID
    echo "Stopped bridge server (PID: $PID)"
fi

echo "✅ Memory system stopped"
EOF
chmod +x stop_memory_system.sh

echo "  ✅ Created start_memory_system.sh"
echo "  ✅ Created stop_memory_system.sh"

# 11. Display summary
echo ""
echo "========================================"
echo "✅ Memory system setup complete!"
echo ""
echo "📊 System Status:"
echo "  • Ollama: Running with nomic-embed-text:v1.5"
echo "  • PostgreSQL: Configured with pgvector"
echo "  • Bridge Server: http://localhost:8000"
echo "  • Memory Domains: $(python3 -c 'import sys; sys.path.insert(0, "src"); from postgres_memory_api import PostgresMemoryAPI; api = PostgresMemoryAPI(); print(len(api.list_domains()))')"
echo "  • Total Memories: $(python3 -c 'import sys; sys.path.insert(0, "src"); from postgres_memory_api import PostgresMemoryAPI; api = PostgresMemoryAPI(); print(sum(len(api.retrieve_memories("", domain=d, limit=1000)) for d in api.list_domains()))')"
echo ""
echo "🚀 Quick Start Commands:"
echo "  • Start system: ./start_memory_system.sh"
echo "  • Stop system: ./stop_memory_system.sh"
echo "  • Test system: python test_memory_config.py"
echo "  • View logs: tail -f bridge_server.log"
echo ""
echo "📚 MCP Tools Available:"
echo "  • store_memory - Store new memories"
echo "  • search_memories - Semantic search"
echo "  • update_memory - Modify existing"
echo "  • list_memory_domains - View domains"
echo ""
echo "Happy memory management! 🧠"
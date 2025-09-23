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

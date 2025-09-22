#!/bin/bash
echo "Stopping memory system services..."

# Stop bridge server
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null; then
    PID=$(lsof -Pi :8000 -sTCP:LISTEN -t)
    kill $PID
    echo "Stopped bridge server (PID: $PID)"
fi

echo "✅ Memory system stopped"

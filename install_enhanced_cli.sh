#!/bin/bash

echo "🚀 Installing Enhanced Local Memory MCP CLI..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    python -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install click asyncpg fastapi uvicorn

# Make CLI accessible
chmod +x src/enhanced_cli/cli.py

# Create symlink for global access
ln -sf "$(pwd)/src/enhanced_cli/cli.py" /usr/local/bin/memory-enhanced

echo "✅ Installation complete!"
echo ""
echo "Usage examples:"
echo "  memory-enhanced store 'Important project decision' --domain=work --importance=0.9"
echo "  memory-enhanced search 'authentication' --domain=work --scored"
echo "  memory-enhanced --help"
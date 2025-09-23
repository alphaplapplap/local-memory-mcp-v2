#!/bin/bash
# Install memory server as a system service

echo "🔧 Installing Memory Server as System Service"
echo "=============================================="

# Check if running as root (needed for systemd)
if [ "$EUID" -eq 0 ]; then
    echo "❌ Don't run this script as root. Run as your regular user."
    exit 1
fi

# Check if systemd is available (Linux)
if command -v systemctl >/dev/null 2>&1; then
    echo "🐧 Linux systemd detected"
    
    # Copy service file
    sudo cp memory-server.service /etc/systemd/system/
    
    # Reload systemd
    sudo systemctl daemon-reload
    
    # Enable service
    sudo systemctl enable memory-server.service
    
    echo "✅ Service installed and enabled"
    echo "📋 Commands:"
    echo "   Start:   sudo systemctl start memory-server"
    echo "   Stop:    sudo systemctl stop memory-server"
    echo "   Status:  sudo systemctl status memory-server"
    echo "   Logs:    sudo journalctl -u memory-server -f"
    
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "🍎 macOS detected - using launchd"
    
    # Create launchd plist
    cat > ~/Library/LaunchAgents/com.localmemory.mcp.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.localmemory.mcp</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/linuxbabe/local-memory-mcp/venv/bin/python</string>
        <string>/Users/linuxbabe/local-memory-mcp/bridge_server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/linuxbabe/local-memory-mcp</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>POSTGRES_DB</key>
        <string>memory_db</string>
        <key>POSTGRES_USER</key>
        <string>postgres</string>
        <key>POSTGRES_PASSWORD</key>
        <string>postgres</string>
        <key>POSTGRES_HOST</key>
        <string>localhost</string>
        <key>POSTGRES_PORT</key>
        <string>5432</string>
        <key>OLLAMA_API_URL</key>
        <string>http://localhost:11434</string>
        <key>OLLAMA_EMBEDDING_MODEL</key>
        <string>nomic-embed-text:v1.5</string>
        <key>ENVIRONMENT</key>
        <string>production</string>
        <key>LOG_LEVEL</key>
        <string>INFO</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/linuxbabe/local-memory-mcp/logs/memory-server.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/linuxbabe/local-memory-mcp/logs/memory-server-error.log</string>
</dict>
</plist>
EOF
    
    # Load the service
    launchctl load ~/Library/LaunchAgents/com.localmemory.mcp.plist
    
    echo "✅ Service installed and started"
    echo "📋 Commands:"
    echo "   Start:   launchctl start com.localmemory.mcp"
    echo "   Stop:    launchctl stop com.localmemory.mcp"
    echo "   Status:  launchctl list | grep com.localmemory.mcp"
    echo "   Logs:    tail -f /Users/linuxbabe/local-memory-mcp/logs/memory-server.log"
    
else
    echo "❌ Unsupported operating system: $OSTYPE"
    echo "   Please install manually or use the development server"
    exit 1
fi

echo ""
echo "🎉 Memory server will now start automatically on boot!"
echo "🌐 Server will be available at: http://localhost:8000"

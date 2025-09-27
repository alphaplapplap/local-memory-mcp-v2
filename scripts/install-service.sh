#!/bin/bash
# Installation script for MCP Memory Server with automatic recovery
# Supports both macOS (launchd) and Linux (systemd)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Detect OS
OS_TYPE="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS_TYPE="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS_TYPE="linux"
else
    echo -e "${RED}❌ Unsupported OS: $OSTYPE${NC}"
    exit 1
fi

echo -e "${BLUE}🚀 Installing MCP Memory Server with Automatic Recovery${NC}"
echo -e "OS: ${YELLOW}$OS_TYPE${NC}"
echo -e "Project Root: ${YELLOW}$PROJECT_ROOT${NC}"
echo "----------------------------------------"

# Function to install on macOS
install_macos() {
    echo -e "${GREEN}📦 Installing for macOS (launchd)${NC}"

    # Check if running as user (not root)
    if [ "$EUID" -eq 0 ]; then
        echo -e "${RED}❌ Please run without sudo for user-level installation${NC}"
        exit 1
    fi

    # Create logs directory
    mkdir -p "$PROJECT_ROOT/logs"

    # Copy plist files to LaunchAgents
    LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
    mkdir -p "$LAUNCH_AGENTS_DIR"

    # Install HTTP server plist
    if [ -f "$PROJECT_ROOT/com.localmemory.mcp.http.plist" ]; then
        echo -e "${YELLOW}Installing HTTP server service...${NC}"

        # Update paths in plist
        sed "s|/Users/linuxbabe|$HOME|g" "$PROJECT_ROOT/com.localmemory.mcp.http.plist" > "$LAUNCH_AGENTS_DIR/com.localmemory.mcp.http.plist"

        # Load the service
        launchctl unload "$LAUNCH_AGENTS_DIR/com.localmemory.mcp.http.plist" 2>/dev/null || true
        launchctl load "$LAUNCH_AGENTS_DIR/com.localmemory.mcp.http.plist"

        echo -e "${GREEN}✅ HTTP server service installed${NC}"
    fi

    # Install stdio server plist (for MCP protocol)
    if [ -f "$PROJECT_ROOT/com.localmemory.mcp.stdio.plist" ]; then
        echo -e "${YELLOW}Installing MCP stdio server service...${NC}"

        # Update paths in plist
        sed "s|/Users/linuxbabe|$HOME|g" "$PROJECT_ROOT/com.localmemory.mcp.stdio.plist" > "$LAUNCH_AGENTS_DIR/com.localmemory.mcp.stdio.plist"

        # Note: stdio servers are typically started by Claude Code, not launchd
        echo -e "${BLUE}ℹ️  MCP stdio service configured (started by Claude Code)${NC}"
    fi

    echo -e "${GREEN}✅ macOS services installed successfully${NC}"
    echo ""
    echo "To manage services:"
    echo "  Start HTTP:  launchctl load ~/Library/LaunchAgents/com.localmemory.mcp.http.plist"
    echo "  Stop HTTP:   launchctl unload ~/Library/LaunchAgents/com.localmemory.mcp.http.plist"
    echo "  Status:      launchctl list | grep localmemory"
    echo ""
    echo "Logs are available at:"
    echo "  $PROJECT_ROOT/logs/mcp-http.log"
    echo "  $PROJECT_ROOT/logs/mcp-http.error.log"
}

# Function to install on Linux
install_linux() {
    echo -e "${GREEN}📦 Installing for Linux (systemd)${NC}"

    # Check if running as root/sudo
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}❌ Please run with sudo for system-level installation${NC}"
        exit 1
    fi

    # Create installation directory
    INSTALL_DIR="/opt/localmemory-mcp"
    echo -e "${YELLOW}Creating installation directory: $INSTALL_DIR${NC}"

    # Copy project files to installation directory
    rsync -av --exclude='.git' --exclude='venv' --exclude='*.pyc' --exclude='__pycache__' \
              --exclude='logs/*' "$PROJECT_ROOT/" "$INSTALL_DIR/"

    # Create logs directory
    mkdir -p "$INSTALL_DIR/logs"
    chmod 755 "$INSTALL_DIR/logs"

    # Make scripts executable
    chmod +x "$INSTALL_DIR/scripts/run_with_restart.sh"

    # Install systemd service
    if [ -f "$PROJECT_ROOT/localmemory-mcp.service" ]; then
        echo -e "${YELLOW}Installing systemd service...${NC}"

        # Copy service file
        cp "$PROJECT_ROOT/localmemory-mcp.service" /etc/systemd/system/

        # Reload systemd
        systemctl daemon-reload

        # Enable service to start on boot
        systemctl enable localmemory-mcp.service

        # Start the service
        systemctl start localmemory-mcp.service

        echo -e "${GREEN}✅ Systemd service installed and started${NC}"
    fi

    echo -e "${GREEN}✅ Linux service installed successfully${NC}"
    echo ""
    echo "To manage service:"
    echo "  Start:   sudo systemctl start localmemory-mcp"
    echo "  Stop:    sudo systemctl stop localmemory-mcp"
    echo "  Restart: sudo systemctl restart localmemory-mcp"
    echo "  Status:  sudo systemctl status localmemory-mcp"
    echo "  Logs:    sudo journalctl -u localmemory-mcp -f"
    echo ""
    echo "Log files are also available at:"
    echo "  $INSTALL_DIR/logs/mcp-systemd.log"
    echo "  $INSTALL_DIR/logs/mcp-systemd.error.log"
}

# Function to check Python dependencies
check_dependencies() {
    echo -e "${YELLOW}Checking dependencies...${NC}"

    # Check for Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python 3 not found. Please install Python 3.8+${NC}"
        exit 1
    fi

    # Check Python version
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo -e "Python version: ${GREEN}$PYTHON_VERSION${NC}"

    # Check for PostgreSQL
    if ! command -v psql &> /dev/null; then
        echo -e "${YELLOW}⚠️  PostgreSQL client not found. Make sure PostgreSQL is accessible${NC}"
    else
        echo -e "PostgreSQL: ${GREEN}Available${NC}"
    fi

    # Install Python dependencies
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    cd "$PROJECT_ROOT"

    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi

    # Activate venv and install dependencies
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt

    echo -e "${GREEN}✅ Dependencies installed${NC}"
}

# Main installation flow
main() {
    echo -e "${BLUE}=== MCP Memory Server Installation ===${NC}"

    # Check dependencies
    check_dependencies

    # Install based on OS
    case "$OS_TYPE" in
        macos)
            install_macos
            ;;
        linux)
            install_linux
            ;;
        *)
            echo -e "${RED}❌ Unsupported OS type: $OS_TYPE${NC}"
            exit 1
            ;;
    esac

    echo ""
    echo -e "${GREEN}🎉 Installation complete!${NC}"
    echo -e "${BLUE}The server will automatically restart on crashes.${NC}"
    echo -e "${BLUE}Check the logs for any issues.${NC}"
}

# Run main function
main "$@"
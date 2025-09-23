#!/usr/bin/env python3
"""
Installation script for Claude Code commands for Local Memory MCP.
Adapted from mcp-memory-service claude_commands_utils.py
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple


def print_info(text: str) -> None:
    """Print formatted info text."""
    print(f"  → {text}")


def print_error(text: str) -> None:
    """Print formatted error text."""
    print(f"  ❌ ERROR: {text}")


def print_success(text: str) -> None:
    """Print formatted success text."""
    print(f"  ✅ {text}")


def print_warning(text: str) -> None:
    """Print formatted warning text."""
    print(f"  ⚠️  {text}")


def check_claude_code_cli() -> Tuple[bool, Optional[str]]:
    """
    Check if Claude Code CLI is installed and available.

    Returns:
        Tuple of (is_available, version_or_error)
    """
    try:
        # Try to run claude --version
        result = subprocess.run(
            ['claude', '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            version = result.stdout.strip()
            return True, version
        else:
            return False, f"claude command failed: {result.stderr.strip()}"

    except subprocess.TimeoutExpired:
        return False, "claude command timed out"
    except FileNotFoundError:
        return False, "claude command not found in PATH"
    except Exception as e:
        return False, f"Error checking claude CLI: {str(e)}"


def get_claude_commands_directory() -> Path:
    """
    Get the Claude Code commands directory path.

    Returns:
        Path to ~/.claude/commands/
    """
    return Path.home() / ".claude" / "commands"


def get_claude_config_directory() -> Path:
    """
    Get the Claude Code config directory path.

    Returns:
        Path to ~/.claude/
    """
    return Path.home() / ".claude"


def check_commands_directory_access() -> Tuple[bool, str]:
    """
    Check if we can access and write to the Claude commands directory.

    Returns:
        Tuple of (can_access, status_message)
    """
    commands_dir = get_claude_commands_directory()

    try:
        # Check if directory exists
        if not commands_dir.exists():
            # Try to create it
            commands_dir.mkdir(parents=True, exist_ok=True)
            return True, f"Created commands directory: {commands_dir}"

        # Check if we can write to it
        test_file = commands_dir / ".test_write_access"
        try:
            test_file.write_text("test")
            test_file.unlink()
            return True, f"Commands directory accessible: {commands_dir}"
        except PermissionError:
            return False, f"No write permission to commands directory: {commands_dir}"

    except Exception as e:
        return False, f"Cannot access commands directory: {str(e)}"


def get_source_commands_directory() -> Path:
    """
    Get the source directory containing the command markdown files.

    Returns:
        Path to the claude_commands directory in this project
    """
    # Get the directory containing this script
    script_dir = Path(__file__).parent
    return script_dir / "claude_commands"


def list_available_commands() -> List[Dict[str, str]]:
    """
    List all available command files in the source directory.

    Returns:
        List of command info dictionaries
    """
    source_dir = get_source_commands_directory()
    commands = []

    if not source_dir.exists():
        return commands

    for md_file in source_dir.glob("*.md"):
        # Skip README files
        if md_file.name.lower() in ['readme.md']:
            continue

        # Extract command name from filename
        command_name = md_file.stem

        # Read the first line to get the description
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                # Remove markdown header formatting
                description = first_line.lstrip('# ').strip()
        except Exception:
            description = "Command description unavailable"

        commands.append({
            'name': command_name,
            'file': md_file.name,
            'description': description,
            'path': str(md_file)
        })

    return commands


def backup_existing_commands() -> Optional[str]:
    """
    Create a backup of existing command files before installation.

    Returns:
        Path to backup directory if backup was created, None otherwise
    """
    commands_dir = get_claude_commands_directory()

    if not commands_dir.exists():
        return None

    # Check if there are any existing memory-*.md files
    existing_commands = list(commands_dir.glob("memory-*.md"))
    if not existing_commands:
        return None

    # Create backup directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = commands_dir / f"backup_{timestamp}"

    try:
        backup_dir.mkdir(exist_ok=True)

        for cmd_file in existing_commands:
            shutil.copy2(cmd_file, backup_dir / cmd_file.name)

        print_info(f"Backed up {len(existing_commands)} existing commands to: {backup_dir}")
        return str(backup_dir)

    except Exception as e:
        print_error(f"Failed to create backup: {str(e)}")
        return None


def install_command_files() -> Tuple[bool, List[str]]:
    """
    Install command markdown files to the Claude commands directory.

    Returns:
        Tuple of (success, list_of_installed_files)
    """
    source_dir = get_source_commands_directory()
    commands_dir = get_claude_commands_directory()
    installed_files = []

    if not source_dir.exists():
        print_error(f"Source commands directory not found: {source_dir}")
        return False, []

    try:
        # Ensure destination directory exists
        commands_dir.mkdir(parents=True, exist_ok=True)

        # Copy all .md files except README
        for md_file in source_dir.glob("*.md"):
            if md_file.name.lower() == 'readme.md':
                continue

            dest_file = commands_dir / md_file.name
            shutil.copy2(md_file, dest_file)
            installed_files.append(md_file.name)
            print_info(f"Installed: {md_file.name}")

        if installed_files:
            print_success(f"Successfully installed {len(installed_files)} Claude Code commands")
            return True, installed_files
        else:
            print_warning("No command files found to install")
            return False, []

    except Exception as e:
        print_error(f"Failed to install command files: {str(e)}")
        return False, []


def update_claude_config() -> bool:
    """
    Update Claude Code configuration to include MCP server for local-memory-mcp.

    Returns:
        True if configuration was updated successfully, False otherwise
    """
    config_file = get_claude_config_directory() / "config.json"

    # Get the current script directory to build paths
    script_dir = Path(__file__).parent
    python_path = script_dir / "venv" / "bin" / "python"
    server_path = script_dir / "src" / "postgres_memory_server.py"

    # New MCP server configuration
    new_server_config = {
        "local-memory-postgres": {
            "command": str(python_path),
            "args": [str(server_path)],
            "env": {
                "POSTGRES_HOST": "localhost",
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "postgres",
                "POSTGRES_USER": "postgres",
                "POSTGRES_PASSWORD": "postgres",
                "OLLAMA_API_URL": "http://localhost:11434",
                "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text",
                "DEFAULT_MEMORY_DOMAIN": "default",
                "MCP_SERVER_NAME": "Local Memory MCP"
            }
        }
    }

    try:
        # Create config directory if it doesn't exist
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing configuration or create new one
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}

        # Add or update mcpServers section
        if "mcpServers" not in config:
            config["mcpServers"] = {}

        # Update with our server configuration
        config["mcpServers"].update(new_server_config)

        # Write back to file
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

        print_success(f"Updated Claude configuration: {config_file}")
        return True

    except Exception as e:
        print_error(f"Failed to update Claude configuration: {str(e)}")
        return False


def test_memory_service() -> Tuple[bool, str]:
    """
    Test that the local memory service is running and accessible.

    Returns:
        Tuple of (is_running, status_message)
    """
    try:
        import socket

        # Test if port 8000 is listening (our MCP server)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('localhost', 8000))
        sock.close()

        if result == 0:
            return True, "Local memory service is running on port 8000"
        else:
            return False, "Local memory service is not running (port 8000 not accessible)"

    except Exception as e:
        return False, f"Error testing memory service: {str(e)}"


def install_claude_commands(verbose: bool = True) -> bool:
    """
    Main function to install Claude Code commands for Local Memory MCP.

    Args:
        verbose: Whether to print detailed progress information

    Returns:
        True if installation was successful, False otherwise
    """
    if verbose:
        print("🧠 Installing Claude Code commands for Local Memory MCP...")
        print("=" * 60)

    # Check Claude Code CLI availability
    claude_available, claude_status = check_claude_code_cli()
    if not claude_available:
        print_error(f"Claude Code CLI not available: {claude_status}")
        print_info("Please install Claude Code CLI first: https://claude.ai/code")
        return False

    if verbose:
        print_success(f"Claude Code CLI detected: {claude_status}")

    # Check commands directory access
    can_access, access_status = check_commands_directory_access()
    if not can_access:
        print_error(access_status)
        return False

    if verbose:
        print_success(access_status)

    # Create backup of existing commands
    backup_path = backup_existing_commands()

    # Install command files
    install_success, installed_files = install_command_files()
    if not install_success:
        return False

    # Update Claude configuration to include MCP server
    config_success = update_claude_config()
    if not config_success:
        print_warning("Failed to update Claude configuration - you may need to configure MCP manually")

    # Test memory service
    service_running, service_status = test_memory_service()
    if service_running:
        if verbose:
            print_success(service_status)
    else:
        if verbose:
            print_warning(f"Memory service status: {service_status}")
            print_info("Start the memory service with: python src/postgres_memory_server.py")

    # Show usage instructions
    if verbose:
        print("")
        print_success("Claude Code commands installed successfully!")
        print_info("Available commands:")
        for cmd_file in installed_files:
            cmd_name = cmd_file.replace('.md', '')
            print_info(f"  claude /{cmd_name}")

        print("")
        print_info("Example usage:")
        print_info('  claude /memory-store "Important decision about architecture"')
        print_info('  claude /memory-recall "what did we decide last week?"')
        print_info('  claude /memory-search --tags "architecture,database"')
        print_info('  claude /memory-health')

        print("")
        print_info("To test if tools are available in Claude sessions:")
        print_info('  Start a new Claude Code session and look for mcp__memory__* tools')

    return True


def uninstall_commands() -> Tuple[bool, List[str]]:
    """
    Uninstall Local Memory MCP commands from Claude Code.

    Returns:
        Tuple of (success, list_of_removed_files)
    """
    commands_dir = get_claude_commands_directory()
    removed_files = []

    if not commands_dir.exists():
        return True, []  # Nothing to remove

    try:
        # Remove all memory-*.md files
        for md_file in commands_dir.glob("memory-*.md"):
            md_file.unlink()
            removed_files.append(md_file.name)
            print_info(f"Removed: {md_file.name}")

        if removed_files:
            print_success(f"Successfully removed {len(removed_files)} commands")
        else:
            print_info("No Local Memory MCP commands found to remove")

        return True, removed_files

    except Exception as e:
        print_error(f"Failed to uninstall commands: {str(e)}")
        return False, []


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Install Claude Code commands for Local Memory MCP")
    parser.add_argument('--test', action='store_true', help='Test installation without installing')
    parser.add_argument('--uninstall', action='store_true', help='Uninstall commands')
    parser.add_argument('--quiet', action='store_true', help='Minimal output')

    args = parser.parse_args()

    if args.uninstall:
        success, removed = uninstall_commands()
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    elif args.test:
        # Test mode - check prerequisites but don't install
        claude_ok, claude_msg = check_claude_code_cli()
        access_ok, access_msg = check_commands_directory_access()
        service_ok, service_msg = test_memory_service()

        print("Local Memory MCP installation test:")
        print(f"  Claude CLI: {'✓' if claude_ok else '✗'} {claude_msg}")
        print(f"  Directory access: {'✓' if access_ok else '✗'} {access_msg}")
        print(f"  Memory service: {'✓' if service_ok else '⚠'} {service_msg}")

        if claude_ok and access_ok:
            print("✓ Ready to install Claude Code commands")
            sys.exit(0)
        else:
            print("✗ Prerequisites not met")
            sys.exit(1)
    else:
        # Normal installation
        success = install_claude_commands(verbose=not args.quiet)
        sys.exit(0 if success else 1)
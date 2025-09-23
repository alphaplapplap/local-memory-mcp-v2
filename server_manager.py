#!/usr/bin/env python3
"""
Memory Server Manager
Prevents conflicts and manages server instances
"""

import os
import sys
import time
import psutil
import subprocess
from pathlib import Path

class ServerManager:
    def __init__(self):
        self.port = 8000
        self.server_scripts = [
            'bridge_server.py',
            'dev_server.py', 
            'daemon_server.py'
        ]
        self.pid_files = [
            'memory-server.pid',
            'memory-daemon.pid'
        ]
    
    def find_running_servers(self):
        """Find all running memory server processes"""
        running_servers = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if any(script in cmdline for script in self.server_scripts):
                    running_servers.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cmdline': cmdline,
                        'script': next(script for script in self.server_scripts if script in cmdline)
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return running_servers
    
    def check_port_usage(self):
        """Check what's using port 8000"""
        port_users = []
        
        for conn in psutil.net_connections():
            if conn.laddr.port == self.port:
                try:
                    proc = psutil.Process(conn.pid)
                    port_users.append({
                        'pid': conn.pid,
                        'name': proc.name(),
                        'cmdline': ' '.join(proc.cmdline())
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    port_users.append({
                        'pid': conn.pid,
                        'name': 'unknown',
                        'cmdline': 'unknown'
                    })
        
        return port_users
    
    def cleanup_stale_pid_files(self):
        """Remove PID files for processes that no longer exist"""
        cleaned_files = []
        
        for pid_file in self.pid_files:
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    
                    if not psutil.pid_exists(pid):
                        os.remove(pid_file)
                        cleaned_files.append(pid_file)
                except (ValueError, FileNotFoundError):
                    os.remove(pid_file)
                    cleaned_files.append(pid_file)
        
        return cleaned_files
    
    def stop_all_servers(self):
        """Stop all running memory servers"""
        stopped_servers = []
        
        # Stop by PID files first
        for pid_file in self.pid_files:
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    
                    if psutil.pid_exists(pid):
                        proc = psutil.Process(pid)
                        proc.terminate()
                        stopped_servers.append(f"PID {pid} (from {pid_file})")
                        os.remove(pid_file)
                except (ValueError, FileNotFoundError, psutil.NoSuchProcess):
                    if os.path.exists(pid_file):
                        os.remove(pid_file)
        
        # Stop any remaining servers
        running_servers = self.find_running_servers()
        for server in running_servers:
            try:
                proc = psutil.Process(server['pid'])
                proc.terminate()
                stopped_servers.append(f"PID {server['pid']} ({server['script']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        return stopped_servers
    
    def get_status(self):
        """Get comprehensive server status"""
        status = {
            'running_servers': self.find_running_servers(),
            'port_users': self.check_port_usage(),
            'pid_files': [f for f in self.pid_files if os.path.exists(f)],
            'server_responding': False
        }
        
        # Check if server is responding
        try:
            import requests
            response = requests.get(f'http://localhost:{self.port}/api/health', timeout=2)
            status['server_responding'] = response.status_code == 200
        except:
            pass
        
        return status
    
    def print_status(self):
        """Print detailed status information"""
        status = self.get_status()
        
        print("🔍 Memory Server Status")
        print("=" * 50)
        
        # Running servers
        if status['running_servers']:
            print("🔄 Running Servers:")
            for server in status['running_servers']:
                print(f"   PID {server['pid']}: {server['script']}")
        else:
            print("❌ No servers running")
        
        # Port usage
        if status['port_users']:
            print(f"🌐 Port {self.port} users:")
            for user in status['port_users']:
                print(f"   PID {user['pid']}: {user['name']}")
        else:
            print(f"🌐 Port {self.port}: Available")
        
        # PID files
        if status['pid_files']:
            print("📄 PID files:")
            for pid_file in status['pid_files']:
                print(f"   {pid_file}")
        else:
            print("📄 No PID files found")
        
        # Server response
        if status['server_responding']:
            print("✅ Server responding to health checks")
        else:
            print("❌ Server not responding")
        
        print("=" * 50)

def main():
    """Main function"""
    manager = ServerManager()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'status':
            manager.print_status()
        elif command == 'stop':
            stopped = manager.stop_all_servers()
            if stopped:
                print("🛑 Stopped servers:")
                for server in stopped:
                    print(f"   {server}")
            else:
                print("ℹ️  No servers to stop")
        elif command == 'cleanup':
            cleaned = manager.cleanup_stale_pid_files()
            if cleaned:
                print("🧹 Cleaned up stale PID files:")
                for file in cleaned:
                    print(f"   {file}")
            else:
                print("ℹ️  No stale PID files found")
        else:
            print("❌ Unknown command. Use: status, stop, or cleanup")
    else:
        manager.print_status()

if __name__ == "__main__":
    main()

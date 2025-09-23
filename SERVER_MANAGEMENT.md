# Server Management & Conflict Prevention

## 🚀 Server Types

| Type | Script | Purpose | Persistence |
|------|--------|---------|-------------|
| **Development** | `dev_server.py` | Hot reloading, file watching | Session-based |
| **Persistent** | `start_persistent.sh` | Background with nohup | Until stopped |
| **Daemon** | `start_daemon.sh` | True background daemon | Until stopped |
| **Direct** | `bridge_server.py` | Manual server start | Session-based |

## 🔍 Conflict Detection

### Check for Conflicts
```bash
./check_conflicts.sh
```
**What it checks:**
- ✅ Running memory server processes
- ✅ Port 8000 usage
- ✅ PID file validity
- ✅ Server response status

### Example Output
```
🔍 Checking for Memory Server Conflicts
=======================================
🔄 Checking running processes...
✅ One server running (no conflicts)

🌐 Checking port 8000...
⚠️  Port 8000 is in use:
   Python  23104 linuxbabe  TCP *:irdmi (LISTEN)

📄 Checking PID files...
✅ memory-daemon.pid: PID 23104 is running

🔍 Checking server response...
✅ Server is responding at http://localhost:8000

📊 Summary:
✅ One server running (no conflicts)
```

## 🛑 Stopping Servers

### Stop All Servers
```bash
./stop_all_servers.sh
```
**What it does:**
- Stops daemon server
- Stops persistent server  
- Kills any remaining processes
- Cleans up PID files
- Verifies all servers are stopped

### Stop Specific Server
```bash
# Stop daemon
./stop_daemon.sh

# Stop persistent
./stop_persistent.sh
```

## 🚀 Starting Servers

### Start Daemon (Recommended)
```bash
./start_daemon.sh
```
**Features:**
- ✅ Conflict detection before starting
- ✅ Background daemon process
- ✅ PID file tracking
- ✅ Comprehensive logging
- ✅ No console window needed

### Start Development Server
```bash
./start_dev.sh
```
**Features:**
- ✅ Hot reloading
- ✅ File watching
- ✅ Development environment

## ⚠️ Conflict Prevention

### Automatic Prevention
- **Startup scripts** check for conflicts before starting
- **PID file tracking** prevents duplicate processes
- **Port checking** ensures port 8000 is available
- **Process detection** identifies running servers

### Manual Prevention
```bash
# Check status before starting
./check_conflicts.sh

# Stop all servers if conflicts exist
./stop_all_servers.sh

# Then start your preferred server
./start_daemon.sh
```

## 📊 Server Status

### Quick Status Check
```bash
# Check if server is responding
curl -s http://localhost:8000/api/health

# Check running processes
ps aux | grep -E "(bridge_server|dev_server|daemon_server)"

# Check port usage
lsof -i :8000
```

### Detailed Status
```bash
./check_conflicts.sh
```

## 🔧 Troubleshooting

### Multiple Servers Running
```bash
# Stop all servers
./stop_all_servers.sh

# Verify all stopped
./check_conflicts.sh

# Start preferred server
./start_daemon.sh
```

### Port 8000 in Use
```bash
# Check what's using the port
lsof -i :8000

# Stop memory servers
./stop_all_servers.sh

# If still in use, another app is using port 8000
```

### Stale PID Files
```bash
# Clean up stale files
rm -f memory-server.pid memory-daemon.pid

# Or use the conflict checker (auto-cleans)
./check_conflicts.sh
```

## 🎯 Best Practices

### For Development
1. Use `./start_dev.sh` for active development
2. Use `./start_daemon.sh` for background work
3. Always check conflicts before starting: `./check_conflicts.sh`

### For Production
1. Use `./start_daemon.sh` for persistent service
2. Set up system service for auto-start on boot
3. Monitor with `./check_conflicts.sh`

### General
1. **One server at a time** - never run multiple types simultaneously
2. **Check before starting** - always verify no conflicts
3. **Clean shutdown** - use stop scripts instead of killing processes
4. **Monitor logs** - check log files for issues

## 📁 File Structure

```
├── check_conflicts.sh      # Conflict detection
├── stop_all_servers.sh     # Stop all servers
├── start_daemon.sh         # Start daemon server
├── stop_daemon.sh          # Stop daemon server
├── start_persistent.sh     # Start persistent server
├── stop_persistent.sh      # Stop persistent server
├── start_dev.sh           # Start development server
├── daemon_server.py       # Daemon server implementation
├── dev_server.py          # Development server
├── bridge_server.py       # Main server application
├── memory-daemon.pid      # Daemon PID file
├── memory-server.pid      # Persistent PID file
└── logs/                  # Server logs
    ├── memory-daemon.log
    ├── memory-server-persistent.log
    └── daemon-startup.log
```

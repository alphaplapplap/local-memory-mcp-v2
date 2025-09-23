#!/usr/bin/env python3
"""
PostgreSQL Memory Optimization Auto-Configuration
Detects system memory and applies optimal PostgreSQL settings for Local Memory MCP
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def get_system_memory_gb():
    """Detect total system memory in GB"""
    try:
        if platform.system() == "Darwin":  # macOS
            # Get memory in bytes and convert to GB
            memory_bytes = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize']).strip())
            return memory_bytes / (1024**3)
        elif platform.system() == "Linux":
            # Read from /proc/meminfo
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        memory_kb = int(line.split()[1])
                        return memory_kb / (1024**2)
        else:
            print(f"Unsupported platform: {platform.system()}")
            return 8  # Default fallback
    except Exception as e:
        print(f"Error detecting memory: {e}")
        return 8  # Default fallback

def get_optimal_config(memory_gb):
    """Get optimal PostgreSQL configuration based on system memory"""
    if memory_gb >= 64:
        return {
            'shared_buffers': '16GB',
            'work_mem': '512MB',
            'maintenance_work_mem': '8GB',
            'max_maintenance_work_mem': '16GB',
            'effective_cache_size': '48GB',
            'max_connections': 400,
            'use_case': 'Enterprise/High-Load'
        }
    elif memory_gb >= 32:
        return {
            'shared_buffers': '8GB',
            'work_mem': '256MB',
            'maintenance_work_mem': '4GB',
            'max_maintenance_work_mem': '8GB',
            'effective_cache_size': '24GB',
            'max_connections': 300,
            'use_case': 'Large Production'
        }
    elif memory_gb >= 16:
        return {
            'shared_buffers': '4GB',
            'work_mem': '128MB',
            'maintenance_work_mem': '2GB',
            'max_maintenance_work_mem': '4GB',
            'effective_cache_size': '12GB',
            'max_connections': 200,
            'use_case': 'Medium Production'
        }
    else:  # 8GB or less
        return {
            'shared_buffers': '2GB',
            'work_mem': '64MB',
            'maintenance_work_mem': '1GB',
            'max_maintenance_work_mem': '2GB',
            'effective_cache_size': '6GB',
            'max_connections': 100,
            'use_case': 'Development/Small Production'
        }

def generate_config_file(config, output_path):
    """Generate optimized PostgreSQL configuration file"""
    config_content = f"""# Local Memory MCP PostgreSQL Optimizations
# Auto-generated for {config['use_case']}
# System Memory: {get_system_memory_gb():.1f}GB
# Generated: {subprocess.check_output(['date']).decode().strip()}

# === MEMORY CONFIGURATION ===
shared_buffers = {config['shared_buffers']}
work_mem = {config['work_mem']}
maintenance_work_mem = {config['maintenance_work_mem']}
max_maintenance_work_mem = {config['max_maintenance_work_mem']}
effective_cache_size = {config['effective_cache_size']}
max_connections = {config['max_connections']}

# === VECTOR-SPECIFIC OPTIMIZATIONS ===
# pgvector optimizations (hnsw.ef_search set dynamically in application)
enable_indexscan = on
enable_bitmapscan = on

# === SSD OPTIMIZATIONS ===
random_page_cost = 1.1
seq_page_cost = 1.0

# === WRITE PERFORMANCE ===
wal_buffers = 64MB
checkpoint_completion_target = 0.9
checkpoint_timeout = 15min

# === COST ADJUSTMENTS ===
cpu_tuple_cost = 0.01
cpu_index_tuple_cost = 0.005

# === MONITORING ===
track_functions = all
track_activities = on
track_counts = on
track_io_timing = on
log_min_duration_statement = 1000
log_statement = 'ddl'
log_line_prefix = '%t [%p-%l] %q%u@%d '

# === VECTOR MEMORY CALCULATION ===
# work_mem formula: Base (shared_buffers * 0.4 / max_connections) + Vector overhead
# Current: {config['work_mem']} = Optimized for vector operations
#
# To apply these settings:
# 1. Add to postgresql.conf: include = '{output_path}'
# 2. Restart PostgreSQL service
# 3. Verify with: SHOW shared_buffers; SHOW work_mem;
"""

    with open(output_path, 'w') as f:
        f.write(config_content)

def main():
    """Main optimization application"""
    print("🔧 Local Memory MCP PostgreSQL Auto-Optimization")
    print("=" * 50)

    # Detect system memory
    memory_gb = get_system_memory_gb()
    print(f"💾 Detected System Memory: {memory_gb:.1f}GB")

    # Get optimal configuration
    config = get_optimal_config(memory_gb)
    print(f"🎯 Target Configuration: {config['use_case']}")
    print(f"📊 Recommended Settings:")
    print(f"   • shared_buffers: {config['shared_buffers']}")
    print(f"   • work_mem: {config['work_mem']}")
    print(f"   • max_connections: {config['max_connections']}")
    print(f"   • effective_cache_size: {config['effective_cache_size']}")

    # Generate configuration file
    output_path = Path(__file__).parent / "postgresql_optimized.conf"
    generate_config_file(config, output_path)

    print(f"\\n✅ Configuration generated: {output_path}")
    print(f"\\n📋 Next Steps:")
    print(f"1. Backup current PostgreSQL config")
    print(f"2. Add to postgresql.conf:")
    print(f"   include = '{output_path.absolute()}'")
    print(f"3. Restart PostgreSQL service")
    print(f"4. Monitor performance with: SELECT * FROM pg_stat_database;")

    # Show current PostgreSQL settings if accessible
    try:
        result = subprocess.run(['psql', '-c', 'SHOW shared_buffers;'],
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            current_shared_buffers = result.stdout.split('\\n')[2].strip()
            print(f"\\n📊 Current shared_buffers: {current_shared_buffers}")
        else:
            print("\\n⚠️  Could not check current PostgreSQL settings")
    except Exception:
        print("\\n⚠️  PostgreSQL not accessible for settings check")

if __name__ == "__main__":
    main()
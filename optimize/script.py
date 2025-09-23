# Create PostgreSQL optimization configuration recommendations
import pandas as pd

# System memory scenarios and optimal configurations
memory_configs = [
    {
        'System_RAM_GB': 8,
        'shared_buffers_GB': 2,
        'shared_buffers_pct': '25%',
        'work_mem_MB': 64,
        'maintenance_work_mem_GB': 1,
        'max_connections': 100,
        'effective_cache_size_GB': 6,
        'use_case': 'Development/Small Production'
    },
    {
        'System_RAM_GB': 16,
        'shared_buffers_GB': 4,
        'shared_buffers_pct': '25%',
        'work_mem_MB': 128,
        'maintenance_work_mem_GB': 2,
        'max_connections': 200,
        'effective_cache_size_GB': 12,
        'use_case': 'Medium Production'
    },
    {
        'System_RAM_GB': 32,
        'shared_buffers_GB': 8,
        'shared_buffers_pct': '25%',
        'work_mem_MB': 256,
        'maintenance_work_mem_GB': 4,
        'max_connections': 300,
        'effective_cache_size_GB': 24,
        'use_case': 'Large Production'
    },
    {
        'System_RAM_GB': 64,
        'shared_buffers_GB': 16,
        'shared_buffers_pct': '25%',
        'work_mem_MB': 512,
        'maintenance_work_mem_GB': 8,
        'max_connections': 400,
        'effective_cache_size_GB': 48,
        'use_case': 'Enterprise/High-Load'
    }
]

df = pd.DataFrame(memory_configs)
print("PostgreSQL Memory Configuration Recommendations")
print("=" * 55)
print(df.to_string(index=False))

# Save as CSV for reference
df.to_csv('postgresql_memory_configs.csv', index=False)
print(f"\nConfiguration saved to postgresql_memory_configs.csv")

# Calculate work_mem formula validation
print("\nwork_mem Calculation Formula Validation:")
print("Formula: work_mem = (25% of RAM) / max_connections")
for config in memory_configs:
    calculated_work_mem = (config['System_RAM_GB'] * 1024 * 0.25) / config['max_connections']
    print(f"{config['System_RAM_GB']}GB RAM: {calculated_work_mem:.1f}MB (recommended: {config['work_mem_MB']}MB)")
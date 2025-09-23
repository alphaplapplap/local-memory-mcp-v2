# Create semantic memory clustering strategy
import pandas as pd
import json

# Define semantic clustering strategy for memory optimization
clustering_strategy = {
    "temporal_clusters": {
        "recent": {
            "time_window": "last 24 hours",
            "priority_weight": 1.0,
            "max_memories": 20,
            "compression_ratio": 0.0  # No compression for recent
        },
        "short_term": {
            "time_window": "last week", 
            "priority_weight": 0.8,
            "max_memories": 50,
            "compression_ratio": 0.2  # Light compression
        },
        "medium_term": {
            "time_window": "last month",
            "priority_weight": 0.6, 
            "max_memories": 100,
            "compression_ratio": 0.4  # Moderate compression
        },
        "long_term": {
            "time_window": "older than month",
            "priority_weight": 0.4,
            "max_memories": 200,
            "compression_ratio": 0.6  # Heavy compression
        }
    },
    "semantic_clusters": {
        "architecture_decisions": {
            "keywords": ["architecture", "design", "pattern", "structure"],
            "importance_multiplier": 1.2,
            "retention_priority": "high",
            "compression_resistance": 0.8
        },
        "code_implementations": {
            "keywords": ["code", "function", "class", "implementation"],
            "importance_multiplier": 1.0,
            "retention_priority": "medium", 
            "compression_resistance": 0.6
        },
        "debugging_sessions": {
            "keywords": ["bug", "error", "debug", "fix", "issue"],
            "importance_multiplier": 0.9,
            "retention_priority": "medium",
            "compression_resistance": 0.4
        },
        "project_context": {
            "keywords": ["project", "goal", "requirement", "specification"],
            "importance_multiplier": 1.1,
            "retention_priority": "high",
            "compression_resistance": 0.9
        }
    }
}

# Calculate optimal token allocation per cluster
total_token_budget = 8000  # Conservative budget for context injection

# Temporal allocation (60% of budget)
temporal_budget = int(total_token_budget * 0.6)
temporal_allocations = []

for cluster_name, config in clustering_strategy["temporal_clusters"].items():
    allocation = int(temporal_budget * config["priority_weight"] / sum(c["priority_weight"] for c in clustering_strategy["temporal_clusters"].values()))
    temporal_allocations.append({
        "cluster": cluster_name,
        "token_allocation": allocation,
        "max_memories": config["max_memories"],
        "tokens_per_memory": allocation // config["max_memories"] if config["max_memories"] > 0 else 0,
        "compression_ratio": config["compression_ratio"]
    })

# Semantic allocation (40% of budget)
semantic_budget = int(total_token_budget * 0.4)
semantic_allocations = []

for cluster_name, config in clustering_strategy["semantic_clusters"].items():
    allocation = int(semantic_budget * config["importance_multiplier"] / sum(c["importance_multiplier"] for c in clustering_strategy["semantic_clusters"].values()))
    semantic_allocations.append({
        "cluster": cluster_name,
        "token_allocation": allocation,
        "importance_multiplier": config["importance_multiplier"],
        "retention_priority": config["retention_priority"],
        "compression_resistance": config["compression_resistance"]
    })

# Create summary dataframes
temporal_df = pd.DataFrame(temporal_allocations)
semantic_df = pd.DataFrame(semantic_allocations)

print("SEMANTIC MEMORY CLUSTERING STRATEGY")
print("=" * 50)
print(f"Total Token Budget: {total_token_budget:,} tokens")
print(f"Temporal Allocation: {temporal_budget:,} tokens (60%)")
print(f"Semantic Allocation: {semantic_budget:,} tokens (40%)")
print()

print("TEMPORAL CLUSTERING ALLOCATION:")
print(temporal_df.to_string(index=False))
print()

print("SEMANTIC CLUSTERING ALLOCATION:")
print(semantic_df.to_string(index=False))

# Save strategy to JSON for implementation
with open('memory_clustering_strategy.json', 'w') as f:
    json.dump(clustering_strategy, f, indent=2)

# Calculate efficiency metrics
total_allocated = temporal_df['token_allocation'].sum() + semantic_df['token_allocation'].sum()
efficiency_ratio = total_allocated / total_token_budget

print(f"\nEFFICIENCY METRICS:")
print(f"Total Allocated: {total_allocated:,} tokens")
print(f"Budget Utilization: {efficiency_ratio:.1%}")
print(f"Average tokens per temporal memory: {temporal_df['tokens_per_memory'].mean():.1f}")
print(f"Strategy saved to: memory_clustering_strategy.json")
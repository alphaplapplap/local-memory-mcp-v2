# Create mermaid diagram for multi-layer caching architecture
diagram_code = '''
flowchart TD
    A[Client Request] --> B{L1 Cache Check<br/>In-Memory LRU<br/>< 1ms latency<br/>512MB capacity<br/>85-90% hit ratio}
    
    B -->|Hit| C[Return Data<br/>< 1ms total]
    B -->|Miss| D{L2 Cache Check<br/>Redis Distributed<br/>1-5ms latency<br/>8GB capacity<br/>75-85% hit ratio}
    
    D -->|Hit| E[Return Data<br/>+ Populate L1<br/>1-5ms total]
    D -->|Miss| F[L3 Database Query<br/>PostgreSQL + pgvector<br/>5-50ms latency<br/>Unlimited capacity<br/>100% hit ratio]
    
    F --> G[Return Data<br/>+ Populate L2<br/>+ Populate L1<br/>5-50ms total]
    
    H[Cache Management] --> I[L1 Policies<br/>TTL: 5-30 min<br/>Eviction: LRU<br/>Hot data priority]
    H --> J[L2 Policies<br/>TTL: 1-24 hours<br/>Eviction: Redis LRU<br/>Cross-instance sharing]
    H --> K[L3 Policies<br/>TTL: Persistent<br/>Long-term storage<br/>Complex queries]
    
    L[Cache Warming] --> M[Preload frequent queries<br/>Background refresh<br/>Predictive loading]
    
    N[Performance Metrics] --> O[L1: Recent queries<br/>Hot data, Sessions<br/>Ultra-low latency]
    N --> P[L2: Embeddings<br/>Search results<br/>User sessions]
    N --> Q[L3: All memories<br/>Permanent storage<br/>Full data access]
    
    style B fill:#B3E5EC
    style D fill:#A5D6A7
    style F fill:#FFEB8A
    style H fill:#FFCDD2
    style L fill:#9FA8B0
    style N fill:#B3E5EC
'''

# Create the diagram with PNG and SVG outputs
# Note: create_mermaid_diagram function needs to be implemented
# For now, save the diagram code to a file for manual processing
with open('mcp_caching_architecture.mmd', 'w') as f:
    f.write(diagram_code)
print(f"Mermaid diagram saved as: mcp_caching_architecture.mmd")
print("Note: Use a Mermaid renderer to convert to PNG/SVG")
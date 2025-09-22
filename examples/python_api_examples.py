#!/usr/bin/env python3
"""
Python API Examples for Local Memory MCP System

This file demonstrates various ways to use the Python API for the memory system.
It shows both synchronous and asynchronous usage patterns, document ingestion,
and advanced features.

Run this file to see the examples in action:
    python examples/python_api_examples.py
"""

import os
import sys
import asyncio
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from python_api import MemorySystem, AsyncMemorySystem, quick_store, quick_search


def basic_sync_example():
    """Basic synchronous usage example."""
    print("🔧 Basic Synchronous Example")
    print("=" * 40)
    
    # Initialize memory system
    memory = MemorySystem()
    
    # Store some memories
    print("\n📝 Storing memories...")
    mem1 = memory.store(
        "User prefers Python for data analysis and machine learning",
        domain="personal",
        source="conversation",
        importance=0.8,
        tags=["programming", "preferences", "python"]
    )
    
    mem2 = memory.store(
        "User works as a software engineer at a tech startup",
        domain="work",
        source="profile",
        importance=0.9,
        tags=["work", "career", "startup"]
    )
    
    mem3 = memory.store(
        "User enjoys hiking and outdoor activities on weekends",
        domain="personal",
        source="conversation",
        importance=0.6,
        tags=["hobbies", "outdoor", "weekend"]
    )
    
    print(f"✅ Stored memories: {mem1}, {mem2}, {mem3}")
    
    # Search memories
    print("\n🔍 Searching for programming preferences...")
    results = memory.search("programming preferences", limit=3)
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['content']}")
        print(f"   Score: {result.get('score', 0):.3f}, Domain: {result.get('metadata', {}).get('domain', 'unknown')}")
    
    # Search in specific domain
    print("\n🔍 Searching in work domain...")
    work_results = memory.search("software engineer", domain="work", limit=2)
    for i, result in enumerate(work_results, 1):
        print(f"{i}. {result['content']}")
    
    # List domains
    domains = memory.list_domains()
    print(f"\n📂 Available domains: {domains}")
    
    # Get system stats
    stats = memory.get_stats()
    print(f"\n📊 System stats:")
    print(f"   Domains: {stats['total_domains']}")
    print(f"   Ollama available: {stats['ollama_available']}")
    if stats['embedding_model']:
        print(f"   Embedding model: {stats['embedding_model']}")


async def basic_async_example():
    """Basic asynchronous usage example."""
    print("\n🚀 Basic Asynchronous Example")
    print("=" * 40)
    
    # Initialize async memory system
    memory = AsyncMemorySystem()
    
    # Store memories concurrently
    print("\n📝 Storing memories concurrently...")
    tasks = [
        memory.store("User is learning Rust programming language", "learning", importance=0.7),
        memory.store("User has a meeting with investors next week", "work", importance=0.9),
        memory.store("User's favorite programming language is Python", "personal", importance=0.8)
    ]
    
    memory_ids = await asyncio.gather(*tasks)
    print(f"✅ Stored memories concurrently: {memory_ids}")
    
    # Search memories concurrently
    print("\n🔍 Searching memories concurrently...")
    search_tasks = [
        memory.search("programming language", limit=2),
        memory.search("meeting", domain="work", limit=2),
        memory.search("learning", domain="learning", limit=2)
    ]
    
    search_results = await asyncio.gather(*search_tasks)
    for i, results in enumerate(search_results):
        print(f"\nSearch {i+1} results:")
        for j, result in enumerate(results, 1):
            print(f"  {j}. {result['content'][:50]}...")
    
    # Get stats
    stats = await memory.get_stats()
    print(f"\n📊 Async system stats: {stats['total_domains']} domains")


def quick_functions_example():
    """Example using quick convenience functions."""
    print("\n⚡ Quick Functions Example")
    print("=" * 40)
    
    # Quick store
    print("\n📝 Using quick_store...")
    mem_id = quick_store("User loves quick and easy APIs", "personal", importance=0.7)
    print(f"✅ Quick stored: {mem_id}")
    
    # Quick search
    print("\n🔍 Using quick_search...")
    results = quick_search("quick APIs", limit=2)
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['content']}")


def document_ingestion_example():
    """Example of document ingestion."""
    print("\n📄 Document Ingestion Example")
    print("=" * 40)
    
    memory = MemorySystem()
    
    # Create a sample text file for ingestion
    sample_content = """
    This is a sample document about the user's preferences and background.
    
    The user is a software engineer with 5 years of experience in Python development.
    They work at a startup company focused on AI and machine learning.
    
    Personal interests include:
    - Hiking and outdoor activities
    - Reading science fiction novels
    - Learning new programming languages
    - Contributing to open source projects
    
    Technical skills:
    - Python, JavaScript, Go
    - Machine learning frameworks
    - Cloud computing (AWS, GCP)
    - Database design and optimization
    """
    
    # Create temporary file
    temp_file = Path("temp_sample_doc.txt")
    temp_file.write_text(sample_content)
    
    try:
        # Ingest the document
        print("\n📄 Ingesting sample document...")
        result = memory.ingest_document(temp_file, domain="profile")
        
        print(f"✅ Ingestion result:")
        print(f"   Success: {result['success']}")
        print(f"   Chunks stored: {result['chunks_stored']}")
        print(f"   Processing time: {result['processing_time']:.2f}s")
        
        # Search the ingested content
        print("\n🔍 Searching ingested content...")
        results = memory.search("software engineer", domain="profile", limit=3)
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['content'][:80]}...")
    
    finally:
        # Clean up
        if temp_file.exists():
            temp_file.unlink()
            print(f"\n🧹 Cleaned up temporary file")


async def advanced_async_example():
    """Advanced async example with error handling and batch operations."""
    print("\n🎯 Advanced Async Example")
    print("=" * 40)
    
    memory = AsyncMemorySystem()
    
    # Batch store with error handling
    print("\n📝 Batch storing with error handling...")
    memories_to_store = [
        ("User prefers async programming patterns", "technical", 0.8),
        ("User works remotely from home office", "work", 0.7),
        ("User enjoys cooking Italian cuisine", "personal", 0.6),
        ("User is learning about microservices architecture", "learning", 0.7),
        ("User has a pet cat named Whiskers", "personal", 0.5)
    ]
    
    # Store with individual error handling
    stored_memories = []
    for content, domain, importance in memories_to_store:
        try:
            mem_id = await memory.store(content, domain, importance=importance)
            stored_memories.append(mem_id)
            print(f"✅ Stored: {content[:30]}...")
        except Exception as e:
            print(f"❌ Failed to store: {content[:30]}... - {e}")
    
    print(f"\n📊 Successfully stored {len(stored_memories)} memories")
    
    # Complex search with multiple domains
    print("\n🔍 Complex search across domains...")
    search_queries = [
        ("programming", None, 3),  # Search all domains
        ("work", "work", 2),       # Search work domain only
        ("personal", "personal", 2) # Search personal domain only
    ]
    
    for query, domain, limit in search_queries:
        try:
            results = await memory.search(query, domain, limit)
            print(f"\nQuery: '{query}' in domain: {domain or 'all'}")
            for i, result in enumerate(results, 1):
                print(f"  {i}. {result['content'][:50]}... (score: {result.get('score', 0):.3f})")
        except Exception as e:
            print(f"❌ Search failed for '{query}': {e}")
    
    # Get comprehensive stats
    stats = await memory.get_stats()
    print(f"\n📊 Final system stats:")
    print(f"   Total domains: {stats['total_domains']}")
    print(f"   Domains: {', '.join(stats['domains'])}")
    print(f"   Ollama available: {stats['ollama_available']}")


def memory_update_example():
    """Example of updating existing memories."""
    print("\n🔄 Memory Update Example")
    print("=" * 40)
    
    memory = MemorySystem()
    
    # Store initial memory
    print("\n📝 Storing initial memory...")
    mem_id = memory.store(
        "User is learning Python programming",
        domain="learning",
        importance=0.6
    )
    print(f"✅ Initial memory stored: {mem_id}")
    
    # Update the memory
    print("\n🔄 Updating memory...")
    success = memory.update(
        mem_id,
        content="User is learning Python programming and has made good progress",
        importance=0.8,
        metadata={"updated_reason": "progress_update"}
    )
    
    if success:
        print("✅ Memory updated successfully")
        
        # Search to see the updated content
        results = memory.search("Python programming", domain="learning", limit=1)
        if results:
            print(f"📖 Updated content: {results[0]['content']}")
            print(f"📊 Updated importance: {results[0]['metadata'].get('importance', 'N/A')}")
    else:
        print("❌ Failed to update memory")


async def main():
    """Run all examples."""
    print("🧠 Local Memory MCP - Python API Examples")
    print("=" * 60)
    
    # Run synchronous examples
    basic_sync_example()
    quick_functions_example()
    document_ingestion_example()
    memory_update_example()
    
    # Run asynchronous examples
    await basic_async_example()
    await advanced_async_example()
    
    print("\n🎉 All examples completed!")
    print("\n💡 Tips:")
    print("   - Use MemorySystem for simple synchronous operations")
    print("   - Use AsyncMemorySystem for better performance and concurrent operations")
    print("   - Use quick_* functions for one-off operations")
    print("   - Organize memories with meaningful domains")
    print("   - Set appropriate importance scores for better retrieval")


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())

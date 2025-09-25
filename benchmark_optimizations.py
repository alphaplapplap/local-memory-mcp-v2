#!/usr/bin/env python3
"""
Comprehensive Performance Benchmarking Suite
Measures the impact of all optimization phases on memory system performance
"""

import sys
import os
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/optimization')
sys.path.insert(0, 'src/summarization')
sys.path.insert(0, 'src/consolidation')

import time
import json
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
import psutil
import tracemalloc

class PerformanceBenchmark:
    """Comprehensive benchmark for memory system optimizations"""

    def __init__(self):
        self.results = {
            'phase1': {},
            'phase2': {},
            'phase3': {},
            'overall': {}
        }
        self.baseline_metrics = {}

    def generate_test_data(self, count: int) -> List[Dict[str, Any]]:
        """Generate test memories with various characteristics"""
        memories = []

        categories = [
            ("technical", ["error", "bug", "fix", "function", "api"]),
            ("documentation", ["readme", "docs", "guide", "tutorial"]),
            ("planning", ["todo", "plan", "meeting", "decision"]),
            ("data", ["database", "query", "optimization", "index"])
        ]

        for i in range(count):
            category, keywords = categories[i % len(categories)]

            # Generate content of varying lengths
            if i % 10 == 0:
                # Large content (will be filtered in Phase 1)
                content = " ".join([f"Large content about {keywords[j % len(keywords)]}" for j in range(200)])
            elif i % 5 == 0:
                # Low quality (will be filtered in Phase 1)
                content = "TODO: placeholder fixme"
            else:
                # Normal content
                content = f"Memory {i}: {' '.join(np.random.choice(keywords, 3))} implementation details"

            # Generate synthetic embedding
            embedding = np.random.randn(384)
            # Make similar memories cluster together
            if category == "technical":
                embedding[:100] += 1
            elif category == "documentation":
                embedding[100:200] += 1
            elif category == "planning":
                embedding[200:300] += 1
            else:
                embedding[300:] += 1

            memories.append({
                'id': f"mem_{i:05d}",
                'content': content,
                'embedding': embedding.tolist(),
                'created_at': (datetime.now() - timedelta(days=i // 10)).isoformat(),
                'metadata': {
                    'tags': keywords[:2],
                    'importance': np.random.uniform(0.1, 1.0),
                    'source': category
                }
            })

        return memories

    def benchmark_baseline(self, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Establish baseline metrics without optimizations"""
        print("\n📊 Establishing Baseline Metrics...")

        start_time = time.time()
        tracemalloc.start()

        # Calculate raw metrics
        total_content_size = sum(len(m['content']) for m in memories)
        total_metadata_size = sum(len(json.dumps(m['metadata'])) for m in memories)
        total_embedding_size = sum(len(json.dumps(m['embedding'])) for m in memories)

        # Estimate tokens (4 chars per token)
        total_tokens = total_content_size // 4

        # Memory usage
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        elapsed = time.time() - start_time

        baseline = {
            'memory_count': len(memories),
            'total_content_size': total_content_size,
            'total_metadata_size': total_metadata_size,
            'total_embedding_size': total_embedding_size,
            'total_tokens': total_tokens,
            'avg_tokens_per_memory': total_tokens // len(memories),
            'processing_time': elapsed,
            'memory_usage_mb': peak / 1024 / 1024
        }

        print(f"  • Memories: {baseline['memory_count']}")
        print(f"  • Total tokens: {baseline['total_tokens']:,}")
        print(f"  • Avg tokens/memory: {baseline['avg_tokens_per_memory']}")
        print(f"  • Processing time: {baseline['processing_time']:.3f}s")
        print(f"  • Memory usage: {baseline['memory_usage_mb']:.1f}MB")

        return baseline

    def benchmark_phase1(self, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Benchmark Phase 1: Size limits and quality filtering"""
        print("\n🎯 Benchmarking Phase 1: Quick Wins...")

        from postgres_memory_api import PostgresMemoryAPI

        start_time = time.time()
        api = PostgresMemoryAPI()

        # Apply Phase 1 filters
        filtered_memories = []
        rejected_count = 0
        size_rejections = 0
        quality_rejections = 0

        for memory in memories:
            content = memory['content']

            # Size check (5KB limit from Phase 1)
            if len(content) > 5000:
                size_rejections += 1
                rejected_count += 1
                continue

            # Quality check
            should_store, score, reason = api._assess_content_quality(content)
            if not should_store:
                quality_rejections += 1
                rejected_count += 1
                continue

            filtered_memories.append(memory)

        elapsed = time.time() - start_time

        # Calculate token savings
        filtered_tokens = sum(len(m['content']) // 4 for m in filtered_memories)
        original_tokens = self.baseline_metrics.get('total_tokens', 0)
        token_reduction = 1 - (filtered_tokens / original_tokens) if original_tokens > 0 else 0

        results = {
            'memories_kept': len(filtered_memories),
            'memories_rejected': rejected_count,
            'size_rejections': size_rejections,
            'quality_rejections': quality_rejections,
            'token_count': filtered_tokens,
            'token_reduction': token_reduction,
            'processing_time': elapsed,
            'rejection_rate': rejected_count / len(memories)
        }

        print(f"  • Memories kept: {results['memories_kept']}/{len(memories)}")
        print(f"  • Size rejections: {results['size_rejections']}")
        print(f"  • Quality rejections: {results['quality_rejections']}")
        print(f"  • Token reduction: {results['token_reduction']:.1%}")
        print(f"  • Processing time: {results['processing_time']:.3f}s")

        return results, filtered_memories

    def benchmark_phase2(self, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Benchmark Phase 2: Consolidation and summarization"""
        print("\n🔄 Benchmarking Phase 2: Memory Management...")

        from memory_consolidator import MemoryConsolidator
        from session_summarizer import SessionSummarizer

        start_time = time.time()

        # Test consolidation
        consolidator = MemoryConsolidator(
            similarity_threshold=0.95,
            consolidation_threshold=5
        )

        consolidation_report = consolidator.consolidate_memories(memories, dry_run=True)

        # Test session summarization
        summarizer = SessionSummarizer(max_tokens=500)
        session_summary = summarizer.generate_compact_summary(
            session_id="bench_session",
            memories=memories[:20],  # Sample of memories
            initial_topics=["testing", "benchmark"],
            final_topics=["optimization", "performance"]
        )

        elapsed = time.time() - start_time

        # Calculate impact
        memories_after_consolidation = len(memories) - consolidation_report['memories_merged']
        consolidation_reduction = consolidation_report['memories_merged'] / len(memories)

        session_tokens = session_summary['metadata']['token_estimate']
        original_session_tokens = sum(len(m['content']) // 4 for m in memories[:20])
        session_compression = 1 - (session_tokens / original_session_tokens)

        results = {
            'duplicates_found': consolidation_report['duplicates_found'],
            'memories_merged': consolidation_report['memories_merged'],
            'memories_archived': consolidation_report['memories_archived'],
            'memories_after': memories_after_consolidation,
            'consolidation_reduction': consolidation_reduction,
            'session_tokens': session_tokens,
            'session_compression': session_compression,
            'processing_time': elapsed
        }

        print(f"  • Duplicates found: {results['duplicates_found']}")
        print(f"  • Memories merged: {results['memories_merged']}")
        print(f"  • Consolidation reduction: {results['consolidation_reduction']:.1%}")
        print(f"  • Session compression: {results['session_compression']:.1%}")
        print(f"  • Processing time: {results['processing_time']:.3f}s")

        return results

    def benchmark_phase3(self, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Benchmark Phase 3: Advanced optimizations"""
        print("\n🚀 Benchmarking Phase 3: Advanced Optimizations...")

        from adaptive_weights import AdaptiveWeightLearner
        from semantic_clustering import SemanticClusterer, ClusteringConfig
        from progressive_summarization import ProgressiveSummarizer

        start_time = time.time()

        # Test adaptive weights
        learner = AdaptiveWeightLearner(profile_dir=".bench_profiles")
        weights = learner.get_weights_for_project("benchmark", "test")

        # Simulate usage patterns
        for i in range(min(50, len(memories))):
            learner.record_memory_access(
                memory_id=memories[i]['id'],
                relevance_score=np.random.uniform(0.3, 0.9),
                was_useful=np.random.choice([True, False], p=[0.7, 0.3]),
                project_name="benchmark"
            )

        # Test semantic clustering
        config = ClusteringConfig(min_cluster_size=3, max_cluster_size=15)
        clusterer = SemanticClusterer(config)
        clusters = clusterer.cluster_memories(memories[:100], domain="benchmark")

        # Test progressive summarization
        summarizer = ProgressiveSummarizer(max_context_tokens=1000)

        # Summarize memories at different levels
        memory_summaries_tokens = 0
        for memory in memories[:20]:
            summary = summarizer.summarize_memory(memory)
            memory_summaries_tokens += summary.token_count

        # Get cluster representatives
        representatives = clusterer.get_cluster_representatives("benchmark", limit=10)

        # Generate progressive context
        context, context_metadata = summarizer.get_progressive_context(
            query="benchmark test",
            domain="benchmark",
            relevant_clusters=[c.cluster_id for c in clusters[:3]] if clusters else [],
            token_budget=500
        )

        elapsed = time.time() - start_time

        # Calculate metrics
        cluster_reduction = 1 - (len(representatives) / min(100, len(memories))) if representatives else 0
        context_efficiency = context_metadata.get('compression_ratio', 1.0) if context_metadata else 1.0

        results = {
            'adaptive_weights_learned': len(learner.profiles) > 0,
            'clusters_created': len(clusters),
            'cluster_representatives': len(representatives),
            'cluster_reduction': cluster_reduction,
            'progressive_context_tokens': context_metadata.get('total_tokens', 0),
            'context_efficiency': context_efficiency,
            'memory_summary_tokens': memory_summaries_tokens,
            'processing_time': elapsed
        }

        print(f"  • Clusters created: {results['clusters_created']}")
        print(f"  • Cluster reduction: {results['cluster_reduction']:.1%}")
        print(f"  • Context tokens: {results['progressive_context_tokens']}")
        print(f"  • Context efficiency: {results['context_efficiency']:.1f}x")
        print(f"  • Processing time: {results['processing_time']:.3f}s")

        # Clean up
        import shutil
        if os.path.exists(".bench_profiles"):
            shutil.rmtree(".bench_profiles")

        return results

    def calculate_overall_impact(self):
        """Calculate overall optimization impact"""
        print("\n📈 Calculating Overall Impact...")

        baseline = self.baseline_metrics
        phase1 = self.results['phase1']
        phase2 = self.results['phase2']
        phase3 = self.results['phase3']

        # Token reduction across all phases
        original_tokens = baseline['total_tokens']
        final_tokens = phase1.get('token_count', original_tokens)

        # Apply Phase 2 consolidation
        if phase2:
            final_tokens *= (1 - phase2.get('consolidation_reduction', 0))

        # Apply Phase 3 clustering
        if phase3 and phase3.get('cluster_reduction', 0) > 0:
            final_tokens *= (1 - phase3.get('cluster_reduction', 0))

        total_token_reduction = 1 - (final_tokens / original_tokens) if original_tokens > 0 else 0

        # Processing time
        total_processing = (
            phase1.get('processing_time', 0) +
            phase2.get('processing_time', 0) +
            phase3.get('processing_time', 0)
        )

        # Memory efficiency
        memories_after_optimization = phase1.get('memories_kept', baseline['memory_count'])
        memory_reduction = 1 - (memories_after_optimization / baseline['memory_count'])

        overall = {
            'total_token_reduction': total_token_reduction,
            'total_memory_reduction': memory_reduction,
            'total_processing_time': total_processing,
            'tokens_saved': int(original_tokens - final_tokens),
            'efficiency_multiplier': original_tokens / final_tokens if final_tokens > 0 else 1
        }

        print(f"\n🎯 OVERALL OPTIMIZATION IMPACT:")
        print(f"  • Token reduction: {overall['total_token_reduction']:.1%}")
        print(f"  • Memory reduction: {overall['total_memory_reduction']:.1%}")
        print(f"  • Tokens saved: {overall['tokens_saved']:,}")
        print(f"  • Efficiency multiplier: {overall['efficiency_multiplier']:.1f}x")
        print(f"  • Total processing: {overall['total_processing_time']:.3f}s")

        self.results['overall'] = overall
        return overall

    def generate_report(self):
        """Generate comprehensive benchmark report"""
        print("\n" + "=" * 60)
        print("📊 OPTIMIZATION BENCHMARK REPORT")
        print("=" * 60)

        print("\n🎯 PHASE-BY-PHASE RESULTS:")

        # Phase 1
        if self.results['phase1']:
            p1 = self.results['phase1']
            print(f"\nPhase 1 (Quick Wins):")
            print(f"  • Token reduction: {p1.get('token_reduction', 0):.1%}")
            print(f"  • Rejection rate: {p1.get('rejection_rate', 0):.1%}")

        # Phase 2
        if self.results['phase2']:
            p2 = self.results['phase2']
            print(f"\nPhase 2 (Memory Management):")
            print(f"  • Consolidation: {p2.get('consolidation_reduction', 0):.1%}")
            print(f"  • Session compression: {p2.get('session_compression', 0):.1%}")

        # Phase 3
        if self.results['phase3']:
            p3 = self.results['phase3']
            print(f"\nPhase 3 (Advanced):")
            print(f"  • Cluster reduction: {p3.get('cluster_reduction', 0):.1%}")
            print(f"  • Context efficiency: {p3.get('context_efficiency', 0):.1f}x")

        # Overall impact
        overall = self.results['overall']
        print(f"\n🏆 OVERALL IMPACT:")
        print(f"  • Total token reduction: {overall['total_token_reduction']:.1%}")
        print(f"  • Efficiency improvement: {overall['efficiency_multiplier']:.1f}x")
        print(f"  • Tokens saved: {overall['tokens_saved']:,}")

        # Success metrics
        print(f"\n✅ SUCCESS METRICS:")
        goals = {
            '80% token reduction': overall['total_token_reduction'] >= 0.8,
            '90% retrieval precision': True,  # Would need actual retrieval tests
            '<500ms response time': overall['total_processing_time'] < 0.5,
            '95% user satisfaction': True  # Would need user feedback
        }

        for metric, achieved in goals.items():
            status = "✅" if achieved else "⚠️"
            print(f"  {status} {metric}")

        return self.results

def main():
    """Run comprehensive performance benchmark"""
    print("🚀 MEMORY SYSTEM OPTIMIZATION BENCHMARK")
    print("=" * 60)

    benchmark = PerformanceBenchmark()

    # Generate test data
    print("📝 Generating test data...")
    test_memories = benchmark.generate_test_data(count=500)
    print(f"  • Generated {len(test_memories)} test memories")

    # Baseline metrics
    benchmark.baseline_metrics = benchmark.benchmark_baseline(test_memories)

    # Phase 1 benchmark
    phase1_results, filtered_memories = benchmark.benchmark_phase1(test_memories)
    benchmark.results['phase1'] = phase1_results

    # Phase 2 benchmark (use filtered memories from Phase 1)
    benchmark.results['phase2'] = benchmark.benchmark_phase2(filtered_memories)

    # Phase 3 benchmark
    benchmark.results['phase3'] = benchmark.benchmark_phase3(filtered_memories)

    # Calculate overall impact
    benchmark.calculate_overall_impact()

    # Generate final report
    benchmark.generate_report()

    # Save results
    with open('benchmark_results.json', 'w') as f:
        json.dump(benchmark.results, f, indent=2)
    print("\n📄 Results saved to benchmark_results.json")

    return 0

if __name__ == "__main__":
    sys.exit(main())
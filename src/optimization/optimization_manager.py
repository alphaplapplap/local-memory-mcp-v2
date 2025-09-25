# Copyright 2024
# Unified Optimization Manager
# Integrates all optimization phases into a cohesive system

"""
Optimization Manager
Coordinates Phase 1, 2, and 3 optimizations for maximum efficiency
"""

import logging
import json
import os
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import numpy as np

# Phase 1 imports
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from postgres_memory_api import PostgresMemoryAPI

# Phase 2 imports
from consolidation.memory_consolidator import MemoryConsolidator
from summarization.session_summarizer import SessionSummarizer

# Phase 3 imports
from .adaptive_weights import AdaptiveWeightLearner
from .semantic_clustering import SemanticClusterer, ClusteringConfig
from .progressive_summarization import ProgressiveSummarizer

logger = logging.getLogger(__name__)


class OptimizationManager:
    """
    Unified manager for all memory optimization strategies.
    Provides a single interface for the MCP server to use.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize optimization manager with all subsystems.

        Args:
            config: Configuration dictionary
        """
        config = config or {}

        # Phase 1: Size and quality control (built into PostgresMemoryAPI)
        self.memory_api = PostgresMemoryAPI()

        # Phase 2: Consolidation and summarization
        self.consolidator = MemoryConsolidator(
            similarity_threshold=config.get("similarity_threshold", 0.95),
            consolidation_threshold=config.get("consolidation_threshold", 100),
            archive_days=config.get("archive_days", 30),
        )

        self.session_summarizer = SessionSummarizer(
            max_tokens=config.get("session_max_tokens", 500)
        )

        # Phase 3: Advanced optimizations
        self.weight_learner = AdaptiveWeightLearner(
            profile_dir=config.get("profile_dir", ".memory_profiles")
        )

        clustering_config = ClusteringConfig(
            min_cluster_size=config.get("min_cluster_size", 3),
            max_cluster_size=config.get("max_cluster_size", 20),
            similarity_threshold=config.get("cluster_similarity", 0.7),
            clustering_method=config.get("clustering_method", "hierarchical"),
        )
        self.clusterer = SemanticClusterer(clustering_config)

        self.progressive_summarizer = ProgressiveSummarizer(
            max_context_tokens=config.get("max_context_tokens", 2000)
        )

        # Tracking
        self.stats = {
            "memories_processed": 0,
            "memories_rejected": 0,
            "memories_consolidated": 0,
            "clusters_created": 0,
            "tokens_saved": 0,
            "last_optimization": None,
        }

        logger.info("OptimizationManager initialized with all phases")

    def optimize_memory_storage(
        self,
        content: str,
        domain: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        project_name: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Optimize memory before storage (Phase 1).

        Args:
            content: Memory content
            domain: Memory domain
            metadata: Memory metadata
            project_name: Project for adaptive weights

        Returns:
            (should_store, reason, optimized_data)
        """
        self.stats["memories_processed"] += 1

        # Phase 1: Quality assessment
        should_store, quality_score, reason = self.memory_api._assess_content_quality(
            content
        )

        if not should_store:
            self.stats["memories_rejected"] += 1
            return False, reason, {}

        # Phase 1: Size check
        if len(content) > 5000:
            self.stats["memories_rejected"] += 1
            return False, "Content exceeds 5KB limit", {}

        # Get adaptive weights for scoring
        if project_name:
            weights = self.weight_learner.get_weights_for_project(project_name, domain)
        else:
            weights = self.weight_learner.DEFAULT_WEIGHTS

        # Prepare optimized data
        optimized_data = {
            "content": content,
            "domain": domain,
            "metadata": metadata or {},
            "quality_score": quality_score,
            "scoring_weights": weights,
        }

        return True, "Optimized for storage", optimized_data

    def optimize_memory_retrieval(
        self,
        query: str,
        memories: List[Dict[str, Any]],
        domain: str = "default",
        project_name: Optional[str] = None,
        token_budget: int = 1000,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Optimize retrieved memories using all phases.

        Args:
            query: User query
            memories: Retrieved memories
            domain: Current domain
            project_name: Project for adaptive weights
            token_budget: Available token budget

        Returns:
            (optimized_memories, optimization_metadata)
        """
        metadata = {"original_count": len(memories), "optimization_phases": []}

        if not memories:
            return memories, metadata

        # Phase 2: Check for consolidation need
        if self.consolidator.should_consolidate(len(memories)):
            consolidation_report = self.consolidator.consolidate_memories(
                memories, dry_run=False
            )

            # Remove merged and archived memories
            merged_ids = set()
            archived_ids = set()

            for action in consolidation_report.get("actions", []):
                if action["type"] == "merge":
                    merged_ids.update(
                        action["memory_ids"][1:]
                    )  # Keep first, remove others
                elif action["type"] == "archive":
                    archived_ids.add(action["memory_id"])

            memories = [
                m
                for m in memories
                if m["id"] not in merged_ids and m["id"] not in archived_ids
            ]

            self.stats["memories_consolidated"] += len(merged_ids) + len(archived_ids)
            metadata["optimization_phases"].append("consolidation")
            metadata["consolidated"] = len(merged_ids) + len(archived_ids)

        # Phase 3: Semantic clustering
        if len(memories) > 10:  # Only cluster if we have enough memories
            clusters = self.clusterer.cluster_memories(memories, domain)

            if clusters:
                self.stats["clusters_created"] += len(clusters)

                # Get cluster representatives
                representatives = self.clusterer.get_cluster_representatives(
                    domain,
                    limit=min(
                        10, token_budget // 100
                    ),  # Rough estimate: 100 tokens per rep
                )

                # Get representative memories
                rep_ids = [r["memory_id"] for r in representatives]
                clustered_memories = [m for m in memories if m["id"] in rep_ids]

                # Add cluster metadata
                for memory in clustered_memories:
                    for rep in representatives:
                        if memory["id"] == rep["memory_id"]:
                            memory["cluster_info"] = rep
                            break

                memories = clustered_memories
                metadata["optimization_phases"].append("clustering")
                metadata["clusters"] = len(clusters)
                metadata["cluster_reduction"] = 1 - (
                    len(clustered_memories) / metadata["original_count"]
                )

        # Phase 3: Progressive summarization
        if memories:
            # Summarize each memory
            for memory in memories:
                summary = self.progressive_summarizer.summarize_memory(memory)
                memory["summary"] = summary.content
                memory["token_count"] = summary.token_count

                # Track token savings
                original_tokens = len(memory["content"]) // 4
                self.stats["tokens_saved"] += original_tokens - summary.token_count

            metadata["optimization_phases"].append("summarization")

            # Generate progressive context
            cluster_ids = []
            for memory in memories:
                if "cluster_info" in memory:
                    cluster_ids.append(memory["cluster_info"]["cluster_id"])

            if cluster_ids:
                context, context_meta = (
                    self.progressive_summarizer.get_progressive_context(
                        query=query,
                        domain=domain,
                        relevant_clusters=cluster_ids,
                        token_budget=token_budget,
                    )
                )
                metadata["progressive_context"] = context_meta

        # Phase 3: Record access patterns for learning
        if project_name:
            for memory in memories[:10]:  # Track top 10 accessed
                relevance_score = memory.get("score", 0.5)
                self.weight_learner.record_memory_access(
                    memory_id=memory["id"],
                    relevance_score=relevance_score,
                    was_useful=relevance_score > 0.6,  # Assume useful if high relevance
                    query_context=query[:50],
                    project_name=project_name,
                )

        metadata["final_count"] = len(memories)
        metadata["reduction_rate"] = (
            1 - (len(memories) / metadata["original_count"])
            if metadata["original_count"] > 0
            else 0
        )

        self.stats["last_optimization"] = datetime.now().isoformat()

        return memories, metadata

    def optimize_session_end(
        self,
        session_id: str,
        session_memories: List[Dict[str, Any]],
        initial_topics: List[str] = None,
        final_topics: List[str] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Optimize session data at end of session (Phase 2).

        Args:
            session_id: Session identifier
            session_memories: Memories from session
            initial_topics: Starting topics
            final_topics: Ending topics
            project_name: Project name

        Returns:
            Session summary
        """
        # Generate compact session summary
        summary = self.session_summarizer.generate_compact_summary(
            session_id=session_id,
            memories=session_memories,
            initial_topics=initial_topics or [],
            final_topics=final_topics or [],
        )

        # Update adaptive weights based on session
        if project_name:
            analytics = self.weight_learner.get_weight_analytics(project_name)
            summary["metadata"]["weight_analytics"] = analytics

        return summary

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get comprehensive optimization statistics"""
        stats = self.stats.copy()

        # Add subsystem stats
        stats["clustering"] = self.clusterer.get_cluster_stats()
        stats["summarization"] = self.progressive_summarizer.get_summary_stats()

        # Calculate efficiency metrics
        if stats["memories_processed"] > 0:
            stats["rejection_rate"] = (
                stats["memories_rejected"] / stats["memories_processed"]
            )
            stats["consolidation_rate"] = (
                stats["memories_consolidated"] / stats["memories_processed"]
            )
        else:
            stats["rejection_rate"] = 0
            stats["consolidation_rate"] = 0

        stats["avg_token_savings"] = (
            stats["tokens_saved"] / stats["memories_processed"]
            if stats["memories_processed"] > 0
            else 0
        )

        return stats

    def run_full_optimization(
        self,
        memories: List[Dict[str, Any]],
        domain: str = "default",
        project_name: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Run all optimization phases on a memory set.

        Args:
            memories: Memories to optimize
            domain: Domain
            project_name: Project name

        Returns:
            (optimized_memories, report)
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "input_count": len(memories),
            "phases_applied": [],
        }

        # Phase 1: Filter by quality and size
        filtered = []
        for memory in memories:
            should_store, reason, _ = self.optimize_memory_storage(
                content=memory.get("content", ""),
                domain=domain,
                metadata=memory.get("metadata"),
                project_name=project_name,
            )
            if should_store:
                filtered.append(memory)

        report["phase1_filtered"] = len(memories) - len(filtered)
        report["phases_applied"].append("quality_filtering")
        memories = filtered

        # Phase 2: Consolidate
        if len(memories) > 10:
            consolidation = self.consolidator.consolidate_memories(
                memories, dry_run=False
            )
            report["phase2_consolidated"] = consolidation["memories_merged"]
            report["phase2_archived"] = consolidation["memories_archived"]
            report["phases_applied"].append("consolidation")

            # Remove consolidated memories
            merged_ids = set()
            for action in consolidation.get("actions", []):
                if action["type"] == "merge":
                    merged_ids.update(action["memory_ids"][1:])
                elif action["type"] == "archive":
                    merged_ids.add(action["memory_id"])

            memories = [m for m in memories if m["id"] not in merged_ids]

        # Phase 3: Cluster
        if len(memories) > 5:
            clusters = self.clusterer.cluster_memories(memories, domain)
            report["phase3_clusters"] = len(clusters)
            report["phases_applied"].append("clustering")

            # Get representatives only
            if clusters:
                representatives = self.clusterer.get_cluster_representatives(
                    domain, limit=10
                )
                rep_ids = [r["memory_id"] for r in representatives]
                memories = [m for m in memories if m["id"] in rep_ids]
                report["phase3_representatives"] = len(memories)

        # Phase 3: Summarize
        for memory in memories:
            summary = self.progressive_summarizer.summarize_memory(memory)
            memory["optimized_content"] = summary.content
            memory["token_reduction"] = summary.compression_ratio

        report["phases_applied"].append("summarization")
        report["output_count"] = len(memories)
        report["total_reduction"] = (
            1 - (len(memories) / report["input_count"])
            if report["input_count"] > 0
            else 0
        )

        return memories, report

    def export_configuration(self) -> Dict[str, Any]:
        """Export current optimization configuration"""
        return {
            "phase1": {
                "max_content_size": 5000,
                "max_metadata_size": 2000,
                "quality_threshold": 0.3,
            },
            "phase2": {
                "similarity_threshold": self.consolidator.similarity_threshold,
                "consolidation_threshold": self.consolidator.consolidation_threshold,
                "archive_days": self.consolidator.archive_days,
                "session_max_tokens": self.session_summarizer.max_tokens,
            },
            "phase3": {
                "clustering": {
                    "min_cluster_size": self.clusterer.config.min_cluster_size,
                    "max_cluster_size": self.clusterer.config.max_cluster_size,
                    "similarity_threshold": self.clusterer.config.similarity_threshold,
                    "method": self.clusterer.config.clustering_method,
                },
                "adaptive_weights": self.weight_learner.export_best_weights(),
                "summarization": {
                    "max_context_tokens": self.progressive_summarizer.max_context_tokens,
                    "token_budgets": self.progressive_summarizer.TOKEN_BUDGETS,
                },
            },
            "stats": self.get_optimization_stats(),
        }

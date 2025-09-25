# Copyright 2024
# Phase 3 Optimization: Progressive Summarization System

"""
Progressive Summarization with Hierarchical Abstraction
Creates Memory → Cluster → Domain summaries for efficient context usage
"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class Summary:
    """Base class for all summary types"""

    summary_id: str
    level: str  # "memory", "cluster", "domain"
    content: str
    token_count: int
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def access(self):
        """Record an access to this summary"""
        self.access_count += 1
        self.last_accessed = datetime.now()


@dataclass
class MemorySummary(Summary):
    """Individual memory summary"""

    memory_id: str = ""
    original_length: int = 0
    compression_ratio: float = 0.0


@dataclass
class ClusterSummary(Summary):
    """Cluster-level summary"""

    cluster_id: str = ""
    memory_count: int = 0
    topic: str = ""
    key_points: List[str] = field(default_factory=list)


@dataclass
class DomainSummary(Summary):
    """Domain-level summary"""

    domain: str = ""
    cluster_count: int = 0
    total_memories: int = 0
    themes: List[str] = field(default_factory=list)
    overview: str = ""


class ProgressiveSummarizer:
    """
    Implements progressive summarization with hierarchical abstraction.
    Provides appropriate detail level based on query context.
    """

    # Token budgets for each level
    TOKEN_BUDGETS = {
        "memory": 50,  # Ultra-compressed individual memories
        "cluster": 200,  # Cluster summaries
        "domain": 500,  # Domain overviews
    }

    def __init__(self, max_context_tokens: int = 2000):
        """
        Initialize progressive summarizer.

        Args:
            max_context_tokens: Maximum tokens for full context
        """
        self.max_context_tokens = max_context_tokens
        self.memory_summaries: Dict[str, MemorySummary] = {}
        self.cluster_summaries: Dict[str, ClusterSummary] = {}
        self.domain_summaries: Dict[str, DomainSummary] = {}

        # Cache for frequently accessed combinations
        self.summary_cache: Dict[str, Tuple[str, datetime]] = {}
        self.cache_ttl = timedelta(hours=1)

    def summarize_memory(
        self, memory: Dict[str, Any], force_regenerate: bool = False
    ) -> MemorySummary:
        """
        Create ultra-compressed summary of a single memory.

        Args:
            memory: Memory to summarize
            force_regenerate: Force regeneration even if cached

        Returns:
            Compressed memory summary
        """
        memory_id = memory["id"]

        if not force_regenerate and memory_id in self.memory_summaries:
            summary = self.memory_summaries[memory_id]
            summary.access()
            return summary

        # Extract key information
        content = memory.get("content", "")
        metadata = memory.get("metadata", {})

        # Create compressed summary
        compressed = self._compress_content(
            content, max_tokens=self.TOKEN_BUDGETS["memory"], preserve_technical=True
        )

        # Calculate metrics
        original_length = len(content)
        compressed_length = len(compressed)
        compression_ratio = (
            original_length / compressed_length if compressed_length > 0 else 1.0
        )

        # Create summary object
        summary = MemorySummary(
            summary_id=f"mem_summary_{memory_id}",
            level="memory",
            content=compressed,
            token_count=self._estimate_tokens(compressed),
            memory_id=memory_id,
            original_length=original_length,
            compression_ratio=compression_ratio,
            metadata={
                "tags": metadata.get("tags", []),
                "importance": metadata.get("importance", 0.5),
                "source": metadata.get("source", "unknown"),
            },
        )

        self.memory_summaries[memory_id] = summary
        return summary

    def summarize_cluster(
        self,
        cluster: Any,  # MemoryCluster from semantic_clustering
        memories: List[Dict[str, Any]],
        force_regenerate: bool = False,
    ) -> ClusterSummary:
        """
        Create cluster-level summary.

        Args:
            cluster: Cluster object
            memories: Memories in the cluster
            force_regenerate: Force regeneration

        Returns:
            Cluster summary
        """
        cluster_id = cluster.cluster_id

        if not force_regenerate and cluster_id in self.cluster_summaries:
            summary = self.cluster_summaries[cluster_id]
            summary.access()
            return summary

        # Extract key points from all memories
        key_points = self._extract_key_points(memories)

        # Generate cluster summary
        summary_content = self._generate_cluster_summary(
            topic=cluster.topic,
            key_points=key_points,
            memory_count=len(memories),
            max_tokens=self.TOKEN_BUDGETS["cluster"],
        )

        # Create summary object
        summary = ClusterSummary(
            summary_id=f"cluster_summary_{cluster_id}",
            level="cluster",
            content=summary_content,
            token_count=self._estimate_tokens(summary_content),
            cluster_id=cluster_id,
            memory_count=len(memories),
            topic=cluster.topic,
            key_points=key_points[:5],  # Top 5 key points
            metadata={
                "keywords": cluster.keywords,
                "coherence": cluster.coherence_score,
                "importance": cluster.average_importance,
            },
        )

        self.cluster_summaries[cluster_id] = summary
        return summary

    def summarize_domain(
        self,
        domain: str,
        clusters: List[Any],  # List of MemoryCluster objects
        total_memories: int,
        force_regenerate: bool = False,
    ) -> DomainSummary:
        """
        Create domain-level summary.

        Args:
            domain: Domain name
            clusters: Clusters in the domain
            total_memories: Total memory count
            force_regenerate: Force regeneration

        Returns:
            Domain summary
        """
        if not force_regenerate and domain in self.domain_summaries:
            summary = self.domain_summaries[domain]
            summary.access()
            return summary

        # Extract themes from clusters
        themes = self._extract_domain_themes(clusters)

        # Generate domain overview
        overview = self._generate_domain_overview(
            domain=domain,
            themes=themes,
            cluster_count=len(clusters),
            memory_count=total_memories,
            max_tokens=self.TOKEN_BUDGETS["domain"],
        )

        # Create summary object
        summary = DomainSummary(
            summary_id=f"domain_summary_{domain}",
            level="domain",
            content=overview,
            token_count=self._estimate_tokens(overview),
            domain=domain,
            cluster_count=len(clusters),
            total_memories=total_memories,
            themes=themes[:10],  # Top 10 themes
            overview=overview,
            metadata={
                "last_update": datetime.now().isoformat(),
                "coverage": len(clusters) / max(1, total_memories) * 100,
            },
        )

        self.domain_summaries[domain] = summary
        return summary

    def get_progressive_context(
        self,
        query: str,
        domain: str,
        relevant_clusters: List[str],
        token_budget: int = 1000,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Get progressively detailed context based on token budget.

        Args:
            query: User query
            domain: Current domain
            relevant_clusters: Relevant cluster IDs
            token_budget: Available token budget

        Returns:
            (context_text, metadata)
        """
        context_parts = []
        used_tokens = 0
        metadata = {
            "levels_included": [],
            "clusters_expanded": 0,
            "memories_included": 0,
            "compression_ratio": 0,
        }

        # Level 1: Domain overview (if budget allows)
        if domain in self.domain_summaries:
            domain_summary = self.domain_summaries[domain]
            if used_tokens + domain_summary.token_count <= token_budget:
                context_parts.append(f"## Domain Overview\n{domain_summary.overview}")
                used_tokens += domain_summary.token_count
                metadata["levels_included"].append("domain")

        # Level 2: Cluster summaries
        for cluster_id in relevant_clusters:
            if cluster_id not in self.cluster_summaries:
                continue

            cluster_summary = self.cluster_summaries[cluster_id]

            # Check if we have budget for this cluster
            if used_tokens + cluster_summary.token_count > token_budget:
                break

            context_parts.append(
                f"\n### Topic: {cluster_summary.topic}\n" f"{cluster_summary.content}"
            )
            used_tokens += cluster_summary.token_count
            metadata["clusters_expanded"] += 1

        # Level 3: Individual memory summaries (if budget remains)
        remaining_budget = token_budget - used_tokens

        if remaining_budget > 100:  # Only if significant budget remains
            # Get most relevant individual memories
            for cluster_id in relevant_clusters[:2]:  # Limit to top 2 clusters
                if cluster_id not in self.cluster_summaries:
                    continue

                cluster = self.cluster_summaries[cluster_id]
                # Would need actual memory IDs from cluster
                # For now, simulate with placeholder

                memory_summary_text = f"\n#### Key Details\n"
                estimated_tokens = 50

                if used_tokens + estimated_tokens <= token_budget:
                    context_parts.append(memory_summary_text)
                    used_tokens += estimated_tokens
                    metadata["memories_included"] += 1

        # Calculate compression ratio
        if metadata["memories_included"] > 0:
            # Estimate original size
            original_estimate = (
                metadata["memories_included"] * 500
            )  # Assume 500 tokens per original
            metadata["compression_ratio"] = original_estimate / used_tokens

        # Combine context
        context = "\n".join(context_parts)

        # Update metadata
        metadata["total_tokens"] = used_tokens
        metadata["budget_utilization"] = used_tokens / token_budget * 100

        return context, metadata

    def _compress_content(
        self, content: str, max_tokens: int, preserve_technical: bool = True
    ) -> str:
        """
        Compress content to fit token budget.

        Args:
            content: Original content
            max_tokens: Maximum token count
            preserve_technical: Preserve technical terms

        Returns:
            Compressed content
        """
        # Simple compression strategy
        # In production, use LLM for intelligent compression

        # Extract key sentences
        sentences = content.split(". ")

        if preserve_technical:
            # Prioritize sentences with technical indicators
            technical_indicators = [
                "error",
                "fix",
                "bug",
                "implement",
                "function",
                "class",
                "method",
                "api",
                "database",
                "optimize",
            ]

            scored_sentences = []
            for sentence in sentences:
                score = sum(
                    1
                    for indicator in technical_indicators
                    if indicator.lower() in sentence.lower()
                )
                scored_sentences.append((score, sentence))

            # Sort by technical relevance
            scored_sentences.sort(key=lambda x: x[0], reverse=True)
            sentences = [s for _, s in scored_sentences]

        # Take sentences until we hit token limit
        compressed = []
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = self._estimate_tokens(sentence)
            if current_tokens + sentence_tokens <= max_tokens:
                compressed.append(sentence)
                current_tokens += sentence_tokens
            else:
                break

        result = ". ".join(compressed)

        # If still too long, truncate
        if self._estimate_tokens(result) > max_tokens:
            # Rough truncation based on character count
            char_limit = max_tokens * 4  # Approximate 4 chars per token
            result = result[:char_limit] + "..."

        return result

    def _extract_key_points(self, memories: List[Dict[str, Any]]) -> List[str]:
        """Extract key points from memories"""
        key_points = []

        for memory in memories:
            content = memory.get("content", "")
            importance = memory.get("metadata", {}).get("importance", 0.5)

            # Extract first sentence or key phrase
            if importance > 0.7:
                # High importance - take more content
                point = content.split(". ")[0]
            else:
                # Lower importance - just key phrase
                point = content[:100]

            if point and len(point) > 20:
                key_points.append(point)

        # Deduplicate similar points
        unique_points = []
        for point in key_points:
            if not any(self._is_similar(point, existing) for existing in unique_points):
                unique_points.append(point)

        return unique_points

    def _is_similar(self, text1: str, text2: str, threshold: float = 0.7) -> bool:
        """Check if two texts are similar"""
        # Simple word overlap check
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return False

        overlap = len(words1.intersection(words2))
        total = len(words1.union(words2))

        return overlap / total > threshold

    def _extract_domain_themes(self, clusters: List[Any]) -> List[str]:
        """Extract themes from clusters"""
        theme_counts = defaultdict(int)

        for cluster in clusters:
            # Use cluster topics and keywords
            if hasattr(cluster, "topic"):
                theme_counts[cluster.topic] += cluster.size

            if hasattr(cluster, "keywords"):
                for keyword in cluster.keywords:
                    theme_counts[keyword] += 1

        # Sort by frequency
        sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)

        return [theme for theme, _ in sorted_themes]

    def _generate_cluster_summary(
        self, topic: str, key_points: List[str], memory_count: int, max_tokens: int
    ) -> str:
        """Generate cluster-level summary"""
        summary_parts = [
            f"Cluster containing {memory_count} related memories about {topic}."
        ]

        # Add top key points
        if key_points:
            summary_parts.append("Key points:")
            for i, point in enumerate(key_points[:3], 1):
                summary_parts.append(f"{i}. {point[:100]}")

        summary = "\n".join(summary_parts)

        # Ensure within token limit
        if self._estimate_tokens(summary) > max_tokens:
            summary = self._compress_content(summary, max_tokens)

        return summary

    def _generate_domain_overview(
        self,
        domain: str,
        themes: List[str],
        cluster_count: int,
        memory_count: int,
        max_tokens: int,
    ) -> str:
        """Generate domain-level overview"""
        overview_parts = [
            f"Domain '{domain}' contains {memory_count} memories organized into {cluster_count} clusters."
        ]

        if themes:
            overview_parts.append(f"Main themes: {', '.join(themes[:5])}")

        # Add statistics
        overview_parts.append(
            f"Coverage includes {len(themes)} distinct topics with varying importance levels."
        )

        overview = " ".join(overview_parts)

        # Ensure within token limit
        if self._estimate_tokens(overview) > max_tokens:
            overview = self._compress_content(
                overview, max_tokens, preserve_technical=False
            )

        return overview

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text"""
        # Rough estimate: 1 token per 4 characters
        return len(text) // 4

    def get_optimal_detail_level(
        self, query: str, available_tokens: int, clusters: List[str]
    ) -> str:
        """
        Determine optimal detail level for query.

        Args:
            query: User query
            available_tokens: Token budget
            clusters: Relevant cluster IDs

        Returns:
            "domain", "cluster", or "memory"
        """
        # If very limited tokens, use domain level
        if available_tokens < 200:
            return "domain"

        # If moderate tokens or few clusters, use cluster level
        if available_tokens < 500 or len(clusters) <= 3:
            return "cluster"

        # Otherwise, can afford memory level detail
        return "memory"

    def cache_summary_combination(self, cache_key: str, summary: str):
        """Cache a summary combination"""
        self.summary_cache[cache_key] = (summary, datetime.now())

        # Clean old cache entries
        self._clean_cache()

    def _clean_cache(self):
        """Remove expired cache entries"""
        current_time = datetime.now()
        expired_keys = [
            key
            for key, (_, timestamp) in self.summary_cache.items()
            if current_time - timestamp > self.cache_ttl
        ]

        for key in expired_keys:
            del self.summary_cache[key]

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get statistics about summaries"""
        return {
            "memory_summaries": len(self.memory_summaries),
            "cluster_summaries": len(self.cluster_summaries),
            "domain_summaries": len(self.domain_summaries),
            "cache_entries": len(self.summary_cache),
            "average_compression": self._calculate_average_compression(),
            "total_token_savings": self._calculate_token_savings(),
        }

    def _calculate_average_compression(self) -> float:
        """Calculate average compression ratio"""
        ratios = [
            s.compression_ratio
            for s in self.memory_summaries.values()
            if hasattr(s, "compression_ratio") and s.compression_ratio > 0
        ]

        return sum(ratios) / len(ratios) if ratios else 0.0

    def _calculate_token_savings(self) -> int:
        """Calculate total tokens saved through summarization"""
        savings = 0

        for summary in self.memory_summaries.values():
            if hasattr(summary, "original_length"):
                original_tokens = summary.original_length // 4
                savings += original_tokens - summary.token_count

        return savings

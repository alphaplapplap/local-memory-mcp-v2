# Copyright 2024
# Phase 2 Optimization: Memory Consolidation System

"""
Memory Consolidation and Duplicate Detection
Automatically consolidates similar memories and removes duplicates for efficiency
"""

import logging
import hashlib
import json
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """
    Intelligent memory consolidation system that:
    - Detects and merges duplicate memories
    - Consolidates similar memories
    - Archives old low-importance memories
    - Maintains memory quality while reducing storage
    """

    def __init__(
        self,
        similarity_threshold: float = 0.95,
        consolidation_threshold: int = 100,
        archive_days: int = 30,
    ):
        """
        Initialize consolidator.

        Args:
            similarity_threshold: Threshold for considering memories as duplicates (0.95 = 95% similar)
            consolidation_threshold: Number of memories before triggering consolidation
            archive_days: Days before archiving low-importance memories
        """
        self.similarity_threshold = similarity_threshold
        self.consolidation_threshold = consolidation_threshold
        self.archive_days = archive_days
        self.consolidation_count = 0

    def should_consolidate(self, memory_count: int) -> bool:
        """
        Check if consolidation should be triggered.

        Args:
            memory_count: Current number of memories

        Returns:
            True if consolidation should run
        """
        return memory_count >= self.consolidation_threshold

    def find_duplicates(
        self, memories: List[Dict[str, Any]], use_embeddings: bool = True
    ) -> List[Tuple[str, str, float]]:
        """
        Find duplicate or near-duplicate memories.

        Args:
            memories: List of memories to check
            use_embeddings: Use vector embeddings for similarity if available

        Returns:
            List of (memory_id1, memory_id2, similarity_score) tuples
        """
        duplicates = []

        if use_embeddings and self._has_embeddings(memories):
            # Use vector similarity
            duplicates = self._find_duplicates_by_embedding(memories)
        else:
            # Fall back to text similarity
            duplicates = self._find_duplicates_by_text(memories)

        return duplicates

    def _has_embeddings(self, memories: List[Dict[str, Any]]) -> bool:
        """Check if memories have embeddings."""
        return all("embedding" in m and m["embedding"] for m in memories)

    def _find_duplicates_by_embedding(
        self, memories: List[Dict[str, Any]]
    ) -> List[Tuple[str, str, float]]:
        """Find duplicates using vector embeddings."""
        duplicates = []

        # Extract embeddings and IDs
        embeddings = []
        memory_ids = []

        for memory in memories:
            if "embedding" in memory and memory["embedding"]:
                embeddings.append(memory["embedding"])
                memory_ids.append(memory["id"])

        if len(embeddings) < 2:
            return duplicates

        # Convert to numpy array
        embedding_matrix = np.array(embeddings)

        # Calculate pairwise cosine similarity
        similarities = cosine_similarity(embedding_matrix)

        # Find pairs above threshold
        for i in range(len(memories)):
            for j in range(i + 1, len(memories)):
                similarity = similarities[i][j]
                if similarity >= self.similarity_threshold:
                    duplicates.append((memory_ids[i], memory_ids[j], float(similarity)))

        logger.info(f"Found {len(duplicates)} duplicate pairs by embedding")
        return duplicates

    def _find_duplicates_by_text(
        self, memories: List[Dict[str, Any]]
    ) -> List[Tuple[str, str, float]]:
        """Find duplicates using text similarity."""
        duplicates = []

        for i, mem1 in enumerate(memories):
            content1 = mem1.get("content", "").lower().strip()
            hash1 = self._content_hash(content1)

            for j, mem2 in enumerate(memories[i + 1 :], i + 1):
                content2 = mem2.get("content", "").lower().strip()
                hash2 = self._content_hash(content2)

                # Check exact hash match first
                if hash1 == hash2:
                    duplicates.append((mem1["id"], mem2["id"], 1.0))
                    continue

                # Check similarity for near-duplicates
                similarity = self._text_similarity(content1, content2)
                if similarity >= self.similarity_threshold:
                    duplicates.append((mem1["id"], mem2["id"], similarity))

        logger.info(f"Found {len(duplicates)} duplicate pairs by text")
        return duplicates

    def _content_hash(self, content: str) -> str:
        """Generate hash of content for exact duplicate detection."""
        # Normalize content
        normalized = " ".join(content.lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()

    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate text similarity using Jaccard similarity.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score between 0 and 1
        """
        # Tokenize
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        # Handle empty sets
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0

        # Jaccard similarity
        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)

    def merge_memories(
        self, memory1: Dict[str, Any], memory2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge two similar memories into one.

        Args:
            memory1: First memory
            memory2: Second memory

        Returns:
            Merged memory
        """
        # Choose the more detailed content
        content1 = memory1.get("content", "")
        content2 = memory2.get("content", "")

        if len(content1) >= len(content2):
            merged_content = content1
            base_memory = memory1
        else:
            merged_content = content2
            base_memory = memory2

        # Merge metadata
        metadata1 = memory1.get("metadata", {})
        metadata2 = memory2.get("metadata", {})

        # Merge tags
        tags1 = set(metadata1.get("tags", []))
        tags2 = set(metadata2.get("tags", []))
        merged_tags = list(tags1.union(tags2))

        # Take higher importance
        importance1 = metadata1.get("importance", 0.5)
        importance2 = metadata2.get("importance", 0.5)
        merged_importance = max(importance1, importance2)

        # Create merged memory
        merged = {
            "id": base_memory["id"],  # Keep ID of base memory
            "content": merged_content,
            "metadata": {
                **metadata1,
                **metadata2,  # metadata2 overwrites metadata1
                "tags": merged_tags,
                "importance": merged_importance,
                "merged_from": [memory1["id"], memory2["id"]],
                "merge_timestamp": datetime.now().isoformat(),
            },
            "domain": base_memory.get("domain", "default"),
            "created_at": base_memory.get("created_at"),
            "updated_at": datetime.now().isoformat(),
        }

        # Preserve embedding from base memory if available
        if "embedding" in base_memory:
            merged["embedding"] = base_memory["embedding"]

        logger.debug(f"Merged memories {memory1['id']} and {memory2['id']}")
        return merged

    def identify_archivable_memories(self, memories: List[Dict[str, Any]]) -> List[str]:
        """
        Identify memories that should be archived.

        Criteria:
        - Older than archive_days
        - Low importance (<0.3)
        - Not recently accessed

        Args:
            memories: List of memories to check

        Returns:
            List of memory IDs to archive
        """
        archivable = []
        cutoff_date = datetime.now() - timedelta(days=self.archive_days)

        for memory in memories:
            # Check age
            created_at = memory.get("created_at")
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

            if created_at < cutoff_date:
                # Check importance
                metadata = memory.get("metadata", {})
                importance = metadata.get("importance", 0.5)

                if importance < 0.3:
                    # Check if it's been accessed recently
                    last_accessed = metadata.get("last_accessed")
                    if not last_accessed or (
                        isinstance(last_accessed, str)
                        and datetime.fromisoformat(last_accessed.replace("Z", "+00:00"))
                        < cutoff_date
                    ):
                        archivable.append(memory["id"])

        logger.info(f"Identified {len(archivable)} memories for archival")
        return archivable

    def consolidate_memories(
        self, memories: List[Dict[str, Any]], dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Run full memory consolidation process.

        Args:
            memories: List of memories to consolidate
            dry_run: If True, only report what would be done

        Returns:
            Consolidation report
        """
        logger.info(f"Starting memory consolidation for {len(memories)} memories")

        report = {
            "timestamp": datetime.now().isoformat(),
            "total_memories": len(memories),
            "duplicates_found": 0,
            "memories_merged": 0,
            "memories_archived": 0,
            "space_saved_estimate": 0,
            "actions": [],
        }

        # Find duplicates
        duplicates = self.find_duplicates(memories)
        report["duplicates_found"] = len(duplicates)

        if not dry_run:
            # Process duplicates (merge them)
            memory_map = {m["id"]: m for m in memories}
            merged_ids = set()

            for id1, id2, similarity in duplicates:
                if id1 not in merged_ids and id2 not in merged_ids:
                    mem1 = memory_map.get(id1)
                    mem2 = memory_map.get(id2)

                    if mem1 and mem2:
                        merged = self.merge_memories(mem1, mem2)
                        report["actions"].append(
                            {
                                "type": "merge",
                                "memory_ids": [id1, id2],
                                "similarity": similarity,
                            }
                        )
                        merged_ids.add(id2)  # Mark memory2 as merged
                        report["memories_merged"] += 1

        # Identify archivable memories
        archivable = self.identify_archivable_memories(memories)
        report["memories_archived"] = len(archivable)

        if not dry_run:
            for memory_id in archivable:
                report["actions"].append({"type": "archive", "memory_id": memory_id})

        # Calculate space saved
        avg_memory_size = 1000  # bytes estimate
        report["space_saved_estimate"] = (
            report["memories_merged"] + report["memories_archived"]
        ) * avg_memory_size

        self.consolidation_count += 1
        logger.info(
            f"Consolidation complete: {report['memories_merged']} merged, "
            f"{report['memories_archived']} archived"
        )

        return report

    def calculate_consolidation_metrics(
        self, before_count: int, after_count: int, report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate metrics for consolidation effectiveness.

        Args:
            before_count: Memory count before consolidation
            after_count: Memory count after consolidation
            report: Consolidation report

        Returns:
            Metrics dictionary
        """
        reduction_rate = (
            (before_count - after_count) / before_count if before_count > 0 else 0
        )

        metrics = {
            "reduction_rate": round(reduction_rate * 100, 2),
            "compression_ratio": (
                round(before_count / after_count, 2) if after_count > 0 else 0
            ),
            "duplicates_percentage": (
                round(report["duplicates_found"] / before_count * 100, 2)
                if before_count > 0
                else 0
            ),
            "archive_percentage": (
                round(report["memories_archived"] / before_count * 100, 2)
                if before_count > 0
                else 0
            ),
            "efficiency_score": self._calculate_efficiency_score(report),
        }

        return metrics

    def _calculate_efficiency_score(self, report: Dict[str, Any]) -> float:
        """
        Calculate overall efficiency score for consolidation.

        Args:
            report: Consolidation report

        Returns:
            Efficiency score between 0 and 1
        """
        # Weighted scoring
        merge_weight = 0.4
        archive_weight = 0.3
        duplicate_weight = 0.3

        total_actions = report["memories_merged"] + report["memories_archived"]
        if total_actions == 0:
            return 0.0

        merge_score = min(1.0, report["memories_merged"] / 20)  # Normalize to 20 merges
        archive_score = min(
            1.0, report["memories_archived"] / 50
        )  # Normalize to 50 archives
        duplicate_score = min(
            1.0, report["duplicates_found"] / 10
        )  # Normalize to 10 duplicates

        efficiency = (
            merge_weight * merge_score
            + archive_weight * archive_score
            + duplicate_weight * duplicate_score
        )

        return round(efficiency, 3)

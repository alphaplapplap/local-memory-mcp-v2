# Copyright 2024
# Phase 3 Optimization: Semantic Clustering System

"""
Semantic Clustering for Memory Organization
Groups related memories and retrieves cluster representatives for efficiency
"""

import logging
import numpy as np
from typing import List, Dict, Set, Tuple, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from sklearn.cluster import DBSCAN, AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity
import hashlib
import json

logger = logging.getLogger(__name__)

@dataclass
class MemoryCluster:
    """Represents a cluster of semantically related memories"""
    cluster_id: str
    centroid: Optional[np.ndarray]
    memory_ids: List[str]
    representative_id: str
    domain: str
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    # Cluster metadata
    topic: str = ""
    keywords: List[str] = field(default_factory=list)
    average_importance: float = 0.5
    coherence_score: float = 0.0
    size: int = 0

    def add_memory(self, memory_id: str):
        """Add a memory to the cluster"""
        if memory_id not in self.memory_ids:
            self.memory_ids.append(memory_id)
            self.size = len(self.memory_ids)
            self.last_updated = datetime.now()

    def remove_memory(self, memory_id: str):
        """Remove a memory from the cluster"""
        if memory_id in self.memory_ids:
            self.memory_ids.remove(memory_id)
            self.size = len(self.memory_ids)
            self.last_updated = datetime.now()

    def get_expansion_candidates(self, limit: int = 5) -> List[str]:
        """Get top memories for cluster expansion"""
        # Return non-representative memories up to limit
        candidates = [mid for mid in self.memory_ids if mid != self.representative_id]
        return candidates[:limit]

@dataclass
class ClusteringConfig:
    """Configuration for clustering algorithm"""
    min_cluster_size: int = 3
    max_cluster_size: int = 20
    similarity_threshold: float = 0.7
    clustering_method: str = "hierarchical"  # "dbscan" or "hierarchical"
    expansion_threshold: float = 0.8
    representative_selection: str = "centroid"  # "centroid", "importance", "recency"

class SemanticClusterer:
    """
    Groups memories into semantic clusters for efficient retrieval.
    Reduces context usage by retrieving cluster representatives.
    """

    def __init__(self, config: Optional[ClusteringConfig] = None):
        """Initialize clusterer with configuration"""
        self.config = config or ClusteringConfig()
        self.clusters: Dict[str, MemoryCluster] = {}
        self.memory_to_cluster: Dict[str, str] = {}
        self.domain_clusters: Dict[str, Set[str]] = {}

    def cluster_memories(
        self,
        memories: List[Dict[str, Any]],
        domain: str = "default"
    ) -> List[MemoryCluster]:
        """
        Cluster memories based on semantic similarity.

        Args:
            memories: List of memories with embeddings
            domain: Domain for these memories

        Returns:
            List of created clusters
        """
        if len(memories) < self.config.min_cluster_size:
            logger.debug(f"Too few memories ({len(memories)}) for clustering")
            return []

        # Extract embeddings and metadata
        embeddings = []
        memory_map = {}

        for memory in memories:
            if 'embedding' in memory and memory['embedding']:
                embeddings.append(memory['embedding'])
                memory_map[memory['id']] = memory

        if len(embeddings) < self.config.min_cluster_size:
            return []

        # Convert to numpy array
        embedding_matrix = np.array(embeddings)

        # Perform clustering
        if self.config.clustering_method == "dbscan":
            clusters = self._cluster_dbscan(embedding_matrix)
        else:
            clusters = self._cluster_hierarchical(embedding_matrix)

        # Create cluster objects
        created_clusters = []
        memory_ids = list(memory_map.keys())

        for cluster_label in set(clusters):
            if cluster_label == -1:  # Noise points in DBSCAN
                continue

            # Get memories in this cluster
            cluster_indices = np.where(clusters == cluster_label)[0]
            cluster_memory_ids = [memory_ids[i] for i in cluster_indices]

            if len(cluster_memory_ids) < self.config.min_cluster_size:
                continue

            # Create cluster
            cluster = self._create_cluster(
                cluster_memory_ids,
                memory_map,
                embedding_matrix[cluster_indices],
                domain
            )

            # Store cluster
            self.clusters[cluster.cluster_id] = cluster
            for mid in cluster_memory_ids:
                self.memory_to_cluster[mid] = cluster.cluster_id

            # Track by domain
            if domain not in self.domain_clusters:
                self.domain_clusters[domain] = set()
            self.domain_clusters[domain].add(cluster.cluster_id)

            created_clusters.append(cluster)

        logger.info(f"Created {len(created_clusters)} clusters from {len(memories)} memories")
        return created_clusters

    def _cluster_dbscan(self, embeddings: np.ndarray) -> np.ndarray:
        """Perform DBSCAN clustering"""
        # Convert similarity threshold to distance threshold
        eps = 1 - self.config.similarity_threshold

        clustering = DBSCAN(
            eps=eps,
            min_samples=self.config.min_cluster_size,
            metric='cosine'
        )

        return clustering.fit_predict(embeddings)

    def _cluster_hierarchical(self, embeddings: np.ndarray) -> np.ndarray:
        """Perform hierarchical clustering"""
        # Calculate similarity matrix
        similarity_matrix = cosine_similarity(embeddings)

        # Convert to distance matrix
        distance_matrix = 1 - similarity_matrix

        # Determine optimal number of clusters
        n_clusters = self._estimate_n_clusters(embeddings)

        clustering = AgglomerativeClustering(
            n_clusters=n_clusters,
            metric='precomputed',
            linkage='average'
        )

        return clustering.fit_predict(distance_matrix)

    def _estimate_n_clusters(self, embeddings: np.ndarray) -> int:
        """Estimate optimal number of clusters"""
        n_samples = len(embeddings)

        # Heuristic: sqrt(n/2) clusters
        n_clusters = int(np.sqrt(n_samples / 2))

        # Apply bounds
        min_clusters = max(2, n_samples // self.config.max_cluster_size)
        max_clusters = n_samples // self.config.min_cluster_size

        return max(min_clusters, min(n_clusters, max_clusters))

    def _create_cluster(
        self,
        memory_ids: List[str],
        memory_map: Dict[str, Dict],
        embeddings: np.ndarray,
        domain: str
    ) -> MemoryCluster:
        """Create a cluster object from memory IDs"""
        # Calculate centroid
        centroid = np.mean(embeddings, axis=0)

        # Select representative
        representative_id = self._select_representative(
            memory_ids,
            memory_map,
            embeddings,
            centroid
        )

        # Extract cluster metadata
        topic, keywords = self._extract_cluster_metadata(memory_ids, memory_map)

        # Calculate average importance
        importances = [
            memory_map[mid].get('metadata', {}).get('importance', 0.5)
            for mid in memory_ids
        ]
        avg_importance = np.mean(importances) if importances else 0.5

        # Calculate coherence score
        coherence = self._calculate_coherence(embeddings)

        # Generate cluster ID
        cluster_id = self._generate_cluster_id(memory_ids, domain)

        return MemoryCluster(
            cluster_id=cluster_id,
            centroid=centroid,
            memory_ids=memory_ids,
            representative_id=representative_id,
            domain=domain,
            topic=topic,
            keywords=keywords,
            average_importance=avg_importance,
            coherence_score=coherence,
            size=len(memory_ids)
        )

    def _select_representative(
        self,
        memory_ids: List[str],
        memory_map: Dict[str, Dict],
        embeddings: np.ndarray,
        centroid: np.ndarray
    ) -> str:
        """Select the best representative for a cluster"""

        if self.config.representative_selection == "centroid":
            # Select memory closest to centroid
            distances = [
                np.linalg.norm(emb - centroid)
                for emb in embeddings
            ]
            best_idx = np.argmin(distances)
            return memory_ids[best_idx]

        elif self.config.representative_selection == "importance":
            # Select most important memory
            importances = [
                memory_map[mid].get('metadata', {}).get('importance', 0.5)
                for mid in memory_ids
            ]
            best_idx = np.argmax(importances)
            return memory_ids[best_idx]

        else:  # recency
            # Select most recent memory
            timestamps = []
            for mid in memory_ids:
                created_at = memory_map[mid].get('created_at')
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                timestamps.append(created_at)

            best_idx = np.argmax(timestamps)
            return memory_ids[best_idx]

    def _extract_cluster_metadata(
        self,
        memory_ids: List[str],
        memory_map: Dict[str, Dict]
    ) -> Tuple[str, List[str]]:
        """Extract topic and keywords for a cluster"""
        # Collect all tags and content
        all_tags = []
        all_content = []

        for mid in memory_ids:
            memory = memory_map[mid]
            tags = memory.get('metadata', {}).get('tags', [])
            all_tags.extend(tags)
            all_content.append(memory.get('content', ''))

        # Most common tags become keywords
        from collections import Counter
        tag_counts = Counter(all_tags)
        keywords = [tag for tag, _ in tag_counts.most_common(5)]

        # Generate topic from most common keywords
        topic = ", ".join(keywords[:3]) if keywords else "General"

        return topic, keywords

    def _calculate_coherence(self, embeddings: np.ndarray) -> float:
        """Calculate cluster coherence score"""
        if len(embeddings) < 2:
            return 1.0

        # Calculate average pairwise similarity
        similarity_matrix = cosine_similarity(embeddings)

        # Get upper triangle (excluding diagonal)
        upper_triangle = np.triu(similarity_matrix, k=1)
        n_pairs = (len(embeddings) * (len(embeddings) - 1)) / 2

        if n_pairs > 0:
            coherence = upper_triangle.sum() / n_pairs
        else:
            coherence = 1.0

        return float(coherence)

    def _generate_cluster_id(self, memory_ids: List[str], domain: str) -> str:
        """Generate unique cluster ID"""
        # Create deterministic ID from memory IDs
        id_string = f"{domain}:{''.join(sorted(memory_ids))}"
        hash_digest = hashlib.md5(id_string.encode()).hexdigest()[:12]
        return f"cluster_{hash_digest}"

    def get_cluster_representatives(
        self,
        domain: str = "default",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get representative memories from each cluster.

        Args:
            domain: Domain to get clusters from
            limit: Maximum number of representatives

        Returns:
            List of representative memory IDs with cluster info
        """
        if domain not in self.domain_clusters:
            return []

        cluster_ids = self.domain_clusters[domain]
        representatives = []

        # Sort clusters by importance and coherence
        sorted_clusters = sorted(
            [self.clusters[cid] for cid in cluster_ids],
            key=lambda c: c.average_importance * c.coherence_score,
            reverse=True
        )

        for cluster in sorted_clusters[:limit]:
            representatives.append({
                'memory_id': cluster.representative_id,
                'cluster_id': cluster.cluster_id,
                'cluster_size': cluster.size,
                'cluster_topic': cluster.topic,
                'cluster_keywords': cluster.keywords,
                'expansion_available': cluster.size > 1
            })

        return representatives

    def expand_cluster(
        self,
        cluster_id: str,
        relevance_threshold: float = 0.0,
        max_expansion: int = 5
    ) -> List[str]:
        """
        Expand a cluster by retrieving additional memories.

        Args:
            cluster_id: ID of cluster to expand
            relevance_threshold: Minimum relevance to query
            max_expansion: Maximum memories to retrieve

        Returns:
            List of additional memory IDs
        """
        if cluster_id not in self.clusters:
            return []

        cluster = self.clusters[cluster_id]

        # Get expansion candidates
        candidates = cluster.get_expansion_candidates(max_expansion)

        # Filter by relevance if threshold provided
        if relevance_threshold > 0:
            # Would need query embedding to calculate relevance
            # For now, return top candidates
            pass

        return candidates

    def should_expand_cluster(
        self,
        cluster_id: str,
        query_embedding: Optional[np.ndarray] = None
    ) -> bool:
        """
        Determine if a cluster should be expanded based on query.

        Args:
            cluster_id: Cluster to check
            query_embedding: Query vector for similarity check

        Returns:
            True if cluster should be expanded
        """
        if cluster_id not in self.clusters:
            return False

        cluster = self.clusters[cluster_id]

        # Always expand small clusters
        if cluster.size <= 3:
            return True

        # Check query similarity if provided
        if query_embedding is not None and cluster.centroid is not None:
            similarity = cosine_similarity(
                query_embedding.reshape(1, -1),
                cluster.centroid.reshape(1, -1)
            )[0, 0]

            return similarity >= self.config.expansion_threshold

        # Default: don't expand large clusters without query
        return False

    def update_clusters(
        self,
        new_memories: List[Dict[str, Any]],
        domain: str = "default"
    ):
        """
        Update existing clusters with new memories.

        Args:
            new_memories: New memories to add
            domain: Domain for memories
        """
        if not new_memories:
            return

        # Check if we should re-cluster
        total_memories = len(self.memory_to_cluster) + len(new_memories)

        if total_memories > len(self.clusters) * self.config.max_cluster_size:
            # Re-cluster everything
            logger.info("Re-clustering due to size threshold")
            all_memories = list(self.memory_to_cluster.keys())
            all_memories.extend([m['id'] for m in new_memories])
            # Would need to fetch all memories with embeddings
            # For now, just add to existing clusters

        # Assign new memories to nearest cluster
        for memory in new_memories:
            if 'embedding' not in memory or not memory['embedding']:
                continue

            best_cluster = self._find_nearest_cluster(
                memory['embedding'],
                domain
            )

            if best_cluster:
                best_cluster.add_memory(memory['id'])
                self.memory_to_cluster[memory['id']] = best_cluster.cluster_id

    def _find_nearest_cluster(
        self,
        embedding: np.ndarray,
        domain: str
    ) -> Optional[MemoryCluster]:
        """Find the nearest cluster for an embedding"""
        if domain not in self.domain_clusters:
            return None

        best_cluster = None
        best_similarity = -1

        for cluster_id in self.domain_clusters[domain]:
            cluster = self.clusters[cluster_id]
            if cluster.centroid is None:
                continue

            similarity = cosine_similarity(
                embedding.reshape(1, -1),
                cluster.centroid.reshape(1, -1)
            )[0, 0]

            if similarity > best_similarity and similarity >= self.config.similarity_threshold:
                best_similarity = similarity
                best_cluster = cluster

        return best_cluster

    def get_cluster_stats(self, domain: Optional[str] = None) -> Dict[str, Any]:
        """Get clustering statistics"""
        if domain:
            cluster_ids = self.domain_clusters.get(domain, set())
            clusters = [self.clusters[cid] for cid in cluster_ids]
        else:
            clusters = list(self.clusters.values())

        if not clusters:
            return {
                'total_clusters': 0,
                'total_memories': 0,
                'average_cluster_size': 0,
                'average_coherence': 0
            }

        sizes = [c.size for c in clusters]
        coherences = [c.coherence_score for c in clusters]

        return {
            'total_clusters': len(clusters),
            'total_memories': sum(sizes),
            'average_cluster_size': np.mean(sizes),
            'min_cluster_size': min(sizes),
            'max_cluster_size': max(sizes),
            'average_coherence': np.mean(coherences),
            'domains': list(self.domain_clusters.keys())
        }

    def export_clusters(self, domain: str) -> List[Dict[str, Any]]:
        """Export cluster information for analysis"""
        if domain not in self.domain_clusters:
            return []

        exports = []
        for cluster_id in self.domain_clusters[domain]:
            cluster = self.clusters[cluster_id]
            exports.append({
                'cluster_id': cluster.cluster_id,
                'size': cluster.size,
                'topic': cluster.topic,
                'keywords': cluster.keywords,
                'representative_id': cluster.representative_id,
                'memory_ids': cluster.memory_ids,
                'average_importance': cluster.average_importance,
                'coherence_score': cluster.coherence_score,
                'created_at': cluster.created_at.isoformat(),
                'last_updated': cluster.last_updated.isoformat()
            })

        return exports
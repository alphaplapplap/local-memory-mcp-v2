import time
import json
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class ScoredMemory:
    content: str
    metadata: Dict
    relevance_score: float
    time_score: float
    importance_score: float
    final_score: float

class MemoryScorer:
    def __init__(self, embedding_client):
        self.embedding_client = embedding_client

    def score_memories(self, query: str, memories: List[Dict],
                      context: Optional[Dict] = None) -> List[ScoredMemory]:
        """
        Score memories using doobidoo's algorithm adapted for PostgreSQL
        """
        scored_memories = []

        for memory in memories:
            # Time decay scoring (adapt from doobidoo)
            time_score = self._calculate_time_decay(
                memory['created_at'],
                half_life_days=30
            )

            # Content relevance (you already have this via pgvector similarity)
            relevance_score = memory.get('similarity_score', 0.0)

            # Importance scoring based on metadata
            importance_score = self._calculate_importance_score(memory['metadata'])

            # Domain/tag relevance scoring
            domain_score = self._calculate_domain_relevance(
                memory['metadata'],
                context
            )

            # Final weighted score (adapt doobidoo's weights)
            final_score = (
                relevance_score * 0.4 +  # Content similarity
                time_score * 0.25 +      # Recency
                importance_score * 0.2 + # Explicit importance
                domain_score * 0.15      # Domain/tag relevance
            )

            scored_memories.append(ScoredMemory(
                content=memory['content'],
                metadata=memory['metadata'],
                relevance_score=relevance_score,
                time_score=time_score,
                importance_score=importance_score,
                final_score=final_score
            ))

        # Sort by final score
        return sorted(scored_memories, key=lambda x: x.final_score, reverse=True)

    def _calculate_time_decay(self, created_at, half_life_days: int = 30) -> float:
        """Calculate time decay score (newer = higher score)"""
        import datetime

        if isinstance(created_at, str):
            created_at = datetime.datetime.fromisoformat(created_at)

        age_days = (datetime.datetime.now() - created_at).days

        # Exponential decay: score = 0.5 ** (age / half_life)
        return 0.5 ** (age_days / half_life_days)

    def _calculate_importance_score(self, metadata: Dict) -> float:
        """Calculate importance based on metadata flags"""
        importance = metadata.get('importance', 0.5)

        # Boost for certain memory types
        memory_type = metadata.get('memory_type', 'note')
        type_multipliers = {
            'decision': 1.2,
            'insight': 1.1,
            'reference': 1.0,
            'note': 0.9,
            'temporary': 0.5
        }

        return min(1.0, importance * type_multipliers.get(memory_type, 1.0))

    def _calculate_domain_relevance(self, metadata: Dict, context: Optional[Dict]) -> float:
        """Calculate domain/project relevance"""
        if not context:
            return 0.5

        # Check domain match
        memory_domain = metadata.get('domain_id')
        context_domain = context.get('current_domain')

        if memory_domain == context_domain:
            return 1.0
        elif memory_domain and context_domain:
            return 0.3  # Different domain penalty
        else:
            return 0.6  # No domain info
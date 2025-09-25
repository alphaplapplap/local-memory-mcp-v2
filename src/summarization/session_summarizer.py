# Copyright 2024
# Phase 2 Optimization: Session Summarization for Token Efficiency

"""
Session Summarization System
Generates compact session summaries under 500 tokens focusing on decisions and outcomes
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class SessionSummarizer:
    """
    Intelligent session summarization for maximum context efficiency.
    Focuses on:
    - Key decisions made
    - Problems solved
    - Outcomes achieved
    - Next steps identified

    Excludes:
    - Process details
    - Intermediate steps
    - Verbose explanations
    """

    def __init__(self, max_tokens: int = 500):
        """
        Initialize summarizer with token limit.

        Args:
            max_tokens: Maximum tokens for summary (default 500)
        """
        self.max_tokens = max_tokens
        # Rough estimate: 1 token ≈ 4 characters
        self.max_chars = max_tokens * 4

    def generate_compact_summary(
        self,
        session_id: str,
        memories: List[Dict[str, Any]],
        conversation_summary: Optional[str] = None,
        initial_topics: List[str] = None,
        final_topics: List[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a compact session summary optimized for token efficiency.

        Args:
            session_id: Unique session identifier
            memories: List of memories from the session
            conversation_summary: Optional existing summary
            initial_topics: Topics at session start
            final_topics: Topics at session end

        Returns:
            Compact summary dictionary
        """
        logger.debug(f"Generating compact summary for session {session_id}")

        # Extract key information from memories
        decisions = self._extract_decisions(memories)
        solutions = self._extract_solutions(memories)
        outcomes = self._extract_outcomes(memories)
        technical_details = self._extract_technical_details(memories)

        # Build compact summary
        summary = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "summary_type": "compact",
            "content": {}
        }

        # Add decisions (highest priority)
        if decisions:
            summary["content"]["decisions"] = decisions[:3]  # Top 3 decisions

        # Add solutions (high priority)
        if solutions:
            summary["content"]["solutions"] = solutions[:3]  # Top 3 solutions

        # Add outcomes (medium priority)
        if outcomes:
            summary["content"]["outcomes"] = outcomes[:2]  # Top 2 outcomes

        # Add key technical details (if space allows)
        current_size = len(json.dumps(summary))
        if current_size < self.max_chars * 0.8 and technical_details:
            summary["content"]["technical"] = technical_details[:2]

        # Add topic progression (if changed)
        if initial_topics and final_topics:
            topic_changes = set(final_topics) - set(initial_topics)
            if topic_changes:
                summary["content"]["topic_progression"] = list(topic_changes)[:3]

        # Ensure we're under token limit
        summary_json = json.dumps(summary)
        if len(summary_json) > self.max_chars:
            # Trim content to fit
            summary = self._trim_summary(summary)

        # Add metadata
        summary["metadata"] = {
            "memory_count": len(memories),
            "token_estimate": len(json.dumps(summary)) // 4,
            "compression_ratio": self._calculate_compression_ratio(memories, summary)
        }

        logger.info(f"Generated compact summary: {summary['metadata']['token_estimate']} tokens")
        return summary

    def _extract_decisions(self, memories: List[Dict[str, Any]]) -> List[str]:
        """Extract key decisions from memories."""
        decisions = []

        decision_keywords = [
            'decided', 'decision', 'chose', 'selected', 'opted',
            'will use', 'going with', 'approach:', 'strategy:'
        ]

        for memory in memories:
            content = memory.get('content', '').lower()
            for keyword in decision_keywords:
                if keyword in content:
                    # Extract concise decision statement
                    decision = self._extract_concise_statement(memory['content'], keyword)
                    if decision and len(decision) < 100:
                        decisions.append(decision)
                    break

        # Sort by importance if available
        decisions = sorted(
            decisions,
            key=lambda d: self._score_importance(d),
            reverse=True
        )

        return decisions

    def _extract_solutions(self, memories: List[Dict[str, Any]]) -> List[str]:
        """Extract problem solutions from memories."""
        solutions = []

        solution_keywords = [
            'fixed', 'solved', 'solution:', 'resolved', 'workaround',
            'bug fix', 'error fix', 'issue resolved'
        ]

        for memory in memories:
            content = memory.get('content', '').lower()
            for keyword in solution_keywords:
                if keyword in content:
                    solution = self._extract_concise_statement(memory['content'], keyword)
                    if solution and len(solution) < 100:
                        solutions.append(solution)
                    break

        return solutions

    def _extract_outcomes(self, memories: List[Dict[str, Any]]) -> List[str]:
        """Extract achieved outcomes from memories."""
        outcomes = []

        outcome_keywords = [
            'completed', 'achieved', 'implemented', 'created', 'built',
            'deployed', 'released', 'finished', 'done'
        ]

        for memory in memories:
            content = memory.get('content', '').lower()
            for keyword in outcome_keywords:
                if keyword in content:
                    outcome = self._extract_concise_statement(memory['content'], keyword)
                    if outcome and len(outcome) < 100:
                        outcomes.append(outcome)
                    break

        return outcomes

    def _extract_technical_details(self, memories: List[Dict[str, Any]]) -> List[str]:
        """Extract key technical details."""
        technical = []

        technical_patterns = [
            'config:', 'configuration:', 'api:', 'endpoint:',
            'function:', 'class:', 'module:', 'package:'
        ]

        for memory in memories:
            content = memory.get('content', '').lower()
            for pattern in technical_patterns:
                if pattern in content:
                    detail = self._extract_concise_statement(memory['content'], pattern)
                    if detail and len(detail) < 80:
                        technical.append(detail)
                    break

        return technical

    def _extract_concise_statement(self, content: str, keyword: str) -> str:
        """
        Extract a concise statement around a keyword.

        Args:
            content: Full content
            keyword: Keyword to extract around

        Returns:
            Concise statement
        """
        try:
            # Find keyword position
            lower_content = content.lower()
            pos = lower_content.find(keyword)
            if pos == -1:
                return ""

            # Extract sentence containing keyword
            start = max(0, content.rfind('.', 0, pos) + 1)
            end = content.find('.', pos)
            if end == -1:
                end = min(len(content), pos + 100)

            statement = content[start:end].strip()

            # Remove unnecessary words for compactness
            noise_words = ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for']
            words = statement.split()
            filtered = [w for w in words if w.lower() not in noise_words or words.index(w) < 3]

            return ' '.join(filtered)[:100]

        except Exception as e:
            logger.debug(f"Failed to extract statement: {e}")
            return ""

    def _score_importance(self, statement: str) -> float:
        """Score the importance of a statement."""
        score = 0.5

        # Boost for specific important terms
        important_terms = [
            'critical', 'breaking', 'security', 'performance',
            'authentication', 'database', 'api', 'production'
        ]

        statement_lower = statement.lower()
        for term in important_terms:
            if term in statement_lower:
                score += 0.1

        return min(1.0, score)

    def _trim_summary(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """Trim summary to fit token limit."""
        # Priority order for trimming
        trim_order = ['technical', 'topic_progression', 'outcomes', 'solutions', 'decisions']

        content = summary.get('content', {})

        for key in trim_order:
            if key in content:
                items = content[key]
                # Reduce by half
                content[key] = items[:len(items)//2]

                # Check if we're under limit now
                if len(json.dumps(summary)) <= self.max_chars:
                    break

        return summary

    def _calculate_compression_ratio(
        self,
        memories: List[Dict[str, Any]],
        summary: Dict[str, Any]
    ) -> float:
        """Calculate compression ratio."""
        original_size = sum(len(m.get('content', '')) for m in memories)
        summary_size = len(json.dumps(summary))

        if original_size == 0:
            return 0.0

        return round(original_size / summary_size, 2)

    def merge_summaries(
        self,
        summaries: List[Dict[str, Any]],
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Merge multiple session summaries into one.

        Args:
            summaries: List of summaries to merge
            max_tokens: Optional token limit override

        Returns:
            Merged summary
        """
        if not summaries:
            return {}

        max_tokens = max_tokens or self.max_tokens

        merged = {
            "summary_type": "merged",
            "session_count": len(summaries),
            "content": {
                "decisions": [],
                "solutions": [],
                "outcomes": []
            }
        }

        # Collect all items
        for summary in summaries:
            content = summary.get('content', {})
            for key in ['decisions', 'solutions', 'outcomes']:
                if key in content:
                    merged['content'][key].extend(content[key])

        # Deduplicate and limit
        for key in merged['content']:
            items = merged['content'][key]
            # Remove duplicates while preserving order
            seen = set()
            unique = []
            for item in items:
                if item not in seen:
                    seen.add(item)
                    unique.append(item)
            merged['content'][key] = unique[:3]  # Keep top 3 of each type

        return merged
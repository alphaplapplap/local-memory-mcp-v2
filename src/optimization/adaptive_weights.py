# Copyright 2024
# Phase 3 Optimization: Adaptive Weight Learning System

"""
Dynamic Weight Adjustment System
Learns optimal memory scoring weights based on usage patterns
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class AccessPattern:
    """Tracks how memories are accessed and used"""

    memory_id: str
    domain: str
    access_count: int = 0
    relevance_scores: List[float] = field(default_factory=list)
    was_useful: List[bool] = field(default_factory=list)
    query_contexts: List[str] = field(default_factory=list)
    last_accessed: datetime = field(default_factory=datetime.now)

    def add_access(self, relevance_score: float, was_useful: bool, query_context: str):
        """Record a memory access event"""
        self.access_count += 1
        self.relevance_scores.append(relevance_score)
        self.was_useful.append(was_useful)
        self.query_contexts.append(query_context)
        self.last_accessed = datetime.now()

    def get_utility_score(self) -> float:
        """Calculate overall utility of this memory"""
        if not self.was_useful:
            return 0.0

        # Utility = usefulness rate * average relevance * log(access_count + 1)
        usefulness_rate = sum(self.was_useful) / len(self.was_useful)
        avg_relevance = np.mean(self.relevance_scores) if self.relevance_scores else 0.5
        access_factor = np.log1p(self.access_count) / 10  # Normalize to 0-1 range

        return usefulness_rate * avg_relevance * min(1.0, access_factor)


@dataclass
class ProjectProfile:
    """Project-specific weight profile"""

    project_name: str
    domain: str
    weights: Dict[str, float]
    access_patterns: Dict[str, AccessPattern] = field(default_factory=dict)
    learning_rate: float = 0.1
    momentum: float = 0.9
    last_update: datetime = field(default_factory=datetime.now)
    total_queries: int = 0
    successful_queries: int = 0

    def get_success_rate(self) -> float:
        """Calculate query success rate"""
        if self.total_queries == 0:
            return 0.0
        return self.successful_queries / self.total_queries


class AdaptiveWeightLearner:
    """
    Learns and adjusts memory scoring weights based on usage patterns.
    Uses reinforcement learning principles to optimize retrieval.
    """

    # Default weights (from Phase 1 optimization)
    DEFAULT_WEIGHTS = {
        "time_decay": 0.20,
        "tag_relevance": 0.30,
        "content_relevance": 0.20,
        "content_quality": 0.25,
        "conversation_relevance": 0.05,
    }

    # Weight constraints to prevent extreme values
    WEIGHT_BOUNDS = {
        "time_decay": (0.05, 0.40),
        "tag_relevance": (0.10, 0.50),
        "content_relevance": (0.10, 0.40),
        "content_quality": (0.10, 0.40),
        "conversation_relevance": (0.01, 0.20),
    }

    def __init__(self, profile_dir: str = ".memory_profiles"):
        """Initialize weight learner with profile storage directory"""
        self.profile_dir = profile_dir
        self.profiles: Dict[str, ProjectProfile] = {}
        self.current_profile: Optional[ProjectProfile] = None
        self.gradient_history: Dict[str, List[float]] = defaultdict(list)

        # Create profile directory if it doesn't exist
        os.makedirs(profile_dir, exist_ok=True)

        # Load existing profiles
        self._load_profiles()

    def _load_profiles(self):
        """Load saved project profiles from disk"""
        try:
            for filename in os.listdir(self.profile_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.profile_dir, filename)
                    with open(filepath, "r") as f:
                        data = json.load(f)
                        profile = self._dict_to_profile(data)
                        self.profiles[profile.project_name] = profile

            logger.info(f"Loaded {len(self.profiles)} project profiles")
        except Exception as e:
            logger.warning(f"Error loading profiles: {e}")

    def _save_profile(self, profile: ProjectProfile):
        """Save a project profile to disk"""
        try:
            filename = f"{profile.project_name.replace('/', '_')}.json"
            filepath = os.path.join(self.profile_dir, filename)

            # Convert to serializable format
            data = self._profile_to_dict(profile)

            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved profile for {profile.project_name}")
        except Exception as e:
            logger.error(f"Error saving profile: {e}")

    def _profile_to_dict(self, profile: ProjectProfile) -> Dict:
        """Convert profile to JSON-serializable dictionary"""
        return {
            "project_name": profile.project_name,
            "domain": profile.domain,
            "weights": profile.weights,
            "learning_rate": profile.learning_rate,
            "momentum": profile.momentum,
            "last_update": profile.last_update.isoformat(),
            "total_queries": profile.total_queries,
            "successful_queries": profile.successful_queries,
            "access_patterns": {
                mid: {
                    "memory_id": ap.memory_id,
                    "domain": ap.domain,
                    "access_count": ap.access_count,
                    "relevance_scores": ap.relevance_scores,
                    "was_useful": ap.was_useful,
                    "query_contexts": ap.query_contexts,
                    "last_accessed": ap.last_accessed.isoformat(),
                }
                for mid, ap in profile.access_patterns.items()
            },
        }

    def _dict_to_profile(self, data: Dict) -> ProjectProfile:
        """Convert dictionary to ProjectProfile"""
        profile = ProjectProfile(
            project_name=data["project_name"],
            domain=data["domain"],
            weights=data["weights"],
            learning_rate=data.get("learning_rate", 0.1),
            momentum=data.get("momentum", 0.9),
            last_update=datetime.fromisoformat(data["last_update"]),
            total_queries=data.get("total_queries", 0),
            successful_queries=data.get("successful_queries", 0),
        )

        # Reconstruct access patterns
        for mid, ap_data in data.get("access_patterns", {}).items():
            ap = AccessPattern(
                memory_id=ap_data["memory_id"],
                domain=ap_data["domain"],
                access_count=ap_data["access_count"],
                relevance_scores=ap_data["relevance_scores"],
                was_useful=ap_data["was_useful"],
                query_contexts=ap_data["query_contexts"],
                last_accessed=datetime.fromisoformat(ap_data["last_accessed"]),
            )
            profile.access_patterns[mid] = ap

        return profile

    def get_weights_for_project(
        self, project_name: str, domain: str = "default"
    ) -> Dict[str, float]:
        """
        Get optimized weights for a specific project.
        Creates new profile if project is unknown.
        """
        if project_name not in self.profiles:
            # Create new profile with default weights
            self.profiles[project_name] = ProjectProfile(
                project_name=project_name,
                domain=domain,
                weights=self.DEFAULT_WEIGHTS.copy(),
            )
            self._save_profile(self.profiles[project_name])

        self.current_profile = self.profiles[project_name]
        return self.current_profile.weights.copy()

    def record_memory_access(
        self,
        memory_id: str,
        relevance_score: float,
        was_useful: bool,
        query_context: str = "",
        project_name: Optional[str] = None,
    ):
        """Record a memory access event for learning"""
        if project_name:
            profile = self.profiles.get(project_name)
        else:
            profile = self.current_profile

        if not profile:
            logger.warning("No active profile for memory access recording")
            return

        # Create or update access pattern
        if memory_id not in profile.access_patterns:
            profile.access_patterns[memory_id] = AccessPattern(
                memory_id=memory_id, domain=profile.domain
            )

        profile.access_patterns[memory_id].add_access(
            relevance_score=relevance_score,
            was_useful=was_useful,
            query_context=query_context,
        )

        # Update profile stats
        profile.total_queries += 1
        if was_useful:
            profile.successful_queries += 1

        # Trigger learning if enough data collected
        if len(profile.access_patterns) >= 10 and profile.total_queries % 5 == 0:
            self._update_weights(profile)

    def _update_weights(self, profile: ProjectProfile):
        """
        Update weights based on access patterns using gradient descent.
        """
        logger.debug(f"Updating weights for {profile.project_name}")

        # Calculate weight gradients based on utility scores
        gradients = self._calculate_gradients(profile)

        # Apply momentum to smooth updates
        for weight_name in profile.weights:
            if weight_name in self.gradient_history:
                history = self.gradient_history[weight_name]
                if len(history) > 0:
                    # Exponential moving average of gradients
                    gradients[weight_name] = (
                        profile.momentum * history[-1]
                        + (1 - profile.momentum) * gradients[weight_name]
                    )

            # Update weight with learning rate
            new_weight = (
                profile.weights[weight_name]
                + profile.learning_rate * gradients[weight_name]
            )

            # Apply bounds
            min_bound, max_bound = self.WEIGHT_BOUNDS[weight_name]
            new_weight = max(min_bound, min(max_bound, new_weight))

            profile.weights[weight_name] = new_weight

            # Store gradient history
            self.gradient_history[weight_name].append(gradients[weight_name])
            if len(self.gradient_history[weight_name]) > 10:
                self.gradient_history[weight_name].pop(0)

        # Normalize weights to sum to 1.0
        total = sum(profile.weights.values())
        for weight_name in profile.weights:
            profile.weights[weight_name] /= total

        profile.last_update = datetime.now()
        self._save_profile(profile)

        logger.info(f"Updated weights for {profile.project_name}: {profile.weights}")

    def _calculate_gradients(self, profile: ProjectProfile) -> Dict[str, float]:
        """
        Calculate weight adjustment gradients based on memory utility.
        """
        gradients = {k: 0.0 for k in profile.weights}

        # Analyze patterns to determine which weights need adjustment
        patterns = profile.access_patterns.values()

        if not patterns:
            return gradients

        # Calculate utility statistics
        high_utility = [p for p in patterns if p.get_utility_score() > 0.7]
        low_utility = [p for p in patterns if p.get_utility_score() < 0.3]

        # Analyze what makes memories useful
        if high_utility:
            # Memories that are frequently useful
            avg_access_count = np.mean([p.access_count for p in high_utility])

            # If useful memories are accessed frequently, increase time_decay weight
            if avg_access_count > 3:
                gradients["time_decay"] = -0.1  # Negative to reduce time penalty

            # Check if useful memories have high relevance scores
            avg_relevance = np.mean(
                [
                    np.mean(p.relevance_scores)
                    for p in high_utility
                    if p.relevance_scores
                ]
            )
            if avg_relevance > 0.7:
                gradients["content_relevance"] = 0.1

        if low_utility:
            # Memories that are rarely useful
            # If low utility memories are being retrieved, we need to adjust weights

            # Check if they're being retrieved due to tags
            tag_patterns = [
                p for p in low_utility if "tag" in str(p.query_contexts).lower()
            ]
            if len(tag_patterns) > len(low_utility) * 0.5:
                gradients["tag_relevance"] = -0.1  # Reduce tag weight
                gradients["content_relevance"] = 0.1  # Increase content weight

        # Adjust based on success rate
        success_rate = profile.get_success_rate()
        if success_rate < 0.5:
            # Poor performance, make larger adjustments
            for key in gradients:
                gradients[key] *= 2.0
        elif success_rate > 0.8:
            # Good performance, make smaller adjustments
            for key in gradients:
                gradients[key] *= 0.5

        # Quality should remain relatively stable
        gradients["content_quality"] *= 0.5

        # Conversation relevance adjustment based on recency of access
        recent_accesses = [
            p
            for p in patterns
            if (datetime.now() - p.last_accessed) < timedelta(hours=1)
        ]
        if len(recent_accesses) > len(patterns) * 0.3:
            gradients["conversation_relevance"] = 0.05

        return gradients

    def get_weight_analytics(self, project_name: str) -> Dict[str, Any]:
        """Get analytics about weight performance for a project"""
        if project_name not in self.profiles:
            return {"error": "Project not found"}

        profile = self.profiles[project_name]

        # Calculate various metrics
        total_accesses = sum(p.access_count for p in profile.access_patterns.values())
        avg_utility = (
            np.mean([p.get_utility_score() for p in profile.access_patterns.values()])
            if profile.access_patterns
            else 0.0
        )

        # Weight stability (how much weights have changed)
        weight_diffs = {}
        for key, current in profile.weights.items():
            default = self.DEFAULT_WEIGHTS[key]
            weight_diffs[key] = abs(current - default)

        stability_score = 1.0 - np.mean(list(weight_diffs.values()))

        return {
            "project_name": project_name,
            "current_weights": profile.weights,
            "default_weights": self.DEFAULT_WEIGHTS,
            "weight_changes": weight_diffs,
            "total_queries": profile.total_queries,
            "success_rate": profile.get_success_rate(),
            "total_memory_accesses": total_accesses,
            "average_utility_score": round(avg_utility, 3),
            "stability_score": round(stability_score, 3),
            "last_update": profile.last_update.isoformat(),
            "learning_rate": profile.learning_rate,
            "momentum": profile.momentum,
            "unique_memories_accessed": len(profile.access_patterns),
        }

    def export_best_weights(self) -> Dict[str, Dict[str, float]]:
        """Export the best performing weights across all projects"""
        best_weights = {}

        for project_name, profile in self.profiles.items():
            success_rate = profile.get_success_rate()
            if success_rate > 0.7:  # Only export successful profiles
                best_weights[project_name] = {
                    "weights": profile.weights.copy(),
                    "success_rate": success_rate,
                    "total_queries": profile.total_queries,
                }

        return best_weights

    def reset_profile(self, project_name: str):
        """Reset a project profile to default weights"""
        if project_name in self.profiles:
            self.profiles[project_name].weights = self.DEFAULT_WEIGHTS.copy()
            self.profiles[project_name].access_patterns.clear()
            self.profiles[project_name].total_queries = 0
            self.profiles[project_name].successful_queries = 0
            self._save_profile(self.profiles[project_name])
            logger.info(f"Reset profile for {project_name}")

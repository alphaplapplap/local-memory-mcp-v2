# Copyright 2024 Heinrich Krupp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Dream-inspired memory consolidation system.

This module implements autonomous memory consolidation inspired by human cognitive 
processes during sleep cycles, featuring exponential decay scoring, creative 
association discovery, semantic compression, and controlled forgetting.
"""

from consolidation.base import (
    ConsolidationBase,
    ConsolidationConfig,
    ConsolidationReport,
    ConsolidationError,
    ConsolidationConfigError,
    ConsolidationProcessingError
)
from consolidation.postgres_consolidator import PostgreSQLConsolidator
from consolidation.decay import ExponentialDecayCalculator
from consolidation.associations import CreativeAssociationEngine
from consolidation.clustering import SemanticClusteringEngine
from consolidation.compression import SemanticCompressionEngine
from consolidation.forgetting import ControlledForgettingEngine
from consolidation.consolidator import DreamInspiredConsolidator
from consolidation.scheduler import ConsolidationScheduler
from consolidation.health import ConsolidationHealthMonitor, HealthStatus, HealthMetric, HealthAlert

__all__ = [
    'ConsolidationBase',
    'ConsolidationConfig',
    'ConsolidationReport',
    'ConsolidationError',
    'ConsolidationConfigError',
    'ConsolidationProcessingError',
    'PostgreSQLConsolidator',
    'ExponentialDecayCalculator',
    'CreativeAssociationEngine',
    'SemanticClusteringEngine',
    'SemanticCompressionEngine',
    'ControlledForgettingEngine',
    'DreamInspiredConsolidator',
    'ConsolidationScheduler',
    'ConsolidationHealthMonitor',
    'HealthStatus',
    'HealthMetric',
    'HealthAlert'
]
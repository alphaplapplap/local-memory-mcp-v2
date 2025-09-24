"""
Memory Relevance Scoring Utility
Implements intelligent algorithms to score memories by relevance to current project context
Phase 2: Enhanced with conversation context awareness for dynamic memory loading
"""

import math
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def calculate_time_decay(memory_date: str, decay_rate: float = 0.1) -> float:
    """
    Calculate time decay factor for memory relevance
    More recent memories get higher scores
    """
    try:
        now = datetime.now()

        # Handle string dates
        if isinstance(memory_date, str):
            memory_time = datetime.fromisoformat(memory_date.replace('Z', '+00:00'))
        else:
            memory_time = memory_date

        # Calculate days since memory creation
        days_diff = (now - memory_time).total_seconds() / (60 * 60 * 24)

        # Exponential decay: score = e^(-decayRate * days)
        # Recent memories (0-7 days): score 0.8-1.0
        # Older memories (8-30 days): score 0.3-0.8
        # Ancient memories (30+ days): score 0.0-0.3
        decay_score = math.exp(-decay_rate * days_diff)

        # Ensure score is between 0 and 1
        return max(0.01, min(1.0, decay_score))

    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"Time decay calculation failed for date '{memory_date}': {e}")
        return 0.5  # Default score for invalid dates

def calculate_tag_relevance(memory_tags: List[str] = [], project_context: Dict[str, Any] = {}) -> float:
    """
    Calculate tag relevance score
    Memories with tags matching project context get higher scores
    """
    try:
        if not memory_tags or not isinstance(memory_tags, list):
            return 0.3  # Default score for memories without tags

        context_tags = []

        # Add project name
        if project_context.get('name'):
            context_tags.append(project_context['name'].lower())

        # Add language
        if project_context.get('language'):
            context_tags.append(project_context['language'].lower())

        # Add frameworks
        for framework in project_context.get('frameworks', []):
            context_tags.append(framework.lower())

        # Add tools
        for tool in project_context.get('tools', []):
            context_tags.append(tool.lower())

        context_tags = [tag for tag in context_tags if tag]  # Filter empty

        if not context_tags:
            return 0.5  # No context to match against

        # Calculate tag overlap
        memory_tags_lower = [tag.lower() for tag in memory_tags]
        matching_tags = []

        for context_tag in context_tags:
            for memory_tag in memory_tags_lower:
                if context_tag in memory_tag or memory_tag in context_tag:
                    matching_tags.append(context_tag)
                    break

        # Score based on percentage of matching tags
        overlap_score = len(matching_tags) / len(context_tags) if context_tags else 0

        # Bonus for exact project name matches
        project_name = project_context.get('name', '').lower()
        exact_project_match = project_name in memory_tags_lower if project_name else False
        project_bonus = 0.3 if exact_project_match else 0

        # Bonus for exact language matches
        language = project_context.get('language', '').lower()
        exact_language_match = language in memory_tags_lower if language else False
        language_bonus = 0.2 if exact_language_match else 0

        # Bonus for framework matches
        framework_matches = 0
        for framework in project_context.get('frameworks', []):
            if any(framework.lower() in tag for tag in memory_tags_lower):
                framework_matches += 1
        framework_bonus = framework_matches * 0.1

        total_score = min(1.0, overlap_score + project_bonus + language_bonus + framework_bonus)

        return max(0.1, total_score)

    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"Tag relevance calculation failed: {e}")
        return 0.3  # Default score for tag matching errors

def calculate_content_quality(memory_content: str = '') -> float:
    """
    Calculate content quality score to penalize generic/empty content
    """
    try:
        if not memory_content or not isinstance(memory_content, str):
            return 0.1

        content_length = len(memory_content.strip())

        # Penalize too short or too long content
        if content_length < 10:
            return 0.1  # Too short to be useful
        elif content_length > 5000:
            return 0.5  # Too verbose, probably needs summarization

        # Check for generic/placeholder patterns
        generic_patterns = [
            'todo', 'fixme', 'placeholder', 'temp', 'test',
            'delete this', 'remove this', 'update this'
        ]

        content_lower = memory_content.lower()
        if any(pattern in content_lower for pattern in generic_patterns):
            return 0.3  # Likely low-quality or temporary content

        # Check for code blocks (higher quality)
        has_code = '```' in memory_content or '    ' in memory_content
        code_bonus = 0.2 if has_code else 0

        # Check for structured data (lists, sections)
        has_structure = any(marker in memory_content for marker in ['- ', '* ', '1.', '## ', '**'])
        structure_bonus = 0.1 if has_structure else 0

        # Base quality score based on length
        if content_length < 50:
            base_score = 0.4
        elif content_length < 200:
            base_score = 0.6
        elif content_length < 1000:
            base_score = 0.8
        else:
            base_score = 0.7

        return min(1.0, base_score + code_bonus + structure_bonus)

    except (ValueError, TypeError, AttributeError) as e:
        logger.debug(f"Content quality calculation failed: {e}")
        return 0.5  # Default score for content quality errors

def calculate_importance_weight(memory_metadata: Dict[str, Any]) -> float:
    """
    Calculate importance weight from metadata
    """
    try:
        # Check for explicit importance field
        importance = memory_metadata.get('importance', 0.5)
        if isinstance(importance, (int, float)):
            return max(0.1, min(1.0, float(importance)))

        # Map string importance levels
        if isinstance(importance, str):
            importance_map = {
                'critical': 1.0,
                'high': 0.8,
                'medium': 0.5,
                'low': 0.3,
                'trivial': 0.1
            }
            return importance_map.get(importance.lower(), 0.5)

        return 0.5

    except (ValueError, TypeError, KeyError) as e:
        logger.debug(f"Importance extraction failed: {e}")
        return 0.5  # Default importance score

def calculate_conversation_relevance(memory: Dict[str, Any], conversation_analysis: Dict[str, Any]) -> float:
    """
    Calculate relevance to current conversation context
    """
    try:
        if not conversation_analysis:
            return 0.5  # No conversation context

        relevance_score = 0.0
        factors = 0

        # Check topic relevance
        memory_content = memory.get('content', '').lower()
        conversation_topics = conversation_analysis.get('topics', [])

        for topic in conversation_topics:
            if topic['name'].lower() in memory_content:
                relevance_score += topic['confidence']
                factors += 1

        # Check entity relevance
        conversation_entities = conversation_analysis.get('entities', [])
        for entity in conversation_entities:
            if entity['name'].lower() in memory_content:
                relevance_score += entity['confidence']
                factors += 1

        # Check intent alignment
        intent = conversation_analysis.get('intent')
        if intent and intent.get('name'):
            intent_keywords = {
                'learning': ['tutorial', 'guide', 'explanation', 'how'],
                'problem-solving': ['error', 'fix', 'solution', 'debug'],
                'development': ['implement', 'create', 'build', 'develop'],
                'optimization': ['optimize', 'improve', 'performance', 'refactor']
            }

            keywords = intent_keywords.get(intent['name'], [])
            if any(keyword in memory_content for keyword in keywords):
                relevance_score += intent['confidence']
                factors += 1

        # Calculate average relevance
        if factors > 0:
            return min(1.0, relevance_score / factors)

        return 0.3  # Default low relevance

    except (ValueError, TypeError, KeyError, AttributeError) as e:
        logger.debug(f"Conversation relevance calculation failed: {e}")
        return 0.5  # Default relevance score

def score_memory_relevance(memories: List[Dict[str, Any]],
                          project_context: Dict[str, Any] = {},
                          options: Dict[str, Any] = {}) -> List[Dict[str, Any]]:
    """
    Score memories by relevance to project context
    Returns memories sorted by relevance score
    """

    # Default weights
    default_weights = {
        'timeDecay': 0.3,
        'tagRelevance': 0.3,
        'contentQuality': 0.2,
        'importance': 0.2,
        'conversationRelevance': 0.0
    }

    weights = options.get('weights', default_weights)

    # Include conversation context if provided
    include_conversation = options.get('includeConversationContext', False)
    conversation_analysis = options.get('conversationAnalysis', {})

    if include_conversation and conversation_analysis:
        # Adjust weights for conversation-aware scoring
        weights['timeDecay'] = weights.get('timeDecay', 0.2)
        weights['conversationRelevance'] = weights.get('conversationRelevance', 0.35)

    print(f'[Memory Scorer] Scoring {len(memories)} memories for project: {project_context.get("name", "unknown")}')

    scored_memories = []

    for memory in memories:
        try:
            # Calculate individual scores
            time_score = calculate_time_decay(
                memory.get('updated_at') or memory.get('created_at', ''),
                options.get('decayRate', 0.1)
            )

            tag_score = calculate_tag_relevance(
                memory.get('tags', []),
                project_context
            )

            quality_score = calculate_content_quality(
                memory.get('content', '')
            )

            importance_score = calculate_importance_weight(
                memory.get('metadata', {})
            )

            conversation_score = 0.5  # Default
            if include_conversation and conversation_analysis:
                conversation_score = calculate_conversation_relevance(
                    memory,
                    conversation_analysis
                )

            # Calculate weighted total score
            total_score = (
                weights.get('timeDecay', 0.3) * time_score +
                weights.get('tagRelevance', 0.3) * tag_score +
                weights.get('contentQuality', 0.2) * quality_score +
                weights.get('importance', 0.2) * importance_score +
                weights.get('conversationRelevance', 0.0) * conversation_score
            )

            # Add scoring details to memory
            scored_memory = memory.copy()
            scored_memory['relevanceScore'] = total_score
            scored_memory['scoreBreakdown'] = {
                'timeDecay': time_score,
                'tagRelevance': tag_score,
                'contentQuality': quality_score,
                'importance': importance_score,
                'conversationRelevance': conversation_score
            }

            scored_memories.append(scored_memory)

        except Exception as e:
            # Skip problematic memories
            print(f'[Memory Scorer] Error scoring memory: {str(e)}')
            continue

    # Sort by total score (highest first)
    scored_memories.sort(key=lambda m: m['relevanceScore'], reverse=True)

    # Log top scored memories
    print('[Memory Scorer] Top scored memories:')
    for i, memory in enumerate(scored_memories[:3]):
        content_preview = memory.get('content', '')[:60] + '...' if len(memory.get('content', '')) > 60 else memory.get('content', '')
        print(f'  {i+1}. Score: {memory["relevanceScore"]:.3f} - {content_preview}')

    return scored_memories

# Export functions
__all__ = [
    'score_memory_relevance',
    'calculate_time_decay',
    'calculate_tag_relevance',
    'calculate_content_quality',
    'calculate_importance_weight',
    'calculate_conversation_relevance'
]
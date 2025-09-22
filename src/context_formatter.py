"""
Context Formatting Utility
Formats memories for injection into Claude Code sessions
"""

import os
import sys
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

def is_cli_environment() -> bool:
    """
    Detect if running in Claude Code CLI environment
    """
    # Check for Claude Code specific environment indicators
    return (os.environ.get('CLAUDE_CODE_CLI') == 'true' or
            os.environ.get('TERM_PROGRAM') == 'claude-code' or
            any('claude' in arg for arg in sys.argv if arg) or
            not os.isatty(1))  # Check for non-TTY contexts

# ANSI Color codes for CLI formatting
COLORS = {
    'RESET': '\x1b[0m',
    'BRIGHT': '\x1b[1m',
    'DIM': '\x1b[2m',
    'CYAN': '\x1b[36m',
    'GREEN': '\x1b[32m',
    'BLUE': '\x1b[34m',
    'YELLOW': '\x1b[33m',
    'MAGENTA': '\x1b[35m',
    'GRAY': '\x1b[90m'
}

def convert_markdown_to_ansi(text: str, options: Dict[str, Any] = {}) -> str:
    """
    Convert markdown formatting to ANSI color codes for terminal display
    Provides clean, formatted output without raw markdown syntax
    """
    strip_only = options.get('stripOnly', False)
    preserve_structure = options.get('preserveStructure', True)

    if not text or not isinstance(text, str):
        return text

    # Check if markdown conversion is disabled via environment
    if os.environ.get('CLAUDE_MARKDOWN_TO_ANSI') == 'false':
        return text

    processed = text

    # Process headers (must be done before other replacements)
    # H1: # Header -> Bold Cyan
    processed = re.sub(r'^#\s+(.+)$', lambda m: m.group(1) if strip_only else f"{COLORS['BRIGHT']}{COLORS['CYAN']}{m.group(1)}{COLORS['RESET']}", processed, flags=re.MULTILINE)

    # H2: ## Header -> Bold Cyan (slightly different from H1 in real terminal apps)
    processed = re.sub(r'^##\s+(.+)$', lambda m: m.group(1) if strip_only else f"{COLORS['BRIGHT']}{COLORS['CYAN']}{m.group(1)}{COLORS['RESET']}", processed, flags=re.MULTILINE)

    # H3: ### Header -> Bold
    processed = re.sub(r'^###\s+(.+)$', lambda m: m.group(1) if strip_only else f"{COLORS['BRIGHT']}{m.group(1)}{COLORS['RESET']}", processed, flags=re.MULTILINE)

    # H4-H6: #### Header -> Bold (but could be differentiated if needed)
    processed = re.sub(r'^#{4,6}\s+(.+)$', lambda m: m.group(1) if strip_only else f"{COLORS['BRIGHT']}{m.group(1)}{COLORS['RESET']}", processed, flags=re.MULTILINE)

    # Bold text: **text** or __text__
    processed = re.sub(r'\*\*([^*]+)\*\*', lambda m: m.group(1) if strip_only else f"{COLORS['BRIGHT']}{m.group(1)}{COLORS['RESET']}", processed)
    processed = re.sub(r'__([^_]+)__', lambda m: m.group(1) if strip_only else f"{COLORS['BRIGHT']}{m.group(1)}{COLORS['RESET']}", processed)

    # Code blocks MUST be processed before inline code to avoid conflicts
    # Code blocks: ```language\ncode\n```
    def format_code_block(match):
        lang = match.group(1)
        content = match.group(2).strip()
        if strip_only:
            return content
        lines = content.split('\n')
        formatted_lines = [f"{COLORS['GRAY']}{line}{COLORS['RESET']}" for line in lines]
        return '\n'.join(formatted_lines)

    processed = re.sub(r'```(\w*)\n?([\s\S]*?)```', format_code_block, processed)

    # Italic text: *text* or _text_ (avoiding URLs and bold syntax)
    # More conservative pattern to avoid matching within URLs
    processed = re.sub(r'(?<!\*)\*(?!\*)([^*\n]+)(?<!\*)\*(?!\*)', lambda m: m.group(1) if strip_only else f"{COLORS['DIM']}{m.group(1)}{COLORS['RESET']}", processed)
    processed = re.sub(r'(?<!_)_(?!_)([^_\n]+)(?<!_)_(?!_)', lambda m: m.group(1) if strip_only else f"{COLORS['DIM']}{m.group(1)}{COLORS['RESET']}", processed)

    # Inline code: `code` (after code blocks to avoid matching backticks in blocks)
    processed = re.sub(r'`([^`]+)`', lambda m: m.group(1) if strip_only else f"{COLORS['GRAY']}{m.group(1)}{COLORS['RESET']}", processed)

    # Lists: Convert markdown bullets to better symbols
    # Unordered lists: - item or * item
    processed = re.sub(r'^[\s]*[-*]\s+(.+)$', lambda m: m.group(1) if strip_only else f"  {COLORS['CYAN']}•{COLORS['RESET']} {m.group(1)}", processed, flags=re.MULTILINE)

    # Ordered lists: 1. item
    processed = re.sub(r'^[\s]*\d+\.\s+(.+)$', lambda m: m.group(1) if strip_only else f"  {COLORS['CYAN']}›{COLORS['RESET']} {m.group(1)}", processed, flags=re.MULTILINE)

    # Links: [text](url) - process before blockquotes so links in quotes work
    processed = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: m.group(1) if strip_only else f"{COLORS['CYAN']}{m.group(1)}{COLORS['RESET']}", processed)

    # Blockquotes: > quote
    processed = re.sub(r'^>\s+(.+)$', lambda m: m.group(1) if strip_only else f"{COLORS['DIM']}│ {m.group(1)}{COLORS['RESET']}", processed, flags=re.MULTILINE)

    # Horizontal rules: --- or *** or ___
    processed = re.sub(r'^[-*_]{3,}$', lambda m: '' if strip_only else f"{COLORS['DIM']}{'─' * 40}{COLORS['RESET']}", processed, flags=re.MULTILINE)

    # Clean up any double resets or color artifacts
    processed = re.sub(r'(\x1b\[0m)+', COLORS['RESET'], processed)

    return processed

def format_memories_for_cli(memories: List[Dict[str, Any]],
                           project_context: Dict[str, Any],
                           options: Dict[str, Any] = {}) -> str:
    """
    Format memories for CLI environment with enhanced visual formatting
    """
    include_project_summary = options.get('includeProjectSummary', True)
    max_memories = options.get('maxMemories', 8)
    include_timestamp = options.get('includeTimestamp', True)
    max_content_length_cli = options.get('maxContentLengthCLI', 400)
    max_content_length_categorized = options.get('maxContentLengthCategorized', 350)
    storage_info = options.get('storageInfo')

    if not memories or len(memories) == 0:
        return f"{COLORS['DIM']}💭 No relevant memories found for this project.{COLORS['RESET']}\n"

    lines = []

    # Header with project context
    if include_project_summary and project_context:
        lines.append(f"{COLORS['BRIGHT']}{COLORS['CYAN']}📚 Memory Context{COLORS['RESET']}")
        lines.append(f"{COLORS['DIM']}{'─' * 60}{COLORS['RESET']}")
        lines.append(f"{COLORS['BRIGHT']}Project:{COLORS['RESET']} {project_context.get('name', 'Unknown')}")

        if project_context.get('language'):
            lines.append(f"{COLORS['BRIGHT']}Language:{COLORS['RESET']} {project_context['language']}")

        if project_context.get('frameworks'):
            frameworks = ', '.join(project_context['frameworks'][:3])
            lines.append(f"{COLORS['BRIGHT']}Frameworks:{COLORS['RESET']} {frameworks}")

        if storage_info:
            storage_type = storage_info.get('type', 'Unknown')
            color = COLORS['GREEN'] if storage_info.get('connected') else COLORS['YELLOW']
            lines.append(f"{COLORS['BRIGHT']}Storage:{COLORS['RESET']} {color}{storage_type}{COLORS['RESET']}")

        lines.append('')

    # Group memories by category
    categories = {
        'recent': [],
        'important': [],
        'relevant': []
    }

    for memory in memories[:max_memories]:
        score = memory.get('relevanceScore', 0)
        if score > 0.8:
            categories['important'].append(memory)
        elif score > 0.6:
            categories['relevant'].append(memory)
        else:
            categories['recent'].append(memory)

    # Format categories with visual hierarchy
    category_configs = [
        ('important', '⭐ Important Context', COLORS['YELLOW'], max_content_length_categorized),
        ('relevant', '🔍 Relevant Information', COLORS['CYAN'], max_content_length_categorized),
        ('recent', '🕐 Recent Activity', COLORS['GRAY'], max_content_length_categorized)
    ]

    for category_key, title, color, max_length in category_configs:
        category_memories = categories[category_key]
        if category_memories:
            lines.append(f"{color}{title}{COLORS['RESET']}")
            lines.append(f"{COLORS['DIM']}{'─' * 40}{COLORS['RESET']}")

            for memory in category_memories[:3]:  # Limit each category
                content = memory.get('content', '')

                # Truncate if needed
                if len(content) > max_length:
                    content = content[:max_length] + '...'

                # Apply markdown conversion
                formatted_content = convert_markdown_to_ansi(content)

                # Add relevance indicator
                score = memory.get('relevanceScore', 0)
                indicator = '🔥' if score > 0.8 else '⭐' if score > 0.6 else '💡'

                lines.append(f"{indicator} {formatted_content}")

                # Add metadata line
                metadata_parts = []
                if memory.get('tags'):
                    tags = ', '.join(memory['tags'][:3])
                    metadata_parts.append(f"{COLORS['DIM']}#{tags}{COLORS['RESET']}")

                if include_timestamp and memory.get('created_at'):
                    timestamp = format_timestamp(memory['created_at'])
                    metadata_parts.append(f"{COLORS['DIM']}{timestamp}{COLORS['RESET']}")

                if metadata_parts:
                    lines.append(f"   {' • '.join(metadata_parts)}")

                lines.append('')

    # Footer
    lines.append(f"{COLORS['DIM']}{'─' * 60}{COLORS['RESET']}")
    lines.append(f"{COLORS['DIM']}💭 {len(memories)} memories loaded • Use /memory-store to save context{COLORS['RESET']}")

    return '\n'.join(lines)

def format_memories_for_context(memories: List[Dict[str, Any]],
                               project_context: Dict[str, Any] = {},
                               options: Dict[str, Any] = {}) -> str:
    """
    Main formatting function - detects environment and formats accordingly
    """
    # Check if running in CLI environment
    if is_cli_environment():
        return format_memories_for_cli(memories, project_context, options)

    # Default markdown formatting for non-CLI environments
    return format_memories_for_markdown(memories, project_context, options)

def format_memories_for_markdown(memories: List[Dict[str, Any]],
                                project_context: Dict[str, Any] = {},
                                options: Dict[str, Any] = {}) -> str:
    """
    Format memories as clean markdown for non-CLI environments
    """
    if not memories:
        return "💭 No relevant memories found for this project.\n"

    lines = []

    # Header
    lines.append("## 📚 Memory Context\n")

    if project_context:
        lines.append(f"**Project:** {project_context.get('name', 'Unknown')}")
        if project_context.get('language'):
            lines.append(f"**Language:** {project_context['language']}")
        if project_context.get('frameworks'):
            frameworks = ', '.join(project_context['frameworks'][:3])
            lines.append(f"**Frameworks:** {frameworks}")
        lines.append('')

    # Format memories
    lines.append("### Relevant Memories\n")

    for i, memory in enumerate(memories[:8], 1):
        content = memory.get('content', '')
        score = memory.get('relevanceScore', 0)

        # Truncate if needed
        if len(content) > 500:
            content = content[:500] + '...'

        # Add relevance indicator
        indicator = '🔥' if score > 0.8 else '⭐' if score > 0.6 else '💡'

        lines.append(f"{i}. {indicator} {content}")

        # Add metadata
        if memory.get('tags'):
            tags = ', '.join(f"#{tag}" for tag in memory['tags'][:3])
            lines.append(f"   *Tags: {tags}*")

        lines.append('')

    lines.append("---")
    lines.append(f"*{len(memories)} memories loaded*")

    return '\n'.join(lines)

def format_timestamp(timestamp: str) -> str:
    """
    Format timestamp for display
    """
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        now = datetime.now()
        diff = now - dt

        if diff.days == 0:
            hours = diff.seconds // 3600
            if hours == 0:
                minutes = diff.seconds // 60
                return f"{minutes}m ago" if minutes > 0 else "just now"
            return f"{hours}h ago"
        elif diff.days == 1:
            return "yesterday"
        elif diff.days < 7:
            return f"{diff.days}d ago"
        elif diff.days < 30:
            weeks = diff.days // 7
            return f"{weeks}w ago"
        else:
            return dt.strftime("%Y-%m-%d")
    except:
        return timestamp

# Export functions
__all__ = [
    'format_memories_for_context',
    'format_memories_for_cli',
    'format_memories_for_markdown',
    'convert_markdown_to_ansi',
    'is_cli_environment'
]
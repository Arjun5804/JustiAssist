"""
JustiAssist Prompts Package
"""

from .templates import (
    LEGAL_SYSTEM_PROMPT,
    BAIL_SYSTEM_PROMPT,
    LEGAL_QUERY_TEMPLATE,
    BAIL_QUERY_TEMPLATE,
    GROUNDING_REINFORCEMENT,
    LEGAL_RESPONSE_FORMAT,
    BAIL_RESPONSE_FORMAT,
    format_context_for_prompt,
    build_legal_prompt,
    build_bail_prompt
)

__all__ = [
    'LEGAL_SYSTEM_PROMPT',
    'BAIL_SYSTEM_PROMPT',
    'LEGAL_QUERY_TEMPLATE',
    'BAIL_QUERY_TEMPLATE',
    'GROUNDING_REINFORCEMENT',
    'LEGAL_RESPONSE_FORMAT',
    'BAIL_RESPONSE_FORMAT',
    'format_context_for_prompt',
    'build_legal_prompt',
    'build_bail_prompt'
]

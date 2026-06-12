"""Shared LLM model configuration.

Single source of truth for Anthropic model IDs so a model deprecation
is a one-line change instead of a codebase-wide hunt.
"""

# Fast, cost-effective default for categorization/tagging/description tasks
DEFAULT_LLM_MODEL = "claude-haiku-4-5"

# Higher-quality options offered in the TUI model pickers
BALANCED_LLM_MODEL = "claude-sonnet-4-6"
ADVANCED_LLM_MODEL = "claude-opus-4-8"

"""Single source of truth for allowed dialogue / scene emotions (OpenAI output normalization)."""

from __future__ import annotations

# Keep alphabetically grouped by category for readability; order does not matter for sets.
ALLOWED_EMOTIONS: frozenset[str] = frozenset(
    {
        "angry",
        "apologetic",
        "concerned",
        "confused",
        "curious",
        "defensive",
        "desperate",
        "determined",
        "fear",
        "frustrated",
        "happy",
        "hopeful",
        "neutral",
        "nostalgic",
        "pain",
        "regretful",
        "reassuring",
        "resigned",
        "sad",
        "serious",
        "surprised",
        "teasing",
        "urgent",
        "weak",
        "worried",
    }
)


def emotion_prompt_list() -> str:
    """Comma-separated list for LLM prompts (stable sort)."""
    return ", ".join(sorted(ALLOWED_EMOTIONS))

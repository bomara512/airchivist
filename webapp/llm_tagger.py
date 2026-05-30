from __future__ import annotations
import hashlib
import json
import os
from typing import Optional

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TAGS = 200

_SYSTEM_PROMPT = """You are organizing tags from a personal YouTube video library into canonical categories.

Rules:
1. Map unclassified tags to EXISTING canonical tags whenever possible — strongly prefer existing over creating new ones
2. Only include a tag in assignments if you are reasonably confident it belongs there
3. Mark as noise: hashtags, year numbers, video quality descriptors (HD, 4K), generic words (video, watch), creator names, collab tags
4. Leave tags in unassigned if they don't fit any existing canonical and aren't worth a new category on their own
5. Call the categorize_tags tool with your complete analysis"""

_TOOL = {
    "name": "categorize_tags",
    "description": "Submit the complete categorization of unclassified tags.",
    "input_schema": {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "description": "Tags mapped to canonical categories",
                "items": {
                    "type": "object",
                    "properties": {
                        "canonical": {
                            "type": "string",
                            "description": "Canonical tag name — prefer existing ones listed above",
                        },
                        "members": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Unclassified tag names that belong to this canonical",
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                    },
                    "required": ["canonical", "members", "confidence"],
                },
            },
            "noise": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags that are noise/spam and should not be canonicalized",
            },
            "unassigned": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags that couldn't be confidently categorized",
            },
        },
        "required": ["assignments", "noise", "unassigned"],
    },
}


def _build_user_message(
    canonical_tags: list[dict],
    unclassified_tags: list[dict],
) -> str:
    lines = []
    if canonical_tags:
        lines.append("Existing canonical tags:")
        for t in canonical_tags:
            lines.append(f"  {t['name']} ({t.get('video_count', 0)} videos)")
    else:
        lines.append("No canonical tags yet.")
    lines.append("")
    lines.append(f"Unclassified tags to categorize ({len(unclassified_tags)} total):")
    for t in unclassified_tags[:MAX_TAGS]:
        count = t.get("video_count", 1)
        lines.append(f"  \"{t['name']}\" ({count} video{'s' if count != 1 else ''})")
    return "\n".join(lines)


def is_available() -> bool:
    """True if the anthropic package is installed and ANTHROPIC_API_KEY is set."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def get_suggestions(
    canonical_tags: list[dict],
    unclassified_tags: list[dict],
    model: str = DEFAULT_MODEL,
) -> list[dict]:
    """
    Call the Anthropic API to get tag categorization suggestions.

    Returns a list of suggestion dicts:
      {"canonical": str, "members": [str, ...], "confidence": str, "is_noise": bool}

    Raises ImportError if the anthropic package is not installed.
    Raises EnvironmentError if ANTHROPIC_API_KEY is not set.
    Raises ValueError if the model does not call the expected tool.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "The 'anthropic' package is required for LLM tag suggestions. "
            "Install it with: pip install anthropic"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable is not set")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "categorize_tags"},
        messages=[
            {"role": "user", "content": _build_user_message(canonical_tags, unclassified_tags)},
        ],
    )

    tool_use = next(
        (block for block in response.content if block.type == "tool_use"),
        None,
    )
    if tool_use is None:
        raise ValueError("LLM did not call the categorize_tags tool")

    result = tool_use.input
    suggestions: list[dict] = []

    for item in result.get("assignments", []):
        members = [m.strip() for m in item.get("members", []) if m and m.strip()]
        if not members:
            continue
        suggestions.append({
            "canonical": item["canonical"].strip(),
            "members": members,
            "confidence": item.get("confidence", "medium"),
            "is_noise": False,
        })

    noise = [t.strip() for t in result.get("noise", []) if t and t.strip()]
    if noise:
        suggestions.append({
            "canonical": "_noise",
            "members": noise,
            "confidence": "high",
            "is_noise": True,
        })

    return suggestions


def compute_pool_hash(unclassified_tags: list[dict]) -> str:
    """Stable hash of the unclassified tag pool for staleness detection."""
    names = sorted(t["name"] for t in unclassified_tags)
    return hashlib.sha256(json.dumps(names).encode()).hexdigest()[:16]

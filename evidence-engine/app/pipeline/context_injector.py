"""
Context Injector

Builds enriched context strings from folder context instructions and
sibling file information for injection into entity/relationship extraction prompts.
"""

from __future__ import annotations

from typing import Any


def _format_size(size_bytes: int) -> str:
    """Format file size as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def build_enriched_context(
    folder_context: str | None,
    sibling_files: list[dict[str, Any]] | None,
    llm_profile: str,
) -> str:
    """
    Merge folder context, sibling file awareness, and LLM profile into a
    single context string suitable for the case_context parameter in
    entity/relationship extraction prompts.

    Args:
        folder_context: Merged context instructions from the folder ancestor chain.
        sibling_files: List of {name, mime_type, size} dicts for sibling files.
        llm_profile: Base LLM profile string (e.g. "fraud", "generic").

    Returns:
        Enriched context string.
    """
    parts: list[str] = []

    # Base profile
    if llm_profile:
        parts.append(f"INVESTIGATION PROFILE: {llm_profile}")

    # Folder context instructions (from ancestor chain)
    if folder_context:
        parts.append(f"FOLDER CONTEXT:\n{folder_context}")

    # Sibling file awareness
    if sibling_files:
        file_lines = []
        for sf in sibling_files:
            name = sf.get("name", "unknown")
            mime = sf.get("mime_type", "unknown")
            size = sf.get("size", 0)
            file_lines.append(f"- {name} ({mime}, {_format_size(size)})")

        parts.append(
            "SIBLING FILES IN THIS FOLDER (for cross-reference awareness):\n"
            + "\n".join(file_lines)
            + f"\n\nThis file is part of a collection of {len(sibling_files)} files. "
            "Consider cross-references between these documents when extracting entities."
        )

    if not parts:
        return llm_profile or "General investigation"

    return "\n\n".join(parts)

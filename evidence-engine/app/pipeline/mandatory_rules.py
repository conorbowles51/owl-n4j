from __future__ import annotations

from typing import Any


def normalize_mandatory_instructions(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        instruction = str(item or "").strip()
        if not instruction:
            continue
        key = instruction.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(instruction)
    return normalized


def merge_mandatory_instructions(*lists: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for instruction_list in lists:
        for instruction in normalize_mandatory_instructions(instruction_list):
            key = instruction.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(instruction)
    return merged


def format_mandatory_rules_section(
    mandatory_instructions: list[str] | None,
    *,
    title: str = "MANDATORY PROFILE RULES",
) -> str:
    instructions = normalize_mandatory_instructions(mandatory_instructions)
    if not instructions:
        return ""

    ordered_rules = "\n".join(
        f"{index}. {instruction}" for index, instruction in enumerate(instructions, start=1)
    )
    return (
        f"{title}:\n"
        "These rules are binding for the relevant file or item. They are not optional guidance.\n"
        "The list is ordered from general to more specific. If two rules appear to differ, follow the later rule.\n"
        "Preserve outputs that already comply with these rules rather than normalizing them back to defaults.\n"
        f"{ordered_rules}"
    )


def prepend_mandatory_rules(
    prompt: str,
    mandatory_instructions: list[str] | None,
    *,
    title: str = "MANDATORY PROFILE RULES",
) -> str:
    section = format_mandatory_rules_section(mandatory_instructions, title=title)
    if not section:
        return prompt
    return f"{section}\n\n{prompt}"

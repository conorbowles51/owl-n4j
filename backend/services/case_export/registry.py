"""Section registry for case file exports."""

from __future__ import annotations

from collections.abc import Iterable

from services.case_export.types import ExportSection

_SECTIONS: dict[str, ExportSection] = {}


def register_section(section: ExportSection) -> None:
    key = (section.key or "").strip()
    if not key:
        raise ValueError("Export section key is required")
    if key in _SECTIONS:
        raise ValueError(f"Export section already registered: {key}")
    _SECTIONS[key] = section


def list_sections() -> list[ExportSection]:
    return sorted(_SECTIONS.values(), key=lambda section: (section.order, section.key))


def get_sections(keys: Iterable[str] | None) -> list[ExportSection]:
    ordered_sections = list_sections()
    if keys is None:
        return [section for section in ordered_sections if section.default_enabled]

    requested = {str(key or "").strip() for key in keys}
    requested.discard("")
    unknown = sorted(requested - set(_SECTIONS))
    if unknown:
        raise ValueError(f"Unknown export section(s): {', '.join(unknown)}")
    return [section for section in ordered_sections if section.key in requested]

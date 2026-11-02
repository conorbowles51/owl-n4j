"""Phone mappings as versioned data (docs/cellebrite/02 section 6): loader, row tables, applier."""
from __future__ import annotations


def install():
    """Register the mapping set and the applier with the interpretation sweep (called at backend start)."""
    from services.phone import sweep
    from services.phone.mappings import apply, loader
    sweep.register_mapping_set(loader.current_set)
    sweep.register_planner(apply.plan)
    sweep.register_applier(apply.apply_extraction)
    sweep.register_sensitive_fields(lambda: loader.sensitive_fields())

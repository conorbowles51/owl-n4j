# Postgres/permissions.py
from __future__ import annotations

from copy import deepcopy
from typing import TypedDict


class Permissions(TypedDict):
    case: dict
    collaborators: dict
    evidence: dict
    graph: dict
    ai: dict


OWNER_PERMISSIONS: Permissions = {
    "case": {"view": True, "edit": True, "delete": True},
    "collaborators": {"invite": True, "remove": True},
    "evidence": {"upload": True},
}

EDITOR_PERMISSIONS: Permissions = {
    "case": {"view": True, "edit": True, "delete": False},
    "collaborators": {"invite": False, "remove": False},
    "evidence": {"upload": True},
}

VIEWER_PERMISSIONS: Permissions = {
    "case": {"view": True, "edit": False, "delete": False},
    "collaborators": {"invite": False, "remove": False},
    "evidence": {"upload": False},
}


def clone_permissions(template: Permissions) -> dict:
    # Avoid accidental shared mutation
    return deepcopy(template)

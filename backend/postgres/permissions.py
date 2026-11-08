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


# A case owner deletes evidence files and folders in their own case (Neil 2026-11-08: "case owner can delete").
OWNER_PERMISSIONS: Permissions = {
    "case": {"view": True, "edit": True, "delete": True},
    "collaborators": {"invite": True, "remove": True},
    "evidence": {"upload": True, "delete": True},
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

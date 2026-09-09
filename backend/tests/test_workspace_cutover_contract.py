"""Phase 8 public-route contract for the canonical Workspace."""

from __future__ import annotations

from main import app


def _route_contract() -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in app.routes
        for method in (getattr(route, "methods", None) or set())
    }


def test_canonical_workspace_routes_are_registered():
    routes = _route_contract()
    required = {
        ("GET", "/api/workspace/{case_id}/overview"),
        ("GET", "/api/workspace/{case_id}/context"),
        ("POST", "/api/workspace/{case_id}/entries"),
        ("POST", "/api/workspace/{case_id}/tasks"),
        ("GET", "/api/workspace/{case_id}/work"),
        ("POST", "/api/workspace/{case_id}/ai-outputs"),
        ("POST", "/api/dossiers"),
        ("POST", "/api/dossiers/{dossier_id}/evidence"),
        ("DELETE", "/api/dossiers/{dossier_id}/evidence/{evidence_file_id}"),
        ("POST", "/api/dossiers/{dossier_id}/interviews"),
    }
    assert required <= routes


def test_retired_workspace_routes_are_not_registered():
    paths = {path for _, path in _route_contract()}
    retired = {
        "/api/workspace/{case_id}/notes",
        "/api/workspace/{case_id}/findings",
        "/api/workspace/{case_id}/theories",
        "/api/workspace/{case_id}/witnesses",
        "/api/workspace/{case_id}/timeline",
        "/api/workspace/{case_id}/investigation-timeline",
        "/api/workspace/{case_id}/build-graph",
        "/api/workspace/{case_id}/presence",
        "/api/case-profiles",
        "/api/case-profiles/{profile_id}",
        "/api/evidence/entity-links/add",
        "/api/evidence/entity-links/remove",
        "/api/evidence/by-entity",
    }
    assert retired.isdisjoint(paths)

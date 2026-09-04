"""Exercise the Phase 6 overview against the live local API fixtures."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPOSITORY_ROOT / "output" / "workspace-redesign" / "browser-fixtures.json"
REPORT_PATH = REPOSITORY_ROOT / "output" / "workspace-redesign" / "phase6-api-verification.json"
BASE_URL = "http://127.0.0.1:8002"


def _json(response: requests.Response, expected: int | tuple[int, ...] = 200) -> Any:
    statuses = (expected,) if isinstance(expected, int) else expected
    if response.status_code not in statuses:
        raise AssertionError(
            f"{response.request.method} {response.url} returned {response.status_code}: {response.text[:1000]}"
        )
    return response.json() if response.content else None


def _session(email: str, password: str) -> requests.Session:
    session = requests.Session()
    payload = _json(
        session.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": email, "password": password},
            timeout=10,
        )
    )
    session.headers["Authorization"] = f"Bearer {payload['access_token']}"
    return session


def _overview(session: requests.Session, case_id: str) -> tuple[dict[str, Any], float, int]:
    started = time.perf_counter()
    response = session.get(
        f"{BASE_URL}/api/workspace/{case_id}/overview",
        params={"timezone": "Europe/Dublin"},
        timeout=15,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1_000, 2)
    return _json(response), elapsed_ms, len(response.content)


def _bounded(payload: dict[str, Any]) -> bool:
    limits = payload["limits"]
    return (
        payload["bounded"] is True
        and len(payload["shared_attention"]) <= limits["shared_attention"]
        and len(payload["personal_attention"]) <= limits["personal_attention"]
        and len(payload["recent_casework"]) <= limits["recent_casework"]
        and len(payload["dossier_highlights"]) <= limits["dossier_highlights"]
        and len(payload["pinned_evidence"]) <= limits["pinned_evidence"]
    )


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sessions = {
        role: _session(user["email"], manifest["password"])
        for role, user in manifest["users"].items()
    }
    owner, editor, viewer = sessions["owner"], sessions["editor"], sessions["viewer"]
    empty_case = manifest["case_ids"]["empty"]
    small_case = manifest["case_ids"]["small"]
    scale_case = manifest["case_ids"]["scale"]
    report: dict[str, Any] = {"schema_version": 1, "checks": {}}

    empty, empty_ms, empty_bytes = _overview(viewer, empty_case)
    report["checks"]["empty_case"] = {
        "bounded": _bounded(empty),
        "shared_attention_count": len(empty["shared_attention"]),
        "personal_attention_count": len(empty["personal_attention"]),
        "recent_casework_count": len(empty["recent_casework"]),
        "response_bytes": empty_bytes,
        "elapsed_ms": empty_ms,
    }

    owner_overview, owner_ms, _ = _overview(owner, small_case)
    editor_overview, editor_ms, _ = _overview(editor, small_case)
    viewer_overview, viewer_ms, _ = _overview(viewer, small_case)
    shared_projection = lambda payload: [
        (item["attention_key"], item["reason_code"], item["rank"])
        for item in payload["shared_attention"]
    ]
    report["checks"]["role_visibility"] = {
        "owner_bounded": _bounded(owner_overview),
        "editor_bounded": _bounded(editor_overview),
        "viewer_bounded": _bounded(viewer_overview),
        "same_shared_collection": (
            shared_projection(owner_overview)
            == shared_projection(editor_overview)
            == shared_projection(viewer_overview)
        ),
        "elapsed_ms": {"owner": owner_ms, "editor": editor_ms, "viewer": viewer_ms},
    }

    editor_personal = editor_overview["personal_attention"]
    if not editor_personal:
        raise AssertionError("The Phase 5 fixture must provide an editor assignment")
    personal_item = editor_personal[0]
    personal_key = personal_item["attention_key"]
    encoded_key = quote(personal_key, safe="")
    source_before = None
    if personal_item["source_type"] == "task":
        source_before = _json(
            editor.get(
                f"{BASE_URL}/api/workspace/{small_case}/tasks/{personal_item['source_id']}",
                timeout=10,
            )
        )
    dismissed = _json(
        editor.put(
            f"{BASE_URL}/api/workspace/{small_case}/attention/{encoded_key}",
            json={"action": "dismiss"},
            timeout=10,
        )
    )
    editor_after, _, _ = _overview(editor, small_case)
    viewer_after, _, _ = _overview(viewer, small_case)
    source_after = None
    if personal_item["source_type"] == "task":
        source_after = _json(
            editor.get(
                f"{BASE_URL}/api/workspace/{small_case}/tasks/{personal_item['source_id']}",
                timeout=10,
            )
        )
    report["checks"]["personal_state"] = {
        "dismissed_at_recorded": bool(dismissed.get("dismissed_at")),
        "hidden_for_editor": all(
            item["attention_key"] != personal_key
            for item in editor_after["personal_attention"]
        ),
        "viewer_shared_unchanged": (
            shared_projection(viewer_after) == shared_projection(viewer_overview)
        ),
        "source_unchanged": source_before == source_after,
    }

    too_long = editor.put(
        f"{BASE_URL}/api/workspace/{small_case}/attention/{encoded_key}",
        json={
            "action": "snooze",
            "snoozed_until": (
                datetime.now(timezone.utc) + timedelta(days=31)
            ).isoformat(),
        },
        timeout=10,
    )
    report["checks"]["invalid_snooze_rejected"] = too_long.status_code == 400

    shared_only = next(
        (item for item in editor_overview["shared_attention"] if item["source_type"] == "deadline"),
        None,
    )
    if shared_only is None:
        raise AssertionError("The Phase 5 fixture must provide a shared deadline")
    shared_state = editor.put(
        f"{BASE_URL}/api/workspace/{small_case}/attention/{quote(shared_only['attention_key'], safe='')}",
        json={"action": "dismiss"},
        timeout=10,
    )
    report["checks"]["shared_state_rejected"] = shared_state.status_code == 400

    cross_case = editor.put(
        f"{BASE_URL}/api/workspace/{empty_case}/attention/{encoded_key}",
        json={"action": "dismiss"},
        timeout=10,
    )
    invalid_timezone = viewer.get(
        f"{BASE_URL}/api/workspace/{small_case}/overview",
        params={"timezone": "Not/A_Timezone"},
        timeout=10,
    )
    report["checks"]["validation"] = {
        "cross_case_attention_rejected": cross_case.status_code == 400,
        "invalid_timezone_rejected": invalid_timezone.status_code == 400,
    }

    cleared = editor.delete(
        f"{BASE_URL}/api/workspace/{small_case}/attention/{encoded_key}",
        timeout=10,
    )
    editor_restored, _, _ = _overview(editor, small_case)
    report["checks"]["clear_state"] = {
        "status": cleared.status_code,
        "item_visible_again": any(
            item["attention_key"] == personal_key
            for item in editor_restored["personal_attention"]
        ),
    }

    scale, scale_ms, scale_bytes = _overview(owner, scale_case)
    report["checks"]["production_shape"] = {
        "fixture_task_count": manifest.get("scale_task_count"),
        "fixture_evidence_count": manifest.get("scale_evidence_count"),
        "fixture_casework_count": manifest.get("scale_entry_count"),
        "bounded": _bounded(scale),
        "shared_attention_count": len(scale["shared_attention"]),
        "personal_attention_count": len(scale["personal_attention"]),
        "recent_casework_count": len(scale["recent_casework"]),
        "dossier_highlight_count": len(scale["dossier_highlights"]),
        "pinned_evidence_count": len(scale["pinned_evidence"]),
        "response_bytes": scale_bytes,
        "elapsed_ms": scale_ms,
    }

    checks = report["checks"]
    report["passed"] = (
        checks["empty_case"]["bounded"]
        and checks["empty_case"]["shared_attention_count"] == 0
        and checks["empty_case"]["personal_attention_count"] == 0
        and checks["empty_case"]["recent_casework_count"] == 0
        and all(
            checks["role_visibility"][name]
            for name in ("owner_bounded", "editor_bounded", "viewer_bounded", "same_shared_collection")
        )
        and all(checks["personal_state"].values())
        and checks["invalid_snooze_rejected"]
        and checks["shared_state_rejected"]
        and all(checks["validation"].values())
        and checks["clear_state"]["status"] == 204
        and checks["clear_state"]["item_visible_again"]
        and checks["production_shape"]["fixture_task_count"] >= 2_500
        and checks["production_shape"]["fixture_evidence_count"] >= 2_500
        and checks["production_shape"]["fixture_casework_count"] >= 2_500
        and checks["production_shape"]["bounded"]
        and checks["production_shape"]["response_bytes"] < 250_000
        and checks["production_shape"]["elapsed_ms"] < 5_000
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

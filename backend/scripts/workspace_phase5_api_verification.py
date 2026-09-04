"""Exercise Phase 5 against the live local API and isolated browser fixtures."""

from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPOSITORY_ROOT / "output" / "workspace-redesign" / "browser-fixtures.json"
REPORT_PATH = REPOSITORY_ROOT / "output" / "workspace-redesign" / "phase5-api-verification.json"
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


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sessions = {
        role: _session(user["email"], manifest["password"])
        for role, user in manifest["users"].items()
    }
    owner, editor, viewer = sessions["owner"], sessions["editor"], sessions["viewer"]
    small_case = manifest["case_ids"]["small"]
    empty_case = manifest["case_ids"]["empty"]
    scale_case = manifest["case_ids"]["scale"]
    editor_id = manifest["users"]["editor"]["id"]
    report: dict[str, Any] = {"schema_version": 1, "checks": {}}

    deadline_name = "[workspace-verification] Phase 5 API deadline"
    deadline_list = _json(owner.get(f"{BASE_URL}/api/cases/{small_case}/deadlines", timeout=10))
    deadline = next(
        (item for item in deadline_list["deadlines"] if item["name"] == deadline_name),
        None,
    )
    if deadline is None:
        deadline = _json(
            owner.post(
                f"{BASE_URL}/api/cases/{small_case}/deadlines",
                json={"name": deadline_name, "due_date": str(date.today() + timedelta(days=21))},
                timeout=10,
            ),
            201,
        )

    run_tag = str(time.time_ns())
    parent = _json(
        owner.post(
            f"{BASE_URL}/api/workspace/{small_case}/tasks",
            json={
                "title": f"[workspace-verification] API parent {run_tag}",
                "description": "Verify assignment, due dates, deadline links and subtasks.",
                "priority": "urgent",
                "assignee_user_id": editor_id,
                "deadline_id": deadline["id"],
                "links": [
                    {
                        "target_type": "evidence",
                        "target_id": manifest["evidence"][0]["id"],
                        "label": manifest["evidence"][0]["filename"],
                        "source_anchor": {"page": 1},
                    }
                ],
            },
            timeout=10,
        )
    )
    child = _json(
        editor.post(
            f"{BASE_URL}/api/workspace/{small_case}/tasks",
            json={
                "title": f"[workspace-verification] API child {run_tag}",
                "status": "done",
                "priority": "standard",
                "parent_task_id": parent["id"],
            },
            timeout=10,
        )
    )
    parent_refreshed = _json(
        viewer.get(
            f"{BASE_URL}/api/workspace/{small_case}/tasks/{parent['id']}",
            timeout=10,
        )
    )
    report["checks"]["task_roundtrip"] = {
        "parent_id": parent["id"],
        "child_id": child["id"],
        "assigned_to_editor": parent_refreshed["assignee_user_id"] == editor_id,
        "deadline_linked": parent_refreshed["deadline_id"] == deadline["id"],
        "subtask_progress": parent_refreshed["subtask_progress"],
        "evidence_link_count": len(parent_refreshed["links"]),
    }

    viewer_task = viewer.post(
        f"{BASE_URL}/api/workspace/{small_case}/tasks",
        json={"title": "Viewer must not create this"},
        timeout=10,
    )
    report["checks"]["viewer_task_denied"] = viewer_task.status_code == 403

    cross_case = owner.post(
        f"{BASE_URL}/api/workspace/{empty_case}/tasks",
        json={
            "title": "Cross-case link must fail",
            "links": [
                {
                    "target_type": "evidence",
                    "target_id": manifest["evidence"][0]["id"],
                }
            ],
        },
        timeout=10,
    )
    report["checks"]["cross_case_link_denied"] = cross_case.status_code == 400

    evidence_id = manifest["evidence"][0]["id"]
    first_pin = _json(
        owner.post(
            f"{BASE_URL}/api/workspace/{small_case}/pinned",
            params={"item_id": evidence_id, "item_type": "evidence"},
            timeout=10,
        )
    )
    repeated_pin = _json(
        editor.post(
            f"{BASE_URL}/api/workspace/{small_case}/pinned",
            params={"item_id": evidence_id, "item_type": "evidence"},
            timeout=10,
        )
    )
    viewer_pins = _json(
        viewer.get(f"{BASE_URL}/api/workspace/{small_case}/pinned", timeout=10)
    )
    viewer_pin = viewer.post(
        f"{BASE_URL}/api/workspace/{small_case}/pinned",
        params={"item_id": manifest["evidence"][1]["id"]},
        timeout=10,
    )
    report["checks"]["shared_pins"] = {
        "same_identity": first_pin["id"] == repeated_pin["id"],
        "second_request_idempotent": repeated_pin["created"] is False,
        "viewer_can_read": any(item["id"] == first_pin["id"] for item in viewer_pins["pinned_items"]),
        "viewer_mutation_denied": viewer_pin.status_code == 403,
    }

    started = time.perf_counter()
    scale_work = _json(
        viewer.get(
            f"{BASE_URL}/api/workspace/{scale_case}/work",
            params={"limit": 100},
            timeout=15,
        )
    )
    work_elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    started = time.perf_counter()
    scale_evidence = _json(
        viewer.get(
            f"{BASE_URL}/api/evidence-folders/root/contents",
            params={"case_id": scale_case, "limit": 250, "offset": 0},
            timeout=15,
        )
    )
    evidence_elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    next_evidence = _json(
        viewer.get(
            f"{BASE_URL}/api/evidence-folders/root/contents",
            params={"case_id": scale_case, "limit": 1, "offset": 250},
            timeout=15,
        )
    )
    evidence_ids = [item["id"] for item in scale_evidence["files"]]
    started = time.perf_counter()
    pin_status = _json(
        viewer.get(
            f"{BASE_URL}/api/workspace/{scale_case}/pinned/status",
            params=[("evidence_file_ids", value) for value in evidence_ids],
            timeout=15,
        )
    )
    pin_status_elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    oversized_status = viewer.get(
        f"{BASE_URL}/api/workspace/{scale_case}/pinned/status",
        params=[
            ("evidence_file_ids", value)
            for value in [*evidence_ids, next_evidence["files"][0]["id"]]
        ],
        timeout=15,
    )
    bulk_pin = _json(
        owner.post(
            f"{BASE_URL}/api/workspace/{scale_case}/pinned/bulk",
            json={"evidence_file_ids": evidence_ids[:3]},
            timeout=15,
        )
    )
    report["checks"]["bounded_scale"] = {
        "task_total": scale_work["task_total"],
        "returned_tasks": len(scale_work["tasks"]),
        "work_bounded": scale_work["bounded"],
        "work_elapsed_ms": work_elapsed_ms,
        "evidence_total": scale_evidence["file_total"],
        "returned_evidence": len(scale_evidence["files"]),
        "evidence_elapsed_ms": evidence_elapsed_ms,
        "pin_status_checked": len(evidence_ids),
        "pin_status_matches": len(pin_status["pins"]),
        "pin_status_elapsed_ms": pin_status_elapsed_ms,
        "oversized_status_rejected": oversized_status.status_code == 400,
        "bulk_pin_result": bulk_pin,
    }

    checks = report["checks"]
    report["passed"] = (
        checks["task_roundtrip"]["assigned_to_editor"]
        and checks["task_roundtrip"]["deadline_linked"]
        and checks["task_roundtrip"]["subtask_progress"] == {"done": 1, "total": 1}
        and checks["task_roundtrip"]["evidence_link_count"] == 1
        and checks["viewer_task_denied"]
        and checks["cross_case_link_denied"]
        and all(checks["shared_pins"].values())
        and checks["bounded_scale"]["task_total"] >= 2_500
        and checks["bounded_scale"]["returned_tasks"] == 100
        and checks["bounded_scale"]["work_bounded"]
        and checks["bounded_scale"]["evidence_total"] >= 2_500
        and checks["bounded_scale"]["returned_evidence"] == 250
        and checks["bounded_scale"]["pin_status_checked"] == 250
        and checks["bounded_scale"]["oversized_status_rejected"]
        and len(checks["bounded_scale"]["bulk_pin_result"]["pins"]) == 3
        and checks["bounded_scale"]["work_elapsed_ms"] < 5_000
        and checks["bounded_scale"]["evidence_elapsed_ms"] < 5_000
        and checks["bounded_scale"]["pin_status_elapsed_ms"] < 5_000
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

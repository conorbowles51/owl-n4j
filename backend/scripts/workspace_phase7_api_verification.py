"""Exercise cited Workspace AI review flows against the live local API."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPOSITORY_ROOT / "output" / "workspace-redesign" / "browser-fixtures.json"
REPORT_PATH = REPOSITORY_ROOT / "output" / "workspace-redesign" / "phase7-api-verification.json"
BASE_URL = "http://127.0.0.1:8002"


def _json(response: requests.Response, expected: int | tuple[int, ...] = 200) -> Any:
    statuses = (expected,) if isinstance(expected, int) else expected
    if response.status_code not in statuses:
        raise AssertionError(
            f"{response.request.method} {response.url} returned {response.status_code}: "
            f"{response.text[:1000]}"
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


def _list(session: requests.Session, case_id: str, target_type: str, target_id: str) -> dict:
    return _json(
        session.get(
            f"{BASE_URL}/api/workspace/{case_id}/ai-outputs",
            params={"target_type": target_type, "target_id": target_id, "limit": 50},
            timeout=10,
        )
    )


def _citation_integrity(output: dict) -> bool:
    sources = {source["source_id"]: source for source in output["source_set"]}
    citations = output["citations"]
    return (
        output["job_status"] == "completed"
        and output["citation_status"] == "valid"
        and bool(citations)
        and len(output["source_set"]) <= 36
        and all(
            citation["source_id"] in sources
            and citation["evidence_file_id"] == sources[citation["source_id"]]["evidence_file_id"]
            and citation["url"].startswith(f"/cases/{output['case_id']}/evidence?")
            and bool(citation.get("source_anchor"))
            for citation in citations
        )
    )


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    phase7 = manifest["phase7"]
    sessions = {
        role: _session(user["email"], manifest["password"])
        for role, user in manifest["users"].items()
    }
    owner, editor, viewer = sessions["owner"], sessions["editor"], sessions["viewer"]
    case_id = manifest["case_ids"]["small"]
    other_case_id = manifest["case_ids"]["empty"]
    dossier_id = phase7["dossier_id"]
    theory_id = phase7["theory_id"]
    output_ids = phase7["output_ids"]
    report: dict[str, Any] = {"schema_version": 1, "checks": {}}

    dossier_outputs = _list(viewer, case_id, "dossier", dossier_id)
    theory_outputs = _list(viewer, case_id, "theory", theory_id)
    all_outputs = dossier_outputs["outputs"] + theory_outputs["outputs"]
    completed = [item for item in all_outputs if item["job_status"] == "completed"]
    status_pairs = {(item["job_status"], item["review_status"]) for item in all_outputs}
    report["checks"]["durable_outputs"] = {
        "dossier_total": dossier_outputs["total"],
        "theory_total": theory_outputs["total"],
        "citation_integrity": all(_citation_integrity(item) for item in completed),
        "has_pending": ("completed", "pending_review") in status_pairs,
        "has_accepted": ("completed", "accepted") in status_pairs,
        "has_rejected": ("completed", "rejected") in status_pairs,
        "has_running": ("running", "pending_review") in status_pairs,
        "all_mandated": all(
            item["mandate_version_id"] == phase7["mandate_version_id"]
            and item["mandate_version_number"] is not None
            for item in all_outputs
        ),
        "version_history_preserved": len(
            {
                item["version"]
                for item in dossier_outputs["outputs"]
                if item["output_type"] == "statement_summary"
            }
        )
        >= 3,
    }

    pending_summary = output_ids["pending_summary"]
    viewer_start = viewer.post(
        f"{BASE_URL}/api/workspace/{case_id}/ai-outputs",
        json={
            "target_type": "theory",
            "target_id": theory_id,
            "output_type": "theory_analysis",
        },
        timeout=10,
    )
    viewer_accept = viewer.post(
        f"{BASE_URL}/api/workspace/{case_id}/ai-outputs/{pending_summary}/accept",
        timeout=10,
    )
    viewer_reject = viewer.post(
        f"{BASE_URL}/api/workspace/{case_id}/ai-outputs/{pending_summary}/reject",
        json={"reason": "Viewer must not be able to review"},
        timeout=10,
    )
    cross_case = viewer.get(
        f"{BASE_URL}/api/workspace/{other_case_id}/ai-outputs/{pending_summary}",
        timeout=10,
    )
    report["checks"]["authorization"] = {
        "viewer_can_read": dossier_outputs["total"] > 0,
        "viewer_cannot_start": viewer_start.status_code == 403,
        "viewer_cannot_accept": viewer_accept.status_code == 403,
        "viewer_cannot_reject": viewer_reject.status_code == 403,
        "cross_case_hidden": cross_case.status_code == 404,
    }

    accepted = _json(
        editor.post(
            f"{BASE_URL}/api/workspace/{case_id}/ai-outputs/{pending_summary}/accept",
            timeout=15,
        )
    )
    dossier = _json(editor.get(f"{BASE_URL}/api/dossiers/{dossier_id}", timeout=10))
    generated_assessment = next(
        (
            item
            for item in dossier["assessments"]
            if item.get("generated_output_id") == pending_summary
        ),
        None,
    )
    report["checks"]["explicit_dossier_acceptance"] = {
        "accepted": accepted["review_status"] == "accepted",
        "reviewer_is_editor": accepted["reviewed_by_user_id"]
        == manifest["users"]["editor"]["id"],
        "generation_attribution_preserved": accepted["requested_by_user_id"]
        == manifest["users"]["owner"]["id"],
        "assessment_created": generated_assessment is not None,
        "ai_provenance": bool(
            generated_assessment
            and generated_assessment.get("provenance_type") == "ai_assisted"
        ),
    }

    pending_comparison = output_ids["pending_comparison"]
    rejected = _json(
        editor.post(
            f"{BASE_URL}/api/workspace/{case_id}/ai-outputs/{pending_comparison}/reject",
            json={"reason": "Comparison requires a follow-up interview."},
            timeout=10,
        )
    )
    report["checks"]["explicit_rejection"] = {
        "rejected": rejected["review_status"] == "rejected",
        "reason_retained": rejected["rejection_reason"]
        == "Comparison requires a follow-up interview.",
        "no_accepted_targets": rejected["accepted_targets"] == [],
    }

    pending_theory = output_ids["pending_theory"]
    theory_accepted = _json(
        editor.post(
            f"{BASE_URL}/api/workspace/{case_id}/ai-outputs/{pending_theory}/accept",
            timeout=15,
        )
    )
    theory = _json(
        editor.get(
            f"{BASE_URL}/api/workspace/{case_id}/entries/{theory_id}", timeout=10
        )
    )
    phase7_evidence_ids = set(phase7["evidence_ids"].values())
    ai_links = [
        link
        for link in theory["links"]
        if link.get("metadata", {}).get("workspace_ai_output_id")
        and link.get("target_id") in phase7_evidence_ids
    ]
    report["checks"]["balanced_theory_acceptance"] = {
        "accepted": theory_accepted["review_status"] == "accepted",
        "support_and_contradiction_cited": {
            item["relationship"] for item in ai_links
        }
        == {"supports", "contradicts"},
        "canonical_links_created": len(ai_links) == 2,
    }

    running_id = output_ids["running_comparison"]
    running_before = _json(
        owner.get(
            f"{BASE_URL}/api/workspace/{case_id}/ai-outputs/{running_id}", timeout=10
        )
    )
    owner.get(f"{BASE_URL}/api/cases/{other_case_id}", timeout=10)
    time.sleep(0.05)
    running_after = _json(
        owner.get(
            f"{BASE_URL}/api/workspace/{case_id}/ai-outputs/{running_id}", timeout=10
        )
    )
    report["checks"]["navigation_independent_job"] = {
        "still_running": running_before["job_status"] == running_after["job_status"] == "running",
        "same_progress": running_before["progress"] == running_after["progress"] == 47,
        "same_source_set": running_before["source_set"] == running_after["source_set"],
    }

    evidence_checks = []
    for evidence_id in phase7["evidence_ids"].values():
        metadata = _json(
            viewer.get(f"{BASE_URL}/api/evidence/{evidence_id}", timeout=10)
        )
        file_response = viewer.get(
            f"{BASE_URL}/api/evidence/{evidence_id}/file",
            headers={"Range": "bytes=0-127"},
            timeout=10,
        )
        evidence_checks.append(
            metadata["case_id"] == case_id
            and metadata["id"] == evidence_id
            and file_response.status_code in {200, 206}
            and len(file_response.content) > 0
        )
    report["checks"]["citation_destinations"] = {
        "all_metadata_resolves": all(evidence_checks),
        "all_files_navigable": all(evidence_checks),
    }

    checks = report["checks"]
    report["passed"] = (
        checks["durable_outputs"]["dossier_total"] >= 5
        and checks["durable_outputs"]["theory_total"] >= 2
        and all(
            value
            for key, value in checks["durable_outputs"].items()
            if key not in {"dossier_total", "theory_total"}
        )
        and all(checks["authorization"].values())
        and all(checks["explicit_dossier_acceptance"].values())
        and all(checks["explicit_rejection"].values())
        and all(checks["balanced_theory_acceptance"].values())
        and all(checks["navigation_independent_job"].values())
        and all(checks["citation_destinations"].values())
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

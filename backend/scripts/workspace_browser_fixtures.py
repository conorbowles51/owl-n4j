"""Create or remove isolated local fixtures for Workspace browser verification.

All records carry a unique ``[workspace-verification]`` prefix and their exact UUIDs
are persisted in the generated manifest. Cleanup refuses to remove records that no
longer match that prefix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from postgres.models.case import Case
from postgres.backfills.workspace_cutover import backfill_missing_entry_history
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole, GlobalRole
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from postgres.models.workspace_entry import WorkspaceEntry
from postgres.models.work import CaseTask
from postgres.session import get_background_session
from routers.users import hash_password
from services.case_service import get_permissions_for_preset


PREFIX = "[workspace-verification]"
DEFAULT_MANIFEST = (
    REPOSITORY_ROOT / "output" / "workspace-redesign" / "browser-fixtures.json"
)


def _manifest_path(value: str | None) -> Path:
    return Path(value).resolve() if value else DEFAULT_MANIFEST


def _fixture_file_metadata(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), path.stat().st_size


def _ensure_phase3_sources(manifest: dict[str, object]) -> dict[str, object]:
    """Add bounded image and graph sources used by the Dossier browser journeys."""
    small_case_id = UUID(str(manifest["case_ids"]["small"]))
    owner_id = UUID(str(manifest["users"]["owner"]["id"]))
    fixture_id = str(manifest["fixture_id"])
    source_paths = [
        REPOSITORY_ROOT / "frontend_v2" / "public" / "loupe-logo.png",
        REPOSITORY_ROOT / "frontend_v2" / "public" / "loupe-red-light.png",
    ]
    evidence_manifest: list[dict[str, object]] = []
    with get_background_session() as db:
        for index, source_path in enumerate(source_paths, start=1):
            if not source_path.is_file():
                raise RuntimeError(f"Dossier fixture image is missing: {source_path}")
            filename = f"{PREFIX} dossier-source-{index}.png"
            sha256, size = _fixture_file_metadata(source_path)
            record = (
                db.query(EvidenceFile)
                .filter(
                    EvidenceFile.case_id == small_case_id,
                    EvidenceFile.original_filename == filename,
                )
                .one_or_none()
            )
            if record is None:
                record = EvidenceFile(
                    case_id=small_case_id,
                    original_filename=filename,
                    stored_path=str(source_path.resolve()),
                    size=size,
                    sha256=sha256,
                    status="unprocessed",
                    owner=str(manifest["users"]["owner"]["email"]),
                    created_by_id=owner_id,
                    metadata_={"fixture_id": fixture_id, "purpose": "dossier-media"},
                )
                db.add(record)
                db.flush()
            evidence_manifest.append(
                {
                    "id": str(record.id),
                    "filename": record.original_filename,
                    "sha256": record.sha256,
                    "size": record.size,
                    "metadata": dict(record.metadata_ or {}),
                }
            )

    graph_entities = [
        {
            "key": f"workspace-verification-{fixture_id}-henry",
            "name": f"{PREFIX} Henry subject",
            "summary": "Evidence-derived identity used only for isolated Dossier verification.",
        },
        {
            "key": f"workspace-verification-{fixture_id}-caller",
            "name": f"{PREFIX} Identified caller",
            "summary": "Later evidence resolved the previously unknown caller identity.",
        },
    ]
    try:
        from services.neo4j import neo4j_service

        for entity in graph_entities:
            neo4j_service.run_cypher(
                """
                MERGE (n:Person {case_id: $case_id, key: $key})
                SET n.id = $key,
                    n.name = $name,
                    n.summary = $summary,
                    n.verification_fixture_id = $fixture_id
                RETURN n.key AS key
                """,
                {
                    "case_id": str(small_case_id),
                    **entity,
                    "fixture_id": fixture_id,
                },
            )
    except Exception as exc:
        raise RuntimeError("Could not create the isolated Dossier graph fixture") from exc

    manifest["evidence"] = evidence_manifest
    manifest["graph_entities"] = [
        {"case_id": str(small_case_id), "type": "Person", **entity}
        for entity in graph_entities
    ]
    return manifest


def _ensure_phase5_sources(
    manifest: dict[str, object],
    scale_count: int,
) -> dict[str, object]:
    """Add canonical Work records and a large, bounded Evidence listing."""

    fixture_id = str(manifest["fixture_id"])
    owner_id = UUID(str(manifest["users"]["owner"]["id"]))
    scale_case_id = UUID(str(manifest["case_ids"]["scale"]))
    task_count = max(0, min(scale_count, 10_000))
    evidence_count = max(1_000, min(task_count, 5_000))
    now = datetime.now(timezone.utc)
    title_prefix = f"{PREFIX} scale task "
    filename_prefix = f"{PREFIX} scale evidence "

    with get_background_session() as db:
        existing_task_count = (
            db.query(CaseTask)
            .filter(
                CaseTask.case_id == scale_case_id,
                CaseTask.title.like(f"{title_prefix}%"),
            )
            .count()
        )
        if existing_task_count == 0:
            tasks: list[CaseTask] = []
            for index in range(task_count):
                tasks.append(
                    CaseTask(
                        case_id=scale_case_id,
                        title=f"{title_prefix}{index + 1:04d}",
                        description="Representative bounded Work fixture.",
                        status=("todo", "in_progress", "done")[index % 3],
                        priority=("low", "standard", "high", "urgent")[index % 4],
                        assignee_user_id=owner_id if index % 2 == 0 else None,
                        due_at=now + timedelta(hours=index % 720),
                        created_by_user_id=owner_id,
                        updated_by_user_id=owner_id,
                        completed_at=now if index % 3 == 2 else None,
                        created_at=now - timedelta(minutes=index),
                        updated_at=now - timedelta(minutes=index),
                    )
                )
                if len(tasks) == 500:
                    db.bulk_save_objects(tasks)
                    tasks.clear()
            if tasks:
                db.bulk_save_objects(tasks)

        existing_evidence_count = (
            db.query(EvidenceFile)
            .filter(
                EvidenceFile.case_id == scale_case_id,
                EvidenceFile.original_filename.like(f"{filename_prefix}%"),
            )
            .count()
        )
        if existing_evidence_count == 0:
            evidence_rows: list[EvidenceFile] = []
            for index in range(evidence_count):
                filename = f"{filename_prefix}{index + 1:04d}.txt"
                evidence_rows.append(
                    EvidenceFile(
                        case_id=scale_case_id,
                        original_filename=filename,
                        stored_path=f"/workspace-verification/{fixture_id}/{filename}",
                        size=512 + index,
                        sha256=hashlib.sha256(
                            f"{fixture_id}:scale-evidence:{index}".encode()
                        ).hexdigest(),
                        status="unprocessed",
                        owner=str(manifest["users"]["owner"]["email"]),
                        created_by_id=owner_id,
                        metadata_={"fixture_id": fixture_id, "purpose": "scale"},
                        created_at=now - timedelta(minutes=index),
                        updated_at=now - timedelta(minutes=index),
                    )
                )
                if len(evidence_rows) == 500:
                    db.bulk_save_objects(evidence_rows)
                    evidence_rows.clear()
            if evidence_rows:
                db.bulk_save_objects(evidence_rows)

        if (
            db.query(CaseDeadline)
            .filter(
                CaseDeadline.case_id == scale_case_id,
                CaseDeadline.name == f"{PREFIX} scale deadline",
            )
            .count()
            == 0
        ):
            db.add(
                CaseDeadline(
                    case_id=scale_case_id,
                    name=f"{PREFIX} scale deadline",
                    due_date=(now + timedelta(days=30)).date(),
                    created_by_user_id=owner_id,
                )
            )

    manifest["scale_task_count"] = task_count
    manifest["scale_evidence_count"] = evidence_count
    return manifest


def _create(path: Path, scale_count: int) -> dict[str, object]:
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        with get_background_session() as db:
            case_ids = [UUID(value) for value in existing.get("case_ids", {}).values()]
            if case_ids and db.query(Case).filter(Case.id.in_(case_ids)).count() == len(case_ids):
                _ensure_phase3_sources(existing)
                _ensure_phase5_sources(existing, scale_count)
                path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
                return existing

    fixture_id = uuid4().hex[:10]
    password = secrets.token_urlsafe(18)
    users = {
        role: User(
            id=uuid4(),
            email=f"workspace-{role}-{fixture_id}@example.test",
            name=f"Workspace {role.title()}",
            password_hash=hash_password(password),
            global_role=GlobalRole.user,
            is_active=True,
        )
        for role in ("owner", "editor", "viewer")
    }
    cases = {
        shape: Case(
            id=uuid4(),
            title=f"{PREFIX} {shape.title()} {fixture_id}",
            description=f"Isolated {shape} case for automated Workspace verification.",
            status="active",
            created_by_user_id=users["owner"].id,
            owner_user_id=users["owner"].id,
        )
        for shape in ("empty", "small", "scale")
    }
    user_manifest = {
        role: {"id": str(user.id), "email": user.email}
        for role, user in users.items()
    }
    case_manifest = {shape: str(case.id) for shape, case in cases.items()}

    with get_background_session() as db:
        db.add_all(users.values())
        db.flush()
        db.add_all(cases.values())
        db.flush()
        for case in cases.values():
            for role, user in users.items():
                db.add(
                    CaseMembership(
                        case_id=case.id,
                        user_id=user.id,
                        membership_role=(
                            CaseMembershipRole.owner
                            if role == "owner"
                            else CaseMembershipRole.collaborator
                        ),
                        permissions=get_permissions_for_preset(
                            "editor" if role in {"owner", "editor"} else "viewer"
                        ),
                        added_by_user_id=users["owner"].id,
                    )
                )

        small_entries = [
            WorkspaceEntry(
                case_id=cases["small"].id,
                entry_type="note",
                title="Initial interview observation",
                body="The account holder described an unexplained transfer.",
                tags=["interview"],
                review_state="accepted",
                version=1,
                author_user_id=users["owner"].id,
                author_email=users["owner"].email,
                author_name=users["owner"].name,
                updated_by_user_id=users["owner"].id,
                updated_by_email=users["owner"].email,
                updated_by_name=users["owner"].name,
            ),
            WorkspaceEntry(
                case_id=cases["small"].id,
                entry_type="finding",
                title="Transfer followed formal notice",
                body="The dated statement places the transfer after formal notice.",
                tags=["banking", "chronology"],
                lifecycle_state="active",
                significance="high",
                review_state="accepted",
                version=1,
                author_user_id=users["editor"].id,
                author_email=users["editor"].email,
                author_name=users["editor"].name,
                updated_by_user_id=users["editor"].id,
                updated_by_email=users["editor"].email,
                updated_by_name=users["editor"].name,
            ),
            WorkspaceEntry(
                case_id=cases["small"].id,
                entry_type="theory",
                title="The transfer was coordinated",
                body="The timing and counterparties may indicate coordination.",
                tags=["assets"],
                lifecycle_state="investigating",
                confidence=55,
                review_state="accepted",
                version=1,
                author_user_id=users["owner"].id,
                author_email=users["owner"].email,
                author_name=users["owner"].name,
                updated_by_user_id=users["owner"].id,
                updated_by_email=users["owner"].email,
                updated_by_name=users["owner"].name,
            ),
        ]
        db.add_all(small_entries)

        now = datetime.now(timezone.utc)
        scale_entries: list[WorkspaceEntry] = []
        for index in range(max(0, min(scale_count, 10_000))):
            entry_type = ("finding", "theory", "note")[index % 3]
            scale_entries.append(
                WorkspaceEntry(
                    case_id=cases["scale"].id,
                    entry_type=entry_type,
                    title=(
                        None
                        if entry_type == "note"
                        else f"Scale {entry_type} {index + 1:04d}"
                    ),
                    body=f"Representative browser-verification casework record {index + 1}.",
                    tags=["scale", f"batch-{index % 12}"],
                    lifecycle_state=(
                        "active"
                        if entry_type == "finding"
                        else "investigating"
                        if entry_type == "theory"
                        else None
                    ),
                    significance=(
                        ("high", "medium", "low")[index % 3]
                        if entry_type == "finding"
                        else None
                    ),
                    confidence=(index % 21) * 5 if entry_type == "theory" else None,
                    review_state="accepted",
                    version=1,
                    author_user_id=users["owner"].id,
                    author_email=users["owner"].email,
                    author_name=users["owner"].name,
                    updated_by_user_id=users["owner"].id,
                    updated_by_email=users["owner"].email,
                    updated_by_name=users["owner"].name,
                    created_at=now - timedelta(minutes=index),
                    updated_at=now - timedelta(minutes=index),
                )
            )
            if len(scale_entries) == 500:
                db.bulk_save_objects(scale_entries)
                scale_entries.clear()
        if scale_entries:
            db.bulk_save_objects(scale_entries)

    manifest: dict[str, object] = {
        "fixture_id": fixture_id,
        "prefix": PREFIX,
        "password": password,
        "users": user_manifest,
        "case_ids": case_manifest,
        "scale_entry_count": scale_count,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _ensure_phase3_sources(manifest)
    _ensure_phase5_sources(manifest, scale_count)
    with get_background_session() as db:
        manifest["entry_history"] = backfill_missing_entry_history(
            db.connection(),
            case_ids=[UUID(value) for value in case_manifest.values()],
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _cleanup(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"removed": False, "reason": "manifest not found"}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    case_ids = [UUID(value) for value in manifest.get("case_ids", {}).values()]
    user_ids = [UUID(value["id"]) for value in manifest.get("users", {}).values()]
    with get_background_session() as db:
        cases = db.query(Case).filter(Case.id.in_(case_ids)).all()
        unsafe = [str(case.id) for case in cases if not case.title.startswith(PREFIX)]
        if unsafe:
            raise RuntimeError(
                "Refusing fixture cleanup because case titles no longer carry the safety prefix: "
                + ", ".join(unsafe)
            )
        for case in cases:
            db.delete(case)
        db.flush()
        for user in db.query(User).filter(User.id.in_(user_ids)).all():
            if not user.email.startswith("workspace-") or not user.email.endswith(
                "@example.test"
            ):
                raise RuntimeError(
                    f"Refusing fixture cleanup for unexpected user {user.email}"
                )
            db.delete(user)
    try:
        from services.neo4j import neo4j_service

        neo4j_service.run_cypher(
            """
            MATCH (n {verification_fixture_id: $fixture_id})
            WHERE n.case_id IN $case_ids
            DETACH DELETE n
            """,
            {
                "fixture_id": str(manifest.get("fixture_id", "")),
                "case_ids": [str(value) for value in case_ids],
            },
        )
    except Exception as exc:
        raise RuntimeError(
            "PostgreSQL fixtures were removed, but isolated graph cleanup failed"
        ) from exc
    path.unlink()
    return {
        "removed": True,
        "case_ids": [str(value) for value in case_ids],
        "user_ids": [str(value) for value in user_ids],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("create", "cleanup"))
    parser.add_argument("--manifest")
    parser.add_argument("--scale-count", type=int, default=2500)
    args = parser.parse_args()
    path = _manifest_path(args.manifest)
    result = (
        _create(path, args.scale_count)
        if args.mode == "create"
        else _cleanup(path)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

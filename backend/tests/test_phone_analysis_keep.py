"""Keeping an approach result and linking it (02 decision 50; J-14b). Invented data only."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from postgres import link_types
from services.pattern_of_life import snapshots
from services.phone_analysis import framework as F
from services.phone_analysis import keep as K
from services.phone_analysis import message_reconciliation as R
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone
from tests.test_phone_analysis_message_reconciliation import X_OWNER, Y_OWNER, _msg


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


@needs_template
def test_a_kept_result_is_a_frozen_snapshot_the_phone_analysis_resolver_resolves(engine):
    F.register(R)
    snapshots.register()
    t = at(2023, 3, 1, 9)
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", owner=X_OWNER, events=[_msg(t, "a kept line of text", X_OWNER, [Y_OWNER],
                                                                      X_OWNER)])
        y, _ = phone(c, case, label="C2", owner=Y_OWNER, events=[_msg(t + timedelta(seconds=2), "a kept line of text",
                                                                      X_OWNER, [Y_OWNER], Y_OWNER)])
        run, _ = F.request_run(c, case, "message_reconciliation", None, "synthetic@example.org")
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        (item,) = F.results(c, case, run["id"], kind="both_sides")["items"]
    with Session(engine) as db:
        kept = K.keep(db, case, item["id"])
        again = K.keep(db, case, item["id"])
        db.commit()
    assert kept["id"] == again["id"] and kept["id"].startswith("pa_")
    assert kept["kind"] == "analysis_result" and kept["record_count"] == 2 and kept["stale"] is False
    assert kept["label"] == "Messages across phones: both sides, C1 and C2 (Lead for enquiry)"
    snap = kept["snapshot"]
    assert snap["subject"]["approach"] == "message_reconciliation" and snap["subject"]["result_key"] == item["result_key"]
    assert sorted(snap["mapping_versions"]["extractions"]) == sorted([str(x), str(y)])
    with Session(engine) as db:
        target = link_types.resolve_phone_target(db, case, "phone_analysis", kept["id"])
        assert target.snapshot["kind"] == "analysis_result" and len(target.members) == 2
        with pytest.raises(link_types.LinkTargetError):
            link_types.resolve_phone_target(db, make_case(db.connection()), "phone_analysis", kept["id"])


@needs_template
def test_co1_analyses_cells_single_and_bulk_into_each_container_open_back(engine):
    """CO-1 cells "analyses" (07 6.5): a kept result (single) and the records behind it (bulk), as the analysis
    screens send them, go into a finding, a dossier and an interview; each stored link keeps what opens it back (the
    analysis and the kept id; the record uid), and a repeat add reports the already-present ones, never twice."""
    from unittest.mock import patch

    from sqlalchemy import text

    from postgres.models.user import User
    from services import dossier_service
    from services import workspace_entry_service as entries
    from services.phone import resolvers
    F.register(R)
    snapshots.register()
    resolvers.register()
    t = at(2023, 3, 1, 9)
    with engine.begin() as c:
        case = make_case(c)
        x, _ = phone(c, case, label="C1", owner=X_OWNER, events=[_msg(t, "a kept line of text", X_OWNER, [Y_OWNER],
                                                                      X_OWNER)])
        y, _ = phone(c, case, label="C2", owner=Y_OWNER, events=[_msg(t + timedelta(seconds=2), "a kept line of text",
                                                                      X_OWNER, [Y_OWNER], Y_OWNER)])
        run, _ = F.request_run(c, case, "message_reconciliation", None, "synthetic@example.org")
        owner = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        (item,) = F.results(c, case, run["id"], kind="both_sides")["items"]
        uids = sorted({r["record_uid"] for r in F.result_detail(c, case, item["id"])["records"] if r["record_uid"]})
    assert len(uids) == 2
    single = {"target_type": "phone_analysis", "label": "kept",
              "source_anchor": {"kind": "analysis_result", "approach": "message_reconciliation"}}
    bulk = [{"target_type": "phone_record", "target_id": u, "label": "record",
             "source_anchor": {"kind": "phone_record", "record_uid": u}} for u in uids]
    with Session(engine) as db, \
            patch.object(dossier_service, "check_case_access", return_value=(None, None)), \
            patch.object(dossier_service, "get_case_if_allowed", return_value=None), \
            patch.object(dossier_service, "_case_member_ids", return_value=set()):
        kept = K.keep(db, case, item["id"])
        db.commit()
        single["target_id"] = kept["id"]
        user = db.get(User, owner)
        finding = uuid.UUID(entries.create_entry(db, case_id=case, current_user=user, entry_type="finding",
                                                 title="Synthetic", body="synthetic")["id"])
        entries.batch_add_entry_links(db, case_id=case, entry_id=finding, current_user=user, rationale="t",
                                      links=[single] + bulk)
        dossier = uuid.UUID(dossier_service.create_dossier(db, case_id=case, user=user,
                                                          data={"display_name": "Synthetic"})["id"])
        first = dossier_service.add_links(db, dossier_id=dossier, user=user, links=[single] + bulk)
        again = dossier_service.add_links(db, dossier_id=dossier, user=user, links=[single] + bulk)
        interview = dossier_service.create_interview(db, dossier_id=dossier, user=user,
                                                     data={"evidence_links": [single] + bulk})
        stored = {
            "finding": [(lk["target_type"], lk["target_id"], lk["source_anchor"]) for lk in entries.get_entry(
                db, case_id=case, entry_id=finding)["links"]],
            "dossier": [(lk["target_type"], lk["target_id"], lk["source_anchor"]) for lk in dossier_service.get_dossier(
                db, dossier_id=dossier, user=user)["links"]],
            "interview": [(lk["target_type"], lk["target_id"], lk.get("source_anchor") or {})
                          for lk in interview["evidence_links"]],
        }
    assert (first["added"], first["skipped"]) == (3, 0) and (again["added"], again["skipped"]) == (0, 3)
    for container, links in stored.items():
        assert sorted((tt, tid) for tt, tid, _ in links) == sorted(
            [("phone_analysis", kept["id"])] + [("phone_record", u) for u in uids]), container
        for tt, tid, anchor in links:
            if tt == "phone_analysis":   # phoneLinkHref opens /phone-analyses/<approach path>?kept=<id>
                assert anchor["kind"] == "analysis_result" and anchor["approach"] == "message_reconciliation", container
            else:                        # the record panel opens by record uid
                assert anchor["record_uid"] == tid, container

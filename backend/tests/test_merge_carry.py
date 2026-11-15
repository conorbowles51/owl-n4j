"""After a graph merge, theory and finding links and saved groups follow the merged entity, keeping what each held,
and the merged entity says what it was merged from (lx-theorycase D). SQLite on the theory fixture."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from postgres.base import Base
from postgres.models.case_selection import CaseSelection
from postgres.models.collection_membership import CollectionMembership
from postgres.models.graph_recycle_bin import GraphRecycleBinItem
from postgres.models.merge_job import MergeJob
from postgres.models.theory_narrative import TheoryNarrative
from postgres.models.workspace_entry import WorkspaceEntryLink
from services import merge_carry, theory_additions as T
from services.workspace_entry_service import create_entry, get_entry
from tests import test_theory_additions as base

MERGED = "person:ann-smith"


class MergeCarryTests(base.TheoryAdditionTests):
    # The fixture of TheoryAdditionTests, without running its tests a second time here.
    locals().update({name: None for name in dir(base.TheoryAdditionTests) if name.startswith("test_")})

    def setUp(self):
        super().setUp()
        # Both tables hold Postgres JSONB: copies with JSON for SQLite, as tests/test_deleted_items_bin.py does.
        from sqlalchemy import JSON, MetaData
        from postgres.models.case import Case
        from postgres.models.user import User
        copy = MetaData()
        Case.__table__.to_metadata(copy)
        User.__table__.to_metadata(copy)
        recycle = GraphRecycleBinItem.__table__.to_metadata(copy)
        recycle.c.snapshot.type = JSON()
        merges = MergeJob.__table__.to_metadata(copy)
        merges.c.source_entity_keys.type = JSON()
        merges.c.recycled_source_keys.type = JSON()
        copy.create_all(self.engine, tables=[recycle, merges])
        self.graph[str(self.case.id)].add(MERGED)
        for key, name in (("person:ann", "Ann"), ("person:bob", "A. Smith")):
            self.db.add(GraphRecycleBinItem(case_id=self.case.id, recycle_key=f"r-{key}", original_key=key,
                                            original_name=name, reason="merged", deleted_at=datetime.now(timezone.utc)))
        self.db.commit()

    def carry(self):
        job = MergeJob(id=uuid.uuid4(), case_id=self.case.id, source_entity_keys=["person:ann", "person:bob"],
                       merged_entity_key=MERGED, status="completed", created_by="Investigator")
        self.db.add(job)
        self.db.flush()
        counts = merge_carry.carry_casework_after_merge(self.db, case_id=self.case.id,
                                                        source_entity_keys=["person:ann", "person:bob"],
                                                        merged_entity_key=MERGED, merge_job_id=job.id)
        self.db.commit()
        return counts, job

    def test_a_theory_link_follows_the_merged_entity_keeping_its_reason_relationship_and_narrative(self):
        added = self.add(surface="graph", relationship="supports", why="the hub", narrative="Ann receives it all",
                         items=[{"target_type": "graph_entity", "target_id": "person:ann", "target_label": "Ann"}])
        counts, job = self.carry()
        self.assertEqual(counts["links_moved"], 1)
        link = self.db.get(WorkspaceEntryLink, uuid.UUID(added["added_link_ids"][0]))
        self.assertEqual((link.target_id, link.relationship_type), (MERGED, "supports"))
        self.assertEqual(link.link_metadata["merged_from"][0]["key"], "person:ann")
        self.assertEqual(link.link_metadata["merged_from"][0]["name"], "Ann")
        self.assertEqual(link.link_metadata["merged_from"][0]["merge_job_id"], str(job.id))
        addition = {a["link_id"]: a for a in self.reading()["additions"]}[str(link.id)]
        self.assertEqual((addition["why"], addition["narrative"]["text"]), ("the hub", "Ann receives it all"))

    def test_two_sources_in_one_finding_fold_into_one_link_and_no_narrative_is_lost(self):
        finding = create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="finding",
                               title="F", body="b")
        a = T.add(self.db, case_id=self.case.id, entry_id=finding["id"], user=self.user, surface="graph",
                  narrative="first", items=[{"target_type": "graph_entity", "target_id": "person:ann"}])
        b = T.add(self.db, case_id=self.case.id, entry_id=finding["id"], user=self.user, surface="graph",
                  relationship="contradicts", why="second reason", narrative="second",
                  items=[{"target_type": "graph_entity", "target_id": "person:bob"}])
        counts, _ = self.carry()
        self.assertEqual((counts["links_moved"], counts["links_folded"]), (1, 1))
        links = get_entry(self.db, case_id=self.case.id, entry_id=uuid.UUID(finding["id"]))["links"]
        self.assertEqual([l["target_id"] for l in links], [MERGED])
        merged_from = links[0]["metadata"]["merged_from"]
        self.assertEqual([(m["key"], m["relationship"]) for m in merged_from],
                         [("person:ann", "unclassified"), ("person:bob", "contradicts")])
        self.assertEqual(merged_from[1]["why"], "second reason")
        texts = sorted(self.db.scalars(select(TheoryNarrative.text).where(
            TheoryNarrative.entry_id == uuid.UUID(finding["id"]))))
        self.assertEqual(texts, ["first", "second"])
        self.assertIsNone(self.db.get(WorkspaceEntryLink, uuid.UUID(b["added_link_ids"][0])))
        self.assertEqual(links[0]["id"], a["added_link_ids"][0])

    def test_a_saved_group_holds_the_merged_entity_once_and_its_index_follows(self):
        grp = self.group("graph_selection", [{"type": "graph_entity", "id": "person:ann", "label": "Ann"},
                                             {"type": "graph_entity", "id": "company:acme", "label": "Acme"},
                                             {"type": "graph_entity", "id": "person:bob", "label": "Bob"}],
                         {"selection": "lasso"}, "Ann, Acme and Bob", "graph")
        counts, _ = self.carry()
        self.assertEqual(counts["groups"], 1)
        row = self.db.get(CaseSelection, uuid.UUID(grp["group"]["id"]))
        self.assertEqual([m["id"] for m in row.members], [MERGED, "company:acme"])
        self.assertEqual(row.member_count, 2)
        self.assertEqual([m["key"] for m in row.members[0]["merged_from"]], ["person:ann", "person:bob"])
        index = sorted(self.db.scalars(select(CollectionMembership.record_id).where(
            CollectionMembership.link_id == uuid.UUID(grp["added_link_ids"][0]))))
        self.assertEqual(index, ["graph_entity:company:acme", f"graph_entity:{MERGED}"])

    def test_the_merged_entity_says_what_it_was_merged_from(self):
        _, job = self.carry()
        merges = merge_carry.lineage(self.db, case_id=self.case.id, entity_key=MERGED)
        self.assertEqual(len(merges), 1)
        self.assertEqual(merges[0]["sources"], [{"key": "person:ann", "name": "Ann"},
                                                {"key": "person:bob", "name": "A. Smith"}])
        self.assertEqual((merges[0]["by"], merges[0]["merge_job_id"]), ("Investigator", str(job.id)))
        self.assertEqual(merge_carry.lineage(self.db, case_id=self.case.id, entity_key="person:ann"), [])

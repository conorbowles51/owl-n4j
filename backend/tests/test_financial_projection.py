"""Tests for :mod:`services.financial.projection`.

Five things these tests exist to hold, beyond the obvious one that admitted
rows get drawn.

**That direction is structural, and the two directions stay opposite.**  This
is the failure mode with no downstream detector.  A debit drawn as a credit
still balances: every period still reconciles, every total still foots, every
check digit still passes, because reversing an edge in Neo4j changes nothing in
Postgres, where the arithmetic lives.  The graph simply says the money went the
other way.  So the orientation is asserted by endpoint label *and* by which end
the account sits on, in both directions, and never inferred from the fact that
a ``TRANSFERRED_TO`` edge exists.

**That the same ledger state produces the same plan, byte for byte.**  The
retraction predicate is ``projection_digest <> $digest``, so a digest that
moves when the ledger has not moved does not merely churn -- it deletes and
redraws the entire case on every run, and a digest that fails to move when the
ledger *has* moved leaves withdrawn evidence in the graph.  Determinism is
therefore tested against input order, against dict iteration, and against
repetition, and the digest is tested for movement on every field that a reader
could be shown.

**That refusal is loud.**  A projection that silently omits a row produces a
total nobody can check.  Every path that declines to draw something -- a
quarantined document, an unknown account, an unparseable direction, a shared
``ref_id`` -- is asserted to produce both the omission *and* the record of it,
because a test that only asserted the omission would pass against a module that
dropped rows without saying so.

**That folding a duplicate is not the same as losing one.**  ``sha256`` is
unique on a document's bytes, not on the ``financial_source_documents`` row, so
one file ingested twice is two admitted rows reaching one content-addressed
node.  Folding them is correct; doing it quietly is not.  The tests hold that
the fold happens, that it is reported, that the transactions of *both* rows
still reach the surviving node, and that which row survives does not depend on
the order the rows arrived in.

**That the projection never writes what a person owns.**  The graph is a view
of the ledger, but analysts also edit it.  ``SET n += $props`` touches only the
keys it mentions, and the set of keys the projection mentions is asserted to be
disjoint from :data:`~services.financial.projection.USER_OWNED_PROPERTIES` --
so a later refactor that adds a property cannot silently start overwriting
someone's work.
"""

from __future__ import annotations

import itertools
import json
import unittest
import uuid
from datetime import date

from postgres.models.enums import DocumentStatus, LedgerStatus, TransactionDirection
from services.financial import projection
from services.financial.projection import (
    DEFAULT_BATCH_SIZE,
    DIGEST_PROPERTY,
    EVIDENCE_SOURCE_TYPES,
    FINANCIAL_MODEL_VERSION,
    LABEL_ACCOUNT,
    LABEL_DOCUMENT,
    LABEL_PERIOD,
    LABEL_TRANSACTION,
    PROJECTED_FLAG,
    PROJECTED_LABELS,
    PROJECTED_RELATIONSHIPS,
    PROJECTION_VERSION,
    REL_APPEARS_IN,
    REL_COVERS,
    REL_READ_FROM,
    REL_TRANSFERRED_TO,
    USER_OWNED_PROPERTIES,
    ProjectedAccount,
    ProjectedDocument,
    ProjectedPeriod,
    ProjectedTransaction,
    ProjectionError,
    account_key,
    document_key,
    evidence_source_type_for,
    interpret_preflight,
    project_case,
    transaction_key,
)

DEBIT = TransactionDirection.debit.value
CREDIT = TransactionDirection.credit.value

CASE = uuid.UUID(int=7)


def oid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def make_account(n: int = 1, identity_key: str = "chase:****1234", **kw) -> ProjectedAccount:
    fields = dict(holder_name="Blue River LLC", currency="USD",
                  institution_name="Chase", identifier_as_printed="****1234")
    fields.update(kw)
    return ProjectedAccount(account_id=oid(n), identity_key=identity_key, **fields)


def make_document(n: int = 2, sha: str | None = None, **kw) -> ProjectedDocument:
    fields = dict(
        document_type="camt.053", proof_class="p0", extraction_layer=0,
        parser_name="camt053", parser_version="1",
        status=DocumentStatus.admitted.value, original_filename="march.xml",
    )
    fields.update(kw)
    return ProjectedDocument(
        document_id=oid(n), sha256_at_ingestion=sha or (f"{n:x}" * 64)[:64], **fields
    )


def make_period(n: int = 3, document: int = 2, account: int = 1, **kw) -> ProjectedPeriod:
    fields = dict(
        currency="USD", period_start=date(2024, 3, 1), period_end=date(2024, 3, 31),
        opening_balance_minor=100000, closing_balance_minor=150000,
        reconciliation_status="balanced", delta_minor=0,
    )
    fields.update(kw)
    return ProjectedPeriod(
        period_id=oid(n), source_document_id=oid(document), account_id=oid(account), **fields
    )


def make_transaction(n: int, ref_id: str, *, direction: str = DEBIT, amount_minor: int = 50000,
                     account: int = 1, document: int = 2, **kw) -> ProjectedTransaction:
    fields = dict(
        currency="USD", ordering_date=date(2024, 3, 5), ordering_date_source="value",
        proof_class="p0", extraction_layer=0,
        ledger_status=LedgerStatus.admitted.value,
        content_hash=("b" * 64), row_index=n, description=f"PAYMENT {n}",
    )
    fields.update(kw)
    return ProjectedTransaction(
        transaction_id=oid(n), ref_id=ref_id, account_id=oid(account),
        source_document_id=oid(document), amount_minor=amount_minor,
        direction=direction, **fields
    )


def project(transactions=(), *, accounts=None, documents=None, periods=(), **kw):
    return project_case(
        CASE,
        accounts=list(accounts if accounts is not None else [make_account()]),
        documents=list(documents if documents is not None else [make_document()]),
        periods=list(periods),
        transactions=list(transactions),
        **kw,
    )


def nodes_labelled(plan, label):
    return [node for node in plan.nodes if node.label == label]


def edges_typed(plan, rel_type):
    return [edge for edge in plan.edges if edge.type == rel_type]


class DirectionIsStructural(unittest.TestCase):
    """The four lines the module exists for."""

    def test_debit_leaves_the_account(self):
        plan = project([make_transaction(11, "TX-AAAA-AAAA-AAAA", direction=DEBIT)])
        edge, = edges_typed(plan, REL_TRANSFERRED_TO)
        self.assertEqual(edge.start_label, LABEL_ACCOUNT)
        self.assertEqual(edge.end_label, LABEL_TRANSACTION)
        self.assertEqual(edge.start_key, account_key("chase:****1234"))
        self.assertEqual(edge.end_key, "TX-AAAA-AAAA-AAAA")

    def test_credit_arrives_at_the_account(self):
        plan = project([make_transaction(11, "TX-AAAA-AAAA-AAAA", direction=CREDIT)])
        edge, = edges_typed(plan, REL_TRANSFERRED_TO)
        self.assertEqual(edge.start_label, LABEL_TRANSACTION)
        self.assertEqual(edge.end_label, LABEL_ACCOUNT)
        self.assertEqual(edge.start_key, "TX-AAAA-AAAA-AAAA")
        self.assertEqual(edge.end_key, account_key("chase:****1234"))

    def test_the_two_directions_are_exact_reverses(self):
        """Not merely different: reversed.

        A module that drew credits with a different *relationship type* would
        pass both tests above and still be wrong, because the reader resolves
        ``from_entity`` and ``to_entity`` over a fixed set of types.
        """
        debit, = edges_typed(project([make_transaction(11, "TX-A", direction=DEBIT)]),
                             REL_TRANSFERRED_TO)
        credit, = edges_typed(project([make_transaction(11, "TX-A", direction=CREDIT)]),
                              REL_TRANSFERRED_TO)
        self.assertEqual(debit.type, credit.type)
        self.assertEqual((debit.start_label, debit.start_key), (credit.end_label, credit.end_key))
        self.assertEqual((debit.end_label, debit.end_key), (credit.start_label, credit.start_key))

    def test_the_reader_resolves_the_account_on_the_expected_side(self):
        """``TRANSFERRED_TO`` is one of the types the reader follows.

        ``get_financial_transactions`` matches
        ``(from_entity)-[:TRANSFERRED_TO|SENT_TO|PAID_TO|ISSUED_TO]->(n)`` and
        ``(n)-[:TRANSFERRED_TO|...]->(to_entity)``.  If the projection ever
        emitted a type outside that set the edge would be drawn and the reader
        would show no counterparty at all.
        """
        self.assertIn(REL_TRANSFERRED_TO,
                      {"TRANSFERRED_TO", "SENT_TO", "PAID_TO", "ISSUED_TO"})

    def test_direction_is_carried_on_the_edge_as_well_as_in_the_shape(self):
        for direction in (DEBIT, CREDIT):
            with self.subTest(direction=direction):
                plan = project([make_transaction(11, "TX-A", direction=direction)])
                edge, = edges_typed(plan, REL_TRANSFERRED_TO)
                self.assertEqual(edge.properties["direction"], direction)

    def test_direction_also_appears_on_the_node_for_a_human_reader(self):
        plan = project([make_transaction(11, "TX-A", direction=CREDIT)])
        node, = nodes_labelled(plan, LABEL_TRANSACTION)
        self.assertEqual(node.properties["direction"], CREDIT)

    def test_reversing_a_direction_moves_the_digest(self):
        a = project([make_transaction(11, "TX-A", direction=DEBIT)])
        b = project([make_transaction(11, "TX-A", direction=CREDIT)])
        self.assertNotEqual(a.digest, b.digest)


class Determinism(unittest.TestCase):
    """Same ledger state, same plan -- or retraction eats the case every run."""

    def _rows(self):
        return [
            make_transaction(11, "TX-AAAA-BBBB-CCCC", direction=DEBIT),
            make_transaction(12, "TX-DDDD-EEEE-FFFF", direction=CREDIT, amount_minor=100000),
            make_transaction(13, "TX-GGGG-HHHH-JJJJ", direction=DEBIT, amount_minor=999),
        ]

    def test_repeating_the_projection_reproduces_it_exactly(self):
        first, second = project(self._rows()), project(self._rows())
        self.assertEqual(first.digest, second.digest)
        self.assertEqual([s.cypher for s in first.statements],
                         [s.cypher for s in second.statements])
        self.assertEqual([dict(s.parameters) for s in first.statements],
                         [dict(s.parameters) for s in second.statements])
        self.assertEqual([s.purpose for s in first.statements],
                         [s.purpose for s in second.statements])

    def test_input_order_does_not_reach_the_output(self):
        digests, cyphers = set(), set()
        for order in itertools.permutations(self._rows()):
            plan = project(order)
            digests.add(plan.digest)
            cyphers.add(json.dumps([s.cypher for s in plan.statements]))
        self.assertEqual(len(digests), 1)
        self.assertEqual(len(cyphers), 1)

    def test_node_and_edge_order_is_fixed(self):
        keys = [[(n.label, n.key) for n in project(order).nodes]
                for order in itertools.permutations(self._rows())]
        self.assertEqual(len(set(map(tuple, keys))), 1)

    def test_the_digest_is_over_the_plan_not_the_clock(self):
        """No timestamp, no uuid4, no run token anywhere in the payload."""
        plan = project(self._rows())
        self.assertEqual(plan.digest, project(self._rows()).digest)
        self.assertEqual(len(plan.digest), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in plan.digest))

    def test_two_cases_projecting_nothing_do_not_share_a_digest(self):
        """An empty plan has no nodes to carry the case id, so it is hashed."""
        one = project_case(uuid.UUID(int=1), accounts=[], documents=[], transactions=[])
        two = project_case(uuid.UUID(int=2), accounts=[], documents=[], transactions=[])
        self.assertTrue(one.is_empty and two.is_empty)
        self.assertNotEqual(one.digest, two.digest)

    def test_every_property_value_is_a_json_scalar(self):
        """The canonical form has no ``default=``, so a stray ``date`` raises.

        Asserted directly as well, because a type that happened to serialise
        would still be free to serialise differently on another interpreter.
        """
        plan = project(self._rows(), periods=[make_period()])
        for carrier in (*plan.nodes, *plan.edges):
            for name, value in carrier.properties.items():
                with self.subTest(key=name):
                    self.assertIsInstance(value, (str, int, bool, type(None)),
                                          f"{name!r} is {type(value).__name__}")

    def test_digest_moves_for_every_field_a_reader_could_be_shown(self):
        base = make_transaction(11, "TX-AAAA-BBBB-CCCC")
        baseline = project([base]).digest
        variants = {
            "amount": dict(amount_minor=50001),
            "currency": dict(currency="EUR"),
            "description": dict(description="SOMETHING ELSE"),
            "ordering_date": dict(ordering_date=date(2024, 3, 6)),
            "counterparty": dict(counterparty_raw="ACME HOLDINGS LTD"),
            "bank_reference": dict(bank_reference="REF-9"),
            "proof_class": dict(proof_class="p1"),
            "extraction_layer": dict(extraction_layer=1),
            "row_index": dict(row_index=99),
            "content_hash": dict(content_hash="c" * 64),
            "running_balance": dict(running_balance_minor=12345),
            "value_date": dict(value_date=date(2024, 3, 7)),
        }
        for name, override in variants.items():
            with self.subTest(field=name):
                moved = project([make_transaction(11, "TX-AAAA-BBBB-CCCC", **override)])
                self.assertNotEqual(baseline, moved.digest, f"{name} did not move the digest")

    def test_batching_does_not_change_the_digest(self):
        rows = [make_transaction(100 + i, f"TX-{i:04d}-0000-0000") for i in range(7)]
        whole = project(rows)
        split = project(rows, batch_size=2)
        self.assertEqual(whole.digest, split.digest)
        self.assertEqual([n.key for n in whole.nodes], [n.key for n in split.nodes])


class Retraction(unittest.TestCase):
    """What the digest is for."""

    def test_withdrawing_a_row_moves_the_digest(self):
        both = project([make_transaction(11, "TX-A"), make_transaction(12, "TX-B")])
        one = project([make_transaction(11, "TX-A")])
        self.assertNotEqual(both.digest, one.digest)

    def test_a_superseded_row_projects_identically_to_an_absent_one(self):
        """The load-bearing equality.

        Supersession must leave the graph in exactly the state it would have
        been in had the row never existed -- not merely in *some* new state, or
        the retraction would delete the row and then draw it again.
        """
        absent = project([make_transaction(11, "TX-A")])
        superseded = project([
            make_transaction(11, "TX-A"),
            make_transaction(12, "TX-B", ledger_status=LedgerStatus.superseded.value),
        ])
        self.assertEqual(absent.digest, superseded.digest)
        self.assertEqual([n.key for n in absent.nodes], [n.key for n in superseded.nodes])

    def test_quarantined_and_rejected_rows_are_not_drawn(self):
        for status in (LedgerStatus.quarantined.value, LedgerStatus.rejected.value,
                       LedgerStatus.superseded.value):
            with self.subTest(status=status):
                plan = project([make_transaction(11, "TX-A", ledger_status=status)])
                self.assertEqual(nodes_labelled(plan, LABEL_TRANSACTION), [])
                self.assertEqual(len(plan.refusals), 1)
                self.assertIn(status, plan.refusals[0].reason)

    def test_retraction_is_scoped_by_case_and_by_digest(self):
        plan = project([make_transaction(11, "TX-A")])
        retractions = [s for s in plan.statements if s.purpose.startswith("retract")]
        self.assertTrue(retractions)
        for statement in retractions:
            with self.subTest(purpose=statement.purpose):
                self.assertIn("$case_id", statement.cypher)
                self.assertIn(f"{DIGEST_PROPERTY} <> $digest", statement.cypher)
                self.assertIn(f"{PROJECTED_FLAG} = true", statement.cypher)
                self.assertEqual(statement.parameters["digest"], plan.digest)
                self.assertEqual(statement.parameters["case_id"], str(CASE))

    def test_retraction_takes_a_constant_number_of_parameters(self):
        """The reason it is a digest and not a list of keys to keep."""
        small = project([make_transaction(11, "TX-A")])
        large = project([make_transaction(100 + i, f"TX-{i:04d}") for i in range(50)])
        for plan in (small, large):
            for statement in plan.statements:
                if statement.purpose.startswith("retract"):
                    self.assertEqual(set(statement.parameters), {"case_id", "digest"})

    def test_retraction_only_ever_names_a_type_the_projection_draws(self):
        """An untyped ``MATCH ()-[r]->()`` would also delete analyst edges."""
        plan = project([make_transaction(11, "TX-A")])
        for statement in plan.statements:
            if statement.purpose.startswith("retract") and "relationships" in statement.purpose:
                named = [r for r in PROJECTED_RELATIONSHIPS if f"[r:{r}]" in statement.cypher]
                self.assertEqual(len(named), 1, statement.cypher)

    def test_every_projected_relationship_type_is_retracted(self):
        plan = project([make_transaction(11, "TX-A")])
        retracted = {r for r in PROJECTED_RELATIONSHIPS
                     for s in plan.statements
                     if s.purpose.startswith("retract") and f"[r:{r}]" in s.cypher}
        self.assertEqual(retracted, set(PROJECTED_RELATIONSHIPS))

    def test_every_projected_label_is_retracted(self):
        plan = project([make_transaction(11, "TX-A")])
        retracted = {label for label in PROJECTED_LABELS
                     for s in plan.statements
                     if s.purpose.startswith("retract") and f"(n:{label} " in s.cypher}
        self.assertEqual(retracted, set(PROJECTED_LABELS))

    def test_an_empty_projection_retracts_and_draws_nothing(self):
        """The loaded gun, documented and asserted.

        A caller whose query silently returned nothing erases the case.  The
        module's contract is that this is *visible*: ``is_empty`` is true and
        ``transaction_count`` is zero, so the caller can refuse to apply it.
        """
        plan = project([])
        self.assertTrue(plan.is_empty)
        self.assertEqual(plan.transaction_count, 0)
        self.assertEqual(plan.nodes, ())
        self.assertEqual(plan.edges, ())
        self.assertTrue(plan.statements)
        self.assertTrue(all(s.purpose.startswith("retract") for s in plan.statements))
        self.assertEqual(len(plan.statements),
                         len(PROJECTED_RELATIONSHIPS) + len(PROJECTED_LABELS))

    def test_the_digest_is_stamped_on_everything_it_will_be_compared_against(self):
        plan = project([make_transaction(11, "TX-A")], periods=[make_period()])
        for carrier in (*plan.nodes, *plan.edges):
            self.assertEqual(carrier.properties[DIGEST_PROPERTY], plan.digest)
            self.assertIs(carrier.properties[PROJECTED_FLAG], True)

    def test_the_digest_is_not_part_of_what_it_hashes(self):
        """Otherwise it could not be computed at all.

        Verified by recomputing the canonical form with the digest stripped and
        confirming it reproduces the digest that was stamped.
        """
        plan = project([make_transaction(11, "TX-A")], periods=[make_period()])
        import hashlib
        from dataclasses import replace

        bare_nodes = [replace(n, properties={k: v for k, v in n.properties.items()
                                             if k != DIGEST_PROPERTY}) for n in plan.nodes]
        bare_edges = [replace(e, properties={k: v for k, v in e.properties.items()
                                             if k != DIGEST_PROPERTY}) for e in plan.edges]
        recomputed = hashlib.sha256(
            projection._canonical(str(CASE), bare_nodes, bare_edges).encode("utf-8")
        ).hexdigest()
        self.assertEqual(recomputed, plan.digest)


class RefusalIsLoud(unittest.TestCase):
    """Nothing is dropped without a record of it."""

    def test_a_quarantined_document_takes_its_transactions_with_it(self):
        plan = project(
            [make_transaction(11, "TX-A", document=4)],
            documents=[make_document(2), make_document(4, status=DocumentStatus.quarantined.value)],
        )
        self.assertEqual(nodes_labelled(plan, LABEL_TRANSACTION), [])
        subjects = {(r.subject, r.subject_id) for r in plan.refusals}
        self.assertIn(("document", str(oid(4))), subjects)
        self.assertIn(("transaction", "TX-A"), subjects)

    def test_a_transaction_on_an_unknown_account_is_refused(self):
        plan = project([make_transaction(11, "TX-A", account=99)])
        self.assertEqual(nodes_labelled(plan, LABEL_TRANSACTION), [])
        self.assertEqual(len(plan.refusals), 1)
        self.assertIn("was not projected", plan.refusals[0].reason)

    def test_a_transaction_on_an_unknown_document_is_refused(self):
        plan = project([make_transaction(11, "TX-A", document=99)])
        self.assertEqual(nodes_labelled(plan, LABEL_TRANSACTION), [])
        self.assertEqual(len(plan.refusals), 1)

    def test_a_shared_ref_id_refuses_both_rows_rather_than_picking_one(self):
        """``MERGE`` would collapse them and one row would vanish untraced.

        It cannot happen legitimately -- ``content_hash`` carries an occurrence
        counter precisely so identical rows differ -- so it is a defect, and a
        defect that silently halves a total is worse than one that refuses.
        """
        plan = project([make_transaction(11, "TX-DUPE"), make_transaction(12, "TX-DUPE")])
        self.assertEqual(nodes_labelled(plan, LABEL_TRANSACTION), [])
        self.assertEqual(edges_typed(plan, REL_TRANSFERRED_TO), [])
        self.assertEqual(len([r for r in plan.refusals if r.subject_id == "TX-DUPE"]), 2)

    def test_a_shared_ref_id_does_not_take_unrelated_rows_with_it(self):
        plan = project([make_transaction(11, "TX-DUPE"), make_transaction(12, "TX-DUPE"),
                        make_transaction(13, "TX-FINE")])
        self.assertEqual([n.key for n in nodes_labelled(plan, LABEL_TRANSACTION)], ["TX-FINE"])

    def test_an_unknown_direction_is_refused_not_guessed(self):
        for bad in ("sideways", "DEBIT", "", "dr"):
            with self.subTest(direction=bad):
                plan = project([make_transaction(11, "TX-A", direction=bad)])
                self.assertEqual(nodes_labelled(plan, LABEL_TRANSACTION), [])
                self.assertEqual(len(plan.refusals), 1)
                self.assertIn("direction", plan.refusals[0].reason)

    def test_a_period_whose_document_was_refused_is_refused(self):
        plan = project(
            [],
            documents=[make_document(2, status=DocumentStatus.quarantined.value)],
            periods=[make_period(3, document=2)],
        )
        self.assertEqual(nodes_labelled(plan, LABEL_PERIOD), [])
        self.assertIn("period", {r.subject for r in plan.refusals})

    def test_refusals_are_ordered_deterministically(self):
        rows = [make_transaction(11, "TX-A", account=99),
                make_transaction(12, "TX-B", document=99),
                make_transaction(13, "TX-C", direction="sideways")]
        orders = {tuple((r.subject, r.subject_id, r.reason) for r in project(o).refusals)
                  for o in itertools.permutations(rows)}
        self.assertEqual(len(orders), 1)

    def test_a_refused_row_leaves_no_trace_in_any_statement(self):
        plan = project([make_transaction(11, "TX-GONE", ledger_status=LedgerStatus.rejected.value),
                        make_transaction(12, "TX-KEPT")])
        blob = json.dumps([[s.cypher, s.parameters] for s in plan.statements], default=str)
        self.assertNotIn("TX-GONE", blob)
        self.assertIn("TX-KEPT", blob)


class Folding(unittest.TestCase):
    """One file ingested twice is two ledger rows and one document."""

    def _two_ingestions(self):
        shared = "a" * 64
        docs = [make_document(2, sha=shared), make_document(3, sha=shared)]
        periods = [make_period(50, document=2), make_period(51, document=3)]
        txs = [make_transaction(11, "TX-A", document=2, statement_period_id=oid(50)),
               make_transaction(12, "TX-B", document=3, statement_period_id=oid(51))]
        return docs, periods, txs

    def test_two_rows_with_the_same_bytes_draw_one_document(self):
        docs, periods, txs = self._two_ingestions()
        plan = project(txs, documents=docs, periods=periods)
        self.assertEqual(len(nodes_labelled(plan, LABEL_DOCUMENT)), 1)

    def test_the_fold_is_reported(self):
        docs, periods, txs = self._two_ingestions()
        plan = project(txs, documents=docs, periods=periods)
        folded = [r for r in plan.refusals if "folded into" in r.reason]
        self.assertEqual({r.subject for r in folded}, {LABEL_DOCUMENT, LABEL_PERIOD})

    def test_transactions_from_both_rows_still_reach_the_surviving_node(self):
        """Folding must not cost evidence -- only a duplicate node."""
        docs, periods, txs = self._two_ingestions()
        plan = project(txs, documents=docs, periods=periods)
        self.assertEqual(len(nodes_labelled(plan, LABEL_TRANSACTION)), 2)
        read_from = {(e.start_key, e.end_key) for e in edges_typed(plan, REL_READ_FROM)}
        surviving = nodes_labelled(plan, LABEL_DOCUMENT)[0].key
        self.assertIn(("TX-A", surviving), read_from)
        self.assertIn(("TX-B", surviving), read_from)

    def test_which_row_survives_does_not_depend_on_input_order(self):
        docs, periods, txs = self._two_ingestions()
        digests, survivors = set(), set()
        for d in itertools.permutations(docs):
            for p in itertools.permutations(periods):
                for t in itertools.permutations(txs):
                    plan = project(t, documents=d, periods=p)
                    digests.add(plan.digest)
                    survivors.add(nodes_labelled(plan, LABEL_DOCUMENT)[0]
                                  .properties["ledger_document_id"])
        self.assertEqual(len(digests), 1)
        self.assertEqual(len(survivors), 1)

    def test_a_folded_node_does_not_leave_a_duplicate_edge_in_the_plan(self):
        docs, periods, txs = self._two_ingestions()
        plan = project(txs, documents=docs, periods=periods)
        keys = [e.edge_key for e in plan.edges]
        self.assertEqual(len(keys), len(set(keys)))

    def test_no_duplicate_node_identity_survives_into_the_merge_rows(self):
        docs, periods, txs = self._two_ingestions()
        plan = project(txs, documents=docs, periods=periods)
        seen = [(n.label, n.key) for n in plan.nodes]
        self.assertEqual(len(seen), len(set(seen)))
        for statement in plan.statements:
            rows = statement.parameters.get("rows")
            if rows and "key" in rows[0]:
                keys = [r["key"] for r in rows]
                self.assertEqual(len(keys), len(set(keys)))


class WhatIsWritten(unittest.TestCase):
    """The property contract with the reader and with the analyst."""

    def test_the_projection_never_writes_a_property_a_person_owns(self):
        plan = project([make_transaction(11, "TX-A")], periods=[make_period()])
        for carrier in (*plan.nodes, *plan.edges):
            overlap = set(carrier.properties) & USER_OWNED_PROPERTIES
            self.assertEqual(overlap, set(), f"{carrier} would overwrite {overlap}")

    def test_merges_add_properties_rather_than_replacing_the_node(self):
        """``SET n = $props`` would delete every analyst-authored property."""
        plan = project([make_transaction(11, "TX-A")])
        for statement in plan.statements:
            if statement.purpose.startswith("merge"):
                self.assertIn("+=", statement.cypher)
                self.assertNotIn("SET n = ", statement.cypher)
                self.assertNotIn("SET r = ", statement.cypher)

    def test_ledger_owned_properties_are_written_even_when_absent(self):
        """Explicitly null, so ``+=`` clears them rather than leaving them stale."""
        plan = project([make_transaction(11, "TX-A", counterparty_raw=None, bank_reference=None)])
        node, = nodes_labelled(plan, LABEL_TRANSACTION)
        self.assertIn("ledger_counterparty_raw", node.properties)
        self.assertIsNone(node.properties["ledger_counterparty_raw"])
        self.assertIn("bank_reference", node.properties)
        self.assertIsNone(node.properties["bank_reference"])

    def test_only_transactions_carry_an_amount(self):
        """The reader treats *any* node carrying ``amount`` as a transaction."""
        plan = project([make_transaction(11, "TX-A")], periods=[make_period()])
        for node in plan.nodes:
            with self.subTest(label=node.label):
                if node.label == LABEL_TRANSACTION:
                    self.assertIsNotNone(node.properties["amount"])
                else:
                    self.assertNotIn("amount", node.properties)

    def test_a_period_names_its_balances_for_what_they_are(self):
        plan = project([], periods=[make_period()])
        node, = nodes_labelled(plan, LABEL_PERIOD)
        self.assertEqual(node.properties["opening_balance"], "1000.00")
        self.assertEqual(node.properties["closing_balance"], "1500.00")

    def test_a_period_carries_no_name_so_it_stays_out_of_the_entity_picker(self):
        plan = project([], periods=[make_period()])
        node, = nodes_labelled(plan, LABEL_PERIOD)
        self.assertNotIn("name", node.properties)

    def test_an_account_always_carries_a_name_or_it_is_invisible(self):
        """``get_financial_entities`` selects on ``n.name IS NOT NULL``."""
        candidates = [
            make_account(holder_name="Blue River LLC"),
            make_account(holder_name=None),
            make_account(holder_name=None, identifier_as_printed=None),
            make_account(holder_name="   ", identifier_as_printed=None,
                         identifier_normalised=None, institution_name=None),
        ]
        for account in candidates:
            with self.subTest(account=account.holder_name):
                plan = project([make_transaction(11, "TX-A")], accounts=[account])
                node, = nodes_labelled(plan, LABEL_ACCOUNT)
                self.assertTrue(node.properties["name"])
                self.assertTrue(node.properties["name"].strip())

    def test_every_node_carries_exactly_one_label(self):
        """``labels(n)[0]`` in the reader is order-dependent."""
        plan = project([make_transaction(11, "TX-A")], periods=[make_period()])
        for node in plan.nodes:
            self.assertIn(node.label, PROJECTED_LABELS)
            self.assertNotIn(":", node.label)
        for statement in plan.statements:
            if statement.purpose.startswith("merge") and "MERGE (n:" in statement.cypher:
                head = statement.cypher.split("MERGE (n:")[1].split(" ")[0]
                self.assertNotIn(":", head)

    def test_a_transaction_carries_all_three_tags_the_reader_checks(self):
        """One untagged amount-bearing node puts the whole case in legacy mode."""
        plan = project([make_transaction(11, "TX-A")])
        node, = nodes_labelled(plan, LABEL_TRANSACTION)
        self.assertEqual(node.properties["financial_model_version"], FINANCIAL_MODEL_VERSION)
        self.assertEqual(node.properties["financial_view_mode"], "transaction")
        self.assertIs(node.properties["is_evidence_backed_transaction"], True)

    def test_provenance_survives_the_projection(self):
        plan = project([make_transaction(11, "TX-A")])
        node, = nodes_labelled(plan, LABEL_TRANSACTION)
        for name in ("ref_id", "proof_class", "extraction_layer", "source_document_id",
                     "ledger_content_hash", "ordering_date_source", "source_filename"):
            self.assertIn(name, node.properties)
        self.assertEqual(node.properties["ref_id"], "TX-A")
        self.assertEqual(node.properties["source_filename"], "march.xml")

    def test_dates_are_zero_padded_iso(self):
        """The reader compares ``n.date`` as a *string* and sorts on it."""
        plan = project([make_transaction(11, "TX-A", ordering_date=date(2024, 1, 2),
                                         value_date=date(2024, 11, 30))])
        node, = nodes_labelled(plan, LABEL_TRANSACTION)
        self.assertEqual(node.properties["date"], "2024-01-02")
        self.assertEqual(node.properties["value_date"], "2024-11-30")

    def test_dates_sort_lexicographically_in_calendar_order(self):
        rows = [make_transaction(10 + i, f"TX-{i}", ordering_date=d) for i, d in enumerate(
            [date(2024, 1, 2), date(2024, 1, 10), date(2024, 2, 1), date(2024, 12, 31)])]
        plan = project(rows)
        dates = [n.properties["date"] for n in nodes_labelled(plan, LABEL_TRANSACTION)]
        self.assertEqual(sorted(dates), sorted(dates, key=lambda s: tuple(map(int, s.split("-")))))

    def test_every_node_carries_the_projection_flag_and_version(self):
        plan = project([make_transaction(11, "TX-A")], periods=[make_period()])
        for carrier in (*plan.nodes, *plan.edges):
            self.assertIs(carrier.properties[PROJECTED_FLAG], True)
            self.assertEqual(carrier.properties["projection_version"], PROJECTION_VERSION)


class Money(unittest.TestCase):
    """Minor units are the evidence; the string is a rendering of it."""

    def test_a_two_exponent_currency_renders_ungrouped(self):
        plan = project([make_transaction(11, "TX-A", amount_minor=123456789)])
        node, = nodes_labelled(plan, LABEL_TRANSACTION)
        self.assertEqual(node.properties["amount"], "1234567.89")
        self.assertNotIn(",", node.properties["amount"])

    def test_a_three_exponent_currency_keeps_all_three_places(self):
        """And is why ``amount_minor`` is the authoritative property.

        ``FinancialService.safe_float`` applies ``round(value, 2)`` on read, so
        a reader shown ``amount`` alone loses the third place of a KWD figure.
        The projection writes the exact string *and* the integer, so the loss is
        the reader's to fix and the evidence is not destroyed on the way in.
        """
        plan = project([make_transaction(11, "TX-A", currency="KWD", amount_minor=1234567)])
        node, = nodes_labelled(plan, LABEL_TRANSACTION)
        self.assertEqual(node.properties["amount"], "1234.567")
        self.assertEqual(node.properties["amount_minor"], 1234567)
        self.assertNotEqual(round(float(node.properties["amount"]), 2), 1234.567)

    def test_a_zero_exponent_currency_has_no_decimal_point(self):
        plan = project([make_transaction(11, "TX-A", currency="JPY", amount_minor=5000)])
        node, = nodes_labelled(plan, LABEL_TRANSACTION)
        self.assertEqual(node.properties["amount"], "5000")

    def test_amount_minor_is_carried_unchanged(self):
        for minor in (0, 1, -1, 999999999999):
            with self.subTest(minor=minor):
                plan = project([make_transaction(11, "TX-A", amount_minor=minor)])
                node, = nodes_labelled(plan, LABEL_TRANSACTION)
                self.assertEqual(node.properties["amount_minor"], minor)

    def test_a_negative_amount_keeps_its_sign_in_the_rendering(self):
        plan = project([make_transaction(11, "TX-A", amount_minor=-50000)])
        node, = nodes_labelled(plan, LABEL_TRANSACTION)
        self.assertEqual(node.properties["amount"], "-500.00")


class SourceTypes(unittest.TestCase):
    """``evidence_source_type`` is closed; ``document_type`` is not."""

    def test_an_exact_member_of_the_vocabulary_passes_through(self):
        for value in sorted(EVIDENCE_SOURCE_TYPES):
            with self.subTest(value=value):
                self.assertEqual(evidence_source_type_for(value), value)

    def test_statement_formats_map_to_bank_statement(self):
        for value in ("camt.053", "CAMT053", "bai2", "BAI2", "mt940", "ofx", "qfx"):
            with self.subTest(value=value):
                self.assertEqual(evidence_source_type_for(value), "bank_statement")

    def test_nacha_is_not_called_a_bank_statement(self):
        """It is a payment origination file.

        Mapping it to ``bank_statement`` would put a file the bank never issued
        into evidence as a bank record, which is a factual error about the
        document rather than a display preference.
        """
        self.assertNotEqual(evidence_source_type_for("nacha"), "bank_statement")
        self.assertEqual(evidence_source_type_for("nacha"), "other")

    def test_an_unrecognised_type_is_other_rather_than_a_guess(self):
        for value in ("", None, "  ", "something_new", "spreadsheet"):
            with self.subTest(value=value):
                self.assertEqual(evidence_source_type_for(value), "other")

    def test_the_answer_is_always_inside_the_closed_vocabulary(self):
        for value in ("camt.053", "nacha", "invoice", "wibble", None):
            self.assertIn(evidence_source_type_for(value), EVIDENCE_SOURCE_TYPES)

    def test_the_transaction_takes_its_source_type_from_its_document(self):
        plan = project([make_transaction(11, "TX-A")],
                       documents=[make_document(2, document_type="invoice")])
        node, = nodes_labelled(plan, LABEL_TRANSACTION)
        self.assertEqual(node.properties["evidence_source_type"], "invoice")


class Keys(unittest.TestCase):
    """Derived from content, so re-ingestion does not orphan a node."""

    def test_a_transaction_is_keyed_on_its_citable_reference(self):
        self.assertEqual(transaction_key("TX-AAAA-BBBB-CCCC"), "TX-AAAA-BBBB-CCCC")

    def test_an_account_key_follows_identity_not_the_surrogate_id(self):
        one = project([make_transaction(11, "TX-A", account=1)],
                      accounts=[make_account(1, "chase:****1234")])
        two = project([make_transaction(11, "TX-A", account=8)],
                      accounts=[make_account(8, "chase:****1234")])
        self.assertEqual(nodes_labelled(one, LABEL_ACCOUNT)[0].key,
                         nodes_labelled(two, LABEL_ACCOUNT)[0].key)

    def test_a_document_key_follows_its_bytes(self):
        self.assertEqual(document_key("a" * 64), document_key("a" * 64))
        self.assertNotEqual(document_key("a" * 64), document_key("b" * 64))

    def test_different_identities_do_not_share_a_key(self):
        self.assertNotEqual(account_key("chase:****1234"), account_key("chase:****5678"))

    def test_keys_are_prefixed_so_a_reader_can_tell_them_apart(self):
        self.assertTrue(account_key("k").startswith("ACC-"))
        self.assertTrue(document_key("k").startswith("DOC-"))

    def test_an_unreachable_account_is_not_drawn(self):
        """A node the ledger does not support is a node nobody can cite."""
        plan = project([make_transaction(11, "TX-A", account=1)],
                       accounts=[make_account(1, "chase:****1234"),
                                 make_account(9, "wells:****9999")])
        self.assertEqual(len(nodes_labelled(plan, LABEL_ACCOUNT)), 1)
        self.assertEqual(nodes_labelled(plan, LABEL_ACCOUNT)[0].key,
                         account_key("chase:****1234"))

    def test_an_unreachable_document_is_not_drawn(self):
        plan = project([make_transaction(11, "TX-A", document=2)],
                       documents=[make_document(2), make_document(5)])
        self.assertEqual(len(nodes_labelled(plan, LABEL_DOCUMENT)), 1)


class Statements(unittest.TestCase):
    """Order is total, and it matters."""

    def _plan(self):
        return project([make_transaction(11, "TX-A", statement_period_id=oid(3))],
                       periods=[make_period(3)])

    def test_nodes_are_merged_before_edges(self):
        purposes = [s.purpose for s in self._plan().statements]
        last_node = max(i for i, p in enumerate(purposes) if p.startswith("merge ") and "-[" not in p)
        first_edge = min(i for i, p in enumerate(purposes) if "-[" in p)
        self.assertLess(last_node, first_edge)

    def test_retraction_comes_last(self):
        purposes = [s.purpose for s in self._plan().statements]
        first_retract = min(i for i, p in enumerate(purposes) if p.startswith("retract"))
        last_merge = max(i for i, p in enumerate(purposes) if p.startswith("merge"))
        self.assertLess(last_merge, first_retract)

    def test_relationships_are_retracted_before_nodes(self):
        """So the final ``DETACH DELETE`` sweeps analyst edges left dangling."""
        purposes = [s.purpose for s in self._plan().statements]
        last_rel = max(i for i, p in enumerate(purposes)
                       if p.startswith("retract") and "relationships" in p)
        first_node = min(i for i, p in enumerate(purposes)
                         if p.startswith("retract") and "nodes" in p)
        self.assertLess(last_rel, first_node)

    def test_every_statement_carries_its_own_parameters(self):
        """``execute_cypher_batch`` passes none, so the caller must not use it."""
        for statement in self._plan().statements:
            self.assertIsInstance(statement.parameters, dict)
            self.assertIn("case_id", statement.parameters)

    def test_no_projected_value_is_interpolated_into_cypher_text(self):
        """Interpolation would be injection through a bank statement."""
        plan = project([make_transaction(11, "TX-A", description="'); DROP ALL; //")])
        for statement in plan.statements:
            self.assertNotIn("DROP ALL", statement.cypher)
            self.assertNotIn("TX-A", statement.cypher)

    def test_both_endpoints_of_every_edge_merge_carry_a_label(self):
        """An unlabelled endpoint is a scan of every node in the database."""
        for statement in self._plan().statements:
            if "-[" in statement.purpose:
                self.assertIn("MATCH (a:", statement.cypher)
                self.assertIn("MATCH (b:", statement.cypher)

    def test_rows_are_chunked_at_the_batch_size(self):
        rows = [make_transaction(100 + i, f"TX-{i:04d}") for i in range(7)]
        plan = project(rows, batch_size=3)
        sizes = [len(s.parameters["rows"]) for s in plan.statements
                 if s.purpose.startswith("merge " + LABEL_TRANSACTION)]
        self.assertEqual(sizes, [3, 3, 1])

    def test_chunking_preserves_every_row_exactly_once(self):
        rows = [make_transaction(100 + i, f"TX-{i:04d}") for i in range(7)]
        plan = project(rows, batch_size=2)
        seen = [r["key"] for s in plan.statements
                if s.purpose.startswith("merge " + LABEL_TRANSACTION)
                for r in s.parameters["rows"]]
        self.assertEqual(sorted(seen), sorted(f"TX-{i:04d}" for i in range(7)))

    def test_a_batch_size_below_one_is_refused(self):
        for size in (0, -1):
            with self.subTest(size=size):
                with self.assertRaises(ProjectionError):
                    project([make_transaction(11, "TX-A")], batch_size=size)

    def test_the_default_batch_size_is_applied(self):
        rows = [make_transaction(1000 + i, f"TX-{i:05d}") for i in range(DEFAULT_BATCH_SIZE + 1)]
        plan = project(rows)
        sizes = [len(s.parameters["rows"]) for s in plan.statements
                 if s.purpose.startswith("merge " + LABEL_TRANSACTION)]
        self.assertEqual(sizes, [DEFAULT_BATCH_SIZE, 1])


class PeriodEdges(unittest.TestCase):
    """A period covers an account and was read from a document."""

    def test_a_period_is_drawn_with_both_its_edges(self):
        plan = project([], periods=[make_period()])
        self.assertEqual(len(edges_typed(plan, REL_COVERS)), 1)
        self.assertEqual(len(edges_typed(plan, REL_READ_FROM)), 1)

    def test_a_transaction_appears_in_its_period(self):
        plan = project([make_transaction(11, "TX-A", statement_period_id=oid(3))],
                       periods=[make_period(3)])
        edge, = edges_typed(plan, REL_APPEARS_IN)
        self.assertEqual(edge.start_key, "TX-A")
        self.assertEqual(edge.end_label, LABEL_PERIOD)

    def test_a_transaction_naming_an_undrawn_period_is_still_drawn(self):
        """The period is missing, not the transaction; losing the row would be worse."""
        plan = project([make_transaction(11, "TX-A", statement_period_id=oid(999))])
        self.assertEqual(len(nodes_labelled(plan, LABEL_TRANSACTION)), 1)
        self.assertEqual(edges_typed(plan, REL_APPEARS_IN), [])


class Preflight(unittest.TestCase):
    """Reproduces the reader's own legacy test, without deciding anything."""

    def test_a_fully_tagged_case_is_not_legacy(self):
        finding = interpret_preflight(10, 10)
        self.assertFalse(finding.uses_legacy)
        self.assertTrue(finding.provenance_will_survive_read)
        self.assertEqual(finding.untagged_amount_nodes, 0)

    def test_one_untagged_node_puts_the_whole_case_in_legacy_mode(self):
        finding = interpret_preflight(10, 9)
        self.assertTrue(finding.uses_legacy)
        self.assertFalse(finding.provenance_will_survive_read)
        self.assertEqual(finding.untagged_amount_nodes, 1)

    def test_an_empty_case_is_not_legacy(self):
        self.assertFalse(interpret_preflight(0, 0).uses_legacy)

    def test_missing_counts_read_as_zero(self):
        self.assertFalse(interpret_preflight(None, None).uses_legacy)


class PlanShape(unittest.TestCase):
    """What the caller is given to decide with."""

    def test_transaction_count_counts_only_transactions(self):
        plan = project([make_transaction(11, "TX-A"), make_transaction(12, "TX-B")],
                       periods=[make_period()])
        self.assertEqual(plan.transaction_count, 2)
        self.assertGreater(len(plan.nodes), 2)

    def test_transaction_count_excludes_refused_rows(self):
        plan = project([make_transaction(11, "TX-A"),
                        make_transaction(12, "TX-B",
                                         ledger_status=LedgerStatus.quarantined.value)])
        self.assertEqual(plan.transaction_count, 1)

    def test_the_plan_is_immutable(self):
        plan = project([make_transaction(11, "TX-A")])
        for field in (plan.statements, plan.nodes, plan.edges, plan.refusals):
            self.assertIsInstance(field, tuple)

    def test_the_case_id_is_carried_as_a_string(self):
        plan = project([make_transaction(11, "TX-A")])
        self.assertEqual(plan.case_id, str(CASE))
        for node in plan.nodes:
            self.assertEqual(node.properties["case_id"], str(CASE))


class NoDatabaseDependency(unittest.TestCase):
    """The module is pure, and stays that way."""

    def test_the_module_does_not_import_the_driver(self):
        """So it is testable without Neo4j, as ``linkage`` is without Postgres."""
        import sys
        self.assertNotIn("neo4j", {name.split(".")[0] for name in dir(projection)
                                   if not name.startswith("_")})
        with open(projection.__file__, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("import neo4j", source)
        self.assertNotIn("from neo4j", source)

    def test_nothing_is_written_by_building_a_plan(self):
        plan = project([make_transaction(11, "TX-A")])
        self.assertTrue(all(isinstance(s.cypher, str) for s in plan.statements))


class SetIterationOrderDoesNotReachThePlan(unittest.TestCase):
    """The rows arrive from Postgres in whatever order Postgres chose.

    ``reachable_accounts`` and ``reachable_documents`` are *sets*, and a set
    built from the same members in a different order does not always iterate
    the same way: when two members' hashes collide in the table, insertion
    order decides which comes out first.  ``uuid.UUID.__hash__`` is the hash of
    its integer, so ints 1 and 33 collide in a small table -- and two runs over
    the same ledger would then produce two different plans, two different
    digests, and a full delete-and-redraw of the case on every projection.

    These use colliding ids deliberately.  A test with ids 1 and 2 passes
    against ``for account_id in reachable_accounts`` and proves nothing.
    """

    def test_a_set_of_colliding_ids_really_does_iterate_by_insertion(self):
        """The premise, asserted, so the two tests below cannot quietly rot."""
        self.assertNotEqual(
            [u.int for u in {oid(1), oid(33)}],
            [u.int for u in {oid(33), oid(1)}],
        )

    def test_account_draw_order_survives_colliding_ids(self):
        accounts = [make_account(1, "acct:one"), make_account(33, "acct:two")]
        documents = [make_document(2)]
        forward = [make_transaction(11, "TX-A", account=1),
                   make_transaction(12, "TX-B", account=33)]
        backward = [make_transaction(12, "TX-B", account=33),
                    make_transaction(11, "TX-A", account=1)]

        first = project(forward, accounts=accounts, documents=documents)
        second = project(backward, accounts=accounts, documents=documents)

        self.assertEqual(
            [n.key for n in nodes_labelled(first, LABEL_ACCOUNT)],
            [n.key for n in nodes_labelled(second, LABEL_ACCOUNT)],
        )
        self.assertEqual(first.digest, second.digest)

    def test_document_draw_order_survives_colliding_ids(self):
        documents = [make_document(2, sha="c" * 64), make_document(34, sha="d" * 64)]
        forward = [make_transaction(11, "TX-A", document=2),
                   make_transaction(12, "TX-B", document=34)]
        backward = [make_transaction(12, "TX-B", document=34),
                    make_transaction(11, "TX-A", document=2)]

        first = project(forward, documents=documents)
        second = project(backward, documents=documents)

        self.assertEqual(
            [n.key for n in nodes_labelled(first, LABEL_DOCUMENT)],
            [n.key for n in nodes_labelled(second, LABEL_DOCUMENT)],
        )
        self.assertEqual(first.digest, second.digest)

    def test_the_edge_list_is_canonically_ordered(self):
        """Not merely deterministic: ordered by a rule the drawing cannot move.

        Edges happen to be appended in a fixed order today because the loops
        that draw them iterate sorted inputs.  The sort is what makes that an
        invariant rather than a coincidence, so a later change to the drawing
        order cannot silently move every digest in the system.
        """
        plan = project(
            [make_transaction(11, "TX-A", direction=DEBIT),
             make_transaction(12, "TX-B", direction=CREDIT)],
            periods=[make_period()],
        )
        self.assertEqual(
            list(plan.edges),
            sorted(plan.edges, key=lambda e: (e.type, e.start_label, e.end_label, e.edge_key)),
        )


class TheCanonicalForm(unittest.TestCase):
    """What the digest is taken over, tested directly.

    Some of these cannot be reached through :func:`project_case`, because the
    plan it builds is already well formed -- property maps are constructed in a
    fixed order, and an edge's key is derived from its endpoints.  That is the
    reason to test the serialiser itself: it is the thing that would have to
    stay correct if either of those ever stopped being true, and a digest that
    ignores a field it should cover is invisible until two different ledgers
    project to the same graph.
    """

    def _node(self, properties):
        return projection.GraphNode(LABEL_TRANSACTION, "TX-A", properties)

    def _edge(self, **kw):
        fields = dict(type=REL_TRANSFERRED_TO, edge_key="EK", start_label=LABEL_ACCOUNT,
                      start_key="ACC-1", end_label=LABEL_TRANSACTION, end_key="TX-A",
                      properties={"direction": DEBIT})
        fields.update(kw)
        return projection.GraphEdge(**fields)

    def test_equal_property_maps_serialise_identically_whatever_their_order(self):
        left = self._node({"a": 1, "b": 2, "c": 3})
        right = self._node({"c": 3, "b": 2, "a": 1})
        self.assertEqual(left.properties, right.properties)
        self.assertEqual(
            projection._canonical("case", [left], []),
            projection._canonical("case", [right], []),
        )

    def test_a_node_property_change_moves_the_serialisation(self):
        self.assertNotEqual(
            projection._canonical("case", [self._node({"amount": "1.00"})], []),
            projection._canonical("case", [self._node({"amount": "2.00"})], []),
        )

    def test_an_edge_property_change_moves_the_serialisation(self):
        self.assertNotEqual(
            projection._canonical("case", [], [self._edge(properties={"direction": DEBIT})]),
            projection._canonical("case", [], [self._edge(properties={"direction": CREDIT})]),
        )

    def test_an_edge_endpoint_change_moves_the_serialisation(self):
        self.assertNotEqual(
            projection._canonical("case", [], [self._edge(start_key="ACC-1")]),
            projection._canonical("case", [], [self._edge(start_key="ACC-2")]),
        )
        self.assertNotEqual(
            projection._canonical("case", [], [self._edge(end_label=LABEL_PERIOD)]),
            projection._canonical("case", [], [self._edge(end_label=LABEL_TRANSACTION)]),
        )

    def test_the_case_is_part_of_what_is_hashed(self):
        self.assertNotEqual(
            projection._canonical("case-a", [], []),
            projection._canonical("case-b", [], []),
        )

    def test_a_non_finite_number_raises_rather_than_hashing(self):
        """``NaN`` is not JSON, and ``Infinity`` is not the same on every reader.

        Property values are never floats by construction, so this is a guard
        rather than a path -- but a guard that silently emitted ``NaN`` would
        produce a digest no other implementation could reproduce.
        """
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                projection._canonical("case", [self._node({"amount": value})], [])

    def test_a_value_that_is_not_a_json_scalar_raises(self):
        with self.assertRaises(TypeError):
            projection._canonical("case", [self._node({"when": date(2024, 3, 1)})], [])


class KeysSeparateThingsThatAreNotTheSame(unittest.TestCase):
    """Every key guard, and every field a key must not ignore.

    A key that ignores a field it should carry does not fail -- it merges two
    different things into one node, and the graph then asserts a period, an
    account or a document that never existed.
    """

    def test_an_account_with_no_identity_cannot_be_keyed(self):
        with self.assertRaises(ProjectionError):
            account_key("")

    def test_a_document_with_no_bytes_cannot_be_keyed(self):
        with self.assertRaises(ProjectionError):
            document_key("")

    def test_a_transaction_with_no_reference_cannot_be_keyed(self):
        with self.assertRaises(ProjectionError):
            transaction_key("")

    def test_an_account_and_a_document_do_not_share_a_namespace(self):
        """The same string is not the same node in two different roles."""
        shared = "a" * 64
        self.assertNotEqual(account_key(shared), document_key(shared))

    def test_two_periods_in_one_document_are_told_apart_by_their_dates(self):
        doc, acc = document_key("a" * 64), account_key("k")
        march = projection.period_key(doc, acc, date(2024, 3, 1), date(2024, 3, 31))
        april = projection.period_key(doc, acc, date(2024, 4, 1), date(2024, 4, 30))
        self.assertNotEqual(march, april)
        self.assertNotEqual(
            march,
            projection.period_key(doc, acc, date(2024, 3, 1), date(2024, 4, 30)),
        )

    def test_two_accounts_on_one_statement_do_not_share_a_period(self):
        doc = document_key("a" * 64)
        self.assertNotEqual(
            projection.period_key(doc, account_key("k1"), date(2024, 3, 1), date(2024, 3, 31)),
            projection.period_key(doc, account_key("k2"), date(2024, 3, 1), date(2024, 3, 31)),
        )

    def test_one_account_on_two_statements_does_not_share_a_period(self):
        acc = account_key("k1")
        self.assertNotEqual(
            projection.period_key(document_key("a" * 64), acc, date(2024, 3, 1), date(2024, 3, 31)),
            projection.period_key(document_key("b" * 64), acc, date(2024, 3, 1), date(2024, 3, 31)),
        )

    def test_a_period_key_is_reproducible(self):
        args = (document_key("a" * 64), account_key("k"), date(2024, 3, 1), date(2024, 3, 31))
        self.assertEqual(projection.period_key(*args), projection.period_key(*args))

    def test_two_relationship_types_between_one_pair_do_not_share_an_edge_key(self):
        self.assertNotEqual(
            projection._edge_key(REL_READ_FROM, "TX-A", "DOC-1"),
            projection._edge_key(REL_APPEARS_IN, "TX-A", "DOC-1"),
        )

    def test_an_edge_key_follows_both_of_its_endpoints(self):
        base = projection._edge_key(REL_READ_FROM, "TX-A", "DOC-1")
        self.assertNotEqual(base, projection._edge_key(REL_READ_FROM, "TX-B", "DOC-1"))
        self.assertNotEqual(base, projection._edge_key(REL_READ_FROM, "TX-A", "DOC-2"))

    def test_an_edge_key_is_not_symmetric(self):
        """Because the two directions are the same pair drawn opposite ways."""
        self.assertNotEqual(
            projection._edge_key(REL_TRANSFERRED_TO, "ACC-1", "TX-A"),
            projection._edge_key(REL_TRANSFERRED_TO, "TX-A", "ACC-1"),
        )


class MoreRefusals(unittest.TestCase):
    """The refusal paths the first pass over these tests did not reach."""

    def test_a_period_on_an_unknown_account_is_refused(self):
        plan = project(periods=[make_period(account=99)])
        self.assertEqual([], nodes_labelled(plan, LABEL_PERIOD))
        self.assertTrue(any(r.subject == "period" and "account" in r.reason
                            for r in plan.refusals))

    def test_an_unknown_extraction_layer_is_refused_not_guessed(self):
        plan = project([make_transaction(11, "TX-A", extraction_layer=99)])
        self.assertEqual([], nodes_labelled(plan, LABEL_TRANSACTION))
        self.assertTrue(any("extraction_layer" in r.reason for r in plan.refusals))

    def test_an_unknown_proof_class_is_refused_not_guessed(self):
        plan = project([make_transaction(11, "TX-A", proof_class="p9")])
        self.assertEqual([], nodes_labelled(plan, LABEL_TRANSACTION))
        self.assertTrue(any("proof_class" in r.reason for r in plan.refusals))


class TheProjectionVersionIsPartOfTheDigest(unittest.TestCase):
    """So that changing how the graph is drawn redraws the graph.

    Without this, a release that changes a property name leaves every existing
    case carrying the old shape, matching on the old digest, and never
    retracted -- the one failure mode the digest exists to prevent, reintroduced
    by the upgrade itself.
    """

    def test_moving_the_version_moves_the_digest(self):
        plan = project([make_transaction(11, "TX-A")])
        original = projection.PROJECTION_VERSION
        try:
            projection.PROJECTION_VERSION = f"{original}-next"
            self.assertNotEqual(plan.digest, project([make_transaction(11, "TX-A")]).digest)
        finally:
            projection.PROJECTION_VERSION = original
        self.assertEqual(plan.digest, project([make_transaction(11, "TX-A")]).digest)

    def test_moving_the_version_moves_an_empty_plans_digest_too(self):
        """The version has to be in the canonical payload, not merely on a node.

        Every projected node carries ``projection_version`` as a property, so
        the test above would pass even if the digest never mentioned the version
        at all -- the property maps it hashes would carry it anyway.  An empty
        plan has no nodes, which is exactly where that accident stops covering
        for the real thing.

        This is the same argument the module makes for putting ``case_id`` in
        the payload: the empty case is the one that has nothing else to speak
        for it, and it is also the case a projection reaches the moment a matter
        is emptied -- the point at which a stale digest stops retracting.
        """
        empty = project([])
        self.assertTrue(empty.is_empty)
        self.assertEqual([], list(empty.nodes))
        original = projection.PROJECTION_VERSION
        try:
            projection.PROJECTION_VERSION = f"{original}-next"
            self.assertNotEqual(empty.digest, project([]).digest)
        finally:
            projection.PROJECTION_VERSION = original
        self.assertEqual(empty.digest, project([]).digest)


class WhichRowSurvivesAFold(unittest.TestCase):
    """Folding must pick a row by a rule, not by arrival.

    ``project_case`` sorts documents by ledger id and periods by
    ``(key, ledger id)`` before folding, so the surviving node always carries
    the lowest ledger id of the rows that collided.  Keeping the *last* row
    instead would be just as consistent within one run and would still fold to
    one node -- and would change the answer whenever Postgres changed its mind
    about row order.
    """

    def _two_documents_sharing_bytes(self):
        return [make_document(2, sha="a" * 64), make_document(3, sha="a" * 64)]

    def _one_row_each(self):
        """A transaction against each document, or the second is never reached.

        Only documents an admitted row actually touches are drawn, so a fold
        needs both rows to be reachable -- otherwise the test passes because
        nothing collided, which is not the same as passing.
        """
        return [make_transaction(11, "TX-A", document=2),
                make_transaction(12, "TX-B", document=3)]

    def test_the_setup_really_does_fold(self):
        plan = project(self._one_row_each(), documents=self._two_documents_sharing_bytes())
        self.assertEqual(1, len(nodes_labelled(plan, LABEL_DOCUMENT)))
        self.assertEqual(2, len(nodes_labelled(plan, LABEL_TRANSACTION)))

    def test_the_surviving_document_is_the_lowest_ledger_row(self):
        documents = self._two_documents_sharing_bytes()
        for order in itertools.permutations(documents):
            plan = project(self._one_row_each(), documents=list(order))
            kept = nodes_labelled(plan, LABEL_DOCUMENT)
            self.assertEqual(1, len(kept))
            self.assertEqual(str(oid(2)), kept[0].properties["ledger_document_id"])

    def test_the_fold_names_the_row_that_survived(self):
        plan = project(self._one_row_each(), documents=self._two_documents_sharing_bytes())
        folded = [r for r in plan.refusals if "folded into" in r.reason]
        self.assertEqual(1, len(folded))
        self.assertEqual(str(oid(3)), folded[0].subject_id)
        self.assertIn(str(oid(2)), folded[0].reason)

    def test_the_surviving_period_is_the_lowest_ledger_row(self):
        documents = self._two_documents_sharing_bytes()
        periods = [make_period(50, document=2), make_period(51, document=3)]
        for order in itertools.permutations(periods):
            plan = project(documents=documents, periods=list(order))
            kept = nodes_labelled(plan, LABEL_PERIOD)
            self.assertEqual(1, len(kept))
            self.assertEqual(str(oid(50)), kept[0].properties["ledger_period_id"])


if __name__ == "__main__":
    unittest.main()

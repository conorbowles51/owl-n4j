"""Tests for the camt.053 native parser.

No corpus document backs these.  The ET-Fraud corpus carries no camt.053, no
BAI2, no MT940 and no NACHA file — its XML is Cellebrite call and audio
forensics — so every fixture below is constructed from `12` §6.1 and the ISO
20022 message definition rather than measured from evidence.  That is a real
weakness and it is stated here rather than left for someone to discover: a
fixture built by the same reading of the specification as the parser shares the
parser's blind spots, and a misreading would produce a test that passes and a
parser that is wrong.  What these tests do establish is that the parser is
self-consistent, that it refuses what it cannot read, and that it never reaches
:attr:`ProofClass.p0` without arithmetic that closed.  What only a real file
from a real bank can establish is that the reading is right.

The suite is written against that limitation in two ways.  Every check is
asserted against a literal — never against the constant the code uses, which
would be a tautology — and the failure paths are tested at least as heavily as
the success path, because the failure paths are where a misreading of the
specification shows up as a document wrongly admitted rather than one wrongly
refused.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import warnings
from decimal import Decimal
from unittest import mock

from lxml import etree

from postgres.models.enums import (
    LocatorKind,
    ProofClass,
    ReconciliationStatus,
    TransactionDirection,
)
from services.financial.camt053 import (
    CAMT053_BALANCE_CLOSING_BOOKED,
    CAMT053_BALANCE_OPENING_BOOKED,
    CAMT053_BALANCE_PREVIOUSLY_CLOSED_BOOKED,
    CAMT053_MAX_DOCUMENT_BYTES,
    Camt053AmountError,
    Camt053Error,
    Camt053MalformedDocumentError,
    Camt053MissingElementError,
    NotACamt053Error,
    Camt053StatementCurrencyError,
    _hardened_parser,
    _reject_hostile_nodes,
    _weakest,
    parse_camt053,
)
from services.financial.money import Money
from services.financial.proof_class import SourceShape

NS_02 = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"
NS_08 = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"


# ---------------------------------------------------------------------------
# Fixture construction
# ---------------------------------------------------------------------------


def bal(code: str, amount: str, indicator: str = "CRDT", *, currency: str = "USD",
        date: str = "2026-02-01", proprietary: bool = False) -> str:
    tag = "Prtry" if proprietary else "Cd"
    return (
        f"<Bal><Tp><CdOrPrtry><{tag}>{code}</{tag}></CdOrPrtry></Tp>"
        f'<Amt Ccy="{currency}">{amount}</Amt>'
        f"<CdtDbtInd>{indicator}</CdtDbtInd>"
        f"<Dt><Dt>{date}</Dt></Dt></Bal>"
    )


def ntry(amount: str, indicator: str = "CRDT", *, status: str = "BOOK",
         currency: str = "USD", reference: str = "REF", details: str = "",
         status_form: str = "text", reversal: bool = False) -> str:
    if status_form == "text":
        status_xml = f"<Sts>{status}</Sts>" if status else ""
    elif status_form == "code":
        status_xml = f"<Sts><Cd>{status}</Cd></Sts>"
    elif status_form == "proprietary":
        status_xml = f"<Sts><Prtry>{status}</Prtry></Sts>"
    else:  # pragma: no cover - guards the fixture itself
        raise ValueError(status_form)
    reversal_xml = "<RvslInd>true</RvslInd>" if reversal else ""
    return (
        f'<Ntry><Amt Ccy="{currency}">{amount}</Amt>'
        f"<CdtDbtInd>{indicator}</CdtDbtInd>{status_xml}{reversal_xml}"
        f"<BookgDt><Dt>2026-02-10</Dt></BookgDt>"
        f"<ValDt><Dt>2026-02-11</Dt></ValDt>"
        f"<NtryRef>{reference}</NtryRef>{details}</Ntry>"
    )


def batch(total: str | None = "2500.00", count: int | None = 2,
          transactions: tuple[str, ...] = ("1500.00", "1000.00"),
          *, currency: str = "USD") -> str:
    parts = []
    if count is not None:
        parts.append(f"<NbOfTxs>{count}</NbOfTxs>")
    if total is not None:
        parts.append(f'<TtlAmt Ccy="{currency}">{total}</TtlAmt>')
    detail_xml = "".join(
        f'<TxDtls><Amt Ccy="{currency}">{amount}</Amt>'
        f"<Refs><EndToEndId>E2E-{index}</EndToEndId></Refs>"
        f"<RmtInf><Ustrd>Invoice {index}</Ustrd></RmtInf></TxDtls>"
        for index, amount in enumerate(transactions)
    )
    return f"<NtryDtls><Btch>{''.join(parts)}</Btch>{detail_xml}</NtryDtls>"


def summary(entries: int | None = 3, credits: str | None = "5000.00",
            credit_count: int | None = 2, debits: str | None = "2500.00",
            debit_count: int | None = 1, net: str | None = "2500.00",
            net_indicator: str | None = "CRDT") -> str:
    total_parts = []
    if entries is not None:
        total_parts.append(f"<NbOfNtries>{entries}</NbOfNtries>")
    if net is not None:
        total_parts.append(f"<TtlNetNtryAmt>{net}</TtlNetNtryAmt>")
    if net_indicator is not None:
        total_parts.append(f"<CdtDbtInd>{net_indicator}</CdtDbtInd>")
    blocks = f"<TtlNtries>{''.join(total_parts)}</TtlNtries>" if total_parts else ""
    if credits is not None or credit_count is not None:
        inner = ""
        if credit_count is not None:
            inner += f"<NbOfNtries>{credit_count}</NbOfNtries>"
        if credits is not None:
            inner += f"<Sum>{credits}</Sum>"
        blocks += f"<TtlCdtNtries>{inner}</TtlCdtNtries>"
    if debits is not None or debit_count is not None:
        inner = ""
        if debit_count is not None:
            inner += f"<NbOfNtries>{debit_count}</NbOfNtries>"
        if debits is not None:
            inner += f"<Sum>{debits}</Sum>"
        blocks += f"<TtlDbtNtries>{inner}</TtlDbtNtries>"
    return f"<TxsSummry>{blocks}</TxsSummry>"


DEFAULT_BALANCES = bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00") + bal(
    CAMT053_BALANCE_CLOSING_BOOKED, "12500.00", date="2026-02-28"
)
DEFAULT_ENTRIES = (
    ntry("3000.00", "CRDT", reference="E1")
    + ntry("2000.00", "CRDT", reference="E2")
    + ntry("2500.00", "DBIT", reference="E3")
)


def stmt(*, identification: str = "STMT-1", balances: str = DEFAULT_BALANCES,
         entries: str = DEFAULT_ENTRIES, transactions_summary: str = "",
         account: str | None = None) -> str:
    if account is None:
        account = (
            "<Acct><Id><IBAN>GB29NWBK60161331926819</IBAN></Id><Ccy>USD</Ccy>"
            "<Ownr><Nm>Marlow Holdings LLC</Nm></Ownr>"
            "<Svcr><FinInstnId><BIC>NWBKGB2L</BIC></FinInstnId></Svcr></Acct>"
        )
    return (
        f"<Stmt><Id>{identification}</Id><ElctrncSeqNb>42</ElctrncSeqNb>"
        f"<CreDtTm>2026-03-01T06:00:00+00:00</CreDtTm>"
        f"<FrToDt><FrDtTm>2026-02-01T00:00:00+00:00</FrDtTm>"
        f"<ToDtTm>2026-02-28T23:59:59+00:00</ToDtTm></FrToDt>"
        f"{account}{balances}{transactions_summary}{entries}</Stmt>"
    )


def build(*, statements: str | None = None, namespace: str = NS_02,
          group_header: str | None = None, envelope: bool = False,
          message_count: int = 1) -> bytes:
    """Assemble a camt.053 message from parts.  Returns bytes, as the parser wants."""
    if statements is None:
        statements = stmt()
    if group_header is None:
        group_header = (
            "<GrpHdr><MsgId>MSG-1</MsgId>"
            "<CreDtTm>2026-03-01T06:00:00+00:00</CreDtTm></GrpHdr>"
        )
    body = f"<BkToCstmrStmt>{group_header}{statements}</BkToCstmrStmt>" * message_count
    document = f'<Document xmlns="{namespace}">{body}</Document>'
    if envelope:
        document = (
            '<BizMsgEnvlp xmlns="urn:iso:std:iso:20022:tech:xsd:head.003.001.01">'
            "<Hdr><AppHdr><Fr>BANK</Fr></AppHdr></Hdr>"
            f"{document}</BizMsgEnvlp>"
        )
    return f'<?xml version="1.0" encoding="UTF-8"?>{document}'.encode("utf-8")


USD = "USD"


def usd(value: str) -> Money:
    return Money.from_decimal(Decimal(value), USD)


class Camt053TestCase(unittest.TestCase):
    """Base that turns lxml's element-truthiness warning into a failure.

    ``bool(element)`` is ``False`` for an element with no children, which is
    every leaf a camt.053 states a figure in.  A single ``a or b`` over two
    element lookups therefore discards a present ``<Amt>`` and reports the
    figure as absent — a defect that produces no exception and no wrong number,
    only a missing one.  lxml warns; this makes the warning fatal so that the
    pattern cannot re-enter the module without a test going red.
    """

    def setUp(self) -> None:
        context = warnings.catch_warnings()
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        warnings.simplefilter("error", FutureWarning)


# ---------------------------------------------------------------------------


class HappyPathTests(Camt053TestCase):
    def test_a_conformant_balanced_statement_reaches_p0(self):
        document = parse_camt053(build(statements=stmt(transactions_summary=summary())))

        self.assertEqual(document.reconciliation_status, ReconciliationStatus.balanced)
        self.assertEqual(document.proof_class, ProofClass.p0)
        self.assertEqual(document.source_shape, SourceShape.native_with_control_totals)

    def test_the_group_header_is_read(self):
        document = parse_camt053(build())
        self.assertEqual(document.message_identification, "MSG-1")
        self.assertEqual(document.creation_date_time, "2026-03-01T06:00:00+00:00")
        self.assertEqual(document.namespace, NS_02)

    def test_the_account_and_period_are_read(self):
        statement = parse_camt053(build()).statements[0]
        self.assertEqual(statement.identification, "STMT-1")
        self.assertEqual(statement.currency, "USD")
        self.assertEqual(statement.account.iban, "GB29NWBK60161331926819")
        self.assertEqual(statement.account.identifier, "GB29NWBK60161331926819")
        self.assertEqual(statement.account.owner_name, "Marlow Holdings LLC")
        self.assertEqual(statement.account.servicer_bic, "NWBKGB2L")
        self.assertEqual(statement.electronic_sequence_number, "42")
        self.assertEqual(statement.period_from, "2026-02-01T00:00:00+00:00")
        self.assertEqual(statement.period_to, "2026-02-28T23:59:59+00:00")

    def test_the_identity_arithmetic_is_exact(self):
        identity = parse_camt053(build()).statements[0].balance_identity

        self.assertEqual(identity.opening, usd("10000.00"))
        self.assertEqual(identity.booked_credits, usd("5000.00"))
        self.assertEqual(identity.booked_debits, usd("2500.00"))
        self.assertEqual(identity.computed_closing, usd("12500.00"))
        self.assertEqual(identity.printed_closing, usd("12500.00"))
        self.assertEqual(identity.delta, usd("0.00"))
        self.assertEqual(identity.booked_entry_count, 3)
        self.assertEqual(identity.excluded_entry_count, 0)
        self.assertEqual(identity.opening_code, "OPBD")
        self.assertFalse(identity.opening_substituted)
        self.assertIsNone(identity.unavailable_reason)
        self.assertTrue(identity.is_balanced)

    def test_entries_carry_magnitude_and_direction_separately(self):
        entries = parse_camt053(build()).statements[0].entries

        self.assertEqual(len(entries), 3)
        self.assertEqual(
            [(e.index, e.direction, str(e.amount.as_decimal())) for e in entries],
            [
                (0, TransactionDirection.credit, "3000.00"),
                (1, TransactionDirection.credit, "2000.00"),
                (2, TransactionDirection.debit, "2500.00"),
            ],
        )
        for entry in entries:
            self.assertFalse(entry.amount.is_negative)
            self.assertTrue(entry.is_booked)
            self.assertFalse(entry.is_reversal)
        self.assertEqual(entries[2].signed, usd("-2500.00"))

    def test_entry_metadata_is_read(self):
        entry = parse_camt053(build()).statements[0].entries[0]
        self.assertEqual(entry.entry_reference, "E1")
        self.assertEqual(entry.booking_date, "2026-02-10")
        self.assertEqual(entry.value_date, "2026-02-11")
        self.assertEqual(entry.status, "BOOK")

    def test_a_camt_entry_is_not_positional(self):
        entry = parse_camt053(build()).statements[0].entries[0]
        self.assertEqual(entry.locator.kind, LocatorKind.not_positional)
        self.assertIsNone(entry.locator.page)
        self.assertFalse(entry.locator.is_clickable)

    def test_the_bank_transaction_code_is_assembled_from_its_parts(self):
        entries = ntry("3000.00", "CRDT") + ntry("3000.00", "DBIT")
        entries = entries.replace(
            "<NtryRef>REF</NtryRef>",
            "<NtryRef>REF</NtryRef><BkTxCd><Domn><Cd>PMNT</Cd>"
            "<Fmly><Cd>RCDT</Cd><SubFmlyCd>ESCT</SubFmlyCd></Fmly></Domn></BkTxCd>",
            1,
        )
        statement = parse_camt053(build(statements=stmt(entries=entries))).statements[0]
        self.assertEqual(statement.entries[0].bank_transaction_code, "PMNT/RCDT/ESCT")
        self.assertIsNone(statement.entries[1].bank_transaction_code)

    def test_parsing_is_deterministic(self):
        payload = build(statements=stmt(transactions_summary=summary()))
        self.assertEqual(parse_camt053(payload), parse_camt053(payload))

    def test_balance_lookup_by_code(self):
        statement = parse_camt053(build()).statements[0]
        self.assertEqual(statement.balance("OPBD").amount, usd("10000.00"))
        self.assertEqual(statement.balance("CLBD").amount, usd("12500.00"))
        self.assertIsNone(statement.balance("CLAV"))

    def test_document_entries_flattens_every_statement_in_order(self):
        document = parse_camt053(
            build(statements=stmt(identification="A") + stmt(identification="B"))
        )
        self.assertEqual(len(document.entries), 6)
        self.assertEqual(
            [e.entry_reference for e in document.entries],
            ["E1", "E2", "E3", "E1", "E2", "E3"],
        )


class VersionAndEnvelopeTests(Camt053TestCase):
    def test_a_later_message_version_parses_the_same(self):
        document = parse_camt053(build(namespace=NS_08))
        self.assertEqual(document.namespace, NS_08)
        self.assertEqual(document.proof_class, ProofClass.p0)

    def test_an_unknown_namespace_is_still_read(self):
        """Local-name matching is the point: a version we have not seen must parse."""
        document = parse_camt053(build(namespace="urn:example:camt.053.001.99"))
        self.assertEqual(document.proof_class, ProofClass.p0)

    def test_a_business_envelope_is_looked_through(self):
        document = parse_camt053(build(envelope=True))
        self.assertEqual(document.message_identification, "MSG-1")
        self.assertEqual(document.proof_class, ProofClass.p0)

    def test_the_status_code_element_form_is_read(self):
        entries = (
            ntry("3000.00", "CRDT", status_form="code")
            + ntry("2000.00", "CRDT", status_form="code")
            + ntry("2500.00", "DBIT", status_form="code")
        )
        statement = parse_camt053(build(statements=stmt(entries=entries))).statements[0]
        self.assertEqual([e.status for e in statement.entries], ["BOOK"] * 3)
        self.assertEqual(statement.balance_identity.status, ReconciliationStatus.balanced)

    def test_a_proprietary_status_is_not_treated_as_booked(self):
        entries = (
            ntry("3000.00", "CRDT", status="SETTLED", status_form="proprietary")
            + ntry("2000.00", "CRDT")
            + ntry("2500.00", "DBIT")
        )
        statement = parse_camt053(build(statements=stmt(entries=entries))).statements[0]
        self.assertEqual(statement.entries[0].status, "SETTLED")
        self.assertFalse(statement.entries[0].is_booked)
        self.assertEqual(statement.balance_identity.excluded_entry_count, 1)
        self.assertEqual(statement.balance_identity.status, ReconciliationStatus.unbalanced)

    def test_an_entry_with_no_status_is_not_treated_as_booked(self):
        entries = ntry("3000.00", "CRDT", status="") + ntry("2000.00", "CRDT")
        statement = parse_camt053(build(statements=stmt(entries=entries))).statements[0]
        self.assertIsNone(statement.entries[0].status)
        self.assertFalse(statement.entries[0].is_booked)
        self.assertEqual(statement.balance_identity.booked_entry_count, 1)


class HostileInputTests(Camt053TestCase):
    def test_a_billion_laughs_expansion_is_refused(self):
        bomb = (
            b'<?xml version="1.0"?><!DOCTYPE l [\n'
            b'<!ENTITY a "aaaaaaaaaa">\n'
            b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">\n'
            b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">\n'
            b'<!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">\n'
            b'<!ENTITY e "&d;&d;&d;&d;&d;&d;&d;&d;&d;&d;">\n'
            b'<!ENTITY f "&e;&e;&e;&e;&e;&e;&e;&e;&e;&e;">\n'
            b"]><l>&f;</l>"
        )
        with self.assertRaises(Camt053MalformedDocumentError):
            parse_camt053(bomb)

    def test_an_external_entity_cannot_read_a_local_file(self):
        handle, path = tempfile.mkstemp()
        try:
            with os.fdopen(handle, "w") as stream:
                stream.write("CANARY-DO-NOT-LEAK-4417")
            payload = (
                '<?xml version="1.0"?>'
                f'<!DOCTYPE l [<!ENTITY x SYSTEM "file://{path}">]>'
                "<l>&x;</l>"
            ).encode("utf-8")
            with self.assertRaises(Camt053MalformedDocumentError) as caught:
                parse_camt053(payload)
            self.assertNotIn("CANARY", str(caught.exception))
        finally:
            os.unlink(path)

    def test_a_document_type_declaration_is_refused_on_its_own(self):
        payload = b'<?xml version="1.0"?><!DOCTYPE Document><Document/>'
        with self.assertRaises(Camt053MalformedDocumentError) as caught:
            parse_camt053(payload)
        self.assertIn("document type declaration", str(caught.exception))

    def test_an_internal_entity_reference_is_refused(self):
        payload = (
            b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY x "harmless">]><l>&x;</l>'
        )
        with self.assertRaises(Camt053MalformedDocumentError):
            parse_camt053(payload)

    def test_a_truncated_document_is_an_error_not_a_partial_statement(self):
        payload = build()[: len(build()) // 2]
        with self.assertRaises(Camt053MalformedDocumentError):
            parse_camt053(payload)

    def test_text_input_is_refused_with_the_reason(self):
        with self.assertRaises(Camt053MalformedDocumentError) as caught:
            parse_camt053(build().decode("utf-8"))
        self.assertIn("encoding", str(caught.exception))

    def test_a_non_bytes_argument_is_refused(self):
        with self.assertRaises(Camt053MalformedDocumentError):
            parse_camt053(None)
        with self.assertRaises(Camt053MalformedDocumentError):
            parse_camt053(42)

    def test_an_empty_document_is_refused(self):
        for payload in (b"", b"   \n  "):
            with self.subTest(payload=payload):
                with self.assertRaises(Camt053MalformedDocumentError):
                    parse_camt053(payload)

    def test_an_oversized_document_is_refused_before_parsing(self):
        with mock.patch("services.financial.camt053.CAMT053_MAX_DOCUMENT_BYTES", 64):
            with self.assertRaises(Camt053MalformedDocumentError) as caught:
                parse_camt053(build())
        self.assertIn("ceiling", str(caught.exception))

    def test_the_size_ceiling_is_the_declared_one(self):
        self.assertEqual(CAMT053_MAX_DOCUMENT_BYTES, 64 * 1024 * 1024)

    def test_a_bytearray_is_accepted(self):
        self.assertEqual(
            parse_camt053(bytearray(build())).message_identification, "MSG-1"
        )

    def test_deeply_nested_markup_is_refused(self):
        """``huge_tree=False`` caps nesting at 256, and the cap must stay on.

        Depth is not a formatting quirk.  Nesting is the cheapest way to make a
        parser allocate without bound, and a camt.053 has a fixed, shallow
        shape — nothing legitimate comes anywhere near the limit.
        """
        payload = (b"<a>" * 300) + b"x" + (b"</a>" * 300)
        document = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Document xmlns="' + NS_02.encode() + b'">' + payload + b"</Document>"
        )
        with self.assertRaises(Camt053MalformedDocumentError):
            parse_camt053(document)

    def test_malformed_markup_is_refused_rather_than_repaired(self):
        """``recover=False``: a damaged file must not parse as though whole.

        The last of these is the one that matters.  With recovery on, lxml
        drops content after the root element without a word, so a file
        truncated and re-terminated in transit — or edited to end early —
        yields a document that parses cleanly, closes its own identity over the
        entries that survived, and reaches P0 while missing the rest.  There is
        no downstream check that could notice, because the evidence that
        something was removed was discarded at parse time.
        """
        head = b'<?xml version="1.0" encoding="UTF-8"?><Document xmlns="' + NS_02.encode() + b'">'
        for label, document in (
            ("mismatched close", head + b"<BkToCstmrStmt><Stmt><Id>A</Bad></Stmt></BkToCstmrStmt></Document>"),
            ("unclosed element", head + b"<BkToCstmrStmt><Stmt><Id>A</Id></BkToCstmrStmt></Document>"),
            ("content after the root", build() + b"<Extra/>"),
        ):
            with self.subTest(label=label):
                with self.assertRaises(Camt053MalformedDocumentError):
                    parse_camt053(document)

    def test_the_hardened_parser_does_not_expand_entities(self):
        """Checked directly, because the doctype refusal hides it in normal use.

        Every entity reference needs a DTD, and a DTD is refused outright, so
        no document reaching :func:`parse_camt053` can exercise entity
        expansion.  That makes ``resolve_entities=False`` invisible to any
        end-to-end test — and an invisible security flag is one that can be
        flipped by anybody, for any reason, with the suite still green.  So it
        is asserted against the parser itself.
        """
        document = (
            b'<?xml version="1.0"?>'
            b'<!DOCTYPE Document [<!ENTITY secret "EXPANDED-4417">]>'
            b"<Document><A>&secret;</A></Document>"
        )
        root = etree.fromstring(document, parser=_hardened_parser())
        self.assertNotIn("EXPANDED-4417", etree.tostring(root).decode())

    def test_entity_nodes_are_refused_by_the_node_check_itself(self):
        """The second line of defence, tested where it can still be reached.

        An entity reference in a parsed document needs a DTD to declare it, and
        ``_reject_hostile_nodes`` refuses the doctype before it looks at a
        single node, so the entity loop that follows is unreachable through the
        public entry point — measured, not assumed: parsing the obvious hostile
        document raises on the doctype, never on the entity.

        The loop is kept anyway.  The two guards fail for different reasons,
        and being wrong about which one is load-bearing costs more than the
        loop does.  So the tree is built here rather than parsed, which is the
        only way to hand the check an entity with no doctype in front of it,
        and removing the loop stops being free.
        """
        root = etree.Element("Document")
        etree.SubElement(root, "Amt").append(etree.Entity("secret"))
        self.assertEqual(root.getroottree().docinfo.doctype, "")
        self.assertTrue(any(node.tag is etree.Entity for node in root.iter()))

        with self.assertRaises(Camt053MalformedDocumentError) as caught:
            _reject_hostile_nodes(root)
        self.assertIn("entity", str(caught.exception).lower())


class StructuralRefusalTests(Camt053TestCase):
    def test_xml_that_is_not_a_statement_message_is_refused(self):
        with self.assertRaises(NotACamt053Error) as caught:
            parse_camt053(b"<Document><BkToCstmrAcctRpt/></Document>")
        self.assertIn("BkToCstmrStmt", str(caught.exception))

    def test_two_statement_messages_in_one_file_are_refused(self):
        with self.assertRaises(NotACamt053Error) as caught:
            parse_camt053(build(message_count=2))
        self.assertIn("2", str(caught.exception))

    def test_a_missing_group_header_is_refused(self):
        with self.assertRaises(Camt053MissingElementError):
            parse_camt053(build(group_header=""))

    def test_a_missing_message_identification_is_refused(self):
        with self.assertRaises(Camt053MissingElementError) as caught:
            parse_camt053(build(group_header="<GrpHdr><CreDtTm>x</CreDtTm></GrpHdr>"))
        self.assertIn("MsgId", str(caught.exception))

    def test_a_message_with_no_statement_is_refused(self):
        with self.assertRaises(Camt053MissingElementError) as caught:
            parse_camt053(build(statements=""))
        self.assertIn("Stmt", str(caught.exception))

    def test_a_statement_with_no_identification_is_refused(self):
        with self.assertRaises(Camt053MissingElementError):
            parse_camt053(build(statements=stmt().replace("<Id>STMT-1</Id>", "", 1)))

    def test_a_balance_with_no_type_is_refused(self):
        broken = DEFAULT_BALANCES.replace(
            "<Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>", "", 1
        )
        with self.assertRaises(Camt053MissingElementError) as caught:
            parse_camt053(build(statements=stmt(balances=broken)))
        self.assertIn("CdOrPrtry", str(caught.exception))

    def test_a_balance_type_with_neither_code_nor_proprietary_is_refused(self):
        broken = DEFAULT_BALANCES.replace(
            "<CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry>", "<CdOrPrtry/>", 1
        )
        with self.assertRaises(Camt053MissingElementError):
            parse_camt053(build(statements=stmt(balances=broken)))

    def test_a_balance_with_no_amount_is_refused(self):
        broken = DEFAULT_BALANCES.replace('<Amt Ccy="USD">10000.00</Amt>', "", 1)
        with self.assertRaises(Camt053MissingElementError):
            parse_camt053(build(statements=stmt(balances=broken)))

    def test_an_entry_with_no_amount_is_refused(self):
        broken = DEFAULT_ENTRIES.replace('<Amt Ccy="USD">3000.00</Amt>', "", 1)
        with self.assertRaises(Camt053MissingElementError):
            parse_camt053(build(statements=stmt(entries=broken)))

    def test_an_empty_amount_element_is_refused(self):
        broken = DEFAULT_ENTRIES.replace(
            '<Amt Ccy="USD">3000.00</Amt>', '<Amt Ccy="USD"></Amt>', 1
        )
        with self.assertRaises(Camt053MissingElementError):
            parse_camt053(build(statements=stmt(entries=broken)))


class DirectionTests(Camt053TestCase):
    def test_a_missing_direction_indicator_is_refused(self):
        broken = DEFAULT_ENTRIES.replace("<CdtDbtInd>CRDT</CdtDbtInd>", "", 1)
        with self.assertRaises(Camt053MissingElementError) as caught:
            parse_camt053(build(statements=stmt(entries=broken)))
        self.assertIn("CdtDbtInd", str(caught.exception))

    def test_an_unknown_direction_indicator_is_refused(self):
        broken = DEFAULT_ENTRIES.replace(
            "<CdtDbtInd>CRDT</CdtDbtInd>", "<CdtDbtInd>CRDTX</CdtDbtInd>", 1
        )
        with self.assertRaises(Camt053MalformedDocumentError) as caught:
            parse_camt053(build(statements=stmt(entries=broken)))
        self.assertIn("CRDT", str(caught.exception))
        self.assertIn("DBIT", str(caught.exception))

    def test_direction_comes_from_the_indicator_and_not_the_sign(self):
        """Every amount is positive; only the indicator distinguishes the debit.

        A parser reading direction from the sign would make all three entries
        credits, compute a closing of 17,500.00, and report a delta of
        5,000.00 — twice the debit — on a document that is entirely correct.
        """
        identity = parse_camt053(build()).statements[0].balance_identity
        self.assertEqual(identity.booked_debits, usd("2500.00"))
        self.assertNotEqual(identity.computed_closing, usd("17500.00"))
        self.assertEqual(identity.computed_closing, usd("12500.00"))

    def test_a_debit_balance_is_an_overdrawn_account(self):
        balances = bal(CAMT053_BALANCE_OPENING_BOOKED, "500.00", "DBIT") + bal(
            CAMT053_BALANCE_CLOSING_BOOKED, "2000.00", "CRDT"
        )
        entries = ntry("2500.00", "CRDT")
        statement = parse_camt053(
            build(statements=stmt(balances=balances, entries=entries))
        ).statements[0]

        opening = statement.balance(CAMT053_BALANCE_OPENING_BOOKED)
        self.assertEqual(opening.amount, usd("500.00"))
        self.assertEqual(opening.direction, TransactionDirection.debit)
        self.assertEqual(opening.signed, usd("-500.00"))
        self.assertEqual(statement.balance_identity.opening, usd("-500.00"))
        self.assertEqual(statement.balance_identity.status, ReconciliationStatus.balanced)

    def test_a_reversal_indicator_is_recorded_without_changing_direction(self):
        entries = (
            ntry("3000.00", "CRDT", reversal=True)
            + ntry("2000.00", "CRDT")
            + ntry("2500.00", "DBIT")
        )
        statement = parse_camt053(build(statements=stmt(entries=entries))).statements[0]
        self.assertTrue(statement.entries[0].is_reversal)
        self.assertEqual(statement.entries[0].direction, TransactionDirection.credit)
        self.assertEqual(statement.balance_identity.status, ReconciliationStatus.balanced)


class AmountTests(Camt053TestCase):
    def _with_amount(self, text: str) -> bytes:
        entries = DEFAULT_ENTRIES.replace(
            '<Amt Ccy="USD">3000.00</Amt>', f'<Amt Ccy="USD">{text}</Amt>', 1
        )
        return build(statements=stmt(entries=entries))

    def test_values_outside_the_xsd_decimal_space_are_refused(self):
        # ``Decimal`` accepts the first four of these and would report them as
        # figures read from the document.  ``1E+2`` is the dangerous one: it
        # parses silently as 100 and nothing downstream could tell that the
        # document never said 100.  XSD decimal permits no exponent, so the
        # lexical space is checked before ``Decimal`` ever sees the text.
        for text in (
            "NaN",
            "Infinity",
            "-Infinity",
            "1E+2",
            "1e2",
            "0x10",
            "1,000.00",
            "1 000.00",
            "$3000.00",
            "3.000,00",
            "--3",
            "abc",
            "+",
            "-",
            ".",
            "3..0",
            "3.0.0",
            "1_000",
        ):
            with self.subTest(text=text):
                with self.assertRaises(Camt053AmountError):
                    parse_camt053(self._with_amount(text))

    def test_an_amount_element_that_states_nothing_is_reported_as_absent(self):
        """Empty is an absence, not a malformed figure, and is reported as one.

        The distinction is for whoever reads the error.  ``Camt053MissingElementError``
        says the document did not state the amount; ``Camt053AmountError`` would say it
        stated one this parser could not read, which is a different fault with a
        different remedy.  Both refuse, so nothing turns on the classification
        for admissibility — only on whether the message sends someone looking in
        the right place.
        """
        for text in ("", " ", "\n\t "):
            with self.subTest(text=text):
                with self.assertRaises(Camt053MissingElementError):
                    parse_camt053(self._with_amount(text))

    def test_the_permitted_lexical_forms_are_accepted(self):
        for text, expected in (("3000", "3000.00"), ("3000.0", "3000.00"),
                               ("3000.", "3000.00"), ("+3000.00", "3000.00")):
            with self.subTest(text=text):
                statement = parse_camt053(self._with_amount(text)).statements[0]
                self.assertEqual(
                    statement.entries[0].amount, usd(expected)
                )

    def test_more_precision_than_the_currency_has_is_refused_not_rounded(self):
        with self.assertRaises(Camt053AmountError) as caught:
            parse_camt053(self._with_amount("3000.005"))
        self.assertIn("precision", str(caught.exception).lower())

    def test_a_zero_decimal_currency_refuses_a_fractional_amount(self):
        balances = bal(CAMT053_BALANCE_OPENING_BOOKED, "1000", currency="JPY") + bal(
            CAMT053_BALANCE_CLOSING_BOOKED, "1500", currency="JPY"
        )
        account = "<Acct><Id><IBAN>JP00</IBAN></Id><Ccy>JPY</Ccy></Acct>"
        good = parse_camt053(
            build(
                statements=stmt(
                    balances=balances,
                    entries=ntry("500", "CRDT", currency="JPY"),
                    account=account,
                )
            )
        ).statements[0]
        self.assertEqual(good.currency, "JPY")
        self.assertEqual(good.balance_identity.status, ReconciliationStatus.balanced)

        with self.assertRaises(Camt053AmountError):
            parse_camt053(
                build(
                    statements=stmt(
                        balances=balances,
                        entries=ntry("500.50", "CRDT", currency="JPY"),
                        account=account,
                    )
                )
            )

    def test_an_amount_with_no_currency_attribute_is_refused(self):
        entries = DEFAULT_ENTRIES.replace(
            '<Amt Ccy="USD">3000.00</Amt>', "<Amt>3000.00</Amt>", 1
        )
        with self.assertRaises(Camt053MissingElementError) as caught:
            parse_camt053(build(statements=stmt(entries=entries)))
        self.assertIn("Ccy", str(caught.exception))

    def test_an_unknown_currency_is_refused(self):
        entries = DEFAULT_ENTRIES.replace(
            '<Amt Ccy="USD">3000.00</Amt>', '<Amt Ccy="ZZZ">3000.00</Amt>', 1
        )
        with self.assertRaises(Camt053AmountError):
            parse_camt053(build(statements=stmt(entries=entries)))

    def test_a_count_that_is_not_a_count_is_refused(self):
        with self.assertRaises(Camt053MalformedDocumentError):
            parse_camt053(
                build(statements=stmt(transactions_summary=summary(entries="three")))
            )
        with self.assertRaises(Camt053MalformedDocumentError):
            parse_camt053(
                build(statements=stmt(transactions_summary=summary(entries="-1")))
            )


class CurrencyTests(Camt053TestCase):
    def test_an_entry_in_another_currency_is_refused_with_the_element_named(self):
        entries = DEFAULT_ENTRIES.replace(
            '<Amt Ccy="USD">3000.00</Amt>', '<Amt Ccy="EUR">3000.00</Amt>', 1
        )
        with self.assertRaises(Camt053StatementCurrencyError) as caught:
            parse_camt053(build(statements=stmt(entries=entries)))
        message = str(caught.exception)
        self.assertIn("EUR", message)
        self.assertIn("USD", message)
        self.assertIn("Ntry", message)

    def test_the_currency_is_taken_from_the_balances_when_the_account_omits_it(self):
        account = "<Acct><Id><IBAN>GB29NWBK60161331926819</IBAN></Id></Acct>"
        statement = parse_camt053(
            build(statements=stmt(account=account))
        ).statements[0]
        self.assertEqual(statement.currency, "USD")
        self.assertIsNone(statement.account.currency)
        self.assertEqual(statement.balance_identity.status, ReconciliationStatus.balanced)

    def test_balances_in_two_currencies_are_refused_rather_than_resolved(self):
        account = "<Acct><Id><IBAN>GB29NWBK60161331926819</IBAN></Id></Acct>"
        balances = bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00") + bal(
            CAMT053_BALANCE_CLOSING_BOOKED, "12500.00", currency="EUR"
        )
        with self.assertRaises(Camt053StatementCurrencyError) as caught:
            parse_camt053(build(statements=stmt(balances=balances, account=account)))
        self.assertIn("EUR", str(caught.exception))
        self.assertIn("USD", str(caught.exception))

    def test_a_statement_with_neither_account_currency_nor_balances_is_refused(self):
        account = "<Acct><Id><IBAN>GB29NWBK60161331926819</IBAN></Id></Acct>"
        with self.assertRaises(Camt053MissingElementError) as caught:
            parse_camt053(build(statements=stmt(balances="", account=account)))
        self.assertIn("Ccy", str(caught.exception))

    def test_an_unusable_account_currency_is_refused(self):
        account = "<Acct><Id><IBAN>GB00</IBAN></Id><Ccy>ZZZ</Ccy></Acct>"
        with self.assertRaises(Camt053AmountError):
            parse_camt053(build(statements=stmt(account=account)))

    def test_a_statement_with_no_account_element_still_reads_its_currency(self):
        statement = parse_camt053(build(statements=stmt(account=""))).statements[0]
        self.assertEqual(statement.currency, "USD")
        self.assertIsNone(statement.account.identifier)


class BalanceIdentityTests(Camt053TestCase):
    def test_a_document_whose_arithmetic_fails_demotes_to_p3(self):
        balances = bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00") + bal(
            CAMT053_BALANCE_CLOSING_BOOKED, "12400.00"
        )
        document = parse_camt053(build(statements=stmt(balances=balances)))
        identity = document.statements[0].balance_identity

        self.assertEqual(identity.status, ReconciliationStatus.unbalanced)
        self.assertEqual(identity.delta, usd("100.00"))
        self.assertEqual(document.proof_class, ProofClass.p3)

    def test_the_delta_sign_says_which_way_the_entries_run(self):
        balances = bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00") + bal(
            CAMT053_BALANCE_CLOSING_BOOKED, "12600.00"
        )
        identity = parse_camt053(
            build(statements=stmt(balances=balances))
        ).statements[0].balance_identity
        self.assertEqual(identity.delta, usd("-100.00"))

    def test_a_previously_closed_balance_may_stand_in_and_says_so(self):
        balances = bal(CAMT053_BALANCE_PREVIOUSLY_CLOSED_BOOKED, "10000.00") + bal(
            CAMT053_BALANCE_CLOSING_BOOKED, "12500.00"
        )
        identity = parse_camt053(
            build(statements=stmt(balances=balances))
        ).statements[0].balance_identity

        self.assertEqual(identity.status, ReconciliationStatus.balanced)
        self.assertEqual(identity.opening_code, "PRCD")
        self.assertTrue(identity.opening_substituted)

    def test_an_opening_balance_is_preferred_over_a_previously_closed_one(self):
        balances = (
            bal(CAMT053_BALANCE_PREVIOUSLY_CLOSED_BOOKED, "9999.00")
            + bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00")
            + bal(CAMT053_BALANCE_CLOSING_BOOKED, "12500.00")
        )
        identity = parse_camt053(
            build(statements=stmt(balances=balances))
        ).statements[0].balance_identity
        self.assertEqual(identity.opening, usd("10000.00"))
        self.assertEqual(identity.opening_code, "OPBD")
        self.assertFalse(identity.opening_substituted)

    def test_a_missing_opening_balance_declines_rather_than_assuming_zero(self):
        balances = bal(CAMT053_BALANCE_CLOSING_BOOKED, "12500.00")
        identity = parse_camt053(
            build(statements=stmt(balances=balances))
        ).statements[0].balance_identity

        self.assertEqual(identity.status, ReconciliationStatus.unavailable)
        self.assertIsNone(identity.computed_closing)
        self.assertIsNone(identity.delta)
        self.assertIn("OPBD", identity.unavailable_reason)
        self.assertIn("PRCD", identity.unavailable_reason)

    def test_a_substitution_is_recorded_even_when_the_identity_declines(self):
        """The flag is about the figure shown, not about whether the sum ran.

        A declining identity still reports an opening balance, and a reviewer
        reading it has to be able to tell that the figure came from ``PRCD``
        standing in for an absent ``OPBD`` rather than from the statement's own
        opening.  Asserted separately from the closing case because the two are
        built on different branches, and the branch that fails is the one
        nobody looks at.
        """
        balances = bal(CAMT053_BALANCE_PREVIOUSLY_CLOSED_BOOKED, "10000.00")
        identity = parse_camt053(
            build(statements=stmt(balances=balances))
        ).statements[0].balance_identity

        self.assertEqual(identity.status, ReconciliationStatus.unavailable)
        self.assertEqual(identity.opening, usd("10000.00"))
        self.assertEqual(identity.opening_code, "PRCD")
        self.assertTrue(identity.opening_substituted)

    def test_a_missing_closing_balance_declines(self):
        balances = bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00")
        identity = parse_camt053(
            build(statements=stmt(balances=balances))
        ).statements[0].balance_identity
        self.assertEqual(identity.status, ReconciliationStatus.unavailable)
        self.assertIn("CLBD", identity.unavailable_reason)
        self.assertEqual(identity.opening, usd("10000.00"))

    def test_a_statement_with_no_balances_at_all_declines_and_lands_at_p3(self):
        account = "<Acct><Id><IBAN>GB00</IBAN></Id><Ccy>USD</Ccy></Acct>"
        document = parse_camt053(
            build(statements=stmt(balances="", account=account))
        )
        identity = document.statements[0].balance_identity
        self.assertEqual(identity.status, ReconciliationStatus.unavailable)
        self.assertIn("OPBD", identity.unavailable_reason)
        self.assertIn("CLBD", identity.unavailable_reason)
        self.assertEqual(document.proof_class, ProofClass.p3)

    def test_flows_are_still_reported_when_the_identity_declines(self):
        balances = bal(CAMT053_BALANCE_CLOSING_BOOKED, "12500.00")
        identity = parse_camt053(
            build(statements=stmt(balances=balances))
        ).statements[0].balance_identity
        self.assertEqual(identity.booked_credits, usd("5000.00"))
        self.assertEqual(identity.booked_debits, usd("2500.00"))
        self.assertEqual(identity.booked_entry_count, 3)

    def test_a_proprietary_balance_code_does_not_satisfy_the_identity(self):
        balances = bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00", proprietary=True) + bal(
            CAMT053_BALANCE_CLOSING_BOOKED, "12500.00"
        )
        identity = parse_camt053(
            build(statements=stmt(balances=balances))
        ).statements[0].balance_identity
        self.assertEqual(identity.status, ReconciliationStatus.unavailable)

    def test_a_statement_with_no_entries_balances_only_when_the_endpoints_agree(self):
        balances = bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00") + bal(
            CAMT053_BALANCE_CLOSING_BOOKED, "10000.00"
        )
        identity = parse_camt053(
            build(statements=stmt(balances=balances, entries=""))
        ).statements[0].balance_identity
        self.assertEqual(identity.status, ReconciliationStatus.balanced)
        self.assertEqual(identity.booked_credits, usd("0.00"))
        self.assertEqual(identity.booked_entry_count, 0)


class BookedPopulationTests(Camt053TestCase):
    def test_a_pending_entry_is_kept_but_excluded_from_the_identity(self):
        entries = (
            ntry("3000.00", "CRDT")
            + ntry("2000.00", "CRDT")
            + ntry("2500.00", "DBIT")
            + ntry("9999.00", "CRDT", status="PDNG", reference="P1")
        )
        statement = parse_camt053(build(statements=stmt(entries=entries))).statements[0]
        identity = statement.balance_identity

        self.assertEqual(len(statement.entries), 4)
        self.assertEqual(len(statement.booked_entries), 3)
        self.assertEqual(identity.booked_entry_count, 3)
        self.assertEqual(identity.excluded_entry_count, 1)
        self.assertEqual(identity.booked_credits, usd("5000.00"))
        self.assertEqual(identity.status, ReconciliationStatus.balanced)

    def test_an_information_entry_is_excluded_too(self):
        entries = DEFAULT_ENTRIES + ntry("1.00", "DBIT", status="INFO", reference="I1")
        identity = parse_camt053(
            build(statements=stmt(entries=entries))
        ).statements[0].balance_identity
        self.assertEqual(identity.excluded_entry_count, 1)
        self.assertEqual(identity.status, ReconciliationStatus.balanced)


class SummaryIdentityTests(Camt053TestCase):
    def test_an_absent_summary_is_not_attempted_and_does_not_prevent_p0(self):
        document = parse_camt053(build())
        self.assertIsNone(document.statements[0].summary)
        self.assertEqual(
            document.statements[0].summary_identity.status,
            ReconciliationStatus.not_attempted,
        )
        self.assertEqual(document.proof_class, ProofClass.p0)

    def test_a_summary_that_agrees_balances(self):
        identity = parse_camt053(
            build(statements=stmt(transactions_summary=summary()))
        ).statements[0].summary_identity

        self.assertEqual(identity.status, ReconciliationStatus.balanced)
        self.assertEqual(identity.credit_delta, usd("0.00"))
        self.assertEqual(identity.debit_delta, usd("0.00"))
        self.assertEqual(identity.net_delta, usd("0.00"))
        self.assertEqual(identity.count_delta, 0)

    def test_a_wrong_credit_total_demotes_the_document_even_when_balances_close(self):
        document = parse_camt053(
            build(statements=stmt(transactions_summary=summary(credits="4000.00")))
        )
        statement = document.statements[0]

        self.assertEqual(statement.balance_identity.status, ReconciliationStatus.balanced)
        self.assertEqual(statement.summary_identity.status, ReconciliationStatus.unbalanced)
        self.assertEqual(statement.summary_identity.credit_delta, usd("1000.00"))
        self.assertEqual(document.proof_class, ProofClass.p3)

    def test_a_wrong_entry_count_demotes_the_document(self):
        statement = parse_camt053(
            build(statements=stmt(transactions_summary=summary(entries=4)))
        ).statements[0]
        self.assertEqual(statement.summary_identity.status, ReconciliationStatus.unbalanced)
        self.assertEqual(statement.summary_identity.count_delta, -1)

    def test_a_wrong_net_amount_demotes_the_document(self):
        statement = parse_camt053(
            build(statements=stmt(transactions_summary=summary(net="2400.00")))
        ).statements[0]
        self.assertEqual(statement.summary_identity.status, ReconciliationStatus.unbalanced)
        self.assertEqual(statement.summary_identity.net_delta, usd("100.00"))

    def test_a_net_amount_signed_debit_is_read_as_negative(self):
        entries = ntry("1000.00", "CRDT") + ntry("3000.00", "DBIT")
        balances = bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00") + bal(
            CAMT053_BALANCE_CLOSING_BOOKED, "8000.00"
        )
        statement = parse_camt053(
            build(
                statements=stmt(
                    balances=balances,
                    entries=entries,
                    transactions_summary=summary(
                        entries=2, credits="1000.00", credit_count=1,
                        debits="3000.00", debit_count=1,
                        net="2000.00", net_indicator="DBIT",
                    ),
                )
            )
        ).statements[0]
        self.assertEqual(statement.summary_identity.status, ReconciliationStatus.balanced)
        self.assertEqual(statement.summary_identity.net_delta, usd("0.00"))

    def test_a_mixed_population_declines_rather_than_choosing_a_reading(self):
        entries = DEFAULT_ENTRIES + ntry("50.00", "CRDT", status="PDNG")
        statement = parse_camt053(
            build(statements=stmt(entries=entries, transactions_summary=summary()))
        ).statements[0]

        self.assertEqual(statement.summary_identity.status, ReconciliationStatus.unavailable)
        self.assertIn("TxsSummry", statement.summary_identity.unavailable_reason)
        self.assertIsNone(statement.summary_identity.credit_delta)

    def test_a_summary_stating_nothing_declines(self):
        empty = summary(entries=None, credits=None, credit_count=None,
                        debits=None, debit_count=None, net=None, net_indicator=None)
        statement = parse_camt053(
            build(statements=stmt(transactions_summary=empty))
        ).statements[0]
        self.assertEqual(statement.summary_identity.status, ReconciliationStatus.unavailable)
        self.assertIn("nothing", statement.summary_identity.unavailable_reason)

    def test_a_summary_stating_only_a_count_is_still_checked(self):
        only_count = summary(entries=3, credits=None, credit_count=None,
                             debits=None, debit_count=None, net=None,
                             net_indicator=None)
        statement = parse_camt053(
            build(statements=stmt(transactions_summary=only_count))
        ).statements[0]
        self.assertEqual(statement.summary_identity.status, ReconciliationStatus.balanced)
        self.assertEqual(statement.summary_identity.count_delta, 0)

    def test_the_summary_figures_are_read_onto_the_statement(self):
        statement = parse_camt053(
            build(statements=stmt(transactions_summary=summary()))
        ).statements[0]
        block = statement.summary
        self.assertEqual(block.total_entries, 3)
        self.assertEqual(block.credit_entries, 2)
        self.assertEqual(block.credit_sum, usd("5000.00"))
        self.assertEqual(block.debit_entries, 1)
        self.assertEqual(block.debit_sum, usd("2500.00"))
        self.assertEqual(block.total_net_amount, usd("2500.00"))
        self.assertEqual(block.total_net_direction, TransactionDirection.credit)


class BatchIdentityTests(Camt053TestCase):
    def _statement(self, block: str):
        entries = (
            ntry("3000.00", "CRDT")
            + ntry("2000.00", "CRDT")
            + ntry("2500.00", "DBIT", details=block)
        )
        return parse_camt053(build(statements=stmt(entries=entries))).statements[0]

    def test_an_entry_with_no_batch_produces_no_batch_check(self):
        statement = parse_camt053(build()).statements[0]
        self.assertEqual(statement.batch_identities, ())
        self.assertIsNone(statement.entries[0].batch)

    def test_a_batch_that_agrees_balances(self):
        statement = self._statement(batch())
        self.assertEqual(len(statement.batch_identities), 1)
        outcome = statement.batch_identities[0]
        self.assertEqual(outcome.status, ReconciliationStatus.balanced)
        self.assertEqual(outcome.entry_index, 2)
        self.assertEqual(outcome.amount_delta, usd("0.00"))
        self.assertEqual(outcome.count_delta, 0)

    def test_a_batch_total_that_disagrees_with_the_entry_demotes(self):
        statement = self._statement(batch(total="2400.00"))
        self.assertEqual(statement.batch_identities[0].status, ReconciliationStatus.unbalanced)
        self.assertEqual(statement.batch_identities[0].amount_delta, usd("-100.00"))
        self.assertEqual(statement.reconciliation_status, ReconciliationStatus.unbalanced)

    def test_a_batch_count_that_disagrees_with_the_details_demotes(self):
        statement = self._statement(batch(count=3))
        self.assertEqual(statement.batch_identities[0].status, ReconciliationStatus.unbalanced)
        self.assertEqual(statement.batch_identities[0].count_delta, -1)

    def test_a_batch_total_with_no_details_is_checked_on_amount_only(self):
        statement = self._statement(batch(count=7, transactions=()))
        outcome = statement.batch_identities[0]
        self.assertEqual(outcome.status, ReconciliationStatus.balanced)
        self.assertEqual(outcome.amount_delta, usd("0.00"))
        self.assertIsNone(outcome.count_delta)

    def test_a_batch_stating_neither_total_nor_details_declines(self):
        statement = self._statement(batch(total=None, count=4, transactions=()))
        outcome = statement.batch_identities[0]
        self.assertEqual(outcome.status, ReconciliationStatus.unavailable)
        self.assertIsNotNone(outcome.unavailable_reason)

    def test_transaction_details_are_read_but_never_added_to_the_identity(self):
        """The entry amount is the batch's total; adding both counts it twice."""
        statement = self._statement(batch())
        entry = statement.entries[2]

        self.assertEqual(len(entry.details), 2)
        self.assertEqual(entry.details[0].amount, usd("1500.00"))
        self.assertEqual(entry.details[1].amount, usd("1000.00"))
        self.assertEqual(entry.details[0].end_to_end_id, "E2E-0")
        self.assertEqual(entry.details[0].remittance_information, ("Invoice 0",))

        identity = statement.balance_identity
        self.assertEqual(identity.booked_debits, usd("2500.00"))
        self.assertNotEqual(identity.booked_debits, usd("5000.00"))
        self.assertEqual(identity.status, ReconciliationStatus.balanced)

    def test_batch_metadata_is_read(self):
        statement = self._statement(batch())
        block = statement.entries[2].batch
        self.assertEqual(block.number_of_transactions, 2)
        self.assertEqual(block.total_amount, usd("2500.00"))


class WeakestOutcomeTests(Camt053TestCase):
    def test_no_checks_is_not_attempted(self):
        self.assertEqual(_weakest([]), ReconciliationStatus.not_attempted)

    def test_all_balanced_is_balanced(self):
        self.assertEqual(
            _weakest([ReconciliationStatus.balanced] * 3),
            ReconciliationStatus.balanced,
        )

    def test_one_failure_governs_over_any_number_of_successes(self):
        self.assertEqual(
            _weakest(
                [
                    ReconciliationStatus.balanced,
                    ReconciliationStatus.unbalanced,
                    ReconciliationStatus.balanced,
                ]
            ),
            ReconciliationStatus.unbalanced,
        )

    def test_unbalanced_outranks_unavailable_and_not_attempted(self):
        self.assertEqual(
            _weakest(
                [
                    ReconciliationStatus.not_attempted,
                    ReconciliationStatus.unavailable,
                    ReconciliationStatus.unbalanced,
                ]
            ),
            ReconciliationStatus.unbalanced,
        )

    def test_unavailable_outranks_not_attempted(self):
        self.assertEqual(
            _weakest(
                [ReconciliationStatus.not_attempted, ReconciliationStatus.unavailable]
            ),
            ReconciliationStatus.unavailable,
        )

    def test_not_attempted_outranks_balanced(self):
        self.assertEqual(
            _weakest(
                [ReconciliationStatus.balanced, ReconciliationStatus.not_attempted]
            ),
            ReconciliationStatus.not_attempted,
        )


class StatementRollupTests(Camt053TestCase):
    """How a statement's three checks combine into its one status.

    The rule is asymmetric on purpose and the asymmetry is the substance of it:
    the balance identity governs unconditionally, while an optional
    corroboration weakens the outcome only by failing outright.  Written the
    obvious way instead — weakest-of-all-three — a camt.053 that simply omits
    ``TxsSummry`` would carry a ``not_attempted`` into the roll-up and never
    reach P0, and since the block is optional and widely omitted, the format's
    entire advantage would be forfeited by files that are not defective at all.
    """

    def _status(self, **kwargs) -> ReconciliationStatus:
        return parse_camt053(build(statements=stmt(**kwargs))).reconciliation_status

    def test_an_absent_summary_does_not_weaken_a_closed_statement(self):
        self.assertEqual(self._status(), ReconciliationStatus.balanced)

    def test_a_declining_summary_does_not_weaken_a_closed_statement(self):
        """A decline says what this parser can interpret, not what the file says.

        A pending entry makes the ``TxsSummry`` population ambiguous, so that
        check declines.  The balances are booked by definition and are not in
        doubt, so the statement still closes.
        """
        entries = DEFAULT_ENTRIES + ntry("900.00", status="PDNG", reference="P1")
        document = parse_camt053(
            build(statements=stmt(entries=entries, transactions_summary=summary()))
        )
        statement = document.statements[0]
        self.assertEqual(
            statement.summary_identity.status, ReconciliationStatus.unavailable
        )
        self.assertEqual(
            statement.balance_identity.status, ReconciliationStatus.balanced
        )
        self.assertEqual(statement.reconciliation_status, ReconciliationStatus.balanced)
        self.assertEqual(document.proof_class, ProofClass.p0)

    def test_a_failing_summary_does_weaken_a_closed_statement(self):
        """Two readings of the same entries disagree, so neither is proved."""
        document = parse_camt053(
            build(statements=stmt(transactions_summary=summary(credits="9999.00")))
        )
        statement = document.statements[0]
        self.assertEqual(
            statement.balance_identity.status, ReconciliationStatus.balanced
        )
        self.assertEqual(
            statement.summary_identity.status, ReconciliationStatus.unbalanced
        )
        self.assertEqual(
            statement.reconciliation_status, ReconciliationStatus.unbalanced
        )
        self.assertNotEqual(document.proof_class, ProofClass.p0)

    def test_a_failing_batch_does_weaken_a_closed_statement(self):
        entries = ntry("3000.00") + ntry("2000.00") + ntry(
            "2500.00", "DBIT", details=batch(total="9999.00")
        )
        document = parse_camt053(build(statements=stmt(entries=entries)))
        statement = document.statements[0]
        self.assertEqual(
            statement.balance_identity.status, ReconciliationStatus.balanced
        )
        self.assertEqual(
            statement.reconciliation_status, ReconciliationStatus.unbalanced
        )

    def test_a_failing_balance_governs_even_when_corroborations_close(self):
        balances = bal("OPBD", "10000.00") + bal("CLBD", "11111.11", date="2026-02-28")
        statement = parse_camt053(
            build(
                statements=stmt(balances=balances, transactions_summary=summary())
            )
        ).statements[0]
        self.assertEqual(
            statement.summary_identity.status, ReconciliationStatus.balanced
        )
        self.assertEqual(
            statement.reconciliation_status, ReconciliationStatus.unbalanced
        )

    def test_an_unavailable_balance_governs_over_a_closing_summary(self):
        """The corroboration cannot supply a proof the mandatory check lacks."""
        statement = parse_camt053(
            build(
                statements=stmt(
                    balances=bal("CLBD", "12500.00", date="2026-02-28"),
                    transactions_summary=summary(),
                )
            )
        ).statements[0]
        self.assertEqual(
            statement.summary_identity.status, ReconciliationStatus.balanced
        )
        self.assertEqual(
            statement.reconciliation_status, ReconciliationStatus.unavailable
        )


class MultipleStatementTests(Camt053TestCase):
    def test_every_statement_is_parsed(self):
        document = parse_camt053(
            build(statements=stmt(identification="A") + stmt(identification="B"))
        )
        self.assertEqual(
            [s.identification for s in document.statements], ["A", "B"]
        )
        self.assertEqual(document.proof_class, ProofClass.p0)

    def test_one_broken_statement_governs_the_whole_message(self):
        broken = stmt(
            identification="B",
            balances=bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00")
            + bal(CAMT053_BALANCE_CLOSING_BOOKED, "9999.00"),
        )
        document = parse_camt053(build(statements=stmt(identification="A") + broken))

        self.assertEqual(
            document.statements[0].reconciliation_status, ReconciliationStatus.balanced
        )
        self.assertEqual(
            document.statements[1].reconciliation_status, ReconciliationStatus.unbalanced
        )
        self.assertEqual(document.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertEqual(document.proof_class, ProofClass.p3)

    def test_a_declining_statement_governs_over_a_balanced_one(self):
        document = parse_camt053(
            build(
                statements=stmt(identification="A")
                + stmt(identification="B", balances=bal(CAMT053_BALANCE_CLOSING_BOOKED, "1.00"))
            )
        )
        self.assertEqual(document.reconciliation_status, ReconciliationStatus.unavailable)
        self.assertEqual(document.proof_class, ProofClass.p3)


class ProofClassIntegrationTests(Camt053TestCase):
    """p0 is reachable only through arithmetic that closed, and nowhere else."""

    def test_p0_requires_a_passing_check(self):
        self.assertEqual(parse_camt053(build()).proof_class, ProofClass.p0)

    def test_every_non_balanced_outcome_lands_at_p3(self):
        cases = {
            ReconciliationStatus.unbalanced: stmt(
                balances=bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00")
                + bal(CAMT053_BALANCE_CLOSING_BOOKED, "1.00")
            ),
            ReconciliationStatus.unavailable: stmt(
                balances=bal(CAMT053_BALANCE_CLOSING_BOOKED, "12500.00")
            ),
        }
        for expected, statement in cases.items():
            with self.subTest(status=expected):
                document = parse_camt053(build(statements=statement))
                self.assertEqual(document.reconciliation_status, expected)
                self.assertEqual(document.proof_class, ProofClass.p3)

    def test_the_shape_is_fixed_and_cannot_be_supplied_by_a_caller(self):
        document = parse_camt053(build())
        self.assertEqual(document.source_shape, SourceShape.native_with_control_totals)
        with self.assertRaises(Exception):
            document.source_shape = SourceShape.unstructured_narrative

    def test_every_error_in_this_module_is_catchable_as_one_type(self):
        for exception in (
            Camt053MalformedDocumentError,
            NotACamt053Error,
            Camt053MissingElementError,
            Camt053AmountError,
            Camt053StatementCurrencyError,
        ):
            with self.subTest(exception=exception.__name__):
                self.assertTrue(issubclass(exception, Camt053Error))


class DeclaredConstantTests(Camt053TestCase):
    def test_the_balance_codes_are_the_iso_ones(self):
        self.assertEqual(CAMT053_BALANCE_OPENING_BOOKED, "OPBD")
        self.assertEqual(CAMT053_BALANCE_CLOSING_BOOKED, "CLBD")
        self.assertEqual(CAMT053_BALANCE_PREVIOUSLY_CLOSED_BOOKED, "PRCD")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

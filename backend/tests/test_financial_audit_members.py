"""Audit events as archive members: outside every snapshot limit, verified link by link, every member hashed."""
import gzip
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from postgres.models.financial_audit import FinancialAuditEvent
from services.financial import audit_members as M
from services.financial.export_comparison import (archive_audit_verification, archive_entry_hashes, compare_ledger_exports,
    read_verified_ledger_archive, read_verified_ledger_archive_file)
from services.financial.ledger_summary import LedgerSummaryError
from tests import test_financial_export_comparison as ledger_fixture


def events(case, count, filler=''):
    result, previous = [], '0' * 64
    for sequence in range(1, count + 1):
        payload = json.dumps(dict(schema_version='loupe.financial.audit_event/1', case_id=str(case), sequence=sequence,
                                  source_table='adjudications', operation='INSERT', after=dict(reason=filler or 'Synthetic')))
        digest = hashlib.sha256(bytes.fromhex(previous) + payload.encode()).hexdigest()
        result.append(dict(sequence=sequence, previous_sha256=previous, entry_sha256=digest, payload_text=payload))
        previous = digest
    return result


class Chain(unittest.TestCase):
    def setUp(self):
        self.case = uuid4()
        self.engine = create_engine('sqlite://')
        FinancialAuditEvent.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)

    def store(self, rows):
        self.db.add_all(FinancialAuditEvent(case_id=self.case, **row) for row in rows)
        self.db.commit()

    def held(self):
        return M.HeldAuditMembers(1024 ** 3)

    def capture(self, members=None):
        members = members if members is not None else self.held()
        return (*M.capture_audit_members(self.db, case_id=self.case, members=members), members)


class ChainOutsideTheDocument(Chain):
    def test_events_past_every_document_limit_stay_outside_the_document(self):
        rows = events(self.case, 25)
        self.store(rows)
        with patch('services.financial.audit_chain.MAX_AUDIT_EVENTS', 1), patch('services.financial.audit_chain.MAX_AUDIT_BYTES', 1):
            chain, listing, members = self.capture()
        self.assertNotIn('entries', chain)
        self.assertEqual((chain['verification']['event_count'], listing['event_count']), (25, 25))
        self.assertEqual(listing['head_sha256'], rows[-1]['entry_sha256'])
        self.assertEqual(chain['event_members'], [part['filename'] for part in listing['parts']])
        entries = list(M.iter_member_entries(members.read, listing))
        self.assertEqual(entries, rows)  # exact bytes, in order

    def test_a_member_stops_at_its_limit_and_the_parts_cover_every_event(self):
        rows = events(self.case, 40, 'x' * 1000)
        self.store(rows)
        with patch.object(M, 'MAX_AUDIT_MEMBER_BYTES', 5000):
            chain, listing, members = self.capture()
            self.assertGreater(len(listing['parts']), 1)
            self.assertTrue(all(part['content_bytes'] <= 5000 for part in listing['parts']))
            self.assertEqual(M.verify_audit_members(members.read, listing, case_id=self.case)['event_count'], 40)
        self.assertEqual(sum(part['events'] for part in listing['parts']), 40)

    def test_one_event_over_the_member_limit_is_refused_in_words(self):
        self.store(events(self.case, 2, 'x' * 1000))
        with patch.object(M, 'MAX_AUDIT_MEMBER_BYTES', 500), self.assertRaisesRegex(LedgerSummaryError, 'alone exceeds'):
            self.capture()

    def test_a_chain_gap_is_refused_and_keeps_no_member(self):
        rows = events(self.case, 6)
        del rows[3]
        self.store(rows)
        members = self.held()
        with self.assertRaisesRegex(LedgerSummaryError, 'chain gap'):
            self.capture(members)
        self.assertEqual(members.held, {})

    def test_an_edited_payload_is_refused(self):
        rows = events(self.case, 3)
        rows[1]['payload_text'] = rows[1]['payload_text'].replace('Synthetic', 'Changed')
        self.store(rows)
        with self.assertRaisesRegex(LedgerSummaryError, 'does not match'):
            self.capture()

    def test_held_members_refuse_past_one_request_and_name_the_way_on(self):
        self.store(events(self.case, 3))
        with self.assertRaisesRegex(LedgerSummaryError, 'background run'):
            self.capture(M.HeldAuditMembers(1))


class ClosedMembersAreKept(Chain):
    def test_a_stored_member_is_not_read_again_and_the_chain_continues_from_it(self):
        rows = events(self.case, 40, 'x' * 1000)
        self.store(rows)
        with tempfile.TemporaryDirectory() as folder, patch.object(M, 'MAX_AUDIT_MEMBER_BYTES', 5000):
            first = M.StoredAuditMembers(folder)
            self.assertTrue(M.pack_audit_members(self.db, case_id=self.case, members=first, closes=1))
            self.assertEqual(len(first.closed), 1)
            with patch('services.financial.audit_members.AuditChainVerifier.add', wraps=None) as add:
                add.side_effect = None
                again = M.StoredAuditMembers(folder)
                self.assertEqual(again.closed, first.closed)
            count = first.closed[0]['events']
            seen = []
            real = M.AuditChainVerifier.add
            with patch('services.financial.audit_members.AuditChainVerifier.add', lambda self, entry: (seen.append(entry['sequence']), real(self, entry))[1]):
                _, listing, members = self.capture(again)
            self.assertEqual(seen[0], count + 1)
            self.assertEqual(listing['event_count'], 40)
            self.assertEqual(M.verify_audit_members(members.read, listing, case_id=self.case)['head_sha256'], rows[-1]['entry_sha256'])
            self.assertEqual(listing['parts'][-1]['filename'], M.member_name(len(listing['parts'])))

    def test_events_past_the_last_closed_member_join_the_next_export(self):
        rows = events(self.case, 9)
        self.store(rows[:5])
        with tempfile.TemporaryDirectory() as folder:
            _, listing, _ = self.capture(M.StoredAuditMembers(folder))
            self.assertEqual(listing['event_count'], 5)
            self.store(rows[5:])
            _, listing, members = self.capture(M.StoredAuditMembers(folder))
            self.assertEqual(listing['event_count'], 9)
            self.assertEqual(listing['head_sha256'], rows[-1]['entry_sha256'])

    def test_a_kept_member_that_no_longer_matches_the_chain_is_read_again(self):
        rows = events(self.case, 40, 'x' * 1000)
        self.store(rows)
        with tempfile.TemporaryDirectory() as folder, patch.object(M, 'MAX_AUDIT_MEMBER_BYTES', 5000):
            members = M.StoredAuditMembers(folder)
            M.pack_audit_members(self.db, case_id=self.case, members=members, closes=1)
            members.closed[0]['head_sha256'] = 'a' * 64
            _, listing, members = self.capture(members)
            self.assertEqual(M.verify_audit_members(members.read, listing, case_id=self.case)['event_count'], 40)

    def test_a_listing_line_cut_by_a_kill_is_dropped(self):
        rows = events(self.case, 40, 'x' * 1000)
        self.store(rows)
        with tempfile.TemporaryDirectory() as folder, patch.object(M, 'MAX_AUDIT_MEMBER_BYTES', 5000):
            members = M.StoredAuditMembers(folder)
            M.pack_audit_members(self.db, case_id=self.case, members=members, closes=2)
            listing = Path(folder) / 'parts.jsonl'
            listing.write_text(listing.read_text()[:-20])
            self.assertEqual(len(M.StoredAuditMembers(folder).closed), 1)

    def test_a_kept_member_changed_on_disk_is_refused(self):
        self.store(events(self.case, 40, 'x' * 1000))
        with tempfile.TemporaryDirectory() as folder, patch.object(M, 'MAX_AUDIT_MEMBER_BYTES', 5000):
            members = M.StoredAuditMembers(folder)
            M.pack_audit_members(self.db, case_id=self.case, members=members, closes=1)
            path = Path(folder) / members.closed[0]['filename']
            path.write_bytes(path.read_bytes()[:-1] + b'x')
            with self.assertRaisesRegex(LedgerSummaryError, 'does not match its digest'):
                members.read(path.name)


class Archive(Chain):
    """The real packaging: ``ledger_export_archive`` over a captured document with its members."""

    def export(self, rows, *, wider=True):
        from services.financial.ledger_snapshot import LedgerExport, LedgerSnapshot, ledger_export_archive
        fixture = ledger_fixture.ExportComparisonTests()
        document = fixture.document()
        document['ledger']['case_id'] = str(self.case)
        self.store(rows)
        chain, listing, members = self.capture()
        if wider:
            document['case_financial_history'] = dict(audit_chain=chain)
        raw = json.dumps(document)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        manifest = dict(schema='loupe.financial.ledger_export_manifest/1', digest_covers='ledger_snapshot_json_utf8', document_sha256=digest,
                        byte_count=len(raw.encode()), case_id=str(self.case), snapshot_schema=document['schema'], audit_events=listing)
        export = LedgerExport(LedgerSnapshot(raw, digest, len(raw.encode())), json.dumps(manifest), audit_members=members)
        support = dict(completeness='incomplete_expert_packet', packet_parts=[], packet_sentence='s', schema_version='loupe.financial.expert_support/1',
                       case_id=str(self.case), derived_from_sha256=digest)
        with patch('services.financial.ledger_snapshot.render_ledger_report', return_value='<h1>x</h1>'), \
                patch('services.financial.expert_support.build_expert_support', return_value=support):
            return export, ledger_export_archive(export), ledger_export_archive

    def test_the_manifest_hashes_every_member(self):
        rows = events(self.case, 12)
        _, content, _ = self.export(rows)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            listed = {part['filename']: part['sha256'] for part in manifest['audit_events']['parts']}
            listed.update({manifest[key]['filename']: manifest[key]['sha256'] for key in ('report', 'expert_support')})
            listed['ledger-snapshot.json'] = manifest['document_sha256']
            self.assertEqual(set(archive.namelist()), set(listed) | {'manifest.json'})
            for name, digest in listed.items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest, name)
        saved = read_verified_ledger_archive(content)
        self.assertEqual(saved['audit_verification']['event_count'], 12)
        self.assertEqual(saved['audit_verification']['head_sha256'], rows[-1]['entry_sha256'])
        self.assertEqual(archive_entry_hashes(io.BytesIO(content)), [row['entry_sha256'] for row in rows])

    def rewrite(self, content, change):
        target = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(target, 'w') as out:
            members = {name: source.read(name) for name in source.namelist()}
            change(members)
            for name, data in members.items():
                out.writestr(name, data)
        return target.getvalue()

    def test_a_changed_removed_or_unlisted_member_is_refused(self):
        _, content, _ = self.export(events(self.case, 5))
        part = M.member_name(1)
        def edit(members):
            lines = gzip.decompress(members[part]).splitlines(keepends=True)
            members[part] = gzip.compress(b''.join(lines[:-1]))
        for change in (edit, lambda members: members.pop(part), lambda members: members.update({'audit-events-part-00009.jsonl.gz': b'x'})):
            with self.assertRaises(LedgerSummaryError):
                read_verified_ledger_archive(self.rewrite(content, change))

    def test_a_listing_rewritten_to_match_an_edited_member_still_fails_the_chain(self):
        _, content, _ = self.export(events(self.case, 5))
        part = M.member_name(1)
        def forge(members):
            lines = gzip.decompress(members[part]).splitlines(keepends=True)
            entry = json.loads(lines[1])
            entry['payload_text'] = entry['payload_text'].replace('Synthetic', 'Changed')
            lines[1] = (json.dumps(entry) + '\n').encode()
            data = gzip.compress(b''.join(lines))
            manifest = json.loads(members['manifest.json'])
            listed = manifest['audit_events']['parts'][0]
            listed.update(sha256=hashlib.sha256(data).hexdigest(), byte_count=len(data), content_bytes=sum(map(len, lines)))
            members[part], members['manifest.json'] = data, json.dumps(manifest).encode()
        with self.assertRaisesRegex(LedgerSummaryError, 'does not match'):
            read_verified_ledger_archive(self.rewrite(content, forge))

    def test_events_listed_without_the_document_naming_them_are_refused(self):
        _, content, _ = self.export(events(self.case, 3), wider=False)
        with self.assertRaises(LedgerSummaryError):
            read_verified_ledger_archive(content)

    def test_a_very_large_archive_is_refused_in_words_where_it_cannot_be_verified_on_a_page(self):
        _, content, _ = self.export(events(self.case, 5))
        with self.assertRaisesRegex(LedgerSummaryError, 'more than can be verified on this page'):
            read_verified_ledger_archive_file(io.BytesIO(content), max_audit_payload_bytes=1)


    def test_a_record_too_large_for_a_page_is_named_not_called_inconsistent(self):
        _, content, _ = self.export(events(self.case, 5))
        with self.assertRaisesRegex(LedgerSummaryError, 'more than can be opened on this page'):
            read_verified_ledger_archive_file(io.BytesIO(content), max_held_bytes=10)


class OldLayout(Chain):
    """An archive saved before the events moved out still opens, verifies and compares."""

    def old_archive(self, rows, document=None):
        from services.financial.audit_chain import capture_financial_audit_chain, verify_financial_audit_chain
        fixture = ledger_fixture.ExportComparisonTests()
        document = document or fixture.document()
        document['ledger']['case_id'] = str(self.case)
        document['case_financial_history'] = dict(audit_chain=dict(schema_version='loupe.financial.audit_chain/1', case_id=str(self.case),
            entries=rows, verification=verify_financial_audit_chain(rows, case_id=self.case)))
        return fixture.archive(document), document

    def test_an_old_archive_opens_and_its_events_verify(self):
        rows = events(self.case, 4)
        content, _ = self.old_archive(rows)
        saved = read_verified_ledger_archive(content)
        self.assertIsNone(saved['audit_verification'])
        self.assertEqual(archive_audit_verification(saved)['head_sha256'], rows[-1]['entry_sha256'])
        self.assertEqual(archive_entry_hashes(io.BytesIO(content)), [row['entry_sha256'] for row in rows])

    def test_an_edited_old_archive_is_refused(self):
        rows = events(self.case, 4)
        content, document = self.old_archive(rows)
        document['case_financial_history']['audit_chain']['verification']['event_count'] = 3
        edited = ledger_fixture.ExportComparisonTests().archive(document)
        with self.assertRaisesRegex(LedgerSummaryError, 'differs from its chain'):
            archive_audit_verification(read_verified_ledger_archive(edited))

    def test_old_and_new_layouts_of_one_capture_compare_as_the_same_content(self):
        rows = events(self.case, 4)
        old, document = self.old_archive(rows)
        new = dict(document)
        members = self.held()
        self.store(rows)
        chain, listing, members = self.capture(members)
        new['case_financial_history'] = dict(audit_chain={**chain})
        fixture = ledger_fixture.ExportComparisonTests()
        target = io.BytesIO()
        raw_archive = fixture.archive(new, manifest_changes=dict(audit_events=listing))
        with zipfile.ZipFile(io.BytesIO(raw_archive)) as source, zipfile.ZipFile(target, 'w') as out:
            for name in source.namelist():
                out.writestr(name, source.read(name))
            for part in listing['parts']:
                out.writestr(part['filename'], members.read(part['filename']))
        compared = compare_ledger_exports(old, target.getvalue())
        self.assertEqual(compared['status'], 'same_captured_content')
        self.assertEqual(compared['other_sections_changed'], [])


class PreparedExportReceipt(unittest.TestCase):
    def test_a_stored_file_is_recorded_by_its_digest_without_being_read(self):
        from services.financial.export_audit import record_prepared_export
        actor = dict(id=str(uuid4()), name='A', email='a@example.test')
        for stored in (('short', 5), ('a' * 64, 0), None):
            with self.assertRaisesRegex(ValueError, 'Invalid prepared export'):
                record_prepared_export(None, case_id=uuid4(), kind='ledger_exports', stored=stored, scope={}, actor=actor)

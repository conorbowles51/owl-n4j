"""A case's audit events as numbered archive members, closed once and never held whole.

BNB2 has 262,753 events and 5.4 GB of payload, OPDMD62 50,156 and 1.8 GB (measured 5 Nov 2026): no snapshot document can
carry them, and no process here should hold them. Events go from the database to gzip members of JSON lines, each
verified as it passes. A member closes at 64 MiB of lines, so where members end depends only on the chain: the chain is
append-only and each hash binds everything before it, so a closed member stays true and is kept for the case. A
background export therefore packs the events first, in short reads, continues from the last closed member after a
restart, and in its own consistent read only checks the head of what is kept and adds the events since.

The snapshot keeps the count, the head hash and the member names; the manifest lists each member's digest, size and
sequence range. Limits apply to one member. A capture that refuses publishes nothing.
"""
import gzip
import hashlib
import io
import json
import os
import shutil
from pathlib import Path

from sqlalchemy import func, select

from services.financial.audit_chain import AuditChainVerifier, audit_chain_terms
from services.financial.ledger_summary import LedgerSummaryError

SCHEMA = 'loupe.financial.audit_members/1'
CHAIN_SCHEMA = 'loupe.financial.audit_chain/2'
MAX_AUDIT_MEMBER_BYTES = 64 * 1024 * 1024
# Rows the server-side cursor holds at once. A statement's event reaches 4.7 MB (BNB2), 760 KB on average.
_FETCH = 50
_LISTING = 'parts.jsonl'


def member_name(number):
    return 'audit-events-part-%05d.jsonl.gz' % number


class HeldAuditMembers:
    """Members of one export held in memory, for an export built inside one request; refused in words at the limit."""

    def __init__(self, limit):
        self.limit, self.total = limit, 0
        self.closed, self.held = [], {}

    def keep(self, part, data):
        self.total += len(data)
        if self.total > self.limit:
            raise LedgerSummaryError('The audit events of this case do not fit one request. Prepare the export as a '
                                     'background run. No partial export was produced.')
        self.held[part['filename']] = data
        self.closed.append(part)

    def tail(self, part, data):
        self.keep(part, data)

    def read(self, name):
        return self.held[name]

    def clear(self):
        self.closed, self.held, self.total = [], {}, 0


class StoredAuditMembers:
    """Closed members of one case on disk, kept across runs; the open end of the chain stays with the run."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.utime(self.directory)  # in use: kept from the fourteen-day clearing of unused folders
        self.closed, self.tail_parts, self.tail_bytes = [], [], {}
        listing = self.directory / _LISTING
        if listing.exists():
            for line in listing.read_text().splitlines():
                try:
                    part = json.loads(line)
                except ValueError:  # a line cut short by a kill: what follows it was never written
                    break
                if not (self.directory / part['filename']).is_file():
                    break
                self.closed.append(part)
            listing.write_text(''.join(json.dumps(part, sort_keys=True, separators=(',', ':')) + '\n' for part in self.closed))

    def keep(self, part, data):
        waiting = self.directory / (part['filename'] + '.tmp')
        waiting.write_bytes(data)
        os.replace(waiting, self.directory / part['filename'])
        with open(self.directory / _LISTING, 'a') as out:
            out.write(json.dumps(part, sort_keys=True, separators=(',', ':')) + '\n')
        self.closed.append(part)

    def tail(self, part, data):
        self.tail_parts.append(part)
        self.tail_bytes[part['filename']] = data

    def read(self, name):
        if name in self.tail_bytes:
            return self.tail_bytes[name]
        data = (self.directory / name).read_bytes()
        expected = next(part for part in self.closed if part['filename'] == name)
        if hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise LedgerSummaryError('A stored audit part does not match its digest. No partial export was produced. Run it again.')
        return data

    def clear(self):
        shutil.rmtree(self.directory, ignore_errors=True)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.closed = []


def _gzip(lines):
    stream = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as out:
        out.writelines(lines)
    return stream.getvalue()


def pack_audit_members(session, *, case_id, members, progress=None, closes=None):
    """Close members from the events after the last closed one, at most ``closes`` in this read. True when there may
    be more to close; the events past the last closed member are left for the export's own read."""
    return _read_events(session, case_id, members, progress, closes)


def capture_audit_members(session, *, case_id, members, progress=None):
    """(chain description for the document, listing for the manifest): the closed members, then the events since,
    which become the last member, all verified in this read."""
    return _read_events(session, case_id, members, progress, None, final=True)


def _read_events(session, case_id, members, progress, closes, final=False):
    from postgres.models.financial_audit import FinancialAuditEvent as Event
    total = session.scalar(select(func.count()).select_from(Event).where(Event.case_id == case_id))
    verifier = AuditChainVerifier(case_id)
    if members.closed:
        last = members.closed[-1]
        found = session.scalar(select(Event.entry_sha256).where(Event.case_id == case_id, Event.sequence == last['last_sequence']))
        if found == last['head_sha256']:
            verifier.previous, verifier.count, verifier.bytes = last['head_sha256'], last['last_sequence'], last['payload_bytes']
        else:
            members.clear()  # read from the start: the events themselves then say what is wrong

    def close(lines, first, keep):
        data = _gzip(lines)
        part = dict(filename=member_name(len(members.closed) + len(getattr(members, 'tail_parts', ())) + 1), sha256=hashlib.sha256(data).hexdigest(),
                    byte_count=len(data), content_bytes=sum(map(len, lines)), events=len(lines), first_sequence=first,
                    last_sequence=verifier.count, head_sha256=verifier.previous, payload_bytes=verifier.bytes)
        keep(part, data)

    lines, size, first = [], 0, verifier.count + 1
    rows = session.execute(select(Event.sequence, Event.previous_sha256, Event.entry_sha256, Event.payload_text)
        .where(Event.case_id == case_id, Event.sequence > verifier.count).order_by(Event.sequence).execution_options(yield_per=_FETCH))
    for sequence, previous, entry, payload in rows:
        item = dict(sequence=sequence, previous_sha256=previous, entry_sha256=entry, payload_text=payload)
        line = (json.dumps(item, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode()
        if len(line) > MAX_AUDIT_MEMBER_BYTES:
            raise LedgerSummaryError('Audit event %d alone exceeds the 64 MiB limit of one archive member. '
                                     'No partial export was produced.' % sequence)
        if size + len(line) > MAX_AUDIT_MEMBER_BYTES:
            close(lines, first, members.keep)
            lines, size, first = [], 0, sequence
            if closes is not None:
                closes -= 1
                if closes == 0:
                    return True
        verifier.add(item)
        lines.append(line)
        size += len(line)
        if progress is not None and verifier.count % 100 == 0:
            progress(verifier.count, total)
    if not final:
        return False
    if lines:
        close(lines, first, members.tail)
    if verifier.count != total:
        raise LedgerSummaryError('The audit events read differ from their count; no partial export was produced.')
    verification = verifier.result()
    parts = [*members.closed, *getattr(members, 'tail_parts', ())]
    listing = dict(schema=SCHEMA, event_count=verifier.count, head_sha256=verification['head_sha256'], status=verification['status'],
                   payload_bytes=verifier.bytes, member_limit_bytes=MAX_AUDIT_MEMBER_BYTES,
                   parts=[{key: part[key] for key in ('filename', 'sha256', 'byte_count', 'content_bytes', 'events', 'first_sequence', 'last_sequence')} for part in parts])
    chain = dict(schema_version=CHAIN_SCHEMA, case_id=str(case_id), verification=verification,
                 event_members=[part['filename'] for part in parts], event_format='gzip of one JSON line per event, in sequence order: '
                 'sequence, previous_sha256, entry_sha256, payload_text. The manifest gives each member\'s digest.', **audit_chain_terms())
    return chain, listing


def iter_member_entries(read_member, listing):
    """Every event of the listed members in order; each member's digest, size and range are checked against the listing."""
    if not isinstance(listing, dict) or listing.get('schema') != SCHEMA or not isinstance(listing.get('parts'), list):
        raise ValueError('Audit member listing is not recognised.')
    next_sequence = 1
    for number, part in enumerate(listing['parts'], 1):
        if (part['filename'] != member_name(number) or part['first_sequence'] != next_sequence
                or part['byte_count'] > MAX_AUDIT_MEMBER_BYTES or part['content_bytes'] > MAX_AUDIT_MEMBER_BYTES):
            raise ValueError('Audit members are out of order or over their limit.')
        data = read_member(part['filename'])
        if len(data) != part['byte_count'] or hashlib.sha256(data).hexdigest() != part['sha256']:
            raise ValueError('Audit member differs from its manifest digest or size.')
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            content = stream.read(MAX_AUDIT_MEMBER_BYTES + 1)
        if len(content) != part['content_bytes']:
            raise ValueError('Audit member differs from its manifest size.')
        lines = content.splitlines(keepends=True)
        if len(lines) != part['events'] or part['last_sequence'] != part['first_sequence'] + len(lines) - 1:
            raise ValueError('Audit member sequence range differs from its events.')
        for line in lines:
            yield json.loads(line)
        next_sequence = part['last_sequence'] + 1


def verify_audit_members(read_member, listing, *, case_id, progress=None):
    """Read every event back: member digests, links, each payload re-hashed, and the listed count and head."""
    verifier = AuditChainVerifier(case_id)
    for entry in iter_member_entries(read_member, listing):
        verifier.add(entry)
        if progress is not None and verifier.count % 1000 == 0:
            progress(verifier.count)
    verification = verifier.result()
    if verification['event_count'] != listing['event_count'] or verification['head_sha256'] != listing['head_sha256']:
        raise ValueError('Audit members differ from their listed count or head.')
    return verification

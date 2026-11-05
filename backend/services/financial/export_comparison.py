"""Verify two retained ledger bundles and explain their captured differences."""
import hashlib
import io
import json
import os
import re
from pathlib import PurePosixPath
from zipfile import ZipFile, BadZipFile

from services.financial.audit_chain import verify_financial_audit_chain
from services.financial.audit_members import MAX_AUDIT_MEMBER_BYTES, iter_member_entries, verify_audit_members
from services.financial.ledger_snapshot import (MAX_EXPORT_BYTES, MAX_LEDGER_SNAPSHOT_BYTES, MAX_LEDGER_ARCHIVE_BYTES,
    MAX_REPORT_BYTES, MAX_RUN_ARCHIVE_HELD_BYTES)
from services.financial.ledger_summary import LedgerSummaryError

MAX_ARCHIVE_BYTES = MAX_LEDGER_ARCHIVE_BYTES
# Audit event members are read one line at a time, so they do not count against the bytes held for a comparison.
MAX_ARCHIVE_MEMBERS = 4096
# A comparison runs in a request of the live service, so it holds both documents and re-hashes both chains there.
MAX_COMPARE_HELD_BYTES = 256 * 1024 * 1024
MAX_COMPARE_AUDIT_BYTES = 256 * 1024 * 1024
AUDIT_MEMBER = re.compile(r'audit-events-part-[0-9]{5}\.jsonl\.gz')


class TooLargeToCheck(LedgerSummaryError):
    """Stated to the user as it is; the archive itself is not in question."""


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Repeated JSON keys.')
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError('Non-finite JSON number.')


def _json(content):
    return json.loads(content, object_pairs_hook=_unique, parse_constant=_nonfinite)


def _same(a, b):
    return json.dumps(a, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) == json.dumps(b, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def read_verified_ledger_archive(content):
    """Check every declared member without extracting any file to disk.

    These are internal consistency checks, not authentication of the manifest.
    """
    if not isinstance(content, bytes) or len(content) > MAX_ARCHIVE_BYTES:
        raise LedgerSummaryError('Ledger archive exceeds 128 MiB or is not bytes.')
    return read_verified_ledger_archive_file(io.BytesIO(content), max_held_bytes=MAX_ARCHIVE_BYTES,
                                             max_snapshot_bytes=MAX_LEDGER_SNAPSHOT_BYTES)


def read_verified_ledger_archive_file(source, *, max_held_bytes=MAX_RUN_ARCHIVE_HELD_BYTES, max_snapshot_bytes=MAX_RUN_ARCHIVE_HELD_BYTES,
                                      max_audit_payload_bytes=None, audit_progress=None):
    """The same checks over a path or seekable file, for an archive too large to hold: its audit event members are
    read one at a time, and every other member stays within ``max_held_bytes`` together."""
    expert_support_content = None
    audit_verification = None
    try:
        with ZipFile(source) as archive:
            infos = archive.infolist()
            names = {entry.filename for entry in infos}
            audit_sizes = sum(entry.file_size for entry in infos if AUDIT_MEMBER.fullmatch(entry.filename))
            held_size = sum(entry.file_size for entry in infos) - audit_sizes
            if held_size > max_held_bytes:
                raise TooLargeToCheck('This export holds %d MB of ledger records, more than can be opened on this page (%d MB). '
                                      'Nothing was compared.' % (held_size // 1024 ** 2, max_held_bytes // 1024 ** 2))
            if len(infos) != len(names) or len(infos) > MAX_ARCHIVE_MEMBERS:
                raise ValueError('Archive member count, duplicates or uncompressed size exceeds the limit.')
            for name in names:
                if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or '\\' in name:
                    raise ValueError('Unsafe archive path.')

            def read(name, limit=MAX_EXPORT_BYTES):
                if archive.getinfo(name).file_size > limit:
                    raise ValueError('Archive member exceeds its limit.')
                with archive.open(name) as source:
                    data = source.read(limit + 1)
                if len(data) > limit:
                    raise ValueError('Archive member exceeds its limit.')
                return data

            manifest = _json(read('manifest.json'))
            raw = read('ledger-snapshot.json', max_snapshot_bytes)
            document = _json(raw)
            if (manifest['schema'] != 'loupe.financial.ledger_export_manifest/1'
                    or manifest['digest_covers'] != 'ledger_snapshot_json_utf8'
                    or manifest['document_sha256'] != hashlib.sha256(raw).hexdigest()
                    or type(manifest['byte_count']) is not int or manifest['byte_count'] != len(raw)
                    or document.get('export_ready') is not True
                    or document['schema'] not in ('loupe.financial.ledger_snapshot/2', 'loupe.financial.ledger_snapshot/3')
                    or document['ledger']['case_id'] != manifest['case_id']
                    or document['schema'] != manifest['snapshot_schema']):
                raise ValueError('Captured snapshot or case binding differs from manifest.')
            expected = {'manifest.json', 'ledger-snapshot.json'}
            listing = manifest.get('audit_events')
            chain = (document.get('case_financial_history') or {}).get('audit_chain')
            if (listing is not None) != (chain is not None and 'event_members' in chain):
                raise ValueError('Audit events and their listing differ.')
            if listing is not None:
                listed = [part['filename'] for part in listing['parts']]
                if chain['event_members'] != listed or len(set(listed)) != len(listed):
                    raise ValueError('Audit member names differ between the snapshot and the manifest.')
                if max_audit_payload_bytes is not None and listing['payload_bytes'] > max_audit_payload_bytes:
                    raise TooLargeToCheck('This export holds %.1f GB of audit events, more than can be verified on this page (%.1f GB). '
                                        'Nothing was compared.' % (listing['payload_bytes'] / 1e9, max_audit_payload_bytes / 1e9))
                audit_verification = verify_audit_members(lambda name: read(name, MAX_AUDIT_MEMBER_BYTES), listing,
                                                          case_id=document['ledger']['case_id'], progress=audit_progress)
                if any(chain['verification'].get(key) != audit_verification[key] for key in ('case_id', 'event_count', 'head_sha256', 'status')):
                    raise ValueError('Captured audit summary differs from its members.')
                expected.update(listed)
            entries = [(manifest['report'], 'filename', MAX_REPORT_BYTES)]
            for key in ('pdf_report', 'expert_support'):
                if key in manifest:
                    entries.append((manifest[key], 'filename', MAX_REPORT_BYTES))
            entries.extend((item, 'archive_path', 64 * 1024 * 1024) for item in manifest.get('source_files', []))
            for entry, path_key, limit in entries:
                name = entry[path_key]
                if name in expected:
                    raise ValueError('Manifest repeats an archive member.')
                expected.add(name)
                data = read(name, limit)
                if (type(entry['byte_count']) is not int or len(data) != entry['byte_count']
                        or hashlib.sha256(data).hexdigest() != entry['sha256']):
                    raise ValueError('Archive member differs from its manifest digest or size.')
                if path_key == 'filename' and entry['derived_from_sha256'] != manifest['document_sha256']:
                    raise ValueError('Derived report refers to a different snapshot.')
                if entry is manifest.get('expert_support'):
                    support = _json(data)
                    if (not isinstance(support, dict)
                            or support.get('schema_version') != 'loupe.financial.expert_support/1'
                            or support.get('case_id') != manifest['case_id']
                            or support.get('derived_from_sha256') != manifest['document_sha256']):
                        raise ValueError('Expert support refers to a different case or snapshot.')
                    expert_support_content = data
            if names != expected:
                raise ValueError('Archive has unlisted or missing members.')
    except TooLargeToCheck:
        raise
    except LedgerSummaryError as exc:
        raise LedgerSummaryError('Ledger archive audit events do not verify: %s Comparison refused.' % exc) from exc
    except (BadZipFile, KeyError, TypeError, ValueError, UnicodeError, RecursionError, OSError, RuntimeError) as exc:
        raise LedgerSummaryError('Ledger archive is inconsistent or unsupported; comparison refused.') from exc
    return dict(document=document, manifest=manifest, archive_sha256=_file_sha256(source),
                expert_support_content=expert_support_content, audit_verification=audit_verification)


def _file_sha256(source):
    digest = hashlib.sha256()
    if isinstance(source, (str, os.PathLike)):
        with open(source, 'rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest()
    source.seek(0)
    for block in iter(lambda: source.read(1024 * 1024), b''):
        digest.update(block)
    return digest.hexdigest()


def archive_audit_verification(saved):
    """The verified chain of an archive read above, in either layout: events as members, or inside the snapshot of an
    export made before they moved out. None when no wider history was selected."""
    if saved['audit_verification'] is not None:
        return saved['audit_verification']
    document = saved['document']
    chain = (document.get('case_financial_history') or {}).get('audit_chain')
    if not chain:
        return None
    verification = verify_financial_audit_chain(chain['entries'], case_id=document['ledger']['case_id'])
    if any(chain['verification'].get(key) != verification[key] for key in ('case_id', 'event_count', 'head_sha256', 'status')):
        raise LedgerSummaryError('Captured ledger audit summary differs from its chain.')
    return verification


def archive_entry_hashes(source):
    """Each captured event's hash in sequence order, from an archive already verified, in either layout."""
    with ZipFile(source) as archive:
        listing = _json(archive.read('manifest.json')).get('audit_events')
        if listing is not None:
            return [entry['entry_sha256'] for entry in iter_member_entries(archive.read, listing)]
        chain = _json(archive.read('ledger-snapshot.json'))['case_financial_history']['audit_chain']
        return [entry['entry_sha256'] for entry in chain['entries']]


def _without_event_layout(document):
    """Where an export keeps its audit events is packaging: the verified count and head are what it captured."""
    chain = (document.get('case_financial_history') or {}).get('audit_chain')
    if not chain:
        return document
    kept = {key: chain.get('verification', {}).get(key) for key in ('case_id', 'event_count', 'head_sha256', 'status')}
    return {**document, 'case_financial_history': {**document['case_financial_history'], 'audit_chain': kept,
                                                   'schema_version': 'case_review_history'}}


def _index(records, key):
    indexed = {}
    for record in records:
        identity = key(record)
        if not isinstance(identity, str) or not identity or identity in indexed:
            raise LedgerSummaryError('Captured records have missing or repeated identifiers.')
        indexed[identity] = record
    return indexed


def _paths(a, b, prefix=''):
    result = []
    if type(a) is dict and type(b) is dict:
        for key in sorted(a.keys() | b.keys()):
            path = prefix + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in a or key not in b:
                result.append(path)
            elif not _same(a[key], b[key]):
                result.extend(_paths(a[key], b[key], path))
    elif type(a) is list and type(b) is list:
        for index in range(max(len(a), len(b))):
            path = prefix + '/' + str(index)
            if index >= len(a) or index >= len(b):
                result.append(path)
            elif not _same(a[index], b[index]):
                result.extend(_paths(a[index], b[index], path))
    elif not _same(a, b):
        result.append(prefix)
    return result


def _numbers_comparable(before, after):
    """An export taken before payments had printable numbers (FEAT-006, 4 Nov 2026) has no txn_number; adding the
    number is not a change to the payment, so it is left out of the comparison when either side lacks it."""
    def numbered(readings):
        return any('txn_number' in (reading.get('row') or {}) for reading in readings)
    if numbered(before) and numbered(after):
        return before, after
    strip = lambda readings: [{**reading, 'row': {k: v for k, v in (reading.get('row') or {}).items() if k != 'txn_number'}}
                              for reading in readings]  # noqa: E731
    return strip(before), strip(after)


def _changes(before, after, key):
    a, b = _index(before, key), _index(after, key)
    changed = []
    for identity in sorted(a.keys() & b.keys()):
        if not _same(a[identity], b[identity]):
            paths = _paths(a[identity], b[identity])
            changed.append(dict(id=identity, changed_paths=paths[:100], changed_path_count=len(paths), paths_truncated=len(paths) > 100))
    return dict(added=sorted(b.keys() - a.keys()), removed=sorted(a.keys() - b.keys()), changed=changed,
                captured_order_changed=list(a) != list(b))


def _read_for_comparison(source):
    if isinstance(source, bytes):
        return read_verified_ledger_archive(source)
    return read_verified_ledger_archive_file(source, max_held_bytes=MAX_COMPARE_HELD_BYTES, max_snapshot_bytes=MAX_COMPARE_HELD_BYTES,
                                             max_audit_payload_bytes=MAX_COMPARE_AUDIT_BYTES)


def compare_ledger_exports(before, after, *, expected_case_id=None):
    first, second = _read_for_comparison(before), _read_for_comparison(after)
    archive_audit_verification(first), archive_audit_verification(second)
    a, b = _without_event_layout(first['document']), _without_event_layout(second['document'])
    if a['ledger']['case_id'] != b['ledger']['case_id']:
        raise LedgerSummaryError('Compare exports from the same case.')
    if expected_case_id is not None and a['ledger']['case_id'] != str(expected_case_id):
        raise LedgerSummaryError('Selected exports belong to a different case.')
    def scope(document):
        return {**{key:document['ledger'].get(key) for key in ('case_id', 'account_id', 'start_date', 'end_date', 'included_classes')},
                'table_filters':(document.get('table_view') or {}).get('filters'),
                'wider_case_history_included':'case_financial_history' in document}
    scope_changed = not _same(scope(a), scope(b))
    reviews = {}
    for section in ('mappings', 'candidates', 'reviews', 'review_states', 'finalizations', 'transaction_links'):
        def identity(record):
            if section == 'review_states': return record['candidate_id']
            if section == 'transaction_links': return record['finalization_id'] + '/' + record['candidate_id']
            return record['id']
        reviews[section] = _changes((a.get('pdf_review_history') or {}).get(section, []), (b.get('pdf_review_history') or {}).get(section, []), identity)
    ignored = {'export_context'}
    content_changed = not _same({k:v for k,v in a.items() if k not in ignored}, {k:v for k,v in b.items() if k not in ignored})
    summary_paths = _paths({k:v for k,v in a['ledger'].items() if k != 'readings'}, {k:v for k,v in b['ledger'].items() if k != 'readings'})
    manifest_paths = _paths(first['manifest'], second['manifest'])
    result = dict(schema_version='loupe.financial.export_comparison/1', case_id=a['ledger']['case_id'],
        status='scope_changed' if scope_changed else 'captured_content_changed' if content_changed else 'same_captured_content',
        before=dict(archive_sha256=first['archive_sha256'], snapshot_sha256=first['manifest']['document_sha256'], generated_at=first['manifest'].get('generated_at'), code_version=first['manifest'].get('code_version')),
        after=dict(archive_sha256=second['archive_sha256'], snapshot_sha256=second['manifest']['document_sha256'], generated_at=second['manifest'].get('generated_at'), code_version=second['manifest'].get('code_version')),
        scope=dict(changed=scope_changed, before=scope(a), after=scope(b)),
        readings=_changes(*_numbers_comparable(a['ledger']['readings'], b['ledger']['readings']), lambda reading:reading['row']['key']),
        decisions=_changes(a.get('decisions', []), b.get('decisions', []), lambda record:record['id']),
        pdf_review_history=reviews,
        ledger_summary_fields_changed=summary_paths[:100], ledger_summary_field_change_count=len(summary_paths), ledger_summary_paths_truncated=len(summary_paths) > 100,
        other_sections_changed=[key for key in sorted(a.keys() | b.keys()) if key not in {'ledger','decisions','pdf_review_history','export_context'} and (key not in a or key not in b or not _same(a[key], b[key]))],
        export_preparation_changed=not _same(a.get('export_context'), b.get('export_context')),
        packaging_or_generation_changed=not _same(first['manifest'], second['manifest']),
        manifest_fields_changed=manifest_paths[:100], manifest_field_change_count=len(manifest_paths), manifest_paths_truncated=len(manifest_paths) > 100,
        limitation='Differences describe these captured exports, not their cause or the truth of source evidence. Changed filters can change row membership without a data edit. Preparation timestamps/actors/markings are separate from captured content. All listed member hashes are checked against each bundle manifest; this does not authenticate authorship or custody. The comparison uses supplied archives without loading live ledger readings or calling a provider.')
    if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > MAX_EXPORT_BYTES:
        raise LedgerSummaryError('Comparison exceeds 16 MiB; no partial report produced.')
    return result

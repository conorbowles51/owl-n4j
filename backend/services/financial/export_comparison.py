"""Verify two retained ledger bundles and explain their captured differences."""
import hashlib
import io
import json
from pathlib import PurePosixPath
from zipfile import ZipFile, BadZipFile

from services.financial.ledger_snapshot import MAX_EXPORT_BYTES
from services.financial.ledger_summary import LedgerSummaryError

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024


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
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            names = {entry.filename for entry in infos}
            if len(infos) != len(names) or len(infos) > 128 or sum(entry.file_size for entry in infos) > MAX_ARCHIVE_BYTES:
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
            raw = read('ledger-snapshot.json')
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
            entries = [(manifest['report'], 'filename', MAX_EXPORT_BYTES)]
            for key in ('pdf_report', 'expert_support'):
                if key in manifest:
                    entries.append((manifest[key], 'filename', MAX_EXPORT_BYTES))
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
            if names != expected:
                raise ValueError('Archive has unlisted or missing members.')
    except (BadZipFile, KeyError, TypeError, ValueError, UnicodeError, RecursionError, OSError, RuntimeError) as exc:
        raise LedgerSummaryError('Ledger archive is inconsistent or unsupported; comparison refused.') from exc
    return dict(document=document, manifest=manifest, archive_sha256=hashlib.sha256(content).hexdigest())


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


def _changes(before, after, key):
    a, b = _index(before, key), _index(after, key)
    changed = []
    for identity in sorted(a.keys() & b.keys()):
        if not _same(a[identity], b[identity]):
            paths = _paths(a[identity], b[identity])
            changed.append(dict(id=identity, changed_paths=paths[:100], changed_path_count=len(paths), paths_truncated=len(paths) > 100))
    return dict(added=sorted(b.keys() - a.keys()), removed=sorted(a.keys() - b.keys()), changed=changed,
                captured_order_changed=list(a) != list(b))


def compare_ledger_exports(before, after, *, expected_case_id=None):
    first, second = read_verified_ledger_archive(before), read_verified_ledger_archive(after)
    a, b = first['document'], second['document']
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
        readings=_changes(a['ledger']['readings'], b['ledger']['readings'], lambda reading:reading['row']['key']),
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

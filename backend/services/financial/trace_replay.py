"""Replay a captured conditional scenario without a database or provider.

Matching calculations are not authentication of the file, proof of its inputs,
or a determination that a tracing doctrine legally applies.
"""
import hashlib
import json

from services.financial.ledger_snapshot import LedgerExport, LedgerScopeDigest, LedgerSnapshot, MAX_EXPORT_BYTES
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_tracing import LedgerTraceInput, evaluate_ledger_trace
from services.financial.network_tracing import evaluate_network_trace



def _ledger_scope_hash(snapshot):
    """The ledger-scope fingerprint of an embedded export snapshot, or None when it has no decision log."""
    if not isinstance(snapshot.get('decisions'), list) or not isinstance(snapshot.get('ledger'), dict):
        return None
    digest = LedgerScopeDigest()
    for reading in snapshot['ledger'].get('readings') or []:
        digest.reading(reading)
    digest.decisions(snapshot['decisions'])
    return digest.finish(snapshot['ledger'])

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Repeated JSON keys are ambiguous.')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('Non-finite JSON numbers are unsupported.')


def replay_trace(content: bytes, *, expected_sha256=None):
    """Verify captured input bindings and compare current-engine calculations.

The optional expected digest must come from a separately retained source to
provide an independent byte-integrity check. No supplied code is executed.
"""
    if not isinstance(content, bytes) or len(content) > MAX_EXPORT_BYTES:
        raise LedgerSummaryError('A scenario must be UTF-8 bytes no larger than 16 MiB.')
    original_hash = hashlib.sha256(content).hexdigest()
    if expected_sha256 is not None and expected_sha256 != original_hash:
        raise LedgerSummaryError('Scenario does not match the separately supplied digest.')
    try:
        original = json.loads(content.decode('utf-8'), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        schema = original['schema']
        if schema not in ('loupe.financial.conditional_trace/1', 'loupe.financial.network_trace/1', 'loupe.financial.trace_walk/1'):
            raise ValueError('Unsupported scenario schema.')
        if original['applied'] is not False or original['assumptions_verified'] is not False:
            raise ValueError('Only unapplied, conditional scenarios can be replayed.')
        if schema == 'loupe.financial.trace_walk/1':
            # A whole-case step trace carries its own rows, not a full ledger snapshot: the reach, the stops and
            # every method's figures recompute from the file; the snapshot binding stays with the stored run.
            from services.financial.trace_walk import replay_walk
            case_id = original['case_id']
            snapshot_hash = original['snapshot_sha256']
            captured_version = original.get('code_version')
            recalculated, recalculated_bytes = replay_walk(original)
            recalculated_hash = hashlib.sha256(recalculated_bytes).hexdigest()
        else:
            snapshot = original['ledger_snapshot']
            manifest = original['ledger_manifest']
            case_id = snapshot['ledger']['case_id']
            if original['case_id'] != case_id or manifest['case_id'] != case_id:
                raise ValueError('Scenario case references differ.')
            snapshot_text = _canonical(snapshot)
            snapshot_bytes = snapshot_text.encode('utf-8')
            snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
            # A scenario's inputs name the fingerprint they were loaded with: the full document's, or (tracing inputs
            # read as a ledger scope) the readings-and-decisions fingerprint, recomputed here from the embedded snapshot.
            scope_hash = _ledger_scope_hash(snapshot)
            if (manifest['document_sha256'] != snapshot_hash
                    or type(manifest['byte_count']) is not int
                    or manifest['byte_count'] != len(snapshot_bytes)
                    or original['inputs']['expected_snapshot_sha256'] not in {snapshot_hash, scope_hash}):
                raise ValueError('Captured snapshot digest or size differs.')
            captured_version = manifest.get('code_version')
            export = LedgerExport(LedgerSnapshot(snapshot_text, snapshot_hash, len(snapshot_bytes)), _canonical(manifest),
                                  ledger_scope_sha256=scope_hash)
            if schema == 'loupe.financial.conditional_trace/1':
                envelope = evaluate_ledger_trace(export, LedgerTraceInput.model_validate(original['inputs']))
            else:
                envelope = evaluate_network_trace(export, original['inputs'])
            recalculated = json.loads(envelope['scenario_json'])
            recalculated_hash = envelope['scenario_sha256']
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise LedgerSummaryError('Captured scenario is invalid or cannot be replayed: ' + str(exc)) from exc

    # Keep the diagnostic bounded; exact original/recalculated hashes remain even
    # if more differences exist. Values can contain sensitive evidence, so the
    # diagnostic lists paths only, never prints original financial content.
    paths = []
    count = 0

    def compare(a, b, path):
        nonlocal count
        if type(a) is dict and type(b) is dict:
            for key in sorted(a.keys() | b.keys()):
                if key not in a or key not in b:
                    record(path + '/' + str(key).replace('~', '~0').replace('/', '~1'))
                else:
                    compare(a[key], b[key], path + '/' + str(key).replace('~', '~0').replace('/', '~1'))
        elif type(a) is list and type(b) is list:
            for index in range(max(len(a), len(b))):
                if index >= len(a) or index >= len(b):
                    record(path + '/' + str(index))
                else:
                    compare(a[index], b[index], path + '/' + str(index))
        elif type(a) is not type(b) or a != b:
            record(path)

    def record(path):
        nonlocal count
        count += 1
        if len(paths) < 100:
            paths.append(path)

    compare(original, recalculated, '')
    from services.financial.version import code_version
    return dict(schema_version='loupe.financial.trace_replay/1', case_id=case_id,
        status='matching_calculations' if not count else 'different_replay_output',
        original_sha256=original_hash, original_byte_count=len(content),
        independently_supplied_digest_checked=expected_sha256 is not None,
        canonical_original_sha256=hashlib.sha256(_canonical(original).encode('utf-8')).hexdigest(),
        recalculated_sha256=recalculated_hash, snapshot_sha256=snapshot_hash,
        captured_code_version=captured_version, replay_code_version=code_version(),
        difference_count=count, difference_paths=paths, paths_truncated=count > len(paths),
        financial_writes=0, provider_calls=0,
        limitation='Recomputed with the current installed calculation code from captured inputs only. Matching calculations do not authenticate the file, establish source accuracy, verify assumptions, or determine legal applicability. Original source bytes and historical custody are not checked.'
                   + (' A step-trace report carries the rows of its reached accounts and named pairs, not a full ledger snapshot:'
                      ' the snapshot digest binding and each pair\'s membership in the captured comparison stay with the stored run and a ledger export.'
                      if schema == 'loupe.financial.trace_walk/1' else ''))

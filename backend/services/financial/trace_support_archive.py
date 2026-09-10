"""Bundle selected captured tracing scenarios and their expert-review support.

Each scenario keeps its own snapshot and scope; no union ledger or complete
case-history claim is inferred from different captures of the same case.
"""
import hashlib
import io
import json
import zipfile

from services.financial.expert_support import build_expert_support
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.trace_replay import replay_trace
from services.financial.extraction_evaluation import evaluate_extraction


def build_trace_support_archive(scenarios, *, validation_corpus=None, expected_case_id=None, preparation=None):
    if not isinstance(scenarios, (list, tuple)) or not 1 <= len(scenarios) <= 8:
        raise LedgerSummaryError('Select between one and eight captured scenarios.')
    if any(not isinstance(content, bytes) for content in scenarios) or sum(map(len, scenarios)) > 64 * 1024 * 1024:
        raise LedgerSummaryError('Selected scenario bytes exceed 64 MiB or are invalid.')
    entries = {}
    cases, digests, scopes = set(), set(), []

    def add_json(name, value):
        entries[name] = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')

    for index, content in enumerate(scenarios, 1):
        replay = replay_trace(content)
        if expected_case_id is not None and replay['case_id'] != str(expected_case_id):
            raise LedgerSummaryError('Selected scenario belongs to a different case.')
        if replay['status'] != 'matching_calculations':
            raise LedgerSummaryError('A selected scenario differs from recalculation; inspect its replay report before assembling support.')
        if replay['original_sha256'] in digests:
            raise LedgerSummaryError('The same scenario was selected more than once.')
        digests.add(replay['original_sha256'])
        cases.add(replay['case_id'])
        if len(cases) != 1:
            raise LedgerSummaryError('All selected scenarios must belong to the same case.')
        scenario = json.loads(content)
        prefix = f'scenarios/{index:02d}/'
        entries[prefix + 'scenario.json'] = content
        add_json(prefix + 'replay.json', replay)
        support = build_expert_support(scenario['ledger_snapshot'],
            snapshot_sha256=replay['snapshot_sha256'], code_version=scenario['ledger_manifest'].get('code_version'))
        support['tracing'] = dict(status='selected_conditional_scenario',
            scenario_reference=prefix + 'scenario.json', scenario_sha256=replay['original_sha256'],
            replay_reference=prefix + 'replay.json', inputs_reference='inputs',
            results_reference='comparison.results' if 'comparison' in scenario else 'results',
            limitation='Only the selected methods and recorded assumptions; no legal applicability or verified-attribution finding.')
        add_json(prefix + 'expert-support.json', support)
        scopes.append(dict(scenario_reference=prefix + 'scenario.json', snapshot_sha256=replay['snapshot_sha256'],
                          support_reference=prefix + 'expert-support.json'))

    validation = dict(status='unavailable', reason='No measured extraction corpus supplied.')
    if validation_corpus is not None:
        measurement = evaluate_extraction(validation_corpus)
        add_json('validation/corpus.json', validation_corpus)
        add_json('validation/measurements.json', measurement)
        if len(entries['validation/corpus.json']) > 16 * 1024 * 1024:
            raise LedgerSummaryError('Validation corpus exceeds 16 MiB.')
        validation = dict(status='supplied_measurement_context', label_status=measurement['label_status'],
            corpus_reference='validation/corpus.json', report_reference='validation/measurements.json',
            limitation='These measurements describe the supplied corpus. Reviewer independence and representativeness are declared inputs. No equivalence to the selected case documents or extraction versions is inferred; synthetic labels remain synthetic.')
    manifest = dict(schema_version='loupe.financial.trace_support_archive/1', case_id=next(iter(cases)),
        completeness='incomplete_expert_packet', scenarios=scopes, validation=validation, preparation=preparation,
        limitation='Selected scenarios preserve separate captured scopes. This bundle does not establish complete case custody, all human decisions, a complete historical toolchain, an expert opinion or signature. Hashes detect byte changes relative to this manifest; they do not authenticate authorship.',
        files=[dict(filename=name, byte_count=len(content), sha256=hashlib.sha256(content).hexdigest())
               for name, content in sorted(entries.items())])
    add_json('manifest.json', manifest)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return stream.getvalue()

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
from services.financial.reference_reviews import evaluation_from_reference_reviews
from services.financial.export_comparison import read_verified_ledger_archive
from services.financial.audit_chain import verify_financial_audit_chain


def validation_source_overlap(source_records, corpus):
    """Compare recorded source digests only; do not infer extractor equivalence."""
    sources = source_records['sources']
    known = {source.get('sha256_at_ingestion') for source in sources if source.get('sha256_at_ingestion')}
    measured = {document['source_sha256'] for document in corpus['documents']}
    return dict(scope='selected_ledger_source_records',
        matching_source_sha256=sorted(known & measured),
        unmeasured_source_sha256=sorted(known - measured),
        sources_without_digest=sum(not source.get('sha256_at_ingestion') for source in sources),
        corpus_sources_not_selected=sorted(measured - known),
        extraction_version_equivalence='not_established',
        limitation='Recorded digest overlap does not establish that the case used the measured extraction version, settings or review process. Pending sources outside selected ledger readings are not covered by this comparison.')


def build_trace_support_archive(scenarios, *, validation_corpus=None, reference_review=None, validation_predictions=None, ledger_archive=None, expected_case_id=None, preparation=None):
    if not isinstance(scenarios, (list, tuple)) or not 1 <= len(scenarios) <= 8:
        raise LedgerSummaryError('Select between one and eight captured scenarios.')
    if any(not isinstance(content, bytes) for content in scenarios) or sum(map(len, scenarios)) > 64 * 1024 * 1024:
        raise LedgerSummaryError('Selected scenario bytes exceed 64 MiB or are invalid.')
    if (reference_review is None) != (validation_predictions is None):
        raise LedgerSummaryError('Supply both the reference review record and extraction predictions.')
    if reference_review is not None:
        if validation_corpus is not None:
            raise LedgerSummaryError('Select a supplied corpus or reconciled review inputs, not both.')
        validation_corpus = evaluation_from_reference_reviews(reference_review, validation_predictions)
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

    captured_ledger = None
    if ledger_archive is not None:
        saved = read_verified_ledger_archive(ledger_archive)
        document = saved['document']
        if document['ledger']['case_id'] != next(iter(cases)):
            raise LedgerSummaryError('Captured ledger export belongs to a different case.')
        history = document.get('case_financial_history')
        chain = (history or {}).get('audit_chain')
        verification = None
        if chain:
            verification = verify_financial_audit_chain(chain['entries'], case_id=document['ledger']['case_id'])
            if any(chain['verification'].get(key) != verification[key]
                   for key in ('case_id', 'event_count', 'head_sha256', 'status')):
                raise LedgerSummaryError('Captured ledger audit summary differs from its chain.')
        entries['ledger/original-export.zip'] = ledger_archive
        captured_ledger = dict(archive_reference='ledger/original-export.zip',
            archive_sha256=saved['archive_sha256'], snapshot_sha256=saved['manifest']['document_sha256'],
            wider_case_history='included' if history is not None else 'not_selected',
            audit_verification=verification,
            limitation='Original verified archive retained without rewriting. Its capture time and scope may differ from selected scenarios; no union ledger, latest-state claim or complete custody is inferred.')

    validation = dict(status='unavailable', reason='No measured extraction corpus supplied.')
    if validation_corpus is not None:
        measurement = evaluate_extraction(validation_corpus)
        if reference_review is not None:
            add_json('validation/reference-review.json', reference_review)
            add_json('validation/predictions.json', validation_predictions)
            if len(entries['validation/reference-review.json']) > 64 * 1024 * 1024:
                raise LedgerSummaryError('Reference review exceeds 64 MiB.')
            measurement['reference_review_sha256'] = reference_review['review_record_sha256']
        add_json('validation/corpus.json', validation_corpus)
        add_json('validation/measurements.json', measurement)
        if len(entries['validation/corpus.json']) > 16 * 1024 * 1024:
            raise LedgerSummaryError('Validation corpus exceeds 16 MiB.')
        validation = dict(status='supplied_measurement_context', label_status=measurement['label_status'],
            corpus_reference='validation/corpus.json', report_reference='validation/measurements.json',
            limitation='These measurements describe the supplied corpus. Reviewer independence and representativeness are declared inputs. No equivalence to the selected case documents or extraction versions is inferred; synthetic labels remain synthetic.')
        if reference_review is not None:
            validation.update(status='reconciled_reference_measurement_context',
                reference_review_sha256=reference_review['review_record_sha256'],
                reference_review_reference='validation/reference-review.json',
                predictions_reference='validation/predictions.json')
        # Make the attachment visible from each selected expert index, without
        # claiming that its extraction version or source inventory matches.
        for scope in scopes:
            support = json.loads(entries[scope['support_reference']])
            support['validation'] = {**validation, 'source_overlap': validation_source_overlap(support['source_records'], validation_corpus)}
            add_json(scope['support_reference'], support)
    manifest = dict(schema_version='loupe.financial.trace_support_archive/1', case_id=next(iter(cases)),
        completeness='incomplete_expert_packet', scenarios=scopes, validation=validation, preparation=preparation,
        limitation='Selected scenarios preserve separate captured scopes. This bundle does not establish complete case custody, all human decisions, a complete historical toolchain, an expert opinion or signature. Hashes detect byte changes relative to this manifest; they do not authenticate authorship.',
        files=[dict(filename=name, byte_count=len(content), sha256=hashlib.sha256(content).hexdigest())
               for name, content in sorted(entries.items())])
    if captured_ledger is not None:
        manifest['captured_ledger'] = captured_ledger
    add_json('manifest.json', manifest)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return stream.getvalue()

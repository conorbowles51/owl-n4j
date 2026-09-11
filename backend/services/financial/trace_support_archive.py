"""Bundle selected captured tracing scenarios and their expert-review support.

Each scenario keeps its own snapshot and scope; no union ledger or complete
case-history claim is inferred from different captures of the same case.
"""
import hashlib
import io
import json
import zipfile

from services.financial.expert_support import build_expert_support
from services.financial.review_package_report import render_review_package_report
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


def build_trace_support_archive(scenarios, *, validation_corpus=None, reference_review=None, validation_predictions=None, ledger_archive=None, expected_case_id=None, preparation=None, include_readable_index=True):
    if type(include_readable_index) is not bool:
        raise LedgerSummaryError('Readable index selection must be boolean.')
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
    ledger_document = None
    if ledger_archive is not None:
        saved = read_verified_ledger_archive(ledger_archive)
        document = saved['document']
        ledger_document = document
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
        if saved['expert_support_content'] is not None:
            entries['ledger/captured-expert-support.json'] = saved['expert_support_content']
            captured_ledger['support_reference'] = 'ledger/captured-expert-support.json'
            captured_ledger['support_sha256'] = hashlib.sha256(saved['expert_support_content']).hexdigest()

    measurement = None
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
    if include_readable_index:
        entries['review-index.html'] = render_review_package_report(case_id=next(iter(cases)),
            scenarios=[json.loads(content) for content in scenarios],
            supports=[json.loads(entries[scope['support_reference']]) for scope in scopes],
            preparation=preparation, ledger=ledger_document, measurement=measurement,
            ledger_support_attached=bool(captured_ledger and captured_ledger.get('support_reference')))
    manifest = dict(schema_version='loupe.financial.trace_support_archive/1', case_id=next(iter(cases)),
        completeness='incomplete_expert_packet', scenarios=scopes, validation=validation, preparation=preparation,
        limitation='Selected scenarios preserve separate captured scopes. This bundle does not establish complete case custody, all human decisions, a complete historical toolchain, an expert opinion or signature. Hashes detect byte changes relative to this manifest; they do not authenticate authorship.',
        files=[dict(filename=name, byte_count=len(content), sha256=hashlib.sha256(content).hexdigest())
               for name, content in sorted(entries.items())])
    if include_readable_index:
        manifest['readable_index'] = 'review-index.html'
    if captured_ledger is not None:
        manifest['captured_ledger'] = captured_ledger
    add_json('manifest.json', manifest)
    if sum(map(len, entries.values())) > MAX_SUPPORT_ARCHIVE_BYTES:
        raise LedgerSummaryError('Combined support content exceeds 256 MiB.')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    content = stream.getvalue()
    if len(content) > MAX_SUPPORT_ARCHIVE_BYTES:
        raise LedgerSummaryError('Compressed support archive exceeds 256 MiB.')
    return content


MAX_SUPPORT_ARCHIVE_BYTES = 256 * 1024 * 1024


def verify_trace_support_archive(content, *, expected_sha256=None, expected_case_id=None):
    """Check captured bytes and compare a rebuild without overwriting originals."""
    from pathlib import PurePosixPath
    from services.financial.reference_reviews import parse_review_json
    if not isinstance(content, bytes) or len(content) > MAX_SUPPORT_ARCHIVE_BYTES:
        raise LedgerSummaryError('Support archive exceeds 256 MiB or is not bytes.')
    digest = hashlib.sha256(content).hexdigest()
    if expected_sha256 is not None and expected_sha256 != digest:
        raise LedgerSummaryError('Support archive differs from the supplied independent digest.')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if len(infos) != len(names) or len(infos) > 64 or sum(i.file_size for i in infos) > MAX_SUPPORT_ARCHIVE_BYTES:
                raise ValueError('Duplicate members or archive limits exceeded.')
            for name in names:
                if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or '\\' in name:
                    raise ValueError('Unsafe archive path.')
            def read(name, limit):
                if archive.getinfo(name).file_size > limit:
                    raise ValueError('Member limit exceeded.')
                with archive.open(name) as source:
                    data = source.read(limit + 1)
                if len(data) > limit:
                    raise ValueError('Member limit exceeded.')
                return data
            manifest = parse_review_json(read('manifest.json', 1024 * 1024))
            if manifest['schema_version'] != 'loupe.financial.trace_support_archive/1':
                raise ValueError('Unsupported support schema.')
            if expected_case_id is not None and manifest['case_id'] != str(expected_case_id):
                raise ValueError('Support archive belongs to a different case.')
            members = {}
            for item in manifest['files']:
                name = item['filename']
                if name == 'manifest.json' or name in members:
                    raise ValueError('Repeated declared member.')
                limit = 128 * 1024 * 1024 if name == 'ledger/original-export.zip' else 64 * 1024 * 1024
                data = read(name, limit)
                if type(item['byte_count']) is not int or len(data) != item['byte_count'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise ValueError('Member digest or size differs.')
                members[name] = data
            if names != set(members) | {'manifest.json'}:
                raise ValueError('Missing or unlisted members.')
        if 'readable_index' in manifest and manifest['readable_index'] != 'review-index.html':
            raise ValueError('Unsupported readable index reference.')
        options = dict(expected_case_id=manifest['case_id'], preparation=manifest.get('preparation'),
            include_readable_index='readable_index' in manifest)
        validation = manifest['validation']
        if validation['status'] == 'reconciled_reference_measurement_context':
            options['reference_review'] = parse_review_json(members[validation['reference_review_reference']])
            options['validation_predictions'] = parse_review_json(members[validation['predictions_reference']])
        elif validation['status'] == 'supplied_measurement_context':
            options['validation_corpus'] = parse_review_json(members[validation['corpus_reference']])
        elif validation['status'] != 'unavailable':
            raise ValueError('Unsupported validation context.')
        if 'captured_ledger' in manifest:
            options['ledger_archive'] = members[manifest['captured_ledger']['archive_reference']]
        rebuilt = build_trace_support_archive([members[s['scenario_reference']] for s in manifest['scenarios']], **options)
        with zipfile.ZipFile(io.BytesIO(rebuilt)) as archive:
            rebuilt_members = {name: archive.read(name) for name in archive.namelist() if name != 'manifest.json'}
            rebuilt_manifest = parse_review_json(archive.read('manifest.json'))
        changed = sorted(name for name in members.keys() | rebuilt_members.keys()
                         if members.get(name) != rebuilt_members.get(name))
        replay_version_changes = []
        for name in list(changed):
            if name.endswith('/replay.json') and name in members and name in rebuilt_members:
                saved_replay = parse_review_json(members[name])
                current_replay = parse_review_json(rebuilt_members[name])
                saved_version = saved_replay.pop('replay_code_version', None)
                current_version = current_replay.pop('replay_code_version', None)
                if saved_replay == current_replay and saved_version != current_version:
                    replay_version_changes.append(dict(member=name, captured_replay_code_version=saved_version,
                        current_replay_code_version=current_version))
                    changed.remove(name)
        # Manifest member digests are already checked; compare remaining metadata
        # separately so pretty-printing the original JSON does not create a mismatch.
        metadata_changed = ({k:v for k,v in manifest.items() if k != 'files'} !=
                            {k:v for k,v in rebuilt_manifest.items() if k != 'files'})
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise LedgerSummaryError('Support archive is inconsistent or cannot be recalculated.') from exc
    return dict(schema_version='loupe.financial.trace_support_verification/1',
        archive_sha256=digest, case_id=manifest['case_id'], member_count=len(members),
        status=('verified_bytes_different_rebuild' if changed or metadata_changed else
                'verified_bytes_matching_calculations' if replay_version_changes else 'verified_bytes_matching_rebuild'),
        replay_version_changes=replay_version_changes,
        changed_members=changed, manifest_metadata_changed=metadata_changed,
        checkpoint_status='matches_supplied_digest' if expected_sha256 is not None else 'not_supplied',
        limitation='Checks internal file consistency and a rebuild using the current installed code. '
        'Differences can reflect changed code or changed derived content and require review. '
        'Without an independently retained digest, consistent rewriting is not detected. '
        'Matching calculations do not establish authorship, reviewer independence, custody completeness or evidence truth.')

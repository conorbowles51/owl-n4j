"""Persisted user delivery constraints and checks on the latest immutable outputs."""
from __future__ import annotations

import re

from services.agent.claim_validation import fingerprint

COMPLETION_CHECK_VERSION = 2


def delivery_contract(instructions):
    """Extract explicit report page counts, never source-page ranges or inferred report topics."""
    contract = {'version': 1, 'report_requested': False, 'min_pages': None, 'max_pages': None, 'page_bounds_specified': False,
                'min_outputs': None, 'slide_count': None}
    texts = [str(item.get('text', '')) if isinstance(item, dict) else str(item) for item in instructions]
    for message in texts:
        numbers = {'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6', 'seven': '7',
                   'eight': '8', 'nine': '9', 'ten': '10', 'eleven': '11', 'twelve': '12'}
        normalized = re.sub(r'\b(' + '|'.join(numbers) + r')\b', lambda m: numbers[m.group().lower()], message, flags=re.I)
        for sentence in re.split(r'[\n.!?]', normalized):
            slide_count = re.search(r'\b(\d{1,3})\s*-?\s*slide\s+(?:editable\s+)?(?:presentation|deck)\b', sentence, re.I)
            if slide_count:
                contract['slide_count'] = int(slide_count.group(1))
            outputs = re.search(r'\b(?:create|produce|prepare|generate|build|make|save|want|need)\b[^.!?\n]{0,70}?\b(\d{1,3})\s+(?:(?:separate(?:ly)?|distinct|named|saved|different|numbered)\s+)*(?:artifacts|exhibits|deliverables)\b', sentence, re.I)
            if outputs:
                contract['min_outputs'] = int(outputs.group(1))
            if not (re.search(r'\b(report|deliverable|rendered|memo)\b', sentence, re.I)
                    or (contract.get('source_instruction') and re.search(r'\b(instead|change|make|shorten|expand|now)\b', sentence, re.I))):
                continue
            if re.search(r'\b(no|remove|ignore|drop)\s+(?:the\s+)?page\s+(limit|count|requirement)', sentence, re.I):
                contract.update(min_pages=None, max_pages=None, page_bounds_specified=True)
                continue
            match = re.search(r'\b(\d{1,4})\s*(?:-|–|—|to)\s*(\d{1,4})\s*[-–]?\s*(?:rendered\s+)?(?:pdf\s+)?pages?\b', sentence, re.I)
            if match:
                low, high = map(int, match.groups())
                if 1 <= low <= high:
                    contract.update(min_pages=low, max_pages=high, page_bounds_specified=True, source_instruction=sentence.strip())
                continue
            exact = re.search(r'\b(?:exactly\s+)?(\d{1,4})\s*[-–]?\s*(?:rendered\s+)?(?:pdf\s+)?page(?:s\s+(?:long|in total)|\s+(?:report|memo))\b', sentence, re.I)
            if exact and not re.search(r'\b(about|roughly|approximately)\b', sentence, re.I):
                pages = int(exact.group(1))
                if pages:
                    contract.update(min_pages=pages, max_pages=pages, page_bounds_specified=True, source_instruction=sentence.strip())
    latest = texts[-1] if texts else ''
    contract['full_source_reads'] = bool(re.search(r'\bread\b[^.!?\n]{0,120}\b(?:completely|in full|entire|whole|complete|all(?:\d|\s))', latest, re.I))
    contract['source_file_ids'] = re.findall(r'\bfile\s+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b', latest, re.I)
    # A follow-up that only revises one prior output must not recreate an earlier batch.
    if not re.search(r'\b(?:create|produce|prepare|generate|build|make|save|want|need)\b[^.!?\n]{0,90}\b(?:artifacts|exhibits|deliverables)\b', latest, re.I):
        contract['min_outputs'] = None
    contract['report_requested'] = bool(re.search(r'\b(report|memo)\b', latest, re.I)
                                        and re.search(r'\b(create|write|produce|prepare|draft|build|generate|want|need|give|deliver)\b', latest, re.I))
    return contract


def latest_outputs(context, artifacts):
    touched = {(a.get('metadata') or {}).get('deliverable_id', a.get('id')) for a in artifacts}
    latest = {}
    for value in [*context.artifact_store.values(), *artifacts]:
        meta = value.get('metadata') or {}
        family = meta.get('deliverable_id', value.get('id'))
        if family in touched and (family not in latest or int(meta.get('revision', 1)) >= int((latest[family].get('metadata') or {}).get('revision', 1))):
            latest[family] = value
    return list(latest.values())


def revision_needed_answer(artifacts, problems):
    """A failed check cannot be contradicted by a model-written success claim."""
    latest = {}
    for artifact in artifacts:
        meta = artifact.get('metadata') or {}
        family = meta.get('deliverable_id', artifact.get('id'))
        if family not in latest or meta.get('revision', 1) >= latest[family].get('metadata', {}).get('revision', 1):
            latest[family] = artifact
    lines = ['The saved work still needs revision before it meets your request.' if latest else
             'The request is not complete. The remaining checks are listed below.']
    if latest:
        lines += ['', 'Saved drafts:', *[f"- {a['title']} · version {a.get('metadata', {}).get('revision', 1)}" for a in latest.values()]]
    issues = list(dict.fromkeys(str(issue).split(' Draft: ', 1)[0] for problem in problems for issue in problem.get('issues', [])))
    if not issues:
        issues = list(dict.fromkeys(str(issue) for a in latest.values()
            for issue in a.get('metadata', {}).get('validation', {}).get('issues', [])))
    if issues:
        lines += ['', 'Checks that need attention:', *['- ' + issue for issue in issues[:8]]]
        if len(issues) > 8:
            lines += [f'{len(issues) - 8} further issues are available in the saved draft checks.']
    if latest:
        lines += ['', 'Open the affected draft and choose Resolve checks with agent to continue from the saved work.']
    return '\n'.join(lines)


def assess(context, artifacts, contract, receipts, *, source_receipts=None):
    """Return precise failures; a render receipt never establishes source truth or visual quality."""
    from services.agent.render_checks import inspect_export, CHECK_VERSION
    from services.agent.deliverables import dependency_metadata
    from services.agent.claim_validation import validate_claims
    latest = latest_outputs(context, artifacts)
    problems = []
    if contract.get('full_source_reads'):
        read_ids = {r['evidence_id'] for r in source_receipts or []}
        for source_id in contract.get('source_file_ids', []):
            if source_id not in read_ids:
                problems.append({'artifact_id': None, 'issues': [f'The requested full source file {source_id} has not been read with the complete document reader.']})
        for source in source_receipts or []:
            if source['status'] != 'complete_text_delivered':
                problems.append({'artifact_id': None, 'source_coverage': source,
                    'issues': [f"Only {source['complete_pages']} of {source['total_pages']} parts of {source['name']} have been delivered in full. Finish the valid next_read continuations and any unfetched document windows before claiming complete source coverage. Unreadable parts remain an explicit source gap."]})
    if contract.get('min_outputs') and len(latest) < contract['min_outputs']:
        problems.append({'artifact_id': None, 'issues': [f"The request needs at least {contract['min_outputs']} separate saved deliverables; only {len(latest)} have been created or revised in this job. Revisions of one deliverable count once."]})
    if contract.get('report_requested') and not any(a.get('type') == 'report' for a in latest):
        problems.append({'artifact_id': None, 'issues': ['The requested report has not been saved.']})
    for artifact in latest:
        meta = dependency_metadata(artifact, context.artifact_store)
        issues = list((meta.get('validation') or {}).get('issues') or [])
        # Refresh source checks even for a draft created before the current run.
        # A historical structural receipt must never bypass a newly detected error.
        evidence = validate_claims(artifact['data'], result_store=context.result_store,
            artifact_store=context.artifact_store, required_items=meta.get('required_items', []),
            source_result_ids=meta.get('source_result_ids', []))
        issues.extend(evidence['issues'])
        digest = fingerprint(artifact['data'])
        # Only exact current-revision results are relevant; a failed earlier revision never blocks a correction.
        for result in context.result_store.values():
            if (isinstance(result, dict) and result.get('artifact_id') == artifact['id']
                    and result.get('payload_sha256') == digest and result.get('format') == 'pdf'
                    and result.get('check_version') == CHECK_VERSION):
                receipts[artifact['id']] = result
        if artifact.get('type') in {'report', 'presentation'} or artifact['id'] in receipts:
            receipt = receipts.get(artifact['id'])
            if receipt is None or receipt.get('payload_sha256') != digest or receipt.get('check_version') != CHECK_VERSION:
                try:
                    receipt = inspect_export(artifact, min_pages=contract.get('min_pages') if artifact['type'] == 'report' else None,
                                             max_pages=contract.get('max_pages') if artifact['type'] == 'report' else None)
                except Exception as exc:
                    receipt = {'artifact_id': artifact['id'], 'payload_sha256': digest, 'status': 'needs_revision',
                               'issues': [f'The saved PDF could not be rendered and checked: {exc}'],
                               'visual_review': 'not_established', 'source_truth': 'not_established'}
            # The actual page count can be checked against the user's contract even if a tool omitted its bounds.
            render_issues = [item for item in receipt.get('issues', []) if not str(item).startswith('The rendered PDF has ')]
            count = receipt.get('page_count')
            if artifact['type'] == 'report' and count is not None:
                low, high = ((contract.get('min_pages'), contract.get('max_pages')) if contract.get('page_bounds_specified')
                             else (receipt.get('requested_min_pages'), receipt.get('requested_max_pages')))
                if low and count < low:
                    render_issues.append(f'The rendered PDF has {count} pages; the requested minimum is {low}.')
                if high and count > high:
                    render_issues.append(f'The rendered PDF has {count} pages; the requested maximum is {high}.')
                receipt = {**receipt, 'requested_min_pages': low, 'requested_max_pages': high}
            if artifact['type'] == 'presentation' and contract.get('slide_count') and count != contract['slide_count']:
                render_issues.append(f"The exported presentation has {count} slides; the request specifies {contract['slide_count']}. Revise its composition, including any optional cover and continued or embedded slides, then inspect the actual export.")
            receipt = {**receipt, 'issues': render_issues, 'status': 'needs_revision' if render_issues else 'render_checks_passed'}
            receipts[artifact['id']] = receipt
            issues.extend(render_issues)
        if issues:
            problems.append({'artifact_id': artifact['id'], 'title': artifact['title'],
                             'revision': meta.get('revision', 1), 'issues': list(dict.fromkeys(issues))})
    return problems

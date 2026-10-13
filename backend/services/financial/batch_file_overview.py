"""Per-file summary of a batch's statements, built from items the batch read already projected.

It answers, before the investigator opens anything, which files hold work and
which are only copies the system set aside: "All 53 statements are copies of
<retained file> — nothing to review" or "12 of 40 are copies". No database
access, no reading: it only regroups the projected statuses and dispositions,
so it can never disagree with the statement list it sits beside.

A copy here is exactly what the batch read shows as ``duplicate_ignored`` with
a current ignored disposition. Anything less certain (a possible duplicate, a
stale or restored decision) stays ordinary work.
"""

FINISHED = ('imported', 'skipped', 'assigned', 'duplicate_ignored', 'superseded_reading', 'removed')


def is_system_copy(item):
    """An item the system set aside as a copy of a retained statement, under current inputs."""
    if item.status != 'duplicate_ignored':
        return False
    disposition = item.summary.get('duplicate_disposition') or {}
    return disposition.get('status') == 'ignored' and disposition.get('current') is True


def copy_files(items):
    """File ids whose every current statement is a system copy."""
    by_file = {}
    for item in items:
        if item.status in ('removed', 'superseded_reading'):
            continue
        by_file.setdefault(item.file_id, []).append(is_system_copy(item))
    return {file_id for file_id, flags in by_file.items() if flags and all(flags)}


def file_overview(items):
    """One entry per file, in first-seen order of the (already sorted) items."""
    files = {}
    for item in items:
        if item.status in ('removed', 'superseded_reading'):
            continue
        entry = files.get(item.file_id)
        if entry is None:
            entry = files[item.file_id] = dict(file_id=str(item.file_id),
                filename=item.summary.get('filename') or 'Source unavailable',
                statements=0, copies=0, unfinished=0, saved=0, retained=[])
        entry['statements'] += 1
        entry['saved'] += int(item.status == 'imported')
        entry['unfinished'] += int(item.status not in FINISHED)
        if is_system_copy(item):
            entry['copies'] += 1
            retained = item.summary['duplicate_disposition'].get('retained') or {}
            name = retained.get('filename') or 'another statement'
            target = next((r for r in entry['retained'] if r['filename'] == name
                           and r['evidence_file_id'] == retained.get('evidence_file_id')), None)
            if target is None:
                target = dict(filename=name, evidence_file_id=retained.get('evidence_file_id'), copies=0)
                entry['retained'].append(target)
            target['copies'] += 1
    result = list(files.values())
    for entry in result:
        entry['all_copies'] = entry['statements'] > 0 and entry['copies'] == entry['statements']
        entry['retained'].sort(key=lambda r: (-r['copies'], r['filename']))
    # Files with work first, then partly-copied files, then files that are only copies.
    result.sort(key=lambda e: (e['all_copies'], e['unfinished'] == 0))
    return result

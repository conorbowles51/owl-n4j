"""Per-period routing between the general engine and the family-reader library.

* The engine PROVES a period no library reader claims -> the engine serves it.
* The engine does not prove it -> the library reader's result if one claims
  it (as before the engine existed), else the engine's held reading when the
  file has no library statement at all (so the period is listed, held, with
  its best reading and a named reason), else the pages stay unclassified.
* The engine and a library reader BOTH prove the same pages:
  - equal readings -> the library serves (its statement id and reviews stay
    exactly as they were) and the agreement is recorded;
  - different readings -> the period is held as an engine/library
    disagreement (a defect in one of them; never picked silently).
* The library claims the pages but does not prove them and the engine does
  -> the engine serves, under the library statement's id, so saved reviews of
  that period stay attached.
* A layout fingerprint routed ``library_first`` in the route table (data,
  filled from the benchmark's verified truth) is never served by the engine.

Switches (environment):
* ``LOUPE_FINANCIAL_GENERIC_READER``: '1' runs the engine with the library as
  fallback, '0' runs the library alone. Default: see ``DEFAULT_ENABLED``.
* ``LOUPE_FINANCIAL_GENERIC_ONLY=1``: benchmark-only measurement switch; every
  family reader is skipped. Never a production path.
"""
import json
import logging
import os
import time
from pathlib import Path

from services.financial.statement_engine import HOLD_MESSAGES, engine_catalog, read_statements

DEFAULT_ENABLED = False
ROUTES = Path(__file__).with_name('statement_engine_routes.json')
logger = logging.getLogger(__name__)


def generic_enabled():
    value = os.environ.get('LOUPE_FINANCIAL_GENERIC_READER')
    return DEFAULT_ENABLED if value is None else value.strip() == '1'


def generic_only():
    return os.environ.get('LOUPE_FINANCIAL_GENERIC_ONLY', '').strip() == '1'


_ROUTE_CACHE = {}


def routes():
    try:
        stamp = ROUTES.stat().st_mtime
    except OSError:
        return {}
    if _ROUTE_CACHE.get('stamp') != stamp:
        data = json.loads(ROUTES.read_text())
        _ROUTE_CACHE.update(stamp=stamp, routes=data.get('routes', {}))
    return _ROUTE_CACHE['routes']


def _pages(statement):
    return {s['page_number'] for s in statement['sources']}


def reading_key(rows):
    """What a period's money reading says, independent of the reader: endpoints and every movement."""
    opening = [r['fields'].get('balance') for r in rows if r['kind'] == 'balance'
               and r['fields'].get('description') == 'Opening Balance']
    closing = [r['fields'].get('balance') for r in rows if r['kind'] == 'balance'
               and r['fields'].get('description') == 'Closing Balance']
    moves = sorted((r['fields'].get('date') or '', r['fields'].get('direction') or '', r['fields'].get('amount_minor') or '')
                   for r in rows if not r['excluded'])
    return (tuple(opening), tuple(closing), tuple(moves))


def closing_reconciles(rows, liability):
    from services.financial.statement_review_checks import check_statement_rows
    return check_statement_rows(rows, liability=liability)['checks'][0]['status'] == 'matches'


IDENTITY = ('institution', 'account_reference', 'holder', 'currency')


def proved_rows(rows, liability):
    """A reader's rows prove their period: closing reconciles and nothing is left unresolved."""
    from services.financial.statement_review_checks import check_statement_rows
    if any(r['issues'] for r in rows if not r['excluded']) or any(r['kind'] == 'unresolved' for r in rows):
        return False
    checks = check_statement_rows(rows, liability=liability)
    closing = checks['checks'][0]
    return closing['status'] == 'matches' and not checks['has_difference']


def _same_account(a, b):
    da, db = ''.join(ch for ch in a if ch.isdigit()), ''.join(ch for ch in b if ch.isdigit())
    shorter, longer = sorted((da, db), key=len)
    return len(shorter) >= 4 and shorter in longer


def disagreement_row(rows, choice):
    anchor = next((r for r in rows if r['kind'] == 'balance'), rows[0] if rows else None)
    base = dict(anchor) if anchor else dict(id='engine', page_number=None, table_index=None, row_index=None,
                                             source_revision=None, source_cells=[])
    return dict(base, id=str(base['id']) + ':engine_disagreement', kind='unresolved', excluded=False,
                fields=dict(description=HOLD_MESSAGES['library_disagrees']),
                issues=['Two readers reconcile this period but read it differently: '
                        + HOLD_MESSAGES['library_disagrees']
                        + ' Compare the balances and every movement with the PDF before importing.'],
                engine_hold='library_disagrees')


def _engine_only(sources):
    statements = [s for s in engine_catalog(sources) if s['period_start']]
    claimed = {p for s in statements for p in _pages(s)}
    unclassified = [dict(page_number=s['page_number'], table_index=s['table_index'])
                    for s in sources if s['page_number'] not in claimed]
    return dict(statements=statements, unclassified_sources=unclassified, information_sources=[],
                complete_coverage=not unclassified, engine_routing=dict(mode='generic_only'))


def route_catalog(sources, library_catalog):
    if generic_only():
        return _engine_only(sources)
    library = library_catalog(sources)
    if not generic_enabled():
        return library
    started = time.monotonic()
    engine = read_statements(sources)
    routing_profile = None
    # A library profile (data) that matches the document is used only if it keeps every period the
    # plain engine proves, with the identical money reading, and proves at least as many.
    from services.financial.statement_engine_profiles import matching_profile, profile_text
    profile = matching_profile(profile_text(sources))
    if profile is not None:
        profiled = read_statements(sources, profile=profile)
        plain_keys = {(st['period_start'], st['period_end'], reading_key(st['_rows'])) for st in engine if st['engine']['proved']}
        profiled_keys = {(st['period_start'], st['period_end'], reading_key(st['_rows'])) for st in profiled if st['engine']['proved']}
        if plain_keys <= profiled_keys and profiled_keys:
            engine = profiled
            routing_profile = profile['name']
    table = routes()
    groups = list(library['statements'])
    library_pages = {p for g in groups if not g.get('document_kind') for p in _pages(g)}
    by_address = {(s['page_number'], s['table_index']): s for s in sources}
    served, routing = [], dict(mode='engine_primary', engine_served=0, library_served=0, agreements=0,
                               disagreements=[], replaced=[], library_first=0, held_engine=0)
    replacements = {}
    routing['profile'] = routing_profile
    for statement in engine:
        pages = _pages(statement)
        proved = statement['engine']['proved']
        public = {k: v for k, v in statement.items() if k != '_rows'}
        if proved and table.get(statement.get('layout_fingerprint')) == 'library_first':
            routing['library_first'] += 1
            proved = False
            public['engine'] = dict(statement['engine'], proved=False, reason='route_library_first')
        if not pages & library_pages:
            if proved:
                served.append(public)
                routing['engine_served'] += 1
            elif not groups and statement['period_start']:
                served.append(public)
                routing['held_engine'] += 1
            continue
        if not proved:
            continue
        matching = [g for g in groups if not g.get('document_kind') and _pages(g) & pages]
        if len(matching) != 1 or _pages(matching[0]) != pages:
            continue
        group = matching[0]
        currency = statement.get('currency') or group.get('currency') or ''
        try:
            from services.financial.statement_review_checks import statement_rows, is_liability
            from services.financial.statement_currency import currencies_by_statement
            currency = currency or (currencies_by_statement([group], sources)[0].get('currency') or '')
            if not currency:
                continue
            library_rows = statement_rows(group, [by_address[(s['page_number'], s['table_index'])]
                                                  for s in group['sources']], currency)
        except (ValueError, KeyError):
            library_rows = None
        if library_rows is None:
            continue
        library_proved = proved_rows(library_rows, is_liability(group))
        engine_rows = statement['_rows']
        if library_proved:
            if reading_key(library_rows) == reading_key(engine_rows):
                group['engine_agrees'] = True
                routing['agreements'] += 1
            else:
                group['engine_disagreement'] = dict(engine_id=statement['id'],
                                                    layout_fingerprint=statement['layout_fingerprint'])
                routing['disagreements'].append(group['id'])
                logger.warning('Engine/library disagreement on statement %s (layout %s, fingerprint %s).',
                               group['id'], group.get('layout_id'), statement['layout_fingerprint'])
            continue
        if closing_reconciles(library_rows, is_liability(group)):
            # The library's reading reconciles its balances (it may still be held for another reason,
            # or be ready): it keeps the period. The engine replaces only a reading that cannot reconcile.
            continue
        conflicts = [field for field in IDENTITY if public.get(field) and group.get(field)
                     and public[field] != group[field] and not (field == 'account_reference' and _same_account(public[field], group[field]))]
        if conflicts:
            continue
        # The library cannot reconcile this period and the engine proves it: the engine serves under the
        # library id, with the library's identity facts where the engine read none.
        replaced = dict(public, id=group['id'], engine_id=statement['id'], replaced_layout=group.get('layout_id'))
        for field in IDENTITY:
            if not replaced.get(field) and group.get(field):
                replaced[field] = group[field]
                if field == 'currency':
                    replaced['currency_source'] = 'printed_account_section'
        replacements[group['id']] = replaced
        routing['replaced'].append(group['id'])
        routing['engine_served'] += 1
    statements = [replacements.get(g['id'], g) for g in groups] + served
    routing['library_served'] = sum(1 for g in groups if g['id'] not in replacements)
    taken = {p for s in served for p in _pages(s)}
    unclassified = [u for u in library['unclassified_sources'] if u['page_number'] not in taken]
    routing['seconds'] = round(time.monotonic() - started, 3)
    return dict(library, statements=statements, unclassified_sources=unclassified,
                complete_coverage=not unclassified, engine_routing=routing)

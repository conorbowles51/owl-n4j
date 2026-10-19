"""Per-period routing between the general engine and the family-reader library.

* The engine PROVES a period no library reader claims -> the engine serves it.
* The engine does not prove it -> the library reader's result if one claims
  it (as before the engine existed), else the engine's held reading when the
  file has no library statement at all (so the period is listed, held, with
  its best reading and a named reason), else the pages stay unclassified.
* The engine and a library reader BOTH prove the same pages, or the same printed
  period (dates, currency, account) on overlapping pages (row-level scope):
  - equal readings -> the library serves (its statement id and reviews stay
    exactly as they were) and the agreement is recorded;
  - different readings -> the period is held as an engine/library
    disagreement (a defect in one of them; never picked silently).
* The library claims the pages but does not prove them and the engine does
  -> the engine serves, under the library statement's id, so saved reviews of
  that period stay attached, when the library's reading cannot reconcile its
  balances, or reconciles with exactly the engine's reading (every movement's
  date, direction and amount, and both balances: two readers agree; the library
  was held for something else). When the engine section reads every page of
  the library period plus covers or continuation pages holding no other library
  period, or only library periods whose recorded rows it does not share
  (row-level scope), the same applies to the one library period of the same
  printed period, currency, account and opening balance.
  Identity facts that differ only by case or a printed legal form are the same
  fact; any other identity difference keeps the library period.
* A layout fingerprint routed ``library_first`` in the route table (data,
  filled from the benchmark's verified truth) is never served by the engine.

Switches (environment):
* ``LOUPE_FINANCIAL_GENERIC_READER``: '1' runs the engine with the library as
  fallback, '0' runs the library alone. Default: on (``DEFAULT_ENABLED``).
* ``LOUPE_FINANCIAL_GENERIC_ONLY=1``: benchmark-only measurement switch; every
  family reader is skipped. Never a production path.
"""
import json
import re
import logging
import os
import time
from pathlib import Path

from services.financial.statement_engine import HOLD_MESSAGES, read_statements

# On by default (r2-any-layout ship decision, 2026-10-06): every measured mode admitted 0 wrong periods,
# the 20-period visual sample agreed to the cent, and no period ready with the library alone was lost.
# Reverse: set False (or LOUPE_FINANCIAL_GENERIC_READER=0) to run the library alone.
DEFAULT_ENABLED = True
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
# When the engine and a library reader prove the same reading of a period, the library period keeps
# serving and takes from the engine section the identity facts it left unread (r6-vector-text: a cleaner
# reading of a page made the Intercam library agree with the engine on a section whose holder only the
# engine reads, and the period lost its holder). Only facts every section of one statement shares: the
# currency and the account tell sections apart, and two quiet sections agree on any reading (measured: a
# Monex zero section took another section's currency). Switch off to keep the library period as read.
AGREEMENT_FILLS_IDENTITY = True
AGREEMENT_FILLS = ('institution', 'holder')


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


_BANKING_WORDS = {'BANCO', 'BANK', 'THE', 'NA', 'N', 'A', 'SA', 'S', 'INSTITUCION', 'DE', 'DEL', 'LA', 'EL', 'BANCA',
                  'MULTIPLE', 'GRUPO', 'FINANCIERO', 'OF'}
_LEGAL_FORM_TAIL = re.compile(r'(?:\s*,)?\s+(?:S\.?\s*A\.?\s*(?:P\.?\s*I\.?\s*)?|S\.?\s*DE\s*R\.?\s*L\.?\s*)(?:DE\s+C\.?\s*V\.?)?$')


def _same_identity(field, a, b):
    """Two readings of one identity fact that name the same thing: equal accounts by their digits,
    names equal after case and accents, a holder printed with and without its legal form ('X SA DE CV'
    and 'X'). Anything else is a conflict."""
    from services.financial.statement_engine_vocabulary import fold
    if field == 'account_reference':
        return a == b or _same_account(a, b)
    if field == 'currency':
        return a == b
    fa, fb = fold(a), fold(b)
    if fa == fb:
        return True
    if field == 'institution':
        # 'Intercam' and 'INTERCAM BANCO': the issuer's name with or without a generic banking word; 'BBVA
        # Mexico' and 'BBVA BANCOMER': one issuer under its current and former names (both readers read the
        # same document; the first distinctive word of the name is the same).
        plain = lambda text: [w for w in re.sub(r'[^A-Z0-9 ]', ' ', text).split() if w not in _BANKING_WORDS]
        pa, pb = plain(fa), plain(fb)
        return bool(pa) and bool(pb) and (pa == pb or pa[0] == pb[0] and len(pa[0]) >= 3)
    if field == 'holder':
        bare = lambda text: ' '.join(_LEGAL_FORM_TAIL.sub('', text).replace('.', ' ').replace(',', ' ').split())
        return bare(fa) == bare(fb) and bool(bare(fa))
    return False


def _scope_rows(statement):
    """{(page, table, row)} a reader attributes to a period, or None when it records no row scope."""
    scope = statement.get('section_sources')
    if not scope:
        return None
    return {(s['page_number'], s['table_index'], row) for s in scope for row in s['row_indices']}


def _own_scope(engine_statement, others, sources):
    """The engine section's row scope without the rows other library periods on its pages also claim
    (page furniture the scope check allowed both to count), or None when its import region would still
    overlap another period's region on a page (the import's overlap guard compares each page's vertical
    extent; an overlap would make the other period read as already imported)."""
    from services.financial.statement_import_andrews import andrews_source_regions, source_regions_overlap
    ours = _scope_rows(engine_statement)
    theirs = set()
    for other in others:
        theirs |= _scope_rows(other) or set()
    if ours is None or not theirs:
        return engine_statement.get('section_sources')
    kept = ours - theirs
    if not kept:
        return None
    # Each scope entry keeps its own rows: one entry per region, as the engine recorded them (a summary box
    # and its movement table on one page are two regions).
    scope = [dict(entry, row_indices=rows) for entry in engine_statement['section_sources']
             if (rows := [row for row in entry['row_indices'] if (entry['page_number'], entry['table_index'], row) in kept])]
    mine = andrews_source_regions(sources, dict(sources=scope))
    for other in others:
        region = andrews_source_regions(sources, dict(sources=other.get('section_sources') or []))
        if mine is None or region is None or source_regions_overlap(mine, region) is not False:
            return None
    return scope


def _covers(engine_statement, library_period, by_address=None):
    """The engine section read everything the library period claims: every row of its recorded row scope
    when both readers record one, else every page of it. With the stored rows (``by_address``), a library row
    the engine section does not read may only be page furniture: a line printing no amount and no date (a page
    footer the engine attributes to the next section on the page)."""
    ours, theirs = _scope_rows(engine_statement), _scope_rows(library_period)
    if ours is not None and theirs is not None:
        if by_address is None:
            return theirs <= ours
        rows = {(s['page_number'], s['table_index'], r['row_index']): r for s in by_address.values() for r in s['rows']}
        return all(key in rows and _furniture(rows[key]) for key in theirs - ours)
    return _pages(library_period) <= _pages(engine_statement)


_VALUE = re.compile(r'\d[.,]\d{2}(?!\d)')


def _furniture(row):
    """A stored row printing neither an amount nor a date."""
    from services.financial.statement_engine import is_date_token
    text = ' '.join(c['expected_text'] for c in row['cells'])
    return not _VALUE.search(text) and not any(is_date_token(word) for word in text.split())


def _rows_apart(engine_statement, library_period, by_address):
    """Both readers record row scopes and no row printing an amount or a date belongs to both: the library
    period is another section on a shared page, not part of what the engine section read (page furniture,
    a page number or a footer line, may be counted by both)."""
    ours, theirs = _scope_rows(engine_statement), _scope_rows(library_period)
    if ours is None or theirs is None:
        return False
    rows = {(s['page_number'], s['table_index'], r['row_index']): r for s in by_address.values() for r in s['rows']}
    return all(key in rows and _furniture(rows[key]) for key in ours & theirs)


# When both readers read a period alike, the engine serves it (under the library period's id, as a replacement)
# where it alone establishes a fact the period needs from its own printed lines: the currency printed in the
# section or under the statement's single currency label where the library read none, or, for a period without movements, the printed zero deposit and
# withdrawal totals beside equal balances (the general no-activity proof). Off: the library keeps every agreed
# period, as before.
AGREEMENT_PREFERS_ENGINE = True
AGREED_KEEPS_LIBRARY = ('institution', 'account_reference', 'holder')


def _engine_completes(statement, engine_rows, group, sources, currency):
    from services.financial.statement_currency import currencies_by_statement
    if not statement.get('currency') or statement['currency'] != currency:
        return False
    library_currency = group.get('currency') or (currencies_by_statement([group], sources)[0].get('currency') or '')
    if not library_currency:
        return statement.get('currency_source') in ('printed_account_section', 'printed_statement_currency')
    if library_currency != statement['currency']:
        return False
    if any(r['kind'] == 'transaction' and not r['excluded'] for r in engine_rows):
        return False
    from services.financial.statement_printed_no_activity import zero_totals_evidence
    public = {k: v for k, v in statement.items() if k != '_rows'}
    return bool((zero_totals_evidence(engine_rows, public, currency, family='generic') or {}).get('verified'))


# A library period whose opening balance it could not read (the printed figure is a mark it cannot read as an
# amount) has no printed opening to tell sections apart by: it is the engine section of the same printed account
# and period when both read the same closing balance. Off: an unread opening never pairs, as before.
UNREAD_OPENING_PAIRS_BY_CLOSING = True


def _same_section(library_key, engine_key):
    """Whether a library period on shared pages is the engine section's (same printed account and period
    already checked): the same printed opening balance, or, where the library read no opening amount, the
    same printed closing balance."""
    if library_key[0] == engine_key[0]:
        return True
    return (UNREAD_OPENING_PAIRS_BY_CLOSING and len(library_key[0]) == 1 and library_key[0][0] is None
            and len(library_key[1]) == 1 and library_key[1][0] is not None and library_key[1] == engine_key[1])


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


def _profiled(sources, engine):
    """(reading, profile name): a library profile (data) that matches the document replaces the plain
    reading only if it keeps every period the plain engine proves, with the identical money reading."""
    from services.financial.statement_engine_profiles import furniture_text, matching_profile, profile_text
    profile = matching_profile(profile_text(sources), furniture_text(sources))
    if profile is None:
        return engine, None
    profiled = read_statements(sources, profile=profile)
    plain_keys = {(st['period_start'], st['period_end'], reading_key(st['_rows'])) for st in engine if st['engine']['proved']}
    profiled_keys = {(st['period_start'], st['period_end'], reading_key(st['_rows'])) for st in profiled if st['engine']['proved']}
    # A period the profile reads with the same money but holds for an identity reason it alone can see
    # (two sections printing one account number) is not lost: it is held, never served differently.
    identity_held = {(st['period_start'], st['period_end'], reading_key([r for r in st['_rows'] if r['kind'] != 'unresolved']))
                     for st in profiled if not st['engine']['proved'] and st['engine'].get('reason') in IDENTITY_HOLDS}
    if plain_keys <= profiled_keys | identity_held and profiled_keys:
        return profiled, profile['name']
    return engine, None


IDENTITY_HOLDS = ('account_shared',)


def _engine_only(sources):
    # Family readers (code) are skipped; library profiles (data) apply exactly as in normal routing.
    reading, profile = _profiled(sources, read_statements(sources))
    statements = [{k: v for k, v in s.items() if k != '_rows'} for s in reading if s['period_start']]
    claimed = {p for s in statements for p in _pages(s)}
    unclassified = [dict(page_number=s['page_number'], table_index=s['table_index'])
                    for s in sources if s['page_number'] not in claimed]
    return dict(statements=statements, unclassified_sources=unclassified, information_sources=[],
                complete_coverage=not unclassified, engine_routing=dict(mode='generic_only', profile=profile))


def route_catalog(sources, library_catalog):
    if generic_only():
        return _engine_only(sources)
    library = library_catalog(sources)
    if not generic_enabled():
        return library
    started = time.monotonic()
    # A library profile (data) that matches the document is used only if it keeps every period the
    # plain engine proves, with the identical money reading, and proves at least as many.
    engine, routing_profile = _profiled(sources, read_statements(sources))
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
        exact = len(matching) == 1 and _pages(matching[0]) == pages
        if not exact:
            # Row-level scope: the engine section and the library period share pages but not all of them
            # (sections sharing a page, covers, continuation pages). Exactly one library period of the same
            # printed period, currency, printed account and printed opening balance is cross-checked, and
            # replaced below only when no other library period shares the engine's pages.
            same = [g for g in matching if g.get('period_start') == statement['period_start']
                    and g.get('period_end') == statement['period_end']
                    and not (statement.get('currency') and g.get('currency') and g['currency'] != statement['currency'])
                    # Both print an account and it is the same one: sections of one period on shared pages
                    # (a zero product beside the main account) are never paired by their dates alone.
                    and statement.get('account_reference') and g.get('account_reference')
                    and _same_account(statement['account_reference'], g['account_reference'])]
            if len(same) != 1 or not statement['period_start']:
                continue
            matching = same
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
        if not exact and not _same_section(reading_key(library_rows), reading_key(engine_rows)):
            # Shared pages can hold several sections of one period; a different printed opening
            # balance means a different section, not a different reading of this one.
            routing['scoped_unpaired'] = routing.get('scoped_unpaired', 0) + 1
            continue
        if library_proved and not (reading_key(library_rows) == reading_key(engine_rows) and AGREEMENT_PREFERS_ENGINE
                                   and _engine_completes(statement, engine_rows, group, sources, currency)):
            if reading_key(library_rows) == reading_key(engine_rows):
                group['engine_agrees'] = True
                routing['agreements'] += 1
                if AGREEMENT_FILLS_IDENTITY and not any(
                        public.get(field) and group.get(field) and not _same_identity(field, public[field], group[field])
                        for field in IDENTITY):
                    # Both readers read every movement and balance alike from the same pages: a fact the
                    # library left unread is the engine's printed reading, never over a conflicting one.
                    filled = [field for field in AGREEMENT_FILLS if not group.get(field) and public.get(field)]
                    for field in filled:
                        group[field] = public[field]
                    if filled:
                        group['identity_from_engine'] = filled
                if not exact:
                    routing['scoped_agreements'] = routing.get('scoped_agreements', 0) + 1
            else:
                group['engine_disagreement'] = dict(engine_id=statement['id'],
                                                    layout_fingerprint=statement['layout_fingerprint'])
                routing['disagreements'].append(group['id'])
                logger.warning('Engine/library disagreement on statement %s (layout %s, fingerprint %s).',
                               group['id'], group.get('layout_id'), statement['layout_fingerprint'])
            continue
        agrees = reading_key(library_rows) == reading_key(engine_rows)
        if closing_reconciles(library_rows, is_liability(group)) and not agrees:
            # The library's reading reconciles its balances with a different reading (it may still be held
            # for another reason): it keeps the period. The engine replaces a reading that cannot reconcile,
            # or one that reads every movement and balance exactly as the engine proves them.
            if not exact:
                routing['scoped_unchecked'] = routing.get('scoped_unchecked', 0) + 1
            continue
        if not exact and (not _covers(statement, group, by_address) or any(other is not group and _pages(other) & pages
                                                              and not _rows_apart(statement, other, by_address)
                                                              for other in groups if not other.get('document_kind'))):
            # Row-level scope: the library period claims a page the engine section does not read, or the
            # engine's pages also hold another library period whose rows it may share; nothing is replaced.
            routing['scoped_unchecked'] = routing.get('scoped_unchecked', 0) + 1
            continue
        conflicts = [field for field in IDENTITY if public.get(field) and group.get(field)
                     and not _same_identity(field, public[field], group[field])]
        if conflicts:
            continue
        # The library cannot reconcile this period and the engine proves it: the engine serves under the
        # library id, with the library's identity facts where the engine read none.
        replaced = dict(public, id=group['id'], engine_id=statement['id'], replaced_layout=group.get('layout_id'))
        if not exact:
            scope = _own_scope(statement, [other for other in groups if other is not group
                                            and not other.get('document_kind') and _pages(other) & pages], sources)
            if scope is None:
                # After leaving out the rows another library period also claims, the engine section's
                # import region would still overlap that period's region on a shared page.
                routing['scoped_unchecked'] = routing.get('scoped_unchecked', 0) + 1
                continue
            replaced['section_sources'] = scope
        for field in IDENTITY:
            if not replaced.get(field) and group.get(field):
                replaced[field] = group[field]
                if field == 'currency':
                    replaced['currency_source'] = 'printed_account_section'
        if library_proved:
            # (Reached only through AGREEMENT_PREFERS_ENGINE.) An agreed period served by the engine only for the fact it alone establishes (AGREEMENT_PREFERS_
            # ENGINE): the facts both read alike keep the library's printing of them (the same name or account
            # written with or without its punctuation), so the period's account and holder read as they do on
            # the account's other saved statements.
            for field in AGREED_KEEPS_LIBRARY:
                if group.get(field):
                    replaced[field] = group[field]
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

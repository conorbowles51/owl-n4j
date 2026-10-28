"""Learned layout profiles: text-reader rules derived by the layout-learning loop, kept as DATA.

Each entry of ``learned_profiles.json`` (versioned in git, shipped by the normal release) is an ordinary
statement_engine_profiles profile (same rule families, same ``validate``) plus a ``learned`` block recording
where it came from: the layout fingerprint, the version, the proved page-image examples it re-reads exactly,
the gate results and the date it went live (services/financial/layout_learning.py writes it; a person reviews
the diff like any rule change).

A learned profile never displaces a written one the document prints (``pick``), and
statement_engine_routing._profiled keeps any profile's reading only when every period the plain reading proves
keeps identical money. So a learned profile
cannot change a reading that already proves, nor a person's saved work (it only reads; saving is unchanged).
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

REGISTRY = Path(__file__).with_name('learned_profiles.json')

# Learned profiles turned off by name (comma separated), as LOUPE_FINANCIAL_PROFILES_OFF does for written ones.
LEARNED_OFF = {n.strip() for n in os.environ.get('LOUPE_FINANCIAL_LEARNED_PROFILES_OFF', '').split(',') if n.strip()}

import logging

log = logging.getLogger(__name__)

_LOADED = {}
_CANDIDATES = []  # drafts under test (layout_learning.candidate); never persisted


def registry(path=None):
    """The registry file's content: {'version': n, 'profiles': [entry, ...]} (empty when absent)."""
    path = Path(path or REGISTRY)
    if not path.exists():
        return dict(version=0, profiles=[])
    return json.loads(path.read_text())


def rules_hash(rules):
    """The hash recorded with a registry entry: an entry whose rules were edited after its gates is refused (a
    revision is a new version under a new name, so the engine never serves a reading kept under an old name)."""
    import hashlib
    body = json.dumps({k: v for k, v in rules.items() if k not in ('name', 'learned')}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


# Bounds on a learned entry's lists: the engine compares every heading word with every listed phrase, so an
# unbounded list makes a matching file slow to read (measured: 2,000 column words, 28 s for a 6-page Truist
# file read in 0.5 s plainly). The written profiles' longest list has 12 phrases, the longest phrase 51 characters.
MAX_PHRASES = 40
MAX_PHRASE_CHARS = 200
# The registry's states (layout_learning.STATES and 'retired'); live and retired are served, the others are
# recorded only. Any other state is a malformed entry (refused with an ERROR).
STATES = ('unread', 'learning', 'draft_failed', 'gates_failed', 'passed', 'live', 'read', 'retired')


def _phrases(value):
    return (isinstance(value, list) and 0 < len(value) <= MAX_PHRASES
            and all(isinstance(p, str) and p.strip() and len(p) <= MAX_PHRASE_CHARS for p in value))


def _typed(rules):
    """Every rule value of the type the engine reads it as. statement_engine_profiles.validate checks the shape
    of the written profiles (each reviewed in code); a learned entry arrives as data, so each value is checked
    too: a wrongly typed value would raise inside the reading and lose the file's plain reading as well."""
    name = rules.get('name')
    bad = lambda what: ValueError('Learned profile %s: %s' % (name, what))
    if not isinstance(name, str) or not name.strip():
        raise bad('its name is not text')
    for key in ('labels', 'columns'):
        if key in rules and not (isinstance(rules[key], dict) and all(
                isinstance(role, str) and _phrases(words) for role, words in rules[key].items())):
            raise bad('%s must map each role to a list of printed words' % key)
    for key in ('institution', 'currency', 'convention', 'date_order', 'rule_mark'):
        if key in rules and not (isinstance(rules[key], str) and len(rules[key]) <= MAX_PHRASE_CHARS):
            raise bad('%s is not text' % key)
    if 'currency' in rules and not re.fullmatch(r'[A-Z]{3}', rules['currency']):
        raise bad('currency must be a three-letter code in capitals (the engine records it as given)')
    if len(rules.get('labels') or {}) > 12 or len(rules.get('columns') or {}) > 12:
        raise bad('too many label or column roles')
    for key in ('account_heading', 'statement_account', 'account_suffix_heading', 'client_line',
                'account_number_heading', 'direction_headings', 'repeated_column_groups', 'holdings_currency'):
        if key in rules and rules[key] is not True:
            raise bad('%s must be true when given' % key)
    if 'holder_heading' in rules and not (isinstance(rules['holder_heading'], dict)
                                          and _phrases(rules['holder_heading'].get('title'))):
        raise bad('holder_heading needs a list of printed titles')
    if 'prior_period_block' in rules and not (isinstance(rules['prior_period_block'], dict) and all(
            _phrases(v) for v in rules['prior_period_block'].values())):
        raise bad('prior_period_block needs lists of printed words')
    if 'column_order' in rules and not (isinstance(rules['column_order'], list) and len(rules['column_order']) <= 12
                                        and all(isinstance(r, str) for r in rules['column_order'])):
        raise bad('column_order must be a list of roles')
    first = rules.get('opening_from_first_day')
    if 'opening_from_first_day' in rules and not (isinstance(first, dict) and set(first) == {'cash_line'}
                                                  and _phrases(first['cash_line'])):
        raise bad('opening_from_first_day needs a cash_line list of printed words')


def _validated(entry):
    from services.financial import statement_engine_profiles as sep
    rules = {k: v for k, v in entry.items() if k != 'learned'}
    _typed(rules)
    match = rules.get('match')
    if not isinstance(match, dict) or not match.get('all') or set(match) - {'all', 'any'} or not all(
            _phrases(v) for v in match.values()):
        raise ValueError('Learned profile %s: match needs a non-empty list of printed phrases' % rules.get('name'))
    if any(p['name'] == rules.get('name') for p in sep.PROFILES if not p.get('learned')):
        raise ValueError('Learned profile %s has the name of a written profile' % rules.get('name'))
    sep.validate(rules)
    return dict(rules, learned=entry.get('learned') or True)


def _servable(entry):
    """An entry the engine may use: a learned block recording state live (or retired, kept only so saved choices
    naming it still resolve), gates that passed, a review that passed, and the hash of exactly these rules."""
    learned = entry.get('learned')
    if not isinstance(learned, dict) or learned.get('state') not in STATES:
        raise ValueError('Learned profile %s: its learned block or state is missing or not one of %s'
                         % (entry.get('name'), ', '.join(STATES)))
    if learned['state'] not in ('live', 'retired'):
        return False  # a draft, failed or passed entry: recorded, never served
    fingerprint = learned.get('fingerprint')
    if not (isinstance(fingerprint, str) and fingerprint.strip()):
        raise ValueError('Learned profile %s records no layout fingerprint' % entry.get('name'))
    gates = learned.get('gates')
    if not isinstance(gates, dict) or not (gates.get('corpus_passed') and gates.get('truth_passed')
                                           and learned.get('review') == 'PASS'):
        raise ValueError('Learned profile %s has no passing gates and review on record' % entry.get('name'))
    # The gates must have run on exactly these rules, with every written profile in force (not a backtest).
    if gates.get('rules_hash') != rules_hash(entry) or gates.get('profiles_off') != [] or not gates.get('corpus_dumped_at'):
        raise ValueError('Learned profile %s: its gate result is not for these rules with every profile on'
                         % entry.get('name'))
    if learned.get('rules_hash') != rules_hash(entry):
        raise ValueError('Learned profile %s was changed after its gates (rules hash differs)' % entry.get('name'))
    # The name carries the rules' hash: rules edited under the same name could be served a reading the engine
    # keeps under that name (statement_engine.read_statements caches by file and profile name).
    if not str(entry.get('name') or '').endswith(learned['rules_hash'][:12]):
        raise ValueError('Learned profile %s: its name must end with its rules hash (%s)'
                         % (entry.get('name'), learned['rules_hash'][:12]))
    return True


def problems(path=None):
    """[(name, why)] for every registry entry the engine refuses (the release test requires none)."""
    found = []
    try:
        entries = registry(path).get('profiles', [])
    except Exception as error:  # noqa: BLE001
        return [('(registry)', str(error))]
    if not isinstance(entries, list):
        return [('(registry)', 'the profiles are not a list')]
    for entry in entries:
        try:
            if not isinstance(entry, dict):
                raise ValueError('an entry is not an object')
            if _servable(entry):
                _validated(entry)
        except Exception as error:  # noqa: BLE001
            found.append((entry.get('name') if isinstance(entry, dict) else repr(entry)[:60], str(error)))
    return found


def reset():
    """Forget the loaded registry (the next read loads it again)."""
    global _LOADED
    _LOADED = {}


def _loaded():
    """The registry as loaded for its current file: {'stamp', 'all', 'profiles'}, or {} when there is none.

    Published whole by rebinding ``_LOADED`` (never mutated in place), so a reader on another thread sees either
    the old load or the new one, never a half-built or emptied one."""
    global _LOADED
    try:
        status = REGISTRY.stat()
        stamp = (status.st_mtime_ns, status.st_size, status.st_ino, status.st_ctime_ns)
    except FileNotFoundError:
        return {}
    except OSError as error:  # an unreadable registry serves no learned profile; written ones keep reading
        log.error('Learned profiles refused: the registry cannot be read (%s)', error)
        return {}
    loaded = _LOADED
    if loaded.get('stamp') == stamp:
        return loaded
    # Fail closed per entry: an entry the engine refuses is never served (ERROR in the journal); the others and
    # every written profile keep reading. A saved choice naming a refused entry finds no profile (held).
    accepted = []
    try:
        entries = registry().get('profiles', [])
    except Exception as error:  # noqa: BLE001 - an unreadable registry serves no learned profile at all
        log.error('Learned profiles refused: the registry cannot be read (%s)', error)
        entries = []
    if not isinstance(entries, list):
        log.error('Learned profiles refused: the registry\'s profiles are not a list')
        entries = []
    for entry in entries:
        try:
            if not isinstance(entry, dict):
                raise ValueError('a registry entry is not an object')
            if _servable(entry):
                accepted.append(_validated(entry))
        except Exception as error:  # noqa: BLE001 - one refused entry never stops the others
            log.error('Learned profile refused: %s', error)
    # One live version per layout: two would make every file of it ambiguous (read plainly again).
    layouts = Counter(p['learned'].get('fingerprint') for p in accepted if p['learned'].get('state') == 'live')
    doubled = {f for f, n in layouts.items() if n > 1}
    for p in accepted:
        if p['learned'].get('state') == 'live' and p['learned'].get('fingerprint') in doubled:
            log.error('Learned profile refused: %s shares its layout with another live version', p['name'])
    accepted = [p for p in accepted if not (p['learned'].get('state') == 'live'
                                            and p['learned'].get('fingerprint') in doubled)]
    loaded = dict(stamp=stamp, all=tuple(accepted),
                  profiles=tuple(p for p in accepted if p['learned'].get('state') == 'live'))
    _LOADED = loaded
    return loaded


def live():
    """The registry's live profiles (validated; loaded once per file change)."""
    return _loaded().get('profiles', ())


def everything():
    """Live and retired entries: what a by-name lookup may resolve (a saved choice naming an older version)."""
    return _loaded().get('all', ())


# The gates' exact learned set (layout_learning.with_profiles, the command-line tool only; never set in the server).
_OVERRIDE = None


def profiles():
    """Every learned profile the engine may use now: the live ones, then any draft under test."""
    if _OVERRIDE is not None:
        return tuple(p for p in _OVERRIDE if p['name'] not in LEARNED_OFF)
    found = [p for p in live() if p['name'] not in LEARNED_OFF]
    names = {p['name'] for p in _CANDIDATES}
    return tuple(p for p in found if p['name'] not in names) + tuple(_CANDIDATES)


def named(name):
    """The learned profile called ``name``. A saved choice naming a retired entry, or one switched off with
    LOUPE_FINANCIAL_LEARNED_PROFILES_OFF, still resolves (as LOUPE_FINANCIAL_PROFILES_OFF leaves a written profile
    resolvable by name): switching a profile off stops new matches, never the re-reading of saved work. Under the
    gates' exact set (``_OVERRIDE``) only that set resolves."""
    pool = tuple(_OVERRIDE) if _OVERRIDE is not None else profiles() + everything()
    return next((p for p in pool if p['name'] == name), None)


def _found(profiles, text):
    """statement_engine_profiles._matching over an explicit tuple (no module state is swapped)."""
    from services.financial.statement_engine_profiles import PROFILES_OFF
    lowered = ' '.join(text.lower().split())
    found = []
    for profile in profiles:
        if profile['name'] in PROFILES_OFF or (profile.get('learned') and profile['name'] in LEARNED_OFF):
            continue
        rule = profile['match']
        if all(p in lowered for p in rule.get('all', [])) and (not rule.get('any') or any(p in lowered for p in rule['any'])):
            found.append(profile)
    return found


def match_among(profiles, text, furniture=None):
    """statement_engine_profiles.matching_profile's rule over an explicit tuple: the one matching profile; with
    several, the one printed in the furniture, then the one matched by phrases that must all occur; else None."""
    found = _found(profiles, text)
    if len(found) > 1 and furniture is not None:
        printed = _found(profiles, furniture)
        if len(printed) == 1:
            found = printed
    if len(found) > 1:
        specific = [p for p in found if not p['match'].get('any')]
        found = specific if len(specific) == 1 else found
    return found[0] if len(found) == 1 else None


def pick(text, furniture, written, learned):
    """The profile the router uses, written and learned profiles together under the engine's matching rule (a
    profile printed in the document's furniture outranks one matched only by a movement line, '<date> | CAPITAL
    ONE ...'), with two limits on a learned profile:

    * a learned pick stands only when no written profile is printed in the furniture (the text without dated
      lines; the whole text when no furniture is given): a written profile the layout prints always wins;
    * in every other case (no learned pick, or the learned profiles changing which written profile would win
      the tie-breaks) the written profiles alone decide, exactly as before.

    Pure: the profile tuples are arguments; no module state is changed (the server reads on several threads).
    Measured on OPDMD66 (hand Truist profile removed): 6 of the 7 Truist files print a payment to Capital One in
    a movement line, so the written Capital One card profile matched their text but not their furniture."""
    written, learned = tuple(written), tuple(learned)
    found = match_among(written + learned, text, furniture)
    if found is not None and found.get('learned') and not _found(written, furniture if furniture is not None else text):
        return found
    # Otherwise the written rule alone decides: a learned profile can never move a file to a different written one.
    return match_among(written, text, furniture)


def matching(text, furniture=None):
    """The router's pick among the engine's written profiles and the registry's learned ones (``pick``)."""
    from services.financial import statement_engine_profiles as sep
    return pick(text, furniture, tuple(p for p in sep.PROFILES if not p.get('learned')), profiles())


@contextmanager
def candidate(profile):
    """``profile`` (a draft) among the learned profiles for this block only."""
    rules = _validated(profile)
    _CANDIDATES.append(rules)
    try:
        yield rules
    finally:
        _CANDIDATES.remove(rules)

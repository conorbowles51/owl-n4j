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


def _validated(entry):
    from services.financial import statement_engine_profiles as sep
    rules = {k: v for k, v in entry.items() if k != 'learned'}
    sep.validate(rules)
    return dict(rules, learned=entry.get('learned') or True)


def _servable(entry):
    """An entry the engine may use: a learned block recording state live (or retired, kept only so saved choices
    naming it still resolve), gates that passed, a review that passed, and the hash of exactly these rules."""
    learned = entry.get('learned')
    if not isinstance(learned, dict) or learned.get('state') not in ('live', 'retired'):
        return False
    gates = learned.get('gates') or {}
    if not (gates.get('corpus_passed') and gates.get('truth_passed') and learned.get('review') == 'PASS'):
        raise ValueError('Learned profile %s has no passing gates and review on record' % entry.get('name'))
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
    for entry in registry(path).get('profiles', []):
        try:
            if _servable(entry):
                _validated(entry)
        except ValueError as error:
            found.append((entry.get('name'), str(error)))
    return found


def live():
    """The registry's live profiles (validated; loaded once per file change)."""
    try:
        stamp = REGISTRY.stat().st_mtime_ns
    except FileNotFoundError:
        return ()
    if _LOADED.get('stamp') != stamp:
        # Fail closed per entry: an entry the engine refuses is never served (ERROR in the journal); the others and
        # every written profile keep reading. A saved choice naming a refused entry finds no profile (held).
        accepted = []
        for entry in registry().get('profiles', []):
            try:
                if _servable(entry):
                    accepted.append(_validated(entry))
            except ValueError as error:
                log.error('Learned profile refused: %s', error)
        _LOADED.update(stamp=stamp, all=tuple(accepted))
        _LOADED['profiles'] = tuple(p for p in _LOADED['all'] if p['learned'].get('state') == 'live')
    return _LOADED['profiles']


def everything():
    """Live and retired entries: what a by-name lookup may resolve (a saved choice naming an older version)."""
    live()
    return _LOADED.get('all', ())


def profiles():
    """Every learned profile the engine may use now: the live ones, then any draft under test."""
    found = [p for p in live() if p['name'] not in LEARNED_OFF]
    names = {p['name'] for p in _CANDIDATES}
    return tuple(p for p in found if p['name'] not in names) + tuple(_CANDIDATES)


def named(name):
    return next((p for p in profiles() + tuple(everything()) if p['name'] == name), None)


def pick(text, furniture, written, learned):
    """The profile the router uses, written and learned profiles together under statement_engine_profiles'
    matching rule (a profile printed in the document's furniture outranks one matched only by a movement line,
    '<date> | CAPITAL ONE ...'), with two limits on a learned profile:

    * a learned pick stands only when no written profile is printed in the furniture (the text without dated
      lines; the whole text when no furniture is given): a written profile the layout prints always wins;
    * when the learned profiles make the match ambiguous (None), the written profiles alone decide, as before.

    Measured on OPDMD66 (hand Truist profile removed): 6 of the 7 Truist files print a payment to Capital One in
    a movement line, so the written Capital One card profile matched their text but not their furniture."""
    from services.financial import statement_engine_profiles as sep
    match = getattr(sep.matching_profile, '__wrapped__', sep.matching_profile)
    written, learned = tuple(written), tuple(learned)
    saved = sep.PROFILES
    try:
        sep.PROFILES = written + learned
        found = match(text, furniture) if sep.PROFILES else None
        if found is not None and found.get('learned'):
            sep.PROFILES = written
            if sep._matching(furniture if furniture is not None else text):
                found = None
        if found is None:
            sep.PROFILES = written
            found = match(text, furniture) if written else None
    finally:
        sep.PROFILES = saved
    return found


def matching(text, furniture=None):
    """The router's pick among the engine's written profiles and the learned ones (``pick``)."""
    from services.financial import statement_engine_profiles as sep
    written = tuple(p for p in sep.PROFILES if not p.get('learned'))
    learned = tuple(p for p in sep.PROFILES if p.get('learned'))
    names = {p['name'] for p in learned}
    return pick(text, furniture, written, learned + tuple(p for p in profiles() if p['name'] not in names))


@contextmanager
def candidate(profile):
    """``profile`` (a draft) among the learned profiles for this block only."""
    rules = _validated(profile)
    _CANDIDATES.append(rules)
    try:
        yield rules
    finally:
        _CANDIDATES.remove(rules)

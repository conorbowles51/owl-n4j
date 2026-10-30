"""An account printed under different holder names on different statements: each statement keeps the name printed on it.

The page-image proof refuses a statement whose printed holder differs from every holder its account's saved statements
print ("This card (ending 8160) is saved for ERICA MCCAULEY; this statement prints ERICA HOPPER"), because Loupe never
treats two printed names as one person by itself. A person may decide, for one account, that its statements are
filed with it under the name each one prints. That decision is recorded here (an ``adjudications`` row on the account,
decision ``keep_printed_holders``, with the names it covers) before anything changes; nothing else is written.

What follows from it runs through the normal paths:

* the proof (vision_reader.prove) admits a statement of that account whose printed holder is one of the decided names,
  every other check unchanged, and marks the reading ``holder_basis = HOLDER_BASIS``;
* the saved statement keeps the holder it prints (its review's ``holder``), and its judgement call
  (``holder.printed_on_statement``) says the account is printed under different names, that this statement is
  attributed to the name printed on it, and that who holds the account has not been established;
* the account's history lists each printed name with the statements that print it (account_history).

The decision never says who holds the account and never renames anything: the account's own holder field and every
saved statement stay as printed.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

HOLDER_BASIS = 'printed_holder_decision'
RULE_ID = 'holder.printed_on_statement'


class PrintedHoldersError(ValueError):
    pass


def _key(name):
    from services.financial.field_proposals import holder_key
    return holder_key(name)


def _distinct(names):
    """The names, one per holder key (first spelling kept), in the order given."""
    seen, out = set(), []
    for name in names:
        name = ' '.join(str(name or '').split())
        if name and _key(name) not in seen:
            seen.add(_key(name))
            out.append(name)
    return out


def decisions(session, case_id):
    """{account id (str): {'holders': [...], 'decision_id', 'actor_name', 'at', 'reason'}}: the latest decision of each
    account of the case (a later one replaces an earlier one)."""
    from postgres.models.financial import AdjudicationEvent
    rows = session.execute(select(AdjudicationEvent.subject_id, AdjudicationEvent.id, AdjudicationEvent.after,
                                  AdjudicationEvent.actor_name, AdjudicationEvent.created_at,
                                  AdjudicationEvent.reason)
                           .where(AdjudicationEvent.case_id == case_id,
                                  AdjudicationEvent.decision == 'keep_printed_holders',
                                  AdjudicationEvent.subject_type == 'account')
                           .order_by(AdjudicationEvent.subject_id, AdjudicationEvent.subject_sequence)).all()
    out = {}
    for account_id, decision_id, after, actor, at, reason in rows:
        holders = _distinct((after or {}).get('holders') or [])
        out[str(account_id)] = dict(holders=holders if (after or {}).get('rule') == 'as_printed' else [],
                                    decision_id=str(decision_id), actor_name=actor or '',
                                    at=at.isoformat() if at else '', reason=reason or '')
    return {k: v for k, v in out.items() if len(v['holders']) > 1}


def fingerprint(session, case_id):
    """Changes whenever a decision of the case is recorded (case_knowledge's cache key)."""
    from sqlalchemy import func
    from postgres.models.financial import AdjudicationEvent
    return tuple(str(v) for v in session.execute(select(func.count(AdjudicationEvent.id),
                                                        func.max(AdjudicationEvent.created_at))
                                                 .where(AdjudicationEvent.case_id == case_id,
                                                        AdjudicationEvent.decision == 'keep_printed_holders')).one())


def covers(holders, printed, saved):
    """The decided names cover the statement's printed holder and every holder its account's saved statements print."""
    from services.financial.field_proposals import same_holder
    if len(holders) < 2 or not printed:
        return False
    return all(any(same_holder(name, h) for h in holders) for name in [printed, *saved])


def split(holders, printed, saved):
    """The account is printed under more than one of the decided names (this statement included)."""
    from services.financial.field_proposals import same_holder
    names = [printed, *saved]
    return len({next(i for i, h in enumerate(holders) if same_holder(name, h)) for name in names}) > 1


def judgement_sentence(holders, printed, page=None):
    """The 'Why?' sentence of a statement filed under the name printed on it."""
    shown = ' / '.join(holders)
    where = f' (page {page})' if page else ''
    return (f'This card or account is printed under different holder names on different statements ({shown}). '
            f'This statement is attributed to {printed}, the name printed on it{where}; which person holds the '
            f'account has not been established.')


def outcome_note(printed, holders):
    """Added to the page-image outcome of a statement filed under the name printed on it (queue line and journal)."""
    return (f' Filed under {printed}, the holder printed on it: this account is printed under different names '
            f'({" / ".join(holders)}), and a person decided each statement keeps its own. A judgement call; who holds '
            f'the account is not established.')


def record_decision(session, *, case_id, account_id, holders, actor, reason):
    """Record that the account's statements keep the holder printed on each (``holders``: every name it covers, at
    least two different holders). Returns the decision (an existing one covering the same names is returned as is).
    Raises PrintedHoldersError when the account is not in the case or the names are not two different holders."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from postgres.models.financial import FinancialAccount
    from services.financial.decisions import record
    account = session.get(FinancialAccount, uuid.UUID(str(account_id)))
    if account is None or str(account.case_id) != str(case_id):
        raise PrintedHoldersError('The account is not in this case.')
    names = _distinct(holders)
    if len(names) < 2:
        raise PrintedHoldersError('Name at least two different printed holder names.')
    current = decisions(session, account.case_id).get(str(account.id))
    if current and {_key(h) for h in current['holders']} == {_key(h) for h in names}:
        return current
    before = dict(rule='one_holder', holders=current['holders'] if current else [])
    after = dict(rule='as_printed', holders=names)
    event = record(session, case_id=account.case_id, subject=account, subject_type=AdjudicationSubject.account,
                   decision=AdjudicationDecision.keep_printed_holders, reason=reason, actor=actor,
                   before=before, after=after)
    return dict(holders=names, decision_id=str(event.id), actor_name=event.actor_name,
                at=event.created_at.isoformat() if event.created_at else '', reason=reason)


def merged_accounts(session, case_id):
    """{account id: the account it is merged into} for spreading a decision over a merge; {} (each account on its own,
    as before merges were read here) when the case's merge history needs review, which is logged, never raised: the
    proof and the judgement list keep working."""
    from services.financial.account_consolidation import AccountPartyError, canonical_map
    try:
        return canonical_map(session, case_id)
    except AccountPartyError:
        logging.getLogger(__name__).warning(
            'Case %s: account merge history needs review; printed-holders decisions apply to their own account only',
            str(case_id)[:8])
        return {}


def decisions_by_root(decided, canonical):
    """{root account id (UUID): the decision that applies to it} where a decision on any account merged into one reaches
    the whole merged account. Where two of them carry one, the latest recorded applies (ties: the decision id), and
    the decision lists the others as ``overridden`` (account, names, who, when), so that is said, never silent."""
    by_root = {}
    for account_id, decision in sorted(decided.items(), key=lambda pair: (str(pair[1].get('at') or ''),
                                                                          str(pair[1].get('decision_id') or ''))):
        account = uuid.UUID(str(account_id))
        root = canonical.get(account, account)
        earlier = by_root.get(root)
        entry = dict(decision, account_id=str(account), overridden=[])
        if earlier is not None:
            entry['overridden'] = earlier['overridden'] + [{k: earlier[k] for k in (
                'account_id', 'holders', 'decision_id', 'actor_name', 'at')}]
        by_root[root] = entry
    return by_root


def holders_by_statement(statements, names=()):
    """[{'name', 'statements', 'first', 'last'}] in first-printed order, one per holder: from [(holder, start, end)].

    ``names``: the decided names. A printed name is grouped under the first decided name it matches (same_holder),
    shown as decided, so the grouping does not depend on which spelling was printed first; a name matching none is
    grouped as before. ``printed`` lists each exact spelling printed in the group with its count, so a spelling that
    differs from the group's name stays visible."""
    from services.financial.field_proposals import same_holder
    groups = []
    for holder, start, end in sorted(statements, key=lambda s: (s[1] or '', s[2] or '')):
        name = ' '.join(str(holder or '').split())
        if not name:
            continue
        spelling = name
        name = next((decided for decided in names if same_holder(decided, name)), name)
        # One holder however it is spelt (same_holder, as the proof compares names).
        group = next((g for g in groups if g['name'] == name), None) or \
            next((g for g in groups if g['name'] not in names and name not in names and same_holder(g['name'], name)), None)
        if group is None:
            group = dict(name=name, statements=0, first=start or '', last=end or '', printed=[])
            groups.append(group)
        group['statements'] += 1
        seen = next((item for item in group['printed'] if item['name'] == spelling), None)
        if seen is None:
            group['printed'].append(dict(name=spelling, statements=1))
        else:
            seen['statements'] += 1
        group['last'] = end or group['last']
    return groups


def main(argv=None):
    """python -m services.financial.printed_holders --case C --account A --holder X --holder Y --decided-by NAME
    --decided-by-email EMAIL (--model NAME --model-id ID | --person-running) --why TEXT [--apply]: record a decision
    (dry run without --apply). With --model the record is the model's work carrying out the person's decision (its
    origin names the model, services.financial.model_work), shown as the model's until a person confirms it. A record
    under the person's own name needs --person-running: who runs it is always stated, never assumed."""
    import argparse
    import json
    from services.financial.decisions import Actor
    from postgres.session import _get_session_local
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True)
    parser.add_argument('--account', required=True)
    parser.add_argument('--holder', action='append', required=True)
    parser.add_argument('--decided-by', required=True)
    parser.add_argument('--decided-by-email', required=True)
    parser.add_argument('--decided-by-user-id', default=None)
    runner = parser.add_mutually_exclusive_group(required=True)
    runner.add_argument('--model', default='', help='the model carrying the decision out for the person deciding')
    runner.add_argument('--person-running', action='store_true',
                        help='the person deciding runs this command themselves (recorded under their name)')
    parser.add_argument('--model-id', default='')
    parser.add_argument('--why', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    user_id = uuid.UUID(args.decided_by_user_id) if args.decided_by_user_id else None
    if args.model:
        from services.financial.model_work import model_actor
        actor = model_actor(for_name=args.decided_by, for_email=args.decided_by_email, for_user_id=user_id,
                            model=args.model, model_id=args.model_id,
                            how=f'Recorded the decision {args.decided_by} made: {args.why}')
    else:
        actor = Actor(name=args.decided_by, email=args.decided_by_email, user_id=user_id)
    with _get_session_local()() as session:
        result = record_decision(session, case_id=args.case, account_id=args.account, holders=args.holder,
                                 actor=actor, reason=args.why)
        if args.apply:
            session.commit()
        else:
            session.rollback()
    print(json.dumps(dict(result, applied=args.apply)))


if __name__ == '__main__':
    main()

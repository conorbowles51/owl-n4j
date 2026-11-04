"""Every candidate pairing of a phone money reading with a ledger row, its strength by rule, and a person's decision
on it (05 section 4.3.8; Neil 2026-11-04: "if there are any payment matches at all they should be mentioned. With a
signal strength showing the user how well matched something is and how heavily substantiated. We don't want to miss
things based on an arbitrary cutoff." and "The user can confirm matches or reject which should be remembered by the
system.").

A pairing is offered whatever the correlation outcome: a reading the exact or near-amount pass corroborates keeps that
outcome, and every other row that could be it is listed beside it, strongest first, down to faint ones. The outcome
rules of 4.3.5 are unchanged; strength is extra and never promotes a reading (it stays p4) or a row.

Strength is computed here, never by a model, from three fits and one count:
- amount: the same to the cent (3), within the correlation tolerance (2), within a quarter (1, "could be fees or an
  exchange rate"), within the search bound (0);
- date: the ledger day is the alert's day (3), one day before to three after (2), inside the approach window (1),
  within the search bound (0);
- account: one account fits by bank and ending (3), one account fits by bank or ending alone (2), more than one
  fits (1), no account fits so the bank's accounts, or the case's, were searched (0);
- substantiation: independent sources behind the pairing: the phone record itself, the bank's usual alert wording,
  a reviewed bank, each other phone record stating the same amount on the same day, a balanced statement period.

The search bound (dates within ``SEARCH["days"]``, amount within ``SEARCH["amount_bp"]`` of the reading, same
currency and direction where the reading states them) exists for cost; whatever it leaves out is counted per reading
and stated on screen and in the agent's answer. At most ``SEARCH["per_reading"]`` pairings are kept per reading,
strongest first, and the count beyond that is stated too.

A decision (confirmed, rejected, undo) is a row in the case decision ledger (``adjudications``) on a
``phone_analysis_result_subjects`` row keyed by the phone record and the ledger row, so it survives reruns, releases
and re-parses; a ledger row that was later corrected is followed through ``superseded_by_id``. A rerun that no longer
finds a decided pairing keeps it visible ("no longer found by the rule"). Rejected pairings stay visible and are left
out of counts and the agent's corroboration totals.
"""
import hashlib
import re
import uuid
from datetime import date

from sqlalchemy import text

APPROACH = "money_signals"
SEARCH = {"days": 31, "amount_bp": 5000, "amount_floor_major": 5, "per_reading": 50}
QUARTER_BP = 2500
LEVELS = ("strong", "moderate", "weak", "faint")
LEVEL_WORDS = {"strong": "Strong", "moderate": "Moderate", "weak": "Weak", "faint": "Faint"}
DECISIONS = ("confirmed", "rejected")
_LEDGER = {"confirmed": "confirm_phone_result", "rejected": "reject_phone_result", "undo": "undo_phone_result_decision"}
MANUAL_KIND = "phone_money_match"


# ---- strength ------------------------------------------------------------------------------------------------------

def _tolerance_minor(amount_minor, currency):
    from services.financial.correlation import AmountRange, DEFAULT_MATERIALITY
    from services.financial.money import Money
    m = Money(abs(int(amount_minor)), currency)
    return DEFAULT_MATERIALITY.tolerance_for(AmountRange(m, m)).minor_units


def _exponent(currency):
    from services.financial.money import Money
    try:
        return Money(0, currency).currency_info.exponent
    except Exception:  # noqa: BLE001 - an unknown code reads as two decimals
        return 2


def search_bound_minor(amount_minor, currency):
    rel = abs(int(amount_minor)) * SEARCH["amount_bp"] // 10000
    return max(rel, SEARCH["amount_floor_major"] * 10 ** _exponent(currency))


def amount_fit(reading_minor, row_minor, currency):
    diff = abs(abs(int(reading_minor)) - abs(int(row_minor)))
    if diff == 0:
        return 3, diff
    if diff <= _tolerance_minor(reading_minor, currency):
        return 2, diff
    if diff <= abs(int(reading_minor)) * QUARTER_BP // 10000:
        return 1, diff
    return 0, diff


def date_fit(lag, window):
    if lag == 0:
        return 3
    if -1 <= lag <= 3:
        return 2
    if -window[0] <= lag <= window[1]:
        return 1
    return 0


def account_fit(binding, has_institution):
    if binding["outcome"] == "bound":
        return 3 if (binding["by_ending"] and has_institution) else 2
    if binding["outcome"] == "ambiguous":
        return 1
    return 0


def level(amount, when, account, substantiation):
    """The labelled scale (4.3.8). Never a model's call."""
    if amount >= 2 and when >= 2 and account >= 2 and substantiation >= 2:
        return "strong"
    if amount >= 2 and when >= 1 and (account >= 1 or substantiation >= 2):
        return "moderate"
    if (amount >= 1 and when >= 1) or amount >= 2:
        return "weak"
    return "faint"


def _money(minor, currency):
    exp = _exponent(currency)
    v = abs(int(minor))
    whole, frac = divmod(v, 10 ** exp) if exp else (v, 0)
    return ("%s %s.%0*d" % (currency, "{:,}".format(whole), exp, frac)) if exp else ("%s %s" % (currency, whole))


def reasons(amount, diff, currency, when, lag, account, binding_words, supports):
    """Plain reasons, the match part first, then what substantiates it."""
    match = [{3: "same amount to the cent",
              2: "amount within the usual tolerance (%s apart)" % _money(diff, currency),
              1: "amount %s apart, more than the tolerance (could be fees or an exchange rate)" % _money(diff, currency),
              0: "amount %s apart" % _money(diff, currency)}[amount]]
    match.append("same day" if lag == 0 else
                 ("payment %d day%s %s the phone record" % (abs(lag), "" if abs(lag) == 1 else "s",
                                                             "after" if lag > 0 else "before")))
    match.append(binding_words)
    return {"match": match, "substantiation": supports}


def _binding_words(binding, has_institution, unbound_scope):
    if binding["outcome"] == "bound":
        if binding["by_ending"] and has_institution:
            return "account fits by bank and ending"
        return "account bound by ending only" if binding["by_ending"] else "account bound by bank only"
    if binding["outcome"] == "ambiguous":
        return "more than one account fits (ambiguous)"
    return "no account fits; %s searched (unbound)" % unbound_scope


# ---- pairings ------------------------------------------------------------------------------------------------------

def candidate_accounts(binding, item, accounts):
    """(account ids, scope words). Bound or ambiguous: the accounts that fit; otherwise the bank's accounts in the
    records, else every account in the case (an unbound reading is still offered, at account fit 0)."""
    if binding["outcome"] in ("bound", "ambiguous"):
        return list(binding["accounts"]), None
    match = item["match"]
    if match is not None:
        from services.financial.field_proposals import same_institution
        names = [match.display_name] + list(getattr(match, "aliases", None) or [])
        at = [a["id"] for a in accounts.values() if a["institution"] and
              any(same_institution(a["institution"], n) for n in names)]
        if at:
            return at, "the bank's accounts in the records"
    return list(accounts), "every account in the case"


def pairings(item, binding, accounts, entries, group_of, window, other_records, matched_ids):
    """``(pairings, left_out)`` for one reading. ``other_records``: other phone records stating the same amount on
    the same day. ``matched_ids``: rows the correlation pass linked (they stay the rule's match)."""
    r = item["reading"]
    left = {"beyond_days": 0, "beyond_amount": 0, "other_direction": 0, "other_currency": 0, "beyond_cap": 0}
    if r.amount_minor is None or item["event_date"] is None:
        return [], dict(left, reason="event_time_missing" if item["event_date"] is None else "amount_missing")
    ids, scope = candidate_accounts(binding, item, accounts)
    has_inst = item["match"] is not None
    acc_fit = account_fit(binding, has_inst)
    words = _binding_words(binding, has_inst, scope)
    supports_base = ["the %s on the phone" % item.get("source_word", "record")]
    if item["strength"] == "institution_template":
        supports_base.append("the bank's usual alert wording")
    if item["match"] is not None and item["match"].via == "directory":
        supports_base.append("a reviewed bank (%s)" % item["match"].display_name)
    if other_records:
        supports_base.append("%d other phone record%s with the same amount that day"
                             % (other_records, "" if other_records == 1 else "s"))
    bound = search_bound_minor(r.amount_minor, r.currency or "USD")
    seen, out = set(), []
    for aid in ids:
        members = tuple(group_of(aid) or [aid])
        for m in members:
            for e in entries.get(m, []):
                if e["id"] in seen:
                    continue
                seen.add(e["id"])
                if r.currency and e["currency"] != r.currency:
                    left["other_currency"] += 1
                    continue
                if r.direction in ("debit", "credit") and e["direction"] != r.direction:
                    left["other_direction"] += 1
                    continue
                lag = (e["date"] - item["event_date"]).days
                diff = abs(abs(int(r.amount_minor)) - abs(int(e["amount_minor"])))
                if abs(lag) > SEARCH["days"]:
                    if diff <= bound:
                        left["beyond_days"] += 1
                    continue
                if diff > bound:
                    left["beyond_amount"] += 1
                    continue
                cur = e["currency"]
                a_fit, diff = amount_fit(r.amount_minor, e["amount_minor"], cur)
                d_fit = date_fit(lag, window)
                sup = list(supports_base)
                if e.get("reconciled"):
                    sup.append("a balanced statement period holds the payment")
                lvl = level(a_fit, d_fit, acc_fit, len(sup))
                out.append({
                    "transaction_id": e["id"], "ref_id": e["ref_id"], "account_id": aid,
                    "amount_minor": int(e["amount_minor"]), "currency": cur, "date": e["date"].isoformat(),
                    "direction": e["direction"], "lag_days": lag, "amount_diff_minor": diff,
                    "level": lvl, "fits": {"amount": a_fit, "date": d_fit, "account": acc_fit},
                    "match_score": a_fit + d_fit + acc_fit, "substantiation": len(sup),
                    "rule_match": e["id"] in matched_ids,
                    "reasons": reasons(a_fit, diff, cur, d_fit, lag, acc_fit, words, sup)})
    out.sort(key=sort_key)
    if len(out) > SEARCH["per_reading"]:
        left["beyond_cap"] = len(out) - SEARCH["per_reading"]
        out = out[:SEARCH["per_reading"]]
    return out, left


def sort_key(p):
    return (LEVELS.index(p["level"]), -int(p.get("rule_match", False)), -p["match_score"], -p["substantiation"],
            abs(p["lag_days"]), p["amount_diff_minor"], p["transaction_id"])


def best_rank(pairs):
    """An integer the results order by, strongest first (higher is stronger); -1 when nothing pairs."""
    if not pairs:
        return -1
    p = pairs[0]
    return (3 - LEVELS.index(p["level"])) * 1000 + p["match_score"] * 100 + min(p["substantiation"], 99)


def left_out_words(left):
    parts = []
    if left.get("beyond_days"):
        parts.append("%d more than %d days away" % (left["beyond_days"], SEARCH["days"]))
    if left.get("beyond_amount"):
        parts.append("%d whose amount differs by more than half" % left["beyond_amount"])
    if left.get("beyond_cap"):
        parts.append("%d beyond the %d strongest listed" % (left["beyond_cap"], SEARCH["per_reading"]))
    return ("Not listed: payments on these accounts " + ", ".join(parts) + ".") if parts else None


def search_words():
    return ("Every payment within %d days and within half of the amount (at least %d.00), in the same currency and "
            "direction where the phone states them, is listed, strongest first; payments outside that are counted, "
            "not hidden." % (SEARCH["days"], SEARCH["amount_floor_major"]))


def same_day_counts(items):
    """``{(amount, currency, day): set(record uids)}`` across the readings (substantiation by other records)."""
    out = {}
    for it in items:
        r = it["reading"]
        if r.amount_minor is None or it["event_date"] is None:
            continue
        out.setdefault((abs(int(r.amount_minor)), r.currency, it["event_date"]), set()).add(it["sig"]["record_uid"])
    return out


# ---- decisions -----------------------------------------------------------------------------------------------------

class PairError(ValueError):
    status = 422


class PairNotFound(PairError):
    status = 404


def pair_key(record_uid, field_path, transaction_id) -> str:
    return "%s#%s|%s" % (record_uid, field_path or "", transaction_id)


def subject_key(key) -> str:
    return hashlib.sha256(("pair\n" + key).encode("utf-8")).hexdigest()


def _effective(conn, case_id, txn_ids):
    """``{txn id: the row it now stands as}``, following ``superseded_by_id`` to the end (a corrected or merged row
    keeps its decision)."""
    if not txn_ids:
        return {}
    rows = conn.execute(text(
        "WITH RECURSIVE chain(start, cur, next, depth) AS (SELECT t.id, t.id, t.superseded_by_id, 0 FROM "
        "financial_transactions t WHERE t.case_id = :c AND t.id = ANY(CAST(:ids AS uuid[])) UNION ALL SELECT c.start, "
        "t.id, t.superseded_by_id, c.depth + 1 FROM chain c JOIN financial_transactions t ON t.id = c.next AND "
        "t.case_id = :c WHERE c.depth < 50) SELECT DISTINCT ON (start) start, cur FROM chain ORDER BY start, depth DESC"),
        {"c": str(case_id), "ids": [str(t) for t in txn_ids]})
    out = {str(t): str(t) for t in txn_ids}
    out.update({str(r.start): str(r.cur) for r in rows})
    return out


def _state(events):
    """Replay: confirm or reject pushes, undo pops. Returns (current event or None, prior event or None)."""
    stack = []
    for e in events:
        if e["decision"] == "undo":
            if stack:
                stack.pop()
        else:
            stack.append(e)
    return (stack[-1] if stack else None), (stack[-2] if len(stack) > 1 else None)


def case_decisions(conn, case_id, record_uids=None) -> dict:
    """``{(record_uid, field_path, effective txn id): {state, by, at, note, history, pair}}`` for the case."""
    rows = conn.execute(text(
        "SELECT a.subject_id, a.decision, a.reason, a.reason_kind, a.actor_name, a.created_at, a.after, "
        "a.subject_sequence FROM adjudications a JOIN phone_analysis_result_subjects s ON s.id = a.subject_id WHERE "
        "a.case_id = :c AND a.subject_type = 'phone_analysis_result' AND s.approach = :a AND a.after ? 'pair' "
        "ORDER BY a.subject_id, a.subject_sequence"), {"c": str(case_id), "a": APPROACH}).fetchall()
    by_subject = {}
    for r in rows:
        after = r.after or {}
        pair = after.get("pair") or {}
        if record_uids is not None and pair.get("record_uid") not in record_uids:
            continue
        by_subject.setdefault(str(r.subject_id), {"pair": pair, "events": []})["events"].append({
            "decision": after.get("decision"), "note": after.get("note") or "",
            "by": r.actor_name, "at": r.created_at.isoformat(), "found_by_rule": after.get("found_by_rule"),
            "strength": after.get("level")})
    eff = _effective(conn, case_id, {v["pair"].get("transaction_id") for v in by_subject.values()
                                     if v["pair"].get("transaction_id")})
    out = {}
    for sid, v in by_subject.items():
        cur, _ = _state(v["events"])
        p = v["pair"]
        key = (p.get("record_uid"), p.get("field_path") or "", eff.get(p.get("transaction_id"), p.get("transaction_id")))
        out[key] = {"state": cur["decision"] if cur else None, "by": cur["by"] if cur else None,
                    "at": cur["at"] if cur else None, "note": cur["note"] if cur else "",
                    "history": v["events"], "pair": p, "subject_id": sid,
                    "decided_on": p.get("transaction_id"), "now_row": key[2]}
    return out


def decision_words(d):
    if not d or not d.get("state"):
        return None
    day = (d.get("at") or "")[:10]
    if d["state"] == "confirmed":
        return "confirmed by %s %s" % (d["by"], day)
    return "rejected by %s%s" % (d["by"], (": " + d["note"]) if d.get("note") else "")


def overlay(conn, case_id, items):
    """Adds each pairing's decision to the money readings of a results page, appends decided pairings the rule no
    longer finds, and recounts with rejected pairings left out. ``items``: framework result dicts."""
    readings = [it for it in items if it.get("kind") == "money_reading"]
    if not readings:
        return items
    uids = set()
    for it in readings:
        m = it.get("measures") or {}
        if m.get("record_uid"):
            uids.add(m["record_uid"])
    decided = case_decisions(conn, case_id, uids) if uids else {}
    for it in readings:
        m = it["measures"] = dict(it.get("measures") or {})
        uid, fp = m.get("record_uid"), m.get("field_path") or ""
        pairs = []
        found = set()
        for p in m.get("pairings") or []:
            p = dict(p)
            d = decided.get((uid, fp, p["transaction_id"]))
            p["decision"] = d["state"] if d else None
            p["decision_words"] = decision_words(d)
            p["decision_note"] = d["note"] if d else ""
            p["found_by_rule"] = True
            p["rule_words"] = "found by the rule, strength %s" % p["level"]
            found.add(p["transaction_id"])
            pairs.append(p)
        for (duid, dfp, tid), d in decided.items():
            if duid == uid and dfp == fp and tid not in found and d["state"]:
                pairs.append({"transaction_id": tid, "ref_id": (d["pair"] or {}).get("ref_id"),
                              "level": d["history"][-1].get("strength") or "faint", "found_by_rule": False,
                              "decision": d["state"], "decision_note": d["note"],
                              "decision_words": decision_words(d) + ", no longer found by the rule",
                              "rule_words": "no longer found by the rule", "reasons": {"match": [], "substantiation": []},
                              "amount_minor": (d["pair"] or {}).get("amount_minor"),
                              "currency": (d["pair"] or {}).get("currency"), "date": (d["pair"] or {}).get("date")})
        m["pairings"] = pairs
        m["pair_counts"] = counts(pairs)
    return items


def counts(pairs):
    """Per strength level, rejected pairings left out; confirmed counted apart."""
    by = {lv: 0 for lv in LEVELS}
    confirmed = rejected = 0
    for p in pairs:
        if p.get("decision") == "rejected":
            rejected += 1
            continue
        if p.get("found_by_rule", True):
            by[p["level"]] = by.get(p["level"], 0) + 1
        if p.get("decision") == "confirmed":
            confirmed += 1
    return {"by_level": by, "confirmed": confirmed, "rejected": rejected}


def _current_reading(conn, case_id, record_uid, field_path):
    return conn.execute(text(
        "SELECT r.id, r.measures FROM phone_analysis_results r JOIN phone_analysis_runs x ON x.id = r.run_id AND "
        "x.status = 'completed' AND x.approach = :a WHERE r.case_id = :c AND r.kind = 'money_reading' AND "
        "r.measures ->> 'record_uid' = :u AND coalesce(r.measures ->> 'field_path', '') = :f ORDER BY x.finished_at "
        "DESC NULLS LAST LIMIT 1"), {"a": APPROACH, "c": str(case_id), "u": str(record_uid),
                                     "f": field_path or ""}).first()


def decide(db, case_id, record_uid, field_path, transaction_id, decision, note, actor) -> dict:
    """Confirm, reject or undo one pairing (05 4.3.8). Undo restores the state before the last decision. Confirm or
    reject needs the pairing in the current run (found by the rule) or an earlier decision on it."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from postgres.models.phone_analysis import PhoneAnalysisResultSubject
    from services import manual_changes
    from services.financial import decisions as D
    if decision not in ("confirmed", "rejected", "undo"):
        raise PairError("A match is confirmed or rejected, or the last decision is undone.")
    note = (note or "").strip()[:4000]
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", str(transaction_id)) or not re.fullmatch(r"[0-9a-fA-F-]{36}",
                                                                                      str(record_uid)):
        raise PairError("The record and the payment are named by their ids.")
    conn = db.connection()
    key = pair_key(record_uid, field_path, transaction_id)
    decided = case_decisions(conn, case_id, {str(record_uid)})
    eff = _effective(conn, case_id, [transaction_id]).get(str(transaction_id), str(transaction_id))
    prior = decided.get((str(record_uid), field_path or "", eff))
    reading = _current_reading(conn, case_id, record_uid, field_path)
    pair = None
    if reading is not None:
        pair = next((p for p in (reading.measures or {}).get("pairings") or [] if p["transaction_id"] == eff), None)
    if decision == "undo":
        if prior is None or not prior["state"]:
            raise PairError("There is no decision on this match to undo.")
        subject_hex, pair_info = prior["subject_id"], prior["pair"]
    else:
        if pair is None and prior is None:
            raise PairNotFound("That match is not in this case's current results.")
        if prior is not None:
            subject_hex, pair_info = prior["subject_id"], prior["pair"]
        else:
            pair_info = {"record_uid": str(record_uid), "field_path": field_path or "", "transaction_id": eff,
                         "ref_id": pair.get("ref_id"), "amount_minor": pair.get("amount_minor"),
                         "currency": pair.get("currency"), "date": pair.get("date")}
            subject_hex = None
    if subject_hex is None:
        skey = subject_key(pair_key(record_uid, field_path, eff))
        from services.phone_analysis.framework import subject_id
        sid = subject_id(case_id, APPROACH, skey)
        conn.execute(text("INSERT INTO phone_analysis_result_subjects (id, case_id, approach, result_key) VALUES (:i, "
                          ":c, :a, :k) ON CONFLICT DO NOTHING"), {"i": sid, "c": str(case_id), "a": APPROACH, "k": skey})
    else:
        sid = uuid.UUID(subject_hex)
    subject = db.get(PhoneAnalysisResultSubject, sid)
    before_state = prior["state"] if prior else None
    if decision == "undo":
        _, back = _state(prior["history"])
        after_state = back["decision"] if back else None
    else:
        after_state = decision
        if before_state == decision:
            raise PairError("This match is already %s." % decision)
    lvl = pair["level"] if pair else ((prior or {}).get("history") or [{}])[-1].get("strength")
    reason = note or {"confirmed": "Confirmed on the matches screen.", "rejected": "Rejected on the matches screen.",
                      "undo": "Undid the last decision on the matches screen."}[decision]
    # the pairing and its rule reading at the time are kept on the decision (the ledger row is the record)
    D.record(db, case_id=uuid.UUID(str(case_id)), subject=subject,
             subject_type=AdjudicationSubject.phone_analysis_result,
             decision=AdjudicationDecision(_LEDGER[decision]), reason=reason, actor=actor,
             reason_kind="typed" if note else "standard", before=None,
             after={"state": after_state, "prior_state": before_state, "decision": decision, "note": note,
                    "pair": pair_info, "level": lvl, "found_by_rule": pair is not None,
                    "reasons": (pair or {}).get("reasons"), "fits": (pair or {}).get("fits")})
    fits = (pair or {}).get("fits") or {}
    layout = "%s|amount%s|date%s|account%s" % (lvl or "", fits.get("amount", ""), fits.get("date", ""),
                                               fits.get("account", ""))
    subj = {"type": "phone_money_match", "id": key}
    link = "/cases/%s/phones/analysis/money" % case_id
    if decision == "confirmed":
        manual_changes.record_confirmation(db, MANUAL_KIND, case_id, subj, {"state": "confirmed", "level": lvl},
                                           actor, reason=note, link=link, field="pairing",
                                           producer="money_signals", layout=layout, source="phone")
    elif decision == "rejected":
        manual_changes.record_change(db, MANUAL_KIND, case_id, subj, {"state": before_state, "level": lvl},
                                     {"state": "rejected", "level": lvl}, actor, reason=note, link=link,
                                     change_type="set_aside", field="pairing", producer="money_signals",
                                     layout=layout, source="phone")
    else:
        manual_changes.record_change(db, MANUAL_KIND + "_undo", case_id, subj, {"state": before_state},
                                     {"state": after_state}, actor, reason=note, link=link, field="pairing",
                                     producer="money_signals", layout=layout, source="phone")
    db.flush()
    now = case_decisions(db.connection(), case_id, {str(record_uid)}).get((str(record_uid), field_path or "", eff))
    return {"record_uid": str(record_uid), "field_path": field_path or "", "transaction_id": eff,
            "decision": now["state"] if now else None, "decision_words": decision_words(now),
            "history": now["history"] if now else []}


def orphaned(conn, case_id) -> list:
    """Decided pairings whose reading is no longer in the current run at all (still shown, never dropped)."""
    decided = case_decisions(conn, case_id)
    if not decided:
        return []
    present = {(r.u, r.f or "") for r in conn.execute(text(
        "SELECT r.measures ->> 'record_uid' AS u, r.measures ->> 'field_path' AS f FROM phone_analysis_results r JOIN "
        "phone_analysis_runs x ON x.id = r.run_id AND x.status = 'completed' AND x.approach = :a WHERE r.case_id = :c "
        "AND r.kind = 'money_reading' AND x.id = (SELECT id FROM phone_analysis_runs WHERE case_id = :c AND approach = "
        ":a AND status = 'completed' ORDER BY finished_at DESC NULLS LAST, id LIMIT 1)"),
        {"a": APPROACH, "c": str(case_id)})}
    out = []
    for (uid, fp, tid), d in decided.items():
        if d["state"] and (uid, fp) not in present:
            out.append({"record_uid": uid, "field_path": fp, "transaction_id": tid, "decision": d["state"],
                        "decision_words": decision_words(d) + ", no longer found by the rule",
                        "pair": d["pair"]})
    return out

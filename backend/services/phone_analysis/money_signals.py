"""Approach 1a: money signals on the phone (docs/cellebrite/05 section 4).

1. Which financial events does the phone record (bank and payment alerts, short-code texts, bank emails, money named
   in conversations), and does each correspond to a transaction in the ledger built from the case's financial
   records?
2. Which institutions, accounts and cards does the phone show that are not among the case's financial records?

Every reading is a p4 claim (``correlation.Claim``; ``assign_proof_class(unstructured_narrative)``). Correlation
never promotes: a corroborated reading stays p4 and gains a link to the ledger row; the row gains nothing but that
link (``phone_analysis_result_records`` with role ``ledger_match``). Phase 1a passes coverage without a span, so an
absence is ``unresolved``, never ``contradicted`` (4.3.5 step 3; phase 1b is the coverage join).

Signals (4.2): S1 ``Notification`` (``ServiceIdentifier`` to an app package), S2 a text from a short code or named
sender (the sender's Party identifier, never the SMSC), S3 ``Email`` (the sender's domain), S4 ``InstalledApplication``,
S5 ``Cookie`` (domain only; the value is never read), S6 ``Password`` (service and server only; the secret is never
read) and ``UserAccount``, S7 ``VisitedPage`` and ``WebBookmark`` (host), S8 ``CreditCard`` (its number compared in the
backend for the ending, returned as the last four only) and ``Autofill`` card or account entries, S9 a message from
anyone else that states an amount (``unattributed``).

Decisions (recorded in 05 section 19):

- ``strength`` on a result is the reading strength of 4.3.6 (``institution_template``, ``institution_generic``,
  ``unattributed``) because 4.3.6 makes it the filter; the correlation outcome is ``measures.outcome``. Reverse if the
  results screen needs the outcome as the server-side filter.
- A reading that names neither an institution nor an account ending is not bound to any account and not
  correlated (``binding = no_anchor``): against every account of the case it would test a sentence nobody wrote.
  Reverse if M-1d measured on such readings shows they corroborate as reliably as anchored ones.
"""
from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from services.phone_analysis import institutions as INST
from services.phone_analysis import money_parse as P

CODE = "money_signals"
VERSION = "1a.1"
PARAMETERS = {
    "days_before": {"default": 1, "min": 0, "max": 7},
    "days_after": {"default": 7, "min": 0, "max": 31},
    "near_amount_pass": {"default": True, "choices": [True, False]},
}
KINDS = ("money_reading", "account_lead")
SUPPORTS = ("template_match", "reviewed_institution", "exact_amount", "bound_one_account", "corroborated",
            "evidence_transactional", "evidence_account", "evidence_presence")
UNDERCUTS = ("authorization_may_not_post", "alert_amount_may_exclude_fees", "binding_by_ending_only",
             "institution_from_sender_only", "currency_unknown", "ambiguous_separator", "country_unknown",
             "direction_unknown", "synced_attribution", "selective_extraction", "notification_retention",
             "identity_unreviewed", "institution_alias")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
CLAIM_NS = uuid.UUID("5d0c6a1e-27b9-4f6e-a0c3-1f8e2b9d4c71")
CLASS_RANK = {"transactional": 3, "account": 2, "presence": 1}
SOURCE_WORDS = {"S1": "notification", "S2": "text message", "S3": "email", "S9": "message"}
SIGNALS = [
    {"code": "notifications", "label": "Notifications", "types": ("Notification",)},
    {"code": "texts", "label": "Text messages", "types": ("InstantMessage",)},
    {"code": "emails", "label": "Emails", "types": ("Email",)},
    {"code": "apps", "label": "Installed apps", "types": ("InstalledApplication",)},
    {"code": "web", "label": "Cookies and visited pages", "types": ("Cookie", "VisitedPage", "WebBookmark")},
    {"code": "logins", "label": "Saved logins and accounts", "types": ("Password", "UserAccount")},
    {"code": "cards", "label": "Card records", "types": ("CreditCard", "Autofill")},
]
TYPES = tuple(t for s in SIGNALS for t in s["types"])
AUTOFILL_KEY = re.compile(r"(?i)card|account|acct|iban")
_last = {"counts": {}}


# ---- inputs --------------------------------------------------------------------------------------------------------

def ledger_revision(conn, case_id) -> str:
    """A digest of what the run reads from the financial records: effective rows, accounts and statement periods."""
    return conn.execute(text(
        "SELECT md5(coalesce((SELECT string_agg(t.id::text || ':' || t.ledger_status || ':' || coalesce("
        "t.superseded_by_id::text, '') || ':' || t.amount_minor || t.currency || t.direction || t.proof_class || ':' || "
        "coalesce(t.value_date::text, '') || coalesce(t.transaction_date::text, '') || coalesce(t.posted_date::text, '') "
        "|| coalesce(t.effective_date::text, '') || t.ordering_date || coalesce(t.counterparty_raw, ''), ',' ORDER BY "
        "t.id) FROM financial_transactions t WHERE t.case_id = :c), '') || '|' || coalesce((SELECT string_agg(a.id::text "
        "|| ':' || coalesce(a.institution_name, '') || ':' || coalesce(a.identifier_as_printed, '') || ':' || coalesce("
        "a.holder_name, '') || ':' || coalesce(a.metadata::text, ''), ',' ORDER BY a.id) FROM financial_accounts a WHERE "
        "a.case_id = :c), '') || '|' || coalesce((SELECT string_agg(p.id::text, ',' ORDER BY p.id) FROM "
        "financial_statement_periods p WHERE p.case_id = :c), ''))"), {"c": str(case_id)}).scalar()


def input_manifest(conn, case_id) -> dict:
    d = INST.load()
    return {"ledger": ledger_revision(conn, case_id), "directory": {"version": d["version"], "sha256": d["sha256"]},
            "aliases": [{k: str(v) for k, v in a.items() if k != "created_at"} for a in INST.aliases(conn, case_id)]}


def coverage(conn, case_id) -> dict:
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, str(case_id))
    counts = defaultdict(dict)
    for r in conn.execute(text(
            "SELECT extraction_id, model_type, count(*) FROM pv_record WHERE case_id = :c AND model_type = ANY(:t) "
            "GROUP BY 1, 2"), {"c": str(case_id), "t": list(TYPES)}):
        counts[str(r[0])][r[1]] = int(r[2])
    phones = {}
    for e, label in labels.items():
        active = conn.execute(text("SELECT standing = 'active' FROM phone_extractions WHERE id = :e"), {"e": e}).scalar()
        if not active:
            continue
        sig = {}
        for s in SIGNALS:
            n = sum(counts[e].get(t, 0) for t in s["types"])
            sig[s["code"]] = {"carries_signal": n > 0, "records": n}
        phones[e] = {"label": label, "signals": sig}
    return {"phones": phones, "signals": [{"code": s["code"], "label": s["label"]} for s in SIGNALS]}


def _phone_context(conn, case_id) -> dict:
    """Per active phone: label, device zone, country (owner number's country) and owner identity keys."""
    import phonenumbers
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, str(case_id))
    out = {}
    for r in conn.execute(text(
            "SELECT e.id, s.device_zone FROM phone_extractions e LEFT JOIN phone_interpretation_state s ON "
            "s.extraction_id = e.id WHERE e.case_id = :c AND e.standing = 'active'"), {"c": str(case_id)}):
        out[str(r.id)] = {"label": labels.get(str(r.id)), "zone": r.device_zone, "country": None, "owners": set()}
    for r in conn.execute(text(
            "SELECT extraction_id, identity_key, tier FROM phone_owner_candidates WHERE case_id = :c AND identity_key IS "
            "NOT NULL ORDER BY tier, identity_key"), {"c": str(case_id)}):
        p = out.get(str(r.extraction_id))
        if p is None:
            continue
        p["owners"].add(r.identity_key)
        if p["country"] is None and r.identity_key.startswith("phone:+"):
            try:
                p["country"] = phonenumbers.region_code_for_number(phonenumbers.parse(r.identity_key[6:], None))
            except phonenumbers.NumberParseException:
                pass
    return out


def _zone_date(instant, zone):
    if instant is None:
        return None
    if zone:
        try:
            from zoneinfo import ZoneInfo
            return instant.astimezone(ZoneInfo(zone)).date()
        except Exception:  # noqa: BLE001 - an unknown zone name reads in UTC, flagged by the caller
            pass
    return instant.astimezone(timezone.utc).date()


def read_signals(conn, case_id) -> list:
    """Every signal record of the case's active phones: ``{record_uid, extraction_id, model_type, instant, deleted,
    fields: {field_path: value}, sensitive: {field_path: value}, sender, url}``. Sensitive values are read only for
    S8 ending comparison and never leave this module unmasked."""
    rows = {}
    for r in conn.execute(text(
            "SELECT r.record_uid, r.extraction_id, r.model_type, r.first_instant, r.deleted_state FROM pv_record r WHERE "
            "r.case_id = :c AND r.model_type = ANY(:t) AND r.parent_record_uid IS NULL"),
            {"c": str(case_id), "t": list(TYPES)}):
        rows[str(r.record_uid)] = {"record_uid": str(r.record_uid), "extraction_id": str(r.extraction_id),
                                   "model_type": r.model_type, "instant": r.first_instant, "deleted": r.deleted_state,
                                   "fields": {}, "sensitive": {}, "sender": None, "url": None}
    if not rows:
        return []
    for r in conn.execute(text(
            "SELECT record_uid, field_path, value, is_sensitive FROM pv_text WHERE case_id = :c AND model_type = ANY(:t) "
            "AND value_index = 0"), {"c": str(case_id), "t": list(TYPES)}):
        x = rows.get(str(r.record_uid))
        if x is None:
            continue
        if r.is_sensitive:
            if (x["model_type"], r.field_path) in (("CreditCard", "CreditCardNumber"), ("Autofill", "Value")):
                x["sensitive"][r.field_path] = r.value
        else:
            x["fields"][r.field_path] = r.value
    for r in conn.execute(text(
            "SELECT p.parent_record_uid, x.value FROM pv_text x JOIN pv_record p ON p.record_uid = x.record_uid WHERE "
            "x.case_id = :c AND x.model_type = 'Party' AND x.field_path ~ '^From\\[\\d+\\]\\.Identifier$' AND "
            "x.value_index = 0"), {"c": str(case_id)}):
        x = rows.get(str(r.parent_record_uid))
        if x is not None and x["sender"] is None:
            x["sender"] = r.value
    from services.phone import body as B
    for r in conn.execute(text(
            "SELECT p.record_uid, b.body FROM pv_record p JOIN phone_records b ON b.extraction_id = p.extraction_id AND "
            "b.document_index = p.document_index AND b.ordinal = p.ordinal WHERE p.case_id = :c AND p.model_type IN "
            "('VisitedPage', 'WebBookmark')"), {"c": str(case_id)}):
        x = rows.get(str(r.record_uid))
        if x is not None:
            v = B.first_value(r.body, "Url")
            x["url"] = v.text if v is not None else None
    return list(rows.values())


def _ledger(conn, case_id):
    """(accounts, entries by account): the effective rows only (admitted, not superseded, ledger classes, from an
    admitted source), as ``account_mentions.account_references`` reads them; the corrected value is the one read."""
    from services.financial.proof_class import LEDGER_CLASSES
    classes = [c.value for c in LEDGER_CLASSES]
    accounts = {}
    for a in conn.execute(text(
            "SELECT a.id, a.institution_name, a.identifier_as_printed, a.iban, a.holder_name, a.metadata, (SELECT "
            "count(*) FROM financial_statement_periods p JOIN financial_source_documents s ON s.id = "
            "p.source_document_id WHERE p.account_id = a.id AND s.status = 'admitted') AS periods FROM "
            "financial_accounts a WHERE a.case_id = :c ORDER BY a.id"), {"c": str(case_id)}):
        meta = a.metadata or {}
        idents = [a.identifier_as_printed] + [i.get("value") for i in ((meta.get("identity_review") or {})
                                                                       .get("identifiers") or [])
                                              if i.get("kind") not in ("phone_number", "email")]
        accounts[str(a.id)] = {"id": str(a.id), "institution": a.institution_name, "printed": a.identifier_as_printed,
                               "identifiers": [i for i in idents if i], "holder": a.holder_name,
                               "periods": int(a.periods or 0), "referenced_only": bool(meta.get("referenced_only"))}
    entries = defaultdict(list)
    skipped = []
    for t in conn.execute(text(
            "SELECT t.id, t.ref_id, t.account_id, t.amount_minor, t.currency, t.direction, t.proof_class, t.value_date, "
            "t.transaction_date, t.posted_date, t.effective_date, t.provenance ->> 'date_basis' AS date_basis, "
            "t.counterparty_raw, t.description FROM financial_transactions t JOIN financial_source_documents s ON s.id = "
            "t.source_document_id JOIN financial_accounts a ON a.id = t.account_id WHERE t.case_id = :c AND s.case_id = "
            ":c AND a.case_id = :c AND t.ledger_status = 'admitted' AND t.superseded_by_id IS NULL AND s.status = "
            "'admitted' AND t.proof_class = ANY(:k) AND s.proof_class = ANY(:k) ORDER BY t.id"),
            {"c": str(case_id), "k": classes}):
        basis = next((f for f in ("value_date", "transaction_date", "posted_date", "effective_date")
                      if getattr(t, f)), None)
        if basis is None or t.date_basis == "statement_end_ordering_only":
            skipped.append(str(t.id))  # ordering-date-only rows cannot establish a match (claim_comparison)
            continue
        entries[str(t.account_id)].append({"id": str(t.id), "ref_id": t.ref_id, "amount_minor": int(t.amount_minor),
                                           "currency": t.currency, "direction": t.direction,
                                           "proof_class": t.proof_class, "date": getattr(t, basis), "basis": basis,
                                           "counterparty": t.counterparty_raw, "description": t.description})
    return accounts, entries, skipped


# ---- readings ------------------------------------------------------------------------------------------------------

def _institution_for(sig, directory, country):
    mt = sig["model_type"]
    f = sig["fields"]
    if mt == "Notification":
        return directory.by_package(f.get("ServiceIdentifier"))
    if mt == "InstantMessage":
        return directory.by_sms_sender(sig["sender"], country)
    if mt == "Email":
        return directory.by_domain(sig["sender"], "email_domain")
    return None


def _template(match, channel):
    if match is None or not match.reviewed:
        return None
    for t in match.entry.get("templates") or []:
        if t.get("channel") in (channel, None):
            return t
    return None


def _signal_code(sig, match):
    mt = sig["model_type"]
    if mt == "Notification":
        return "S1"
    if mt == "Email":
        return "S3"
    if mt == "InstantMessage" and (match is not None or INST.sender_kind(sig["sender"])):
        return "S2"
    return "S9"


def readings(signals, directory, phones) -> list:
    out = []
    for sig in signals:
        if sig["model_type"] not in ("Notification", "InstantMessage", "Email"):
            continue
        phone = phones.get(sig["extraction_id"]) or {}
        if sig["model_type"] == "InstantMessage" and sig["sender"] and \
                any(k.endswith(re.sub(r"\D", "", sig["sender"])) for k in phone.get("owners", ())
                    if re.sub(r"\D", "", sig["sender"])):
            continue  # the phone's own outgoing message
        match = _institution_for(sig, directory, phone.get("country"))
        tmpl = _template(match, {"Notification": "notification", "InstantMessage": "sms", "Email": "email"}
                         [sig["model_type"]])
        reading, field_path = None, None
        for fp in ("Body", "Subject", "Snippet"):
            value = sig["fields"].get(fp)
            if value:
                reading = P.parse(value, institution=match.entry if match else None, phone_country=phone.get("country"),
                                  template=tmpl)
                if reading is not None:
                    field_path = fp
                    break
        if reading is None:
            continue
        flags = list(reading.flags)
        if match is not None and match.country_unknown:
            flags.append("country_unknown")
        strength = ("unattributed" if match is None else
                    "institution_template" if tmpl is not None and reading.currency and reading.direction and
                    reading.amount_minor is not None else "institution_generic")
        if match is not None and match.country_unknown:
            strength = {"institution_template": "institution_generic"}.get(strength, strength)
        out.append({"signal": _signal_code(sig, match), "sig": sig, "match": match, "reading": reading,
                    "field_path": field_path, "quote": sig["fields"][field_path], "flags": flags,
                    "strength": strength, "event_instant": sig["instant"],
                    "event_date": _zone_date(sig["instant"], phone.get("zone")), "phone": phone})
    return out


# ---- binding and correlation ---------------------------------------------------------------------------------------

def _names(match):
    return [match.display_name] + list(match.entry.get("ledger_names") or [])


def bind(reading_item, accounts) -> dict:
    """4.3.4: ``{outcome, accounts, by_ending}``. ``outcome``: bound, ambiguous, institution_held_account_unseen,
    not_in_productions, no_anchor."""
    from services.financial.field_proposals import account_identity, account_match, same_institution
    match, r = reading_item["match"], reading_item["reading"]
    if match is None and not r.account_digits:
        return {"outcome": "no_anchor", "accounts": [], "by_ending": False}
    cands = list(accounts.values())
    at_institution = []
    if match is not None:
        at_institution = [a for a in cands if a["institution"] and
                          any(same_institution(a["institution"], n) for n in _names(match))]
        cands = at_institution
    by_ending = False
    if r.account_digits:
        ending = (r.account_digits, True)
        cands = [a for a in cands if any(account_match(ending, account_identity(i)) for i in a["identifiers"])]
        by_ending = True
    if len(cands) == 1:
        return {"outcome": "bound", "accounts": [cands[0]["id"]], "by_ending": by_ending}
    if len(cands) > 1:
        return {"outcome": "ambiguous", "accounts": [a["id"] for a in cands], "by_ending": by_ending}
    if at_institution:
        return {"outcome": "institution_held_account_unseen", "accounts": [], "by_ending": by_ending}
    return {"outcome": "not_in_productions", "accounts": [], "by_ending": by_ending}


def claim_for(item, account, case_source_id):
    """4.3.3: the p4 claim. The class is computed (unstructured narrative), never passed."""
    from services.financial.correlation import AmountRange, Claim, DateRange
    from services.financial.money import Money
    from services.financial.proof_class import SourceShape, assign_proof_class
    r = item["reading"]
    if assign_proof_class(SourceShape.unstructured_narrative).value != "p4":  # computed, never set
        raise RuntimeError("a phone reading must be p4")
    holder = account.get("holder")
    payer, payee = (holder, r.counterparty_text) if r.direction == "debit" else \
        (r.counterparty_text, holder) if r.direction == "credit" else (None, None)
    amount = Money(r.amount_minor, r.currency)
    d = item["event_date"]
    sig = item["sig"]
    locator = "%s#%s" % (sig["record_uid"], item["field_path"])
    return Claim(claim_id=uuid.uuid5(CLAIM_NS, "%s|%s|%s|%s" % (locator, r.amount_minor, r.currency, account["id"])),
                 amounts=AmountRange(amount, amount),
                 dates=DateRange(d - timedelta(days=item["window"][0]), d + timedelta(days=item["window"][1])),
                 quote=item["quote"], source_document_id=case_source_id, payer=payer, payee=payee,
                 speaker="%s %s" % (item["match"].display_name if item["match"] else "Unknown sender",
                                    SOURCE_WORDS[item["signal"]]),
                 locator=locator)


def _entries(rows, account):
    from postgres.models.enums import ProofClass, TransactionDirection
    from services.financial.correlation import LedgerEntry
    from services.financial.money import Money
    return [LedgerEntry(transaction_id=uuid.UUID(e["id"]), account_id=uuid.UUID(account["id"]), ordering_date=e["date"],
                        amount=Money(e["amount_minor"], e["currency"]), direction=TransactionDirection(e["direction"]),
                        proof_class=ProofClass(e["proof_class"]), holder=account.get("holder"),
                        counterparty=e["counterparty"], description=e["description"], reconciled=False)
            for e in rows]


def correlate_item(item, account, rows, case_source_id, near_amount_pass, coverage_for=None) -> dict:
    """4.3.5 for one account: the exact pass, then the default materiality over a claim still unresolved."""
    from services.financial.correlation import (AccountCoverage, Coverage, DEFAULT_MATERIALITY, Materiality,
                                                Outcome, correlate)
    claim = claim_for(item, account, case_source_id)
    entries = _entries(rows, account)
    cov = coverage_for(account, claim) if coverage_for else \
        Coverage([AccountCoverage(uuid.UUID(account["id"]), holder=account.get("holder"))])
    result = correlate(claim, entries, coverage=cov, materiality=Materiality(basis_points=0, floor_major_units=0))
    pass_ = "exact"
    if result.outcome is not Outcome.corroborated and near_amount_pass:
        second = correlate(claim, entries, coverage=cov, materiality=DEFAULT_MATERIALITY)
        if second.outcome is Outcome.corroborated:
            result, pass_ = second, "near_amount"
    by_id = {e["id"]: e for e in rows}
    cands = []
    for c in result.candidates:
        e = by_id[str(c.entry.transaction_id)]
        cands.append({"transaction_id": e["id"], "ref_id": e["ref_id"], "verdict": c.verdict.value,
                      "amount_minor": e["amount_minor"], "currency": e["currency"], "date": e["date"].isoformat(),
                      "date_basis": e["basis"], "direction": e["direction"]})
    keep = [c for c in cands if c["verdict"] in ("matches", "differs_on_amount", "inconclusive")]
    return {"account_id": account["id"], "outcome": result.outcome.value, "pass": pass_,
            "contradiction": result.contradiction.value if result.contradiction else None,
            "unresolved_reason": result.unresolved_reason.value if result.unresolved_reason else None,
            "notes": sorted(result.notes),
            "tolerance_minor": result.tolerance.minor_units if result.tolerance is not None else None,
            "candidates": keep[:20], "candidates_total": len(keep),
            "matches": [c["transaction_id"] for c in cands if c["verdict"] == "matches"]}


def _masked_ref(r):
    return ("ending %s" % r.account_digits) if r.account_digits else None


def _direction(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": list(locators)}


def reading_result(item, binding, per_account, accounts) -> dict:
    r, sig, match = item["reading"], item["sig"], item["match"]
    corroborated = [p for p in per_account if p["outcome"] == "corroborated"]
    if corroborated:
        outcome = "near_amount" if all(p["pass"] == "near_amount" for p in corroborated) else "corroborated"
    elif binding["outcome"] in ("bound", "ambiguous") and per_account:
        outcome = "unresolved"
    else:
        outcome = "not_tested"
    reason = None
    if outcome == "unresolved":
        reason = per_account[0]["unresolved_reason"]
    elif outcome == "not_tested":
        reason = ("amount_or_currency_missing" if not r.testable and binding["outcome"] in ("bound", "ambiguous")
                  else binding["outcome"])
    supports, undercuts = [], []
    loc = ["rec://%s#%s" % (sig["record_uid"], item["field_path"])]
    if item["strength"] == "institution_template":
        supports.append(_direction("template_match", "The text matched the institution's alert wording.", loc))
    if match is not None and match.via == "directory":
        supports.append(_direction("reviewed_institution", "%s is a reviewed institution." % match.display_name))
    if match is not None and match.via == "alias":
        undercuts.append(_direction("institution_alias", "A person in this case said this sender is %s."
                                    % match.display_name))
    if binding["outcome"] == "bound":
        supports.append(_direction("bound_one_account", "One account in the financial records fits."))
    if corroborated:
        lag = None
        matched_ids = [t for p in corroborated for t in p["matches"]]
        supports.append(_direction("corroborated", "A ledger row agrees on amount, currency and date.",
                                   ["ledger:%s" % t for t in matched_ids]))
        if outcome == "corroborated":
            supports.append(_direction("exact_amount", "The amount is the same to the cent."))
    else:
        undercuts.append(_direction("authorization_may_not_post", "An alert can describe a payment that was declined, "
                                    "reversed or never settled."))
        if item["signal"] in ("S1", "S2", "S3"):
            undercuts.append(_direction("alert_amount_may_exclude_fees", "The alert amount can leave out fees or an "
                                        "exchange rate."))
        if binding["by_ending"]:
            undercuts.append(_direction("binding_by_ending_only", "The account was chosen by its last digits."))
        if match is not None and match.channel in ("sms_sender", "email_domain"):
            undercuts.append(_direction("institution_from_sender_only", "The institution is known from the sender "
                                        "only."))
    for f in item["flags"]:
        if f in UNDERCUTS:
            undercuts.append(_direction(f, {"currency_unknown": "The currency is not stated.",
                                            "ambiguous_separator": "The amount could be read two ways.",
                                            "country_unknown": "The phone's country is not known.",
                                            "direction_unknown": "Money in or out is not stated."}.get(f, f)))
    if sig["model_type"] == "Notification":
        undercuts.append(_direction("notification_retention", "A phone keeps notifications for a short time; no "
                                    "alert in a period does not mean no payment."))
    lags = []
    matched_rows = []
    for p in corroborated:
        for c in p["candidates"]:
            if c["transaction_id"] in p["matches"]:
                lags.append((date.fromisoformat(c["date"]) - item["event_date"]).days)
                matched_rows.append({"transaction_id": c["transaction_id"], "ref_id": c["ref_id"],
                                     "account_id": p["account_id"]})
    records = [{"extraction_id": sig["extraction_id"], "record_uid": sig["record_uid"], "field_path": item["field_path"],
                "role": "evidence"}]
    records += [{"extraction_id": None, "record_uid": None, "field_path": None,
                 "ledger_transaction_id": m["transaction_id"], "role": "ledger_match"} for m in matched_rows]
    return {
        "kind": "money_reading", "strength": item["strength"],
        "measures": {
            "signal": item["signal"], "source": SOURCE_WORDS[item["signal"]], "phone_label": item["phone"].get("label"),
            "model_type": sig["model_type"], "deleted_state": sig["deleted"],
            "institution": ({"id": match.institution_id, "name": match.display_name, "via": match.via,
                             "channel": match.channel} if match else None),
            "amount_minor": r.amount_minor, "currency": r.currency, "amount_text": r.amount_text,
            "direction": r.direction, "account_ref": _masked_ref(r), "account_partial": r.account_partial,
            "counterparty_text": r.counterparty_text, "event_instant": item["event_instant"].isoformat()
            if item["event_instant"] else None, "event_date": item["event_date"].isoformat()
            if item["event_date"] else None, "stated_date": r.stated_date, "template": r.template,
            "flags": item["flags"], "spans": [list(s) for s in r.spans], "field_path": item["field_path"],
            "proof_class": "p4", "outcome": outcome, "reason": reason, "device_zone": item["phone"].get("zone"),
            "binding": {"outcome": binding["outcome"], "by_ending": binding["by_ending"],
                        "accounts": [{"id": a, "institution": accounts[a]["institution"],
                                      "ending": (re.sub(r"\D", "", accounts[a]["printed"] or "")[-4:] or None)}
                                     for a in binding["accounts"]]},
            "per_account": per_account, "matched": matched_rows, "lag_days": lags,
            "window_days": list(item["window"]),
        },
        "directions": {"supports": supports, "undercuts": undercuts},
        "sensitive": False,
        "period_start": item["event_instant"], "period_end": item["event_instant"],
        "records": records,
    }


# ---- leads ---------------------------------------------------------------------------------------------------------

def _evidence(signals, directory, phones, reading_items):
    """``[(institution match or None, ending or None, class, signal, record)]`` (4.3.7)."""
    out = []
    for item in reading_items:
        if item["signal"] in ("S1", "S2", "S3") and (item["match"] or item["reading"].account_digits):
            out.append((item["match"], item["reading"].account_digits, "transactional", item["signal"], item["sig"]))
    for sig in signals:
        mt, f = sig["model_type"], sig["fields"]
        match, ending, klass, code = None, None, None, None
        if mt == "InstalledApplication":
            match, klass, code = directory.by_package(f.get("Identifier")), "presence", "S4"
        elif mt == "Cookie":
            match, klass, code = directory.by_domain(f.get("Domain")), "presence", "S5"
        elif mt == "Password":
            match = directory.by_domain(f.get("Server")) or directory.by_domain(f.get("Service"))
            klass, code = "account", "S6"
        elif mt == "UserAccount":
            match = directory.by_package(f.get("ServiceIdentifier")) or directory.by_domain(f.get("ServiceType"))
            klass, code = "account", "S6"
        elif mt in ("VisitedPage", "WebBookmark"):
            match, klass, code = directory.by_domain(sig["url"]), "presence", "S7"
        elif mt == "CreditCard":
            digits = re.sub(r"\D", "", sig["sensitive"].get("CreditCardNumber") or "")
            ending = digits[-4:] if len(digits) >= 4 else None
            klass, code = "account", "S8"
        elif mt == "Autofill" and AUTOFILL_KEY.search(f.get("Key") or ""):
            digits = re.sub(r"\D", "", sig["sensitive"].get("Value") or "")
            ending = digits[-4:] if len(digits) >= 4 else None
            klass, code = "account", "S8"
        if klass and (match is not None or ending):
            out.append((match, ending, klass, code, sig))
    return out


def lead_status(match, ending, accounts) -> tuple:
    """(status, accounts matched): ``possible_statement`` when a matching account has a statement period,
    ``referenced_only`` when only a referenced account matches, else ``no_statement_found`` (as
    ``account_mentions.account_references``). Institution-only evidence matches any account at that institution."""
    from services.financial.field_proposals import account_identity, account_match, same_institution
    found = []
    for a in accounts.values():
        if match is not None and not (a["institution"] and any(same_institution(a["institution"], n)
                                                               for n in _names(match))):
            continue
        if ending and not any(account_match((ending, True), account_identity(i)) for i in a["identifiers"]):
            continue
        found.append(a)
    if any(a["periods"] for a in found):
        return "possible_statement", found
    if any(a["referenced_only"] for a in found):
        return "referenced_only", found
    return "no_statement_found", found


def _day(dt):
    return "%s %d, %d" % (dt.strftime("%B"), dt.day, dt.year)


def lead_sentence(name, ending, counts, first, last, status) -> str:
    """Lead copy (4.3.7 step 4): no em dash; never says what to ask for or from whom."""
    what = "an account ending %s" % ending if ending else None
    parts = []
    if counts.get("transactional"):
        n = counts["transactional"]
        s = "This phone holds %d %s" % (n, "alert" if n == 1 else "alerts")
        s += " from %s" % name if name else ""
        s += " for %s" % what if what else ""
        if first and last:
            s += ", from %s to %s" % (_day(first), _day(last)) if first.date() != last.date() else ", on %s" % _day(first)
        parts.append(s + ".")
    elif counts.get("account"):
        parts.append("This phone holds %s%s%s." % ("a saved login or card record", " for %s" % name if name else "",
                                                     " ending %s" % ending if ending else ""))
    else:
        parts.append("This phone had %s on it." % ("signs of %s" % name if name else "signs of this institution"))
    if status == "no_statement_found":
        if what and name:
            parts.append("No statement for %s at %s is among the financial records in this case." % (what, name))
        elif what:
            parts.append("No statement for %s is among the financial records in this case." % what)
        else:
            parts.append("No account at %s is among the financial records in this case." % name)
    elif status == "referenced_only":
        parts.append("The financial records name this account but hold no statement for it.")
    else:
        parts.append("A statement for a matching account is among the financial records in this case.")
    return " ".join(parts)


def leads(evidence, accounts) -> list:
    groups = {}
    for match, ending, klass, code, sig in evidence:
        key = (match.institution_id if match else None, ending)
        g = groups.setdefault(key, {"match": match, "ending": ending, "items": []})
        if g["match"] is None and match is not None:
            g["match"] = match
        g["items"].append((klass, code, sig))
    out = []
    for (inst_id, ending), g in sorted(groups.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")):
        counts = defaultdict(int)
        for klass, _, _ in g["items"]:
            counts[klass] += 1
        times = sorted(s["instant"] for _, _, s in g["items"] if s["instant"])
        status, found = lead_status(g["match"], ending, accounts)
        top = max(counts, key=lambda k: CLASS_RANK[k])
        name = g["match"].display_name if g["match"] else None
        records = {}
        for klass, code, sig in g["items"]:
            records[sig["record_uid"]] = {"extraction_id": sig["extraction_id"], "record_uid": sig["record_uid"],
                                          "field_path": None, "role": "evidence"}
        out.append({
            "kind": "account_lead", "strength": top,
            "measures": {"institution": ({"id": inst_id, "name": name, "via": g["match"].via} if g["match"] else None),
                         "account_ref": "ending %s" % ending if ending else None, "status": status,
                         "counts": dict(counts), "signals": sorted({c for _, c, _ in g["items"]}),
                         "first_seen": times[0].isoformat() if times else None,
                         "last_seen": times[-1].isoformat() if times else None,
                         "accounts": [a["id"] for a in found],
                         "sentence": lead_sentence(name, ending, counts, times[0] if times else None,
                                                   times[-1] if times else None, status)},
            "directions": {"supports": [_direction("evidence_" + k, "%d %s record%s" % (n, k, "" if n == 1 else "s"))
                                        for k, n in sorted(counts.items())],
                           "undercuts": [_direction("synced_attribution", "An app, login or email can be synced from "
                                                    "another device.")]},
            "sensitive": False, "period_start": times[0] if times else None, "period_end": times[-1] if times else None,
            "records": sorted(records.values(), key=lambda r: r["record_uid"]),
        })
    return out


# ---- run -----------------------------------------------------------------------------------------------------------

def _source_id(conn, case_id, extraction_id):
    """The evidence file of the production the phone came from; the extraction id when none is recorded."""
    v = conn.execute(text(
        "SELECT c.evidence_file_id FROM phone_extractions e JOIN phone_extraction_containers c ON c.id = "
        "e.first_container_id WHERE e.id = :e"), {"e": extraction_id}).scalar()
    return v if v is not None else uuid.UUID(str(extraction_id))


def analyse(conn, case_id, params, ctx=None, coverage_for=None) -> tuple:
    """(results, counts). ``coverage_for(account, claim)``: phase 1b supplies coverage; 1a passes none."""
    directory = INST.for_case(conn, case_id)
    phones = _phone_context(conn, case_id)
    signals = read_signals(conn, case_id)
    items = readings(signals, directory, phones)
    accounts, entries, skipped = _ledger(conn, case_id)
    window = (params["days_before"], params["days_after"])
    sources = {}
    results = []
    counts = {"readings_by_signal": defaultdict(int), "binding": defaultdict(int), "outcome": defaultdict(int),
              "lag_days": defaultdict(int), "ledger_rows_without_date": len(skipped)}
    merged = {}
    for i, item in enumerate(items):
        if ctx is not None and i % 200 == 0:
            ctx.progress(i, len(items))
            if ctx.cancelled():
                from services.phone_analysis.framework import Cancelled
                raise Cancelled()
        item["window"] = window
        counts["readings_by_signal"][item["signal"]] += 1
        b = bind(item, accounts)
        counts["binding"][b["outcome"]] += 1
        per = []
        r = item["reading"]
        if b["outcome"] in ("bound", "ambiguous") and r.testable and item["event_date"] is not None:
            ext = item["sig"]["extraction_id"]
            if ext not in sources:
                sources[ext] = _source_id(conn, case_id, ext)
            for aid in b["accounts"]:
                per.append(correlate_item(item, accounts[aid], entries.get(aid, []), sources[ext],
                                          params["near_amount_pass"], coverage_for))
        res = reading_result(item, b, per, accounts)
        counts["outcome"][res["measures"]["outcome"]] += 1
        for lag in res["measures"]["lag_days"]:
            counts["lag_days"][str(lag)] += 1
        merged[(item["sig"]["record_uid"])] = res
    results.extend(merged.values())
    lead_rows = leads(_evidence(signals, directory, phones, items), accounts)
    counts["leads"] = defaultdict(int)
    for lr in lead_rows:
        counts["leads"]["%s:%s" % (lr["measures"]["status"], lr["strength"])] += 1
    results.extend(lead_rows)
    counts = {k: (dict(v) if isinstance(v, defaultdict) else v) for k, v in counts.items()}
    counts["directory"] = {"version": directory.loaded["version"], "entries": len(directory.loaded["entries"]),
                           "reviewed": len(directory.used), "aliases": len(directory.aliases)}
    return results, counts


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]


# ---- the ledger side (4.4): "Also recorded on phone" ---------------------------------------------------------------

def phone_links(conn, case_id, transaction_ids) -> dict:
    """``{transaction_id: [{phone_label, source, instant, record_uid, link, result_id, outcome}]}`` from the case's
    current completed run. The ledger row's class is unchanged; this is a link only."""
    ids = [str(t) for t in transaction_ids][:500]
    if not ids:
        return {}
    out = defaultdict(list)
    for r in conn.execute(text(
            "SELECT x.ledger_transaction_id, res.id, res.measures, ev.record_uid, ev.field_path FROM "
            "phone_analysis_result_records x JOIN phone_analysis_results res ON res.id = x.result_id JOIN "
            "phone_analysis_runs run ON run.id = res.run_id AND run.status = 'completed' AND run.approach = :a JOIN "
            "phone_analysis_result_records ev ON ev.result_id = res.id AND ev.role = 'evidence' JOIN phone_extractions e "
            "ON e.id = ev.extraction_id AND e.standing = 'active' WHERE res.case_id = :c AND x.role = 'ledger_match' AND "
            "x.ledger_transaction_id = ANY(CAST(:t AS uuid[])) ORDER BY res.period_start, res.id"),
            {"a": CODE, "c": str(case_id), "t": ids}):
        m = r.measures or {}
        out[str(r.ledger_transaction_id)].append({
            "phone_label": m.get("phone_label"), "source": m.get("source"), "instant": m.get("event_instant"),
            "record_uid": str(r.record_uid), "link": "rec://%s#%s" % (r.record_uid, r.field_path),
            "url": "/cases/%s/records/%s" % (case_id, r.record_uid), "result_id": str(r.id),
            "outcome": m.get("outcome"), "proof_class": "p4"})
    return dict(out)

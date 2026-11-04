"""AI mapping drafts (02 section 6.8 step 2; cb-mapdrafts).

``POST /api/phones/registry/mapping-drafts {"type_name"}`` (admin) asks the ``phone_mapping_draft`` workload's model
(DeepSeek's strongest model by default, thinking at max: Neil, 2026-11-04) for a mapping file, from the registry's
structure only. The planner's decision: the "local model" in 6.8 step 2 is superseded by Neil's 4 Nov standing
decision; the input is registry structure only, less than Neil already allows to go out (phone text, 3 Nov).

What a draft can propose (finish item A):

- a record type (a ``phone_schema_types`` row): a ``type`` mapping (6.5), the shape of ``data/type/<name>.json``;
- a named set (a value type whose fields are named sets, e.g. ``DecodingSourceOptions``): an ``attribution`` row
  table (6.5b, spec 04 section 4.3) over the fields that carry the set, the shape of ``data/attribution/*.json``.

The other kinds (``activity_strength``, ``timestamp_meaning``, ``natural_key``, ``platform_family``,
``sensitive_fields``, ``dedup``) are written by the specs that own them and are not drafted here.

What reaches the model (``build_input``) is read from the ``phone_schema_*`` tables and the shipped mapping files
only: type, field and child-type names, field kinds, value types, named-set values, and counts. No record, no
evidence or extraction id and no case id is read (a test records every statement the input builder runs).

The answer is validated against the mapping schema (the loader's pydantic models, its static row checks) and the
registry (every field it names exists with the right value type). A valid answer is stored as a proposal
(``origin = ai_draft``, state ``draft``, the model and its version named). An invalid answer is stored too, state
``rejected``, with the reason as its event, so nothing the model said is dropped. A model that does not answer leaves
the run ``failed`` with the reason. Nothing here writes a mapping file, and nothing at interpretation time reads
``phone_mapping_proposals`` (6.8 step 2).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import threading
import time
import uuid
from typing import Any

from sqlalchemy import text

log = logging.getLogger(__name__)

WORKLOAD = "phone_mapping_draft"
REASONING_EFFORT = "max"
TIMEOUT_SECONDS = 900
SET_VALUES_SHOWN = 100
AUTOMATIC_ACTOR = "Loupe (automatic check of the model's answer)"
STATUSES = ("queued", "running", "drafted", "invalid", "failed")
TYPE_DIR = os.path.join(os.path.dirname(__file__), "mappings", "data")
ATTRIBUTION_OUTPUT_KEYS = {"flag", "group"}


class DraftRefused(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


# ---- what the draft is about ---------------------------------------------------------------------------------

def subject_kind(conn, name) -> str:
    """``type`` for a record type, ``attribution`` for a named set; 404 for a name the registry does not hold."""
    if conn.execute(text("SELECT 1 FROM phone_schema_types WHERE type_name = :n"), {"n": name}).scalar():
        return "type"
    named = conn.execute(text("SELECT 1 FROM phone_schema_fields WHERE value_type = :n AND is_named_set LIMIT 1"),
                         {"n": name}).scalar()
    if named or conn.execute(text("SELECT 1 FROM phone_schema_set_values WHERE set_name = :n LIMIT 1"),
                             {"n": name}).scalar():
        return "attribution"
    raise DraftRefused("The registry holds no type or named set called %s." % name, 404)


def _fields(conn, type_name):
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT field_name AS field, field_kind AS kind, value_type, is_named_set AS named_set, "
        "observed_value_count AS values_observed, observed_empty_count AS empty_observed, "
        "observed_extraction_count AS phones_observed, seed_value_count AS seed_values "
        "FROM phone_schema_fields WHERE type_name = :t ORDER BY field_name, field_kind, value_type"), {"t": type_name})]


def _set_values(conn, set_name):
    total = conn.execute(text("SELECT count(*) FROM phone_schema_set_values WHERE set_name = :s"),
                         {"s": set_name}).scalar()
    rows = conn.execute(text(
        "SELECT value, observed_count FROM phone_schema_set_values WHERE set_name = :s "
        "ORDER BY observed_count DESC, value LIMIT :n"), {"s": set_name, "n": SET_VALUES_SHOWN}).fetchall()
    # every limit is stated: the model is told how many values exist and how many it is shown
    return {"total_values": int(total), "values_shown": len(rows),
            "values": [[r.value, int(r.observed_count)] for r in rows]}


def _shipped(kind, name):
    path = os.path.join(TYPE_DIR, kind, "%s.json" % name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_input(conn, name, kind=None) -> dict:
    """The registry rows of one type (or named set) only. Reads ``phone_schema_*`` and the shipped mapping files."""
    kind = kind or subject_kind(conn, name)
    sets = {}
    if kind == "type":
        t = conn.execute(text(
            "SELECT type_name, observed_record_count, observed_extraction_count, seed_record_count, seed_report_count, "
            "seen_top_level, seen_nested FROM phone_schema_types WHERE type_name = :t"), {"t": name}).one()
        fields = _fields(conn, name)
        nested = []
        for n in conn.execute(text(
                "SELECT field_name, field_kind, child_type, observed_child_count FROM phone_schema_nesting "
                "WHERE parent_type = :t ORDER BY field_name, child_type"), {"t": name}):
            child_fields = _fields(conn, n.child_type) if n.child_type != name else []
            nested.append({"field": n.field_name, "kind": n.field_kind, "child_type": n.child_type,
                           "child_records_observed": int(n.observed_child_count),
                           "child_fields": [{k: f[k] for k in ("field", "kind", "value_type", "named_set",
                                                               "values_observed")} for f in child_fields]})
            for f in child_fields:
                if f["named_set"]:
                    sets.setdefault(f["value_type"], None)
        for f in fields:
            if f["named_set"]:
                sets.setdefault(f["value_type"], None)
        subject = {"type": name, "records_observed": int(t.observed_record_count),
                   "phones_observed": int(t.observed_extraction_count), "seed_records": int(t.seed_record_count),
                   "seed_reports": int(t.seed_report_count), "seen_top_level": bool(t.seen_top_level),
                   "seen_nested": bool(t.seen_nested), "fields": fields, "nested": nested}
        existing = _shipped("type", name)
    else:
        carriers = []
        for r in conn.execute(text(
                "SELECT f.type_name, f.field_name, f.field_kind, f.observed_value_count, t.observed_record_count "
                "FROM phone_schema_fields f JOIN phone_schema_types t ON t.type_name = f.type_name "
                "WHERE f.value_type = :s ORDER BY f.type_name, f.field_name"), {"s": name}):
            times = [x[0] for x in conn.execute(text(
                "SELECT DISTINCT field_name FROM phone_schema_fields WHERE type_name = :t AND value_type = 'TimeStamp' "
                "ORDER BY 1"), {"t": r.type_name})]
            carriers.append({"type": r.type_name, "field": r.field_name, "kind": r.field_kind,
                             "values_observed": int(r.observed_value_count),
                             "type_records_observed": int(r.observed_record_count), "type_time_fields": times})
        sets[name] = None
        subject = {"named_set": name, "carried_by": carriers}
        existing = _shipped("attribution", "catalogue")
    for s in sorted(sets):
        sets[s] = _set_values(conn, s)
    return {"kind": kind, "name": name, "subject": subject, "named_sets": sets,
            "existing_mapping": existing}


def input_summary(inp) -> dict:
    """Counts only, kept on the run (what the model was shown, and every limit)."""
    s = inp["subject"]
    return {"kind": inp["kind"], "name": inp["name"],
            "fields": len(s.get("fields") or []), "nested": len(s.get("nested") or []),
            "carried_by": len(s.get("carried_by") or []),
            "named_sets": {k: {"total_values": v["total_values"], "values_shown": v["values_shown"]}
                           for k, v in inp["named_sets"].items()},
            "existing_mapping": bool(inp["existing_mapping"])}


# ---- the prompt ------------------------------------------------------------------------------------------------

TYPE_RULES = """A `type` mapping body says what one record type's fields mean. Keys (all optional except applies_to):
- applies_to: the type name, exactly "{name}".
- comm_kind: one of "message", "call", "email", "voicemail", "chat_activity", "thread", or null when the record is
  not a communication.
- event_time: {{"field": <a TimeStamp field of the type, the moment the event happened>}} or {{"field": null}}.
- end_time: {{"field": <TimeStamp field or null>, "duration_field": <TimeSpan field or null>}}.
- other_times: [] (other TimeStamp fields keep their own timeline entries without being named here).
- participants: {{"containers": [nested field names whose child type is a party, e.g. "Parties"],
  "role_map": {{...}}, "owner_flag": <Boolean field on the party child type marking the phone's owner, or null>,
  "direction_field": <field of the type or null>}}. With containers, role_map keys are values of the party's role
  named set (e.g. "From": "caller"); without containers, role_map keys are nested field names of the type (e.g.
  "From": "sender").
- thread: {{"strategy": one of "parent_chat", "counterpart_set", "field", "none", "group_field": <field when strategy
  is "field", else null>}}.
- place: null, or {{"text_field": <String field holding written place text>}}, or {{"container": <nested field whose
  child type is Coordinate>}}.
- text_fields: [fields holding the record's words].
- status_fields: {{label: field}} for status-like fields.
- app_field, account_field: a field of the type or null.
- title: a short template such as "{{direction}} call, {{status}}", or null.
Every field you name must be one of the fields listed below (of the type, or of a nested child type where stated).
Name only what the structure supports; leave a key null or empty when unsure."""

ATTRIBUTION_RULES = """An `attribution` mapping is a row table. Each row says: for records of `type`, at the time field
`field`, when the predicates hold, the event carries the attribution flag in `outputs`. Rows:
{{"row_id": unique short id, "type": a type from carried_by, "field": one of that type's type_time_fields,
  "predicates": [{{"field": "{carrier}", "op": "eq" or "in", "value": a value (or list for "in") from the named set's
  values}}], "context": [], "outputs": {{"flag": a snake_case flag name, "group": "A" or "B"}},
  "basis": one of "field_name", "corpus_measured", "vendor_doc", "not_established",
  "reasoning": one sentence why, "would_change": one sentence naming the evidence that would change the row}}
Group A: the event may have been recorded by another device or account; group B: who recorded it is unknown.
Use only values listed for the named set. Two rows with the same type, field and an overlapping value are an error.
Propose rows only where the value's name supports a meaning; return an empty rows list when none does."""


def prompt(inp) -> str:
    kind, name = inp["kind"], inp["name"]
    if kind == "type":
        rules = TYPE_RULES.format(name=name)
        ask = ("Draft the `type` mapping body for the record type %s from the registry structure below." % name)
    else:
        carrier = (inp["subject"]["carried_by"] or [{"field": "UserMapping"}])[0]["field"]
        rules = ATTRIBUTION_RULES.format(carrier=carrier)
        ask = ("Draft `attribution` rows for the named set %s from the registry structure below." % name)
    return (
        "You draft mapping files for a forensic phone-report reader. A person reviews every draft before it is "
        "used; your draft is never applied as written.\n\n" + ask + "\n\n" + rules +
        "\n\nThe registry structure (names, kinds, value types, named-set values and counts; no record content). "
        "A named set lists its values with how many times each was observed; when values_shown is less than "
        "total_values, only the most observed values are shown.\n" +
        json.dumps({"subject": inp["subject"], "named_sets": inp["named_sets"]}, ensure_ascii=False,
                   separators=(",", ":")) +
        ("\n\nThe mapping currently shipped for this %s (for its shape; improve it only where the structure "
         "supports a change):\n%s" % ("type" if kind == "type" else "kind",
                                       json.dumps(inp["existing_mapping"]["body"], ensure_ascii=False,
                                                  separators=(",", ":")))
         if inp["existing_mapping"] else "") +
        '\n\nAnswer with one JSON object: {"body": <the mapping body>, "registry_requirements": [[type, field, '
        'kind, value_type], ...] for the fields the mapping depends on, "notes": "one or two sentences on what you '
        'were unsure of"}.')


# ---- validation ------------------------------------------------------------------------------------------------

def _field_index(conn, type_name):
    out = {}
    for r in conn.execute(text("SELECT field_name, field_kind, value_type, is_named_set FROM phone_schema_fields "
                               "WHERE type_name = :t"), {"t": type_name}):
        out.setdefault(r.field_name, []).append((r.field_kind, r.value_type, r.is_named_set))
    return out


def type_body_problems(conn, body) -> list:
    """6.5 field rules beyond the pydantic model: every named field exists on the type, or on a child type reached
    through a named container, with the value type the rule needs."""
    from services.phone.mappings.loader import TypeBody
    b = TypeBody.model_validate(body)
    t = b.applies_to
    problems = []
    own = _field_index(conn, t)
    nesting = {}
    for r in conn.execute(text("SELECT field_name, child_type FROM phone_schema_nesting WHERE parent_type = :t"),
                          {"t": t}):
        nesting.setdefault(r.field_name, set()).add(r.child_type)

    def has(fname, want=None):
        return any(want is None or vt == want for _k, vt, _n in own.get(fname, ()))

    for label, fname, want in (("event_time", b.event_time.field, "TimeStamp"), ("end_time", b.end_time.field,
                                "TimeStamp"), ("duration", b.end_time.duration_field, "TimeSpan")):
        if fname and not has(fname, want):
            problems.append("%s names %s.%s, which is not a %s field in the registry" % (label, t, fname, want))
    for i, ot in enumerate(b.other_times):
        f = ot.get("field") if isinstance(ot, dict) else None
        if not f or not has(f, "TimeStamp"):
            problems.append("other_times[%d] does not name a TimeStamp field of %s" % (i, t))
    containers = list(b.participants.containers)
    children = set()
    for c in containers:
        if c not in nesting:
            problems.append("participants container %s is not a nested field of %s" % (c, t))
        children |= nesting.get(c, set())
    child_fields = {}
    for ch in children:
        for f, v in _field_index(conn, ch).items():
            child_fields.setdefault(f, []).extend(v)
    if containers:
        role_sets = {vt for vs in child_fields.values() for _k, vt, ns in vs if ns}
        for key in b.participants.role_map:
            hit = role_sets and conn.execute(text(
                "SELECT 1 FROM phone_schema_set_values WHERE set_name = ANY(CAST(:s AS text[])) AND value = :v"),
                {"s": sorted(role_sets), "v": key}).scalar()
            if not hit:
                problems.append("role_map key %s is not a value of the party's named sets" % key)
    else:
        for key in b.participants.role_map:
            if key not in nesting:
                problems.append("role_map key %s is not a nested field of %s" % (key, t))
            else:
                children |= nesting[key]
                for ch in nesting[key]:
                    for f, v in _field_index(conn, ch).items():
                        child_fields.setdefault(f, []).extend(v)
    for label, fname in (("owner_flag", b.participants.owner_flag),
                         ("direction_field", b.participants.direction_field)):
        if fname and fname not in own and fname not in child_fields:
            problems.append("%s %s is not a field of %s or of its party type" % (label, fname, t))
    named = [("text_fields", f) for f in b.text_fields] + [("status_fields", f) for f in b.status_fields.values()]
    named += [("app_field", b.app_field), ("account_field", b.account_field), ("thread.group_field",
                                                                                b.thread.group_field)]
    for label, fname in named:
        if fname and fname not in own and fname not in nesting:
            problems.append("%s names %s, which is not a field of %s" % (label, fname, t))
    if b.thread.strategy == "field" and not b.thread.group_field:
        problems.append("thread strategy field needs a group_field")
    if b.place is not None:
        keys = set(b.place)
        if keys == {"text_field"}:
            if not has(b.place["text_field"], "String"):
                problems.append("place text_field %s is not a String field of %s" % (b.place["text_field"], t))
        elif keys == {"container"}:
            if "Coordinate" not in nesting.get(b.place["container"], set()):
                problems.append("place container %s is not a nested Coordinate of %s" % (b.place["container"], t))
        else:
            problems.append("place must be null, {text_field} or {container}")
    if b.extra:
        problems.append("a draft names nothing under extra")
    if b.activity_strength is not None and set(b.activity_strength) != {"$ref"}:
        problems.append("activity_strength is null or {$ref}")
    return problems


def attribution_problems(conn, name, body) -> list:
    from services.phone.mappings.loader import RowsBody
    rb = RowsBody.model_validate(body)
    problems = []
    carriers = {(r.type_name, r.field_name) for r in conn.execute(text(
        "SELECT type_name, field_name FROM phone_schema_fields WHERE value_type = :s"), {"s": name})}
    carrier_types = {t for t, _ in carriers}
    seen = set()
    for r in rb.rows:
        if r.row_id in seen:
            problems.append("row_id %s appears twice" % r.row_id)
        seen.add(r.row_id)
        if r.type not in carrier_types:
            problems.append("%s: type %s does not carry %s" % (r.row_id, r.type, name))
        if not r.field or not conn.execute(text(
                "SELECT 1 FROM phone_schema_fields WHERE type_name = :t AND field_name = :f AND value_type = "
                "'TimeStamp'"), {"t": r.type, "f": r.field}).scalar():
            problems.append("%s: field %s is not a TimeStamp field of %s" % (r.row_id, r.field, r.type))
        if set(r.outputs) != ATTRIBUTION_OUTPUT_KEYS or not all(isinstance(r.outputs.get(k), str) and r.outputs[k]
                                                                 for k in ATTRIBUTION_OUTPUT_KEYS):
            problems.append("%s: outputs must be {flag, group}" % r.row_id)
        if not r.predicates:
            problems.append("%s: no predicate on the named set" % r.row_id)
    return problems


def validate(conn, inp, answer, model_label) -> tuple[dict | None, list]:
    """(envelope, problems). The envelope is the file a person edits: status draft, origin ai_draft, no reviewer."""
    from pydantic import ValidationError

    from services.phone.mappings import loader
    from services.phone.mappings import rows as row_rules
    if not isinstance(answer, dict) or not isinstance(answer.get("body"), dict):
        return None, ["the answer has no body object"]
    kind, name = inp["kind"], inp["name"]
    reqs = answer.get("registry_requirements") or []
    notes = str(answer.get("notes") or "").strip()[:1000]
    envelope = {
        "kind": kind, "name": name, "version": 1, "status": "draft", "origin": "ai_draft",
        "review": {"reviewed_by": None, "reviewed_on": None,
                   "basis": "Drafted by %s on %s · not reviewed.%s" % (model_label, dt.date.today().isoformat(),
                                                                      (" Model's note: " + notes) if notes else ""),
                   "registry_requirements": reqs},
        "body": answer["body"]}
    try:
        loader.Envelope.model_validate(envelope)
        if kind == "type":
            if answer["body"].get("applies_to") != name:
                return envelope, ["applies_to is %r, not %s" % (answer["body"].get("applies_to"), name)]
            loader.TypeBody.model_validate(answer["body"])
        else:
            loader.RowsBody.model_validate(answer["body"])
    except ValidationError as exc:
        return envelope, ["not a valid mapping: %s" % "; ".join(
            "%s: %s" % (".".join(str(x) for x in e["loc"]), e["msg"]) for e in exc.errors()[:8])]
    problems = []
    m = loader.Mapping(kind, name, 1, "draft", "ai_draft", None, None, envelope, "0" * 64, uuid.uuid4(), "draft")
    if kind == "type":
        problems += type_body_problems(conn, answer["body"])
    else:
        problems += attribution_problems(conn, name, answer["body"])
        try:
            row_rules.check_static(m)
        except Exception as exc:  # noqa: BLE001 - the loader's own refusal, shown as the reason
            problems.append(str(exc))
    problems += loader.registry_problems(conn, m, requirements=True)
    return envelope, problems


# ---- runs ------------------------------------------------------------------------------------------------------

def create_run(conn, name, *, actor_name, actor_email=None, actor_user_id=None) -> uuid.UUID:
    kind = subject_kind(conn, name)
    busy = conn.execute(text("SELECT id FROM phone_mapping_draft_runs WHERE name = :n AND status IN ('queued', "
                             "'running') AND created_at > now() - interval '30 minutes'"), {"n": name}).scalar()
    if busy:
        raise DraftRefused("A draft for %s is already running (%s)." % (name, busy), 409)
    rid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO phone_mapping_draft_runs (id, kind, name, status, requested_by_name, requested_by_email, "
        "requested_by_user_id) VALUES (:i, :k, :n, 'queued', :an, :ae, :au)"),
        {"i": rid, "k": kind, "n": name, "an": actor_name, "ae": actor_email, "au": actor_user_id})
    return rid


def _store_proposal(conn, run, envelope, raw, model, model_version, problems):
    pid = uuid.uuid4()
    content = envelope if envelope is not None else {"kind": run.kind, "name": run.name, "unparsed_answer": raw[:20000]}
    conn.execute(text(
        "INSERT INTO phone_mapping_proposals (id, kind, name, content, model, model_version, origin, state) VALUES "
        "(:i, :k, :n, CAST(:c AS jsonb), :m, :mv, 'ai_draft', 'draft')"),
        {"i": pid, "k": run.kind, "n": run.name, "c": json.dumps(content, ensure_ascii=False), "m": model,
         "mv": model_version})
    if problems:
        from services.phone import proposals
        proposals.reject(conn, pid, "The model's answer is not a valid mapping: " + "; ".join(problems)[:3500],
                         actor_name=AUTOMATIC_ACTOR)
    return pid


def default_ask(db, prompt_text):
    """(answer text, provider, model, usage, model_version). The workload's model; DeepSeek thinks at max."""
    from services.ai_model_policy import get_workload_model
    from services.ai_provider_credentials import get_provider_api_key
    from services.llm_service import LLMExecutionContext
    provider, model_id = get_workload_model(db, WORKLOAD)
    api_key = get_provider_api_key(db, provider)
    if not api_key:
        raise RuntimeError("%s is not configured for phone mapping drafts" % provider.title())
    # End the read transaction before the model thinks (minutes): a background session idle in a transaction is
    # ended by Postgres (postgres/session.py idle_in_transaction_option).
    db.rollback()
    llm = LLMExecutionContext(provider=provider, model_id=model_id, api_key=api_key, use_responses_api_for_gpt5=True)
    raw = llm.call(prompt_text, temperature=0.1, json_mode=True, timeout=TIMEOUT_SECONDS,
                   reasoning_effort=REASONING_EFFORT if provider == "deepseek" else None)
    meta = llm.last_response_metadata or {}
    version = meta.get("reported_model") or model_id
    return raw, provider, model_id, dict(llm.last_usage or {}), str(version)


def execute_run(session, run_id, ask=None) -> dict:
    """Run one draft. ``session`` is an ORM session (the model policy and cost records need one); commits as it
    goes so the page sees ``running`` while the model thinks."""
    ask = ask or default_ask
    conn = session.connection()
    run = conn.execute(text("SELECT * FROM phone_mapping_draft_runs WHERE id = :i FOR UPDATE"), {"i": run_id}).one()
    inp = build_input(conn, run.name, run.kind)
    conn.execute(text("UPDATE phone_mapping_draft_runs SET status = 'running', started_at = now(), "
                      "input_summary = CAST(:s AS jsonb) WHERE id = :i"),
                 {"i": run_id, "s": json.dumps(input_summary(inp))})
    session.commit()
    started = time.monotonic()
    usage, provider, model, version = {}, None, None, None
    try:
        raw, provider, model, usage, version = ask(session, prompt(inp))
    except Exception as exc:  # noqa: BLE001 - the reason is kept on the run and shown on the page
        session.rollback()
        conn = session.connection()
        conn.execute(text("UPDATE phone_mapping_draft_runs SET status = 'failed', error = :e, seconds = :s, "
                          "finished_at = now() WHERE id = :i"),
                     {"i": run_id, "e": ("The model gave no answer: %s" % exc)[:2000],
                      "s": round(time.monotonic() - started, 1)})
        session.commit()
        return read_run(session.connection(), run_id)
    seconds = round(time.monotonic() - started, 1)
    conn = session.connection()
    cost = _record_cost(session, run, provider, model, usage, seconds)
    try:
        answer = json.loads(raw)
    except (TypeError, ValueError):
        answer = None
    if answer is None:
        envelope, problems = None, ["the answer is not JSON"]
    else:
        envelope, problems = validate(conn, inp, answer, "%s (%s)" % (model, provider))
    pid = _store_proposal(conn, run, envelope, raw or "", model, version, problems)
    conn.execute(text(
        "UPDATE phone_mapping_draft_runs SET status = :st, provider = :p, model = :m, proposal_id = :pid, error = :e, "
        "seconds = :s, prompt_tokens = :pt, completion_tokens = :ct, cost_usd = :c, finished_at = now() WHERE id = :i"),
        {"i": run_id, "st": "invalid" if problems else "drafted", "p": provider, "m": model, "pid": pid,
         "e": "; ".join(problems)[:2000] if problems else None, "s": seconds, "pt": usage.get("prompt_tokens"),
         "ct": usage.get("completion_tokens"), "c": cost})
    session.commit()
    return read_run(session.connection(), run_id)


def _record_cost(session, run, provider, model, usage, seconds):
    if not any(usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")):
        return None
    from postgres.models.cost_record import CostJobType
    from services.ai_costs_service import CostOperationKind, record_cost
    rec = record_cost(db=session, job_type=CostJobType.AI_ASSISTANT, provider=provider, model_id=model,
                      operation_kind=CostOperationKind.CHAT_COMPLETION, prompt_tokens=usage.get("prompt_tokens"),
                      completion_tokens=usage.get("completion_tokens"), total_tokens=usage.get("total_tokens"),
                      duration_seconds=seconds, user_id=run.requested_by_user_id,
                      description="Phone mapping draft: %s %s" % (run.kind, run.name),
                      extra_metadata={"workload": WORKLOAD, "mapping_draft_run_id": str(run.id)})
    return float(rec.cost_usd) if rec.cost_usd is not None else None


def run_in_background(session_factory, run_id, ask=None):
    def work():
        session = session_factory()
        try:
            execute_run(session, run_id, ask)
        except Exception as exc:  # noqa: BLE001
            log.exception("mapping draft run %s failed", run_id)
            session.rollback()
            session.execute(text("UPDATE phone_mapping_draft_runs SET status = 'failed', error = :e, finished_at = "
                                 "now() WHERE id = :i AND status IN ('queued','running')"),
                            {"i": run_id, "e": str(exc)[:2000]})
            session.commit()
        finally:
            session.close()
    t = threading.Thread(target=work, name="phone-mapping-draft-%s" % run_id, daemon=True)
    t.start()
    return t


def _run_dict(r) -> dict:
    return {"id": str(r.id), "kind": r.kind, "name": r.name, "status": r.status, "provider": r.provider,
            "model": r.model, "input_summary": r.input_summary, "proposal_id": str(r.proposal_id) if r.proposal_id
            else None, "error": r.error, "seconds": r.seconds, "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens, "cost_usd": r.cost_usd, "requested_by": r.requested_by_name,
            "created_at": r.created_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at
            else None}


def read_run(conn, run_id) -> dict | None:
    r = conn.execute(text("SELECT * FROM phone_mapping_draft_runs WHERE id = :i"), {"i": run_id}).one_or_none()
    return _run_dict(r) if r is not None else None


def list_runs(conn, limit=20) -> dict:
    total = conn.execute(text("SELECT count(*) FROM phone_mapping_draft_runs")).scalar()
    rows = conn.execute(text("SELECT * FROM phone_mapping_draft_runs ORDER BY created_at DESC, id LIMIT :n"),
                        {"n": max(1, min(int(limit), 100))}).fetchall()
    return {"total": int(total), "runs": [_run_dict(r) for r in rows]}


def draftable(conn) -> dict:
    """What can be drafted: every registry type and every named set, with record counts, for the page's picker."""
    types = [{"name": r.type_name, "kind": "type", "records_observed": int(r.observed_record_count)}
             for r in conn.execute(text("SELECT type_name, observed_record_count FROM phone_schema_types "
                                        "ORDER BY observed_record_count DESC, type_name"))]
    sets = [{"name": r[0], "kind": "attribution", "records_observed": int(r[1] or 0)}
            for r in conn.execute(text("SELECT value_type, sum(observed_value_count) FROM phone_schema_fields WHERE "
                                       "is_named_set GROUP BY 1 ORDER BY 2 DESC, 1"))]
    return {"types": types, "named_sets": sets, "total": len(types) + len(sets)}

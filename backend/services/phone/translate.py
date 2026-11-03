"""Translation of phone messages and machine transcripts, on this server (05 section 17.5).

On request, the text of one message (the text in effect: a person's correction where there is one, 02 section 10)
or one finished machine text (a transcript, or text read from an image) has its language identified and, when it is
a language with a translation model installed here, is translated to English. The result is a machine-generated
row in ``phone_translations`` beside the original, never replacing it, with the model, its pinned revision, the
SHA-256 of its weights, the detector and its version, the parameters, and the SHA-256 of the exact text translated.
The original is always shown first, the translation under it with ``label()``.

- Text identified as English is not translated: "Already in English".
- Text whose language is not identified with confidence (``MIN_CONFIDENCE``) is not translated: "Language not
  recognised with confidence; not translated". No translation is invented.
- A translation whose source text has changed since (the message or transcript was corrected) is shown as made
  from an earlier text, never as current, and is not searched.

Nothing here makes a network request. The work runs in a child process (``python -I``) that refuses every outbound
connection before it loads anything (``derive.GUARD``), with a memory cap, a time limit and the Hugging Face
offline switches set; the text goes to the child on its standard input, never on its command line. A model that is
not on disk is refused with words, never downloaded (``translate_models`` installs them, once, by an operator).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import uuid

from sqlalchemy import text

from services.phone import derive
from services.phone import fold as F
from services.phone import translate_models as M

log = logging.getLogger(__name__)

TARGET = "en"
SOURCE_TYPES = ("message", "derived_text")
MIN_CONFIDENCE = 0.5
MAX_ATTEMPTS = 2
TIMEOUT_SECONDS = {"message": 1800, "derived_text": 3600}
STALE_SECONDS = {k: v + derive.STALE_MARGIN_SECONDS for k, v in TIMEOUT_SECONDS.items()}
# the longest piece sent to the model at once (one sentence, or part of a very long one), in characters, so nothing
# is cut off by the model's input limit (512 tokens)
PIECE_CHARS = 400
NUM_BEAMS = 4
DETECTOR = "lingua"

OUTCOME_WORDS = {"already_english": "Already in English; not translated.",
                 "unsure": "Language not recognised with confidence; not translated."}
STALE_WORDS = ("Made from an earlier text: the original has been corrected since, so this translation is not of the "
               "text in effect. Translate again to translate the corrected text.")
STOPPED = "Translating this text stopped twice. The original is unchanged."
NO_TEXT = "This message has no text to translate."


class TranslateError(ValueError):
    pass


def no_model_words(language: str) -> str:
    return ("No %s to English translation model is installed on this server. Nothing was sent anywhere."
            % language)


def sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def label(model, version) -> str:
    return ("Machine translation (local, %s %s), not checked by a person. The original is above."
            % (model or "a model", version or "")).replace("  ", " ")


# ---- the source text --------------------------------------------------------------------------------------------

def _message_source(conn, case_id, event_uid):
    r = conn.execute(text(
        "SELECT event_uid, extraction_id, body, thread_key FROM pv_comm_event WHERE case_id = CAST(:c AS uuid) AND "
        "event_uid = CAST(:u AS uuid)"), {"c": str(case_id), "u": str(event_uid)}).first()
    if r is None:
        raise LookupError("This message is not in this case.")
    return r


def _derived_source(conn, case_id, derived_id):
    try:
        uuid.UUID(str(derived_id))
    except (ValueError, TypeError):
        raise LookupError("This machine-generated text is not in this case.") from None
    r = conn.execute(text(
        "SELECT id, extraction_id, kind, state, text, corrected_text, segments FROM phone_derived_texts WHERE "
        "case_id = CAST(:c AS uuid) AND id = CAST(:i AS uuid)"), {"c": str(case_id), "i": str(derived_id)}).first()
    if r is None:
        raise LookupError("This machine-generated text is not in this case.")
    return r


def source_text(conn, case_id, source_type, source_key) -> dict:
    """The text in effect now: {"text", "sha256", "extraction_id", "segments"}. For a machine text a person
    corrected, the corrected text (whole); otherwise its segments, so a transcript keeps its times."""
    if source_type == "message":
        r = _message_source(conn, case_id, source_key)
        body = r.body or ""
        return {"text": body, "sha256": sha256_text(body), "extraction_id": r.extraction_id, "segments": None}
    r = _derived_source(conn, case_id, source_key)
    if r.state != "done":
        raise TranslateError("This text is not finished yet, so it cannot be translated.")
    if r.corrected_text is not None:
        return {"text": r.corrected_text, "sha256": sha256_text(r.corrected_text), "extraction_id": r.extraction_id,
                "segments": None}
    body = r.text or ""
    segs = [s for s in (r.segments or []) if (s.get("text") or "").strip()]
    return {"text": body, "sha256": sha256_text(body), "extraction_id": r.extraction_id, "segments": segs or None}


# ---- requests -----------------------------------------------------------------------------------------------------

def _current_done(conn, case_id, source_type, source_key):
    return conn.execute(text(
        "SELECT * FROM phone_translations WHERE case_id = CAST(:c AS uuid) AND source_type = :t AND source_key = "
        "CAST(:k AS uuid) AND state = 'done' ORDER BY finished_at DESC, id LIMIT 1"),
        {"c": str(case_id), "t": source_type, "k": str(source_key)}).first()


def _insert(conn, case_id, source_type, source_key, extraction_id, user_id):
    return conn.execute(text(
        "INSERT INTO phone_translations (id, case_id, extraction_id, source_type, source_key, target_language, "
        "created_by_user_id) VALUES (:i, CAST(:c AS uuid), :e, :t, CAST(:k AS uuid), :tl, :by) "
        "ON CONFLICT (case_id, source_type, source_key) WHERE state IN ('queued', 'running') DO NOTHING RETURNING *"),
        {"i": uuid.uuid4(), "c": str(case_id), "e": extraction_id, "t": source_type, "k": str(source_key),
         "tl": TARGET, "by": str(user_id) if user_id else None}).first()


def _open(conn, case_id, source_type, source_key):
    return conn.execute(text(
        "SELECT * FROM phone_translations WHERE case_id = CAST(:c AS uuid) AND source_type = :t AND source_key = "
        "CAST(:k AS uuid) AND state IN ('queued', 'running')"),
        {"c": str(case_id), "t": source_type, "k": str(source_key)}).first()


def request(conn, case_id, source_type, source_key, user_id=None) -> dict:
    """Queue a translation of one message or one machine text. A translation already open is returned; a finished
    one of the same text is returned instead of a second (a corrected text is translated again)."""
    if source_type not in SOURCE_TYPES:
        raise TranslateError("Choose a message or a transcript to translate.")
    src = source_text(conn, case_id, source_type, source_key)
    if not src["text"].strip():
        raise TranslateError(NO_TEXT if source_type == "message" else "No text was found here, so there is nothing "
                             "to translate.")
    done = _current_done(conn, case_id, source_type, source_key)
    if done is not None and done.source_sha256 == src["sha256"]:
        return out(done, src["sha256"])
    r = _insert(conn, case_id, source_type, source_key, src["extraction_id"], user_id)
    if r is None:
        r = _open(conn, case_id, source_type, source_key)
    return out(r, src["sha256"])


def request_thread(conn, case_id, thread_key, user_id=None) -> dict:
    """Queue every message with text in one conversation, one row each. Returns true counts: queued, and left out by
    reason (already translated, already waiting, no text)."""
    rows = conn.execute(text(
        "SELECT ev.event_uid, ev.extraction_id, ev.body, d.source_sha256 AS done_sha, o.id AS open_id FROM "
        "pv_comm_event ev "
        "LEFT JOIN LATERAL (SELECT t.source_sha256 FROM phone_translations t WHERE t.case_id = ev.case_id AND "
        "t.source_type = 'message' AND t.source_key = ev.event_uid AND t.state = 'done' ORDER BY t.finished_at DESC, "
        "t.id LIMIT 1) d ON true "
        "LEFT JOIN phone_translations o ON o.case_id = ev.case_id AND o.source_type = 'message' AND o.source_key = "
        "ev.event_uid AND o.state IN ('queued', 'running') "
        "WHERE ev.case_id = CAST(:c AS uuid) AND ev.thread_key = :k ORDER BY ev.sort_instant NULLS LAST, ev.event_uid"),
        {"c": str(case_id), "k": thread_key}).fetchall()
    if not rows:
        raise LookupError("This conversation is not in this case.")
    counts = {"in_conversation": len(rows), "queued": 0,
              "left_out": {"no_text": 0, "already_translated": 0, "already_waiting": 0}}
    for r in rows:
        body = r.body or ""
        if not body.strip():
            counts["left_out"]["no_text"] += 1
        elif r.open_id is not None:
            counts["left_out"]["already_waiting"] += 1
        elif r.done_sha == sha256_text(body):
            counts["left_out"]["already_translated"] += 1
        elif _insert(conn, case_id, "message", r.event_uid, r.extraction_id, user_id) is not None:
            counts["queued"] += 1
        else:  # opened by someone else between the read and the insert
            counts["left_out"]["already_waiting"] += 1
    return counts


# ---- reading -------------------------------------------------------------------------------------------------------

def out(r, current_sha=None) -> dict:
    """One translation as the screens show it. ``current_sha``: the SHA-256 of the source text in effect now; a
    finished translation of a different text is marked stale with words."""
    d = dict(r._mapping)
    done = d["state"] == "done"
    stale = bool(done and current_sha is not None and d.get("source_sha256") != current_sha)
    o = {"id": str(d["id"]), "source_type": d["source_type"], "source_key": str(d["source_key"]),
         "state": d["state"], "outcome": d.get("outcome"), "text": d.get("text"), "segments": d.get("segments") or [],
         "error": d.get("error"), "target_language": d.get("target_language"),
         "detected_language": d.get("detected_language"), "detected_language_name": d.get("detected_language_name"),
         "detected_confidence": d.get("detected_confidence"), "detector": d.get("detector"),
         "detector_version": d.get("detector_version"), "model": d.get("model"), "model_id": d.get("model_id"),
         "model_version": d.get("model_version"), "weights_sha256": d.get("weights_sha256"),
         "provider": d.get("provider"), "parameters": d.get("parameters"), "source_sha256": d.get("source_sha256"),
         "created_at": d["created_at"].isoformat() if d.get("created_at") else None,
         "finished_at": d["finished_at"].isoformat() if d.get("finished_at") else None,
         "machine_generated": True, "stale": stale, "stale_words": STALE_WORDS if stale else None}
    o["provider_words"] = derive.provider_words(d.get("provider")) if done else None
    o["outcome_words"] = OUTCOME_WORDS.get(d.get("outcome")) if done else None
    o["label"] = label(d.get("model"), d.get("model_version")) if done and d.get("outcome") == "translated" else None
    o["language_words"] = language_words(d) if done else None
    return o


def language_words(d) -> str | None:
    name, conf = d.get("detected_language_name"), d.get("detected_confidence")
    if not name:
        return None
    return "Language identified by %s %s as %s (confidence %d%%)." % (
        d.get("detector") or "a detector", d.get("detector_version") or "", name,
        int(round(100 * float(conf or 0))))


def latest_for(conn, case_id, source_type, keys) -> dict:
    """{source_key: the translation to show} for many sources at once: an open one, else the latest finished, else
    the latest failed. Finished ones are marked stale against the text in effect now."""
    keys = sorted({str(k) for k in keys if k})
    if not keys:
        return {}
    rows = conn.execute(text(
        "SELECT DISTINCT ON (t.source_key) t.* FROM phone_translations t WHERE t.case_id = CAST(:c AS uuid) AND "
        "t.source_type = :t AND t.source_key = ANY(CAST(:k AS uuid[])) ORDER BY t.source_key, "
        "(t.state IN ('queued', 'running')) DESC, (t.state = 'done') DESC, coalesce(t.finished_at, t.created_at) "
        "DESC, t.id"), {"c": str(case_id), "t": source_type, "k": keys}).fetchall()
    if not rows:
        return {}
    current = _current_shas(conn, case_id, source_type, [str(r.source_key) for r in rows])
    return {str(r.source_key): out(r, current.get(str(r.source_key))) for r in rows}


def _current_shas(conn, case_id, source_type, keys) -> dict:
    if source_type == "message":
        q = ("SELECT event_uid AS k, body AS x FROM pv_comm_event WHERE case_id = CAST(:c AS uuid) AND "
             "event_uid = ANY(CAST(:k AS uuid[]))")
    else:
        q = ("SELECT id AS k, coalesce(corrected_text, text) AS x FROM phone_derived_texts WHERE case_id = "
             "CAST(:c AS uuid) AND id = ANY(CAST(:k AS uuid[]))")
    return {str(r.k): sha256_text(r.x or "") for r in conn.execute(text(q), {"c": str(case_id), "k": keys})}


def list_for(conn, case_id, source_type, source_key) -> list:
    """Every translation of one source, newest first, each marked stale or current."""
    current = _current_shas(conn, case_id, source_type, [str(source_key)]).get(str(source_key))
    return [out(r, current) for r in conn.execute(text(
        "SELECT * FROM phone_translations WHERE case_id = CAST(:c AS uuid) AND source_type = :t AND source_key = "
        "CAST(:k AS uuid) ORDER BY created_at DESC, id"),
        {"c": str(case_id), "t": source_type, "k": str(source_key)})]


# ---- the work ------------------------------------------------------------------------------------------------------

# One child per claim: loading the language identifier (all its languages) and the translation libraries costs
# about 30 seconds and translating a sentence under one second (measured on this server, 2026-11-03), so up to
# ``BATCH`` waiting messages are drawn together and the child loads each library once. Each row keeps its own state.
_CHILD = derive.GUARD + r'''
import json, os, resource, sys
mb = int(os.environ.get("LOUPE_PHONE_DERIVE_MEMORY_MB", "6144"))
resource.setrlimit(resource.RLIMIT_AS, (mb * 1024 * 1024, mb * 1024 * 1024))
from importlib import metadata
req = json.load(sys.stdin)
from lingua import LanguageDetectorBuilder
det = LanguageDetectorBuilder.from_all_languages().build()
lv = metadata.version("lingua-language-detector")
loaded = {}
answers = []
for item in req["items"]:
    vals = det.compute_language_confidence_values(item["detect"])
    top = vals[0] if vals else None
    iso = top.language.iso_code_639_1.name.lower() if top is not None else None
    out = {"detector_version": lv, "language": iso,
           "language_name": top.language.name.title() if top is not None else None,
           "confidence": float(top.value) if top is not None else 0.0}
    models = req["models"]
    if iso in models and out["confidence"] >= req["min_confidence"] and iso != req["target"]:
        import torch
        torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "2")))
        from transformers import MarianMTModel, MarianTokenizer
        from transformers.utils import logging as hf_logging
        hf_logging.set_verbosity_error()
        if iso not in loaded:
            tok = MarianTokenizer.from_pretrained(models[iso], local_files_only=True)
            model = MarianMTModel.from_pretrained(models[iso], local_files_only=True)
            model.eval()
            loaded[iso] = (tok, model)
        tok, model = loaded[iso]
        done = []
        with torch.inference_mode():
            for piece in item["pieces"]:
                enc = tok([piece], return_tensors="pt", truncation=False)
                n = int(enc["input_ids"].shape[1])
                if n > 512:
                    raise SystemExit("piece too long for the model: %d tokens" % n)
                gen = model.generate(**enc, num_beams=req["num_beams"], max_new_tokens=min(512, 2 * n + 16))
                done.append(tok.decode(gen[0], skip_special_tokens=True).strip())
        out["pieces"] = done
        out["transformers_version"] = metadata.version("transformers")
        out["torch_version"] = metadata.version("torch")
    answers.append(out)
print(json.dumps({"answers": answers}))
'''

BATCH = 20
_SENTENCE = r"(?<=[.!?。！？])\s+"


def pieces_of(value: str) -> list:
    """Text as lines, each line as the pieces the model translates one at a time: its sentences, a sentence longer
    than ``PIECE_CHARS`` cut at spaces, a run with no space cut by characters. One sentence at a time, because given
    two sentences at once the model was seen to leave the first one out. Nothing is dropped: every character of
    the text is in exactly one piece, apart from the whitespace between sentences."""
    import re
    lines = []
    for line in value.split("\n"):
        pieces = []
        for sentence in re.split(_SENTENCE, line.strip()):
            cur = ""
            for word in sentence.split():
                while len(word) > PIECE_CHARS:
                    if cur:
                        pieces.append(cur)
                        cur = ""
                    pieces.append(word[:PIECE_CHARS])
                    word = word[PIECE_CHARS:]
                if cur and len(cur) + 1 + len(word) > PIECE_CHARS:
                    pieces.append(cur)
                    cur = word
                else:
                    cur = (cur + " " + word) if cur else word
            if cur:
                pieces.append(cur)
        lines.append(pieces)
    return lines


def run_child(items: list, timeout: int) -> list:
    """``items``: [{"detect": text, "pieces": [...]}]. Identify each one's language and, when a model for it is
    installed, translate its pieces. The text goes on standard input. Returns one answer per item."""
    models = {iso: str(M.model_dir(iso)) for iso in M.PAIRS if M.installed(iso)}
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LOUPE_PHONE_DERIVE_MEMORY_MB")}
    env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1", "OMP_NUM_THREADS": "2", "TOKENIZERS_PARALLELISM": "false"})
    payload = json.dumps({"items": items, "models": models, "min_confidence": MIN_CONFIDENCE, "target": TARGET,
                          "num_beams": NUM_BEAMS})
    r = subprocess.run([sys.executable, "-I", "-c", _CHILD], input=payload, capture_output=True, text=True,
                       timeout=timeout, env=env)
    if r.returncode != 0:
        err = r.stderr or ""
        if "No module named 'lingua'" in err:
            raise TranslateError("The language identifier is not installed on this server. Nothing was sent anywhere.")
        if any("No module named '%s'" % m in err for m in ("transformers", "torch", "sentencepiece")):
            raise TranslateError("The translation program is not installed on this server. Nothing was sent anywhere.")
        log.warning("translation child failed: %s", (err.strip().splitlines() or [""])[-1][:200])
        raise TranslateError("This text could not be translated. The original is unchanged.")
    answers = json.loads(r.stdout.strip().splitlines()[-1])["answers"]
    if len(answers) != len(items):
        raise TranslateError("This text could not be translated. The original is unchanged.")
    return answers


def prepare(src: dict) -> dict:
    """The child's item for one source: the whole text for language identification, and the pieces to translate
    (per transcript segment when the transcript has segments, else per line)."""
    units = [pieces_of(s["text"].strip()) for s in src["segments"]] if src.get("segments") else [pieces_of(src["text"])]
    return {"units": units, "item": {"detect": src["text"], "pieces": [p for u in units for line in u for p in line]}}


def result(src: dict, prepared: dict, got: dict) -> dict:
    """The columns to store for one source from the child's answer. Raises ``TranslateError`` with words when the
    language has no model here."""
    pm = derive.phone_media()
    iso, conf = got.get("language"), float(got.get("confidence") or 0)
    res = {"detected_language": iso, "detected_language_name": got.get("language_name"),
           "detected_confidence": conf, "detector": DETECTOR, "detector_version": got.get("detector_version"),
           "source_sha256": src["sha256"], "source_chars": len(src["text"]), "provider": pm.LOCAL,
           "parameters": {"min_confidence": MIN_CONFIDENCE, "detector_languages": "all lingua languages",
                          "detected_over": "the whole text"}}
    if iso == TARGET and conf >= MIN_CONFIDENCE:
        return dict(res, outcome="already_english")
    if iso is None or conf < MIN_CONFIDENCE:
        return dict(res, outcome="unsure")
    if iso not in M.PAIRS:
        raise TranslateError(no_model_words(got.get("language_name") or iso))
    if "pieces" not in got:
        raise TranslateError(no_model_words(M.PAIRS[iso]["language"]))
    done = iter(got["pieces"])
    texts = ["\n".join(" ".join(next(done) for _ in line) for line in u) for u in prepared["units"]]
    ident = pm.marian_identity(M.model_dir(iso), got.get("transformers_version"))
    segs = src.get("segments")
    if segs:
        segments = [{"start": s.get("start"), "end": s.get("end"), "source": s["text"].strip(), "text": t}
                    for s, t in zip(segs, texts)]
    else:
        flat = prepared["item"]["pieces"]
        segments = [{"source": p, "text": t} for p, t in zip(flat, got["pieces"])]
    res["parameters"].update({"num_beams": NUM_BEAMS, "max_new_tokens": "twice the input tokens plus 16, at most 512",
                              "piece_chars": PIECE_CHARS, "device": "cpu", "threads": 2,
                              "torch": got.get("torch_version"), "transformers": got.get("transformers_version"),
                              "translated": "per segment, one sentence at a time" if segs
                              else "one sentence at a time, line breaks kept"})
    return dict(res, **ident, outcome="translated", text="\n".join(texts), segments=segments)


def translate_text(src: dict) -> dict:
    """Language identification then translation of one source (``source_text``)."""
    derive.phone_media().provider_for("translation")  # local only; a third-party provider would need a case setting
    p = prepare(src)
    return result(src, p, run_child([p["item"]], TIMEOUT_SECONDS["derived_text"])[0])


def _claim(engine, limit=BATCH):
    """Up to ``limit`` waiting rows of one source type (a transcript alone), marked running together."""
    out = []
    while True:
        with engine.begin() as c:
            rows = c.execute(text(
                "SELECT id, state, attempts, source_type, solo FROM phone_translations WHERE state = 'queued' OR "
                "(state = 'running' AND started_at < now() - make_interval(secs => CASE source_type WHEN 'message' THEN :sm "
                "ELSE :sd END)) ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT :n"),
                {"sm": STALE_SECONDS["message"], "sd": STALE_SECONDS["derived_text"], "n": limit}).fetchall()
            if not rows:
                return out
            stopped = [r.id for r in rows if r.state == "running" and r.attempts >= MAX_ATTEMPTS]
            if stopped:
                c.execute(text("UPDATE phone_translations SET state = 'failed', error = :e, finished_at = now() "
                               "WHERE id = ANY(:i)"), {"e": STOPPED, "i": stopped})
                continue
            kind = rows[0].source_type
            alone = kind == "derived_text" or rows[0].solo
            take = [r.id for r in rows if r.source_type == kind and not r.solo][:limit] if not alone else [rows[0].id]
            return c.execute(text(
                "UPDATE phone_translations SET state = 'running', started_at = clock_timestamp(), error = NULL, "
                "attempts = attempts + 1 WHERE id = ANY(:i) RETURNING id, case_id, source_type, source_key, "
                "started_at"), {"i": take}).fetchall()


COLUMNS = ("outcome", "text", "detected_language", "detected_language_name", "detected_confidence", "detector",
           "detector_version", "source_sha256", "source_chars", "model", "model_id", "model_version",
           "weights_sha256", "provider")


def _fail_words(e) -> str:
    if isinstance(e, (TranslateError, LookupError)):
        return str(e)
    if isinstance(e, subprocess.TimeoutExpired):
        return "Translating this text took too long and was stopped. The original is unchanged."
    ref = uuid.uuid4().hex[:8]
    log.exception("phone translation failed (reference %s)", ref)
    return "This text could not be translated. The original is unchanged. Reference: %s." % ref


def _finish(engine, job, got=None, error=None):
    guard = {"i": job.id, "t": job.started_at}
    with engine.begin() as c:
        if error is not None:
            c.execute(text("UPDATE phone_translations SET state = 'failed', error = :e, finished_at = now() "
                           "WHERE id = :i AND state = 'running' AND started_at = :t"), dict(guard, e=error))
            return {"id": str(job.id), "state": "failed"}
        vals = {k: got.get(k) for k in COLUMNS}
        vals["text_folded"] = F.fold(got["text"]) if got.get("text") else None
        vals["segments"] = json.dumps(got.get("segments") or [])
        vals["parameters"] = json.dumps(got.get("parameters") or {})
        c.execute(text(
            "UPDATE phone_translations SET state = 'done', %s, text_folded = :text_folded, segments = "
            "CAST(:segments AS jsonb), parameters = CAST(:parameters AS jsonb), finished_at = now() WHERE id = :i AND "
            "state = 'running' AND started_at = :t" % ", ".join("%s = :%s" % (k, k) for k in COLUMNS)),
            dict(guard, **vals))
    return {"id": str(job.id), "state": "done"}


def run_pending(engine, limit=BATCH) -> list:
    """Draw up to ``limit`` waiting translations and run them in one child process; each row ends done or failed
    with words."""
    # the provider is settled before anything is claimed: a refusal leaves every waiting row waiting, never running
    derive.phone_media().provider_for("translation")
    jobs = _claim(engine, limit)
    if not jobs:
        return []
    done, work = [], []
    for job in jobs:
        try:
            with engine.connect() as c:
                src = source_text(c, job.case_id, job.source_type, job.source_key)
            if not src["text"].strip():
                raise TranslateError(NO_TEXT)
            work.append((job, src, prepare(src)))
        except Exception as e:  # noqa: BLE001
            done.append(_finish(engine, job, error=_fail_words(e)))
    if not work:
        return done
    timeout = TIMEOUT_SECONDS[work[0][0].source_type]
    try:
        answers = run_child([p["item"] for _, _, p in work], timeout)
    except Exception as e:  # noqa: BLE001
        if len(work) > 1:
            # one text may have stopped the whole draw (a very long message): each is drawn again on its own, so a
            # failure is stated against the text that failed
            with engine.begin() as c:
                for job, _, _ in work:
                    c.execute(text(
                        "UPDATE phone_translations SET state = 'queued', solo = true, attempts = attempts - 1, "
                        "started_at = NULL WHERE id = :i AND state = 'running' AND started_at = :t"),
                        {"i": job.id, "t": job.started_at})
            return done + [{"id": str(job.id), "state": "queued"} for job, _, _ in work]
        return done + [_finish(engine, work[0][0], error=_fail_words(e))]
    for (job, src, p), got in zip(work, answers):
        try:
            done.append(_finish(engine, job, got=result(src, p, got)))
        except Exception as e:  # noqa: BLE001
            done.append(_finish(engine, job, error=_fail_words(e)))
    return done

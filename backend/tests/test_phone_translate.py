"""05 section 17.5: translation of phone messages and machine transcripts, on this server.

Per message or transcript: language identification, then translation to English by a local model, stored as a
machine-generated row beside the original (never replacing it) with the model, its revision and weights hash. The
original is always shown first; search finds both, labelled; the export prints both with the label; nothing leaves
the server. English and unsure text is not translated; a translation of a text corrected since is shown as made
from an earlier text and is not searched.

The child process is replaced by a stand-in that answers like the real one, except in the last test, which runs the
real child against the pinned Spanish model when ``LOUPE_TRANSLATION_MODEL_DIR`` holds it. Invented text only.
Needs the PostgreSQL phone template.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from tests.phone_pg import TEMPLATE_REASON, TEMPLATE_URL, fresh_engine, make_case
from tests.phone_streams_fixture import at, phone

OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"
ES = "Nos vemos mañana en la plaza sintética. Trae el paquete azul."
ES_EN = ["See you tomorrow in the synthetic square.", "Bring the blue package."]
EN = "See you tomorrow at the synthetic harbour."
UNSURE = "ok ok"
PT = "Até amanhã na praça sintética."
YO_SEG = [{"start": 0.0, "end": 2.5, "text": "Ẹ kú àárọ̀ sintetiki."}, {"start": 2.5, "end": 5.0, "text": "Mo máa wá lọ́la."}]


def msg(instant, sender, recips, body, **kw):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming", thread="t", **kw)


@pytest.fixture
def models(tmp_path, monkeypatch):
    """A model folder with a stand-in Spanish model (synthetic weights) and its manifest; no Yoruba model."""
    from services.phone import translate_models as M
    root = tmp_path / "mt"
    d = root / M.PAIRS["es"]["folder"]
    d.mkdir(parents=True)
    for f in M.FILES:
        (d / f).write_bytes(b"synthetic " + f.encode())
    (d / M.WEIGHTS).write_bytes(b"synthetic weights " * 2048)
    (d / M.MANIFEST).write_text(json.dumps({"repo": M.PAIRS["es"]["repo"], "revision": M.PAIRS["es"]["revision"]}))
    monkeypatch.setenv("LOUPE_TRANSLATION_MODEL_DIR", str(root))
    return root


@pytest.fixture
def world(tmp_path, monkeypatch, models):
    if not TEMPLATE_URL:
        pytest.skip(TEMPLATE_REASON)
    monkeypatch.setenv("LOUPE_PHONE_EXPORT_DIR", str(tmp_path / "exports"))
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, evs = phone(c, case, device_zone="America/New_York", events=[
                msg(at(2023, 3, 15, 15), ANA, [OWNER], ES),
                msg(at(2023, 3, 15, 16), OWNER, [ANA], EN),
                msg(at(2023, 3, 15, 17), ANA, [OWNER], UNSURE),
                msg(at(2023, 3, 15, 18), ANA, [OWNER], PT),
                dict(kind="call", instant=at(2023, 3, 15, 19), body=None, thread="t", call_duration_s=12,
                     parties=[(OWNER, "caller", True, None, None), (BEN, "callee", False, None, None)])])
            user = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
        yield {"engine": engine, "case": case, "other": other, "ext": ext, "evs": evs, "user": user,
               "thread": evs[0]["thread_key"], "dir": tmp_path / "exports"}


class FakeChild:
    """Answers like the child: language by a table, translation of the pieces only when the model was offered."""
    LANG = {ES: ("es", "Spanish", 0.93), EN: ("en", "English", 0.97), UNSURE: (None, None, 0.0),
            PT: ("pt", "Portuguese", 0.88), "\n".join(s["text"] for s in YO_SEG): ("yo", "Yoruba", 0.99)}
    WORDS = {"Nos vemos mañana en la plaza sintética.": ES_EN[0], "Trae el paquete azul.": ES_EN[1],
             "Ẹ kú àárọ̀ sintetiki.": "Good morning synthetic.", "Mo máa wá lọ́la.": "I will come tomorrow."}

    def __init__(self, monkeypatch, fail=False):
        from services.phone import translate
        self.calls, self.fail, self.lang = [], fail, dict(self.LANG)
        real = subprocess.run

        def run(argv, *a, **k):
            if argv[:2] == [sys.executable, "-I"]:
                self.calls.append({"argv": argv, "input": json.loads(k["input"]), "env": k["env"]})
                if self.fail:
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Killed")
                return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(self.answer(json.loads(k["input"]))),
                                                   stderr="")
            return real(argv, *a, **k)
        monkeypatch.setattr(translate.subprocess, "run", run)

    def answer(self, req):
        out = []
        for item in req["items"]:
            iso, name, conf = self.lang.get(item["detect"], ("es", "Spanish", 0.9))
            a = {"detector_version": "2.1.1", "language": iso, "language_name": name, "confidence": conf}
            if iso in req["models"] and conf >= req["min_confidence"] and iso != "en":  # as the child
                a.update(pieces=[self.WORDS.get(p, "[en] " + p) for p in item["pieces"]],
                         transformers_version="5.3.0", torch_version="2.11.0")
            out.append(a)
        return {"answers": out}


def _translations(w, keys, source_type="message"):
    from services.phone import translate
    with w["engine"].connect() as c:
        return translate.latest_for(c, w["case"], source_type, keys)


def _request(w, key, source_type="message"):
    from services.phone import translate
    with w["engine"].begin() as c:
        return translate.request(c, w["case"], source_type, key, user_id=w["user"])


def _no_outbound(monkeypatch):
    """Any outbound connection from this process (other than to the local test database) is recorded."""
    seen = []
    real = socket.socket.connect

    def connect(self, addr, *a, **k):
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        if host not in ("127.0.0.1", "::1", "localhost") and not str(host).startswith("/"):
            seen.append(addr)
        return real(self, addr, *a, **k)
    monkeypatch.setattr(socket.socket, "connect", connect)
    return seen


def test_a_spanish_message_is_translated_beside_the_original_with_the_model_and_nothing_leaves_the_server(
        world, monkeypatch):
    from services.phone import streams as S
    from services.phone import translate
    from services.phone.filters import StreamFilter
    seen = _no_outbound(monkeypatch)
    child = FakeChild(monkeypatch)
    ev = world["evs"][0]["event_uid"]
    first = _request(world, ev)
    again = _request(world, ev)
    assert first["state"] == "queued" and again["id"] == first["id"] and first["label"] is None
    assert translate.run_pending(world["engine"]) == [{"id": first["id"], "state": "done"}]
    got = _translations(world, [ev])[ev]
    assert got["state"] == "done" and got["outcome"] == "translated" and got["machine_generated"]
    assert got["text"] == " ".join(ES_EN)
    assert got["segments"] == [{"source": "Nos vemos mañana en la plaza sintética.", "text": ES_EN[0]},
                               {"source": "Trae el paquete azul.", "text": ES_EN[1]}]
    assert got["detected_language"] == "es" and got["detected_language_name"] == "Spanish"
    assert got["detector"] == "lingua" and got["detector_version"] == "2.1.1"
    assert got["model"] == "opus-mt-es-en"
    assert got["model_id"] == "Helsinki-NLP/opus-mt-es-en@c96e2c5399ebfae4fc43d9669556b9afa74bb69d"
    assert got["model_version"] == "c96e2c5, transformers 5.3.0"
    weights = os.path.join(os.environ["LOUPE_TRANSLATION_MODEL_DIR"], "opus-mt-es-en", "pytorch_model.bin")
    assert got["weights_sha256"] == hashlib.sha256(open(weights, "rb").read()).hexdigest()
    assert got["source_sha256"] == hashlib.sha256(ES.encode()).hexdigest() and not got["stale"]
    assert got["provider"] == "local" and got["provider_words"].startswith("Made on this server.")
    assert got["label"] == ("Machine translation (local, opus-mt-es-en c96e2c5, transformers 5.3.0), not checked by "
                            "a person. The original is above.")
    assert got["language_words"] == "Language identified by lingua 2.1.1 as Spanish (confidence 93%)."
    assert got["parameters"]["num_beams"] == 4 and got["parameters"]["min_confidence"] == 0.0
    # the text went to the child on its standard input, not its command line, with the offline switches set
    [call] = child.calls
    assert ES not in " ".join(call["argv"]) and call["input"]["items"][0]["detect"] == ES
    assert call["argv"][3].startswith(translate.derive.GUARD)
    assert {k: call["env"][k] for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")} == {"HF_HUB_OFFLINE": "1",
                                                                                       "TRANSFORMERS_OFFLINE": "1"}
    # the original is unchanged and the stream row carries the original first and the translation beside it
    f = StreamFilter(case_id=str(world["case"]))
    with world["engine"].connect() as c:
        idx = S.index_comm_events(c, f)
        rows = S.window_comm_events(c, f, snapshot_token=idx["snapshot"], day=idx["items"][0]["day"])["items"]
        body = c.execute(text("SELECT body FROM phone_comm_events WHERE event_uid = :u"), {"u": ev}).scalar()
    row = next(r for r in rows if r["event_uid"] == ev)
    assert body == ES and row["body"] == ES and row["translation"]["text"] == " ".join(ES_EN)
    assert next(r for r in rows if r["kind"] == "call")["translation"] is None
    assert seen == []
    # asking again for the same text returns the translation already made
    assert _request(world, ev)["id"] == first["id"]


def test_english_and_unsure_text_is_not_translated_and_says_so(world, monkeypatch):
    from services.phone import translate
    FakeChild(monkeypatch)
    en, unsure = world["evs"][1]["event_uid"], world["evs"][2]["event_uid"]
    _request(world, en)
    _request(world, unsure)
    assert [d["state"] for d in translate.run_pending(world["engine"])] == ["done", "done"]
    got = _translations(world, [en, unsure])
    assert got[en]["outcome"] == "already_english" and got[en]["text"] is None and got[en]["label"] is None
    assert got[en]["outcome_words"] == "Already in English; not translated."
    assert got[unsure]["outcome"] == "unsure" and got[unsure]["text"] is None
    assert got[unsure]["outcome_words"] == "Language not recognised with confidence; not translated."
    assert got[unsure]["language_words"] is None


def test_spanish_identified_with_a_shared_confidence_is_translated_and_the_confidence_is_stated(world, monkeypatch):
    """On live bodies Spanish shares lingua's relative confidence with Portuguese, Catalan and Italian: 615 of 999
    Spanish bodies scored under 0.5 (3 Nov). Such a text is translated, and its label says how sure the
    identification was; before, it was refused as "unsure"."""
    from services.phone import translate
    child = FakeChild(monkeypatch)
    child.lang[ES] = ("es", "Spanish", 0.41)
    ev = world["evs"][0]["event_uid"]
    _request(world, ev)
    assert [d["state"] for d in translate.run_pending(world["engine"])] == ["done"]
    got = _translations(world, [ev])[ev]
    assert got["outcome"] == "translated" and got["text"] == " ".join(ES_EN)
    assert got["language_words"] == "Language identified by lingua 2.1.1 as Spanish (confidence 41%)."


def test_a_language_with_no_model_here_is_refused_in_words_and_nothing_is_downloaded(world, monkeypatch, models):
    from services.phone import translate
    from services.phone import translate_models as M
    FakeChild(monkeypatch)
    pt = world["evs"][3]["event_uid"]
    _request(world, pt)
    assert translate.run_pending(world["engine"])[0]["state"] == "failed"
    assert _translations(world, [pt])[pt]["error"] == (
        "No Portuguese to English translation model is installed on this server. Nothing was sent anywhere.")
    # Spanish, with its model folder removed: refused with words, and no folder appears
    import shutil
    shutil.rmtree(models / M.PAIRS["es"]["folder"])
    es = world["evs"][0]["event_uid"]
    _request(world, es)
    assert translate.run_pending(world["engine"])[0]["state"] == "failed"
    assert _translations(world, [es])[es]["error"] == (
        "No Spanish to English translation model is installed on this server. Nothing was sent anywhere.")
    assert not (models / M.PAIRS["es"]["folder"]).exists()


def test_a_corrected_message_shows_its_translation_as_made_from_an_earlier_text_and_is_translated_again(
        world, monkeypatch):
    from services.phone import translate
    from services.search import search as S
    FakeChild(monkeypatch)
    ev = world["evs"][0]["event_uid"]
    first = _request(world, ev)
    translate.run_pending(world["engine"])
    with world["engine"].connect() as c:
        assert S.search(c, world["case"], "blue package")["groups"][-1]["total"] == 1
    # a person's correction re-reads the phone: the event's body is the corrected text from then on
    corrected = "Nos vemos mañana en la plaza sintética. Trae el paquete verde."
    with world["engine"].begin() as c:
        c.execute(text("UPDATE phone_comm_events SET body = :b WHERE event_uid = :u"), {"b": corrected, "u": ev})
    got = _translations(world, [ev])[ev]
    assert got["stale"] and got["stale_words"].startswith("Made from an earlier text") and got["id"] == first["id"]
    with world["engine"].connect() as c:  # the translation of the earlier text is not searched
        assert S.search(c, world["case"], "blue package")["groups"][-1]["total"] == 0
    second = _request(world, ev)
    assert second["id"] != first["id"] and second["state"] == "queued"
    translate.run_pending(world["engine"])
    got = _translations(world, [ev])[ev]
    assert got["id"] == second["id"] and not got["stale"]
    assert got["source_sha256"] == hashlib.sha256(corrected.encode()).hexdigest()
    with world["engine"].connect() as c:
        rows = translate.list_for(c, world["case"], "message", ev)
    assert [r["stale"] for r in rows] == [False, True]  # both kept, the earlier one marked


def test_translate_this_conversation_queues_one_row_per_message_with_text_and_counts_the_rest(world, monkeypatch):
    from services.phone import translate
    FakeChild(monkeypatch)
    _request(world, world["evs"][0]["event_uid"])
    translate.run_pending(world["engine"])
    _request(world, world["evs"][1]["event_uid"])  # waiting
    with world["engine"].begin() as c:
        got = translate.request_thread(c, world["case"], world["thread"], user_id=world["user"])
        again = translate.request_thread(c, world["case"], world["thread"], user_id=world["user"])
        with pytest.raises(LookupError):
            translate.request_thread(c, world["other"], world["thread"])
    assert got == {"in_conversation": 5, "queued": 2,
                   "left_out": {"no_text": 1, "already_translated": 1, "already_waiting": 1}}
    assert again["queued"] == 0 and again["left_out"]["already_waiting"] == 3
    # one child for the three waiting messages
    assert sorted(d["state"] for d in translate.run_pending(world["engine"])) == ["done", "done", "failed"]


def test_requests_from_another_case_or_with_no_text_are_refused(world):
    from services.phone import translate
    with world["engine"].begin() as c:
        with pytest.raises(LookupError):
            translate.request(c, world["other"], "message", world["evs"][0]["event_uid"])
        with pytest.raises(translate.TranslateError, match="no text"):
            translate.request(c, world["case"], "message", world["evs"][4]["event_uid"])
        with pytest.raises(LookupError):
            translate.request(c, world["case"], "derived_text", uuid.uuid4())


def test_a_failed_draw_of_several_is_drawn_again_one_by_one_so_the_failure_names_its_text(world, monkeypatch):
    from services.phone import translate
    child = FakeChild(monkeypatch, fail=True)
    a, b = world["evs"][0]["event_uid"], world["evs"][1]["event_uid"]
    _request(world, a)
    _request(world, b)
    assert sorted(d["state"] for d in translate.run_pending(world["engine"])) == ["queued", "queued"]
    assert len(child.calls) == 1
    assert [d["state"] for d in translate.run_pending(world["engine"])] == ["failed"]
    assert len(child.calls[-1]["input"]["items"]) == 1
    child.fail = False
    assert [d["state"] for d in translate.run_pending(world["engine"])] == ["done"]
    got = _translations(world, [a, b])
    assert sorted(g["state"] for g in got.values()) == ["done", "failed"]
    assert [g["error"] for g in got.values() if g["state"] == "failed"] == [
        "This text could not be translated. The original is unchanged."]


def _transcript(w, corrected=None, attach=False):
    """A finished Yoruba transcript of a synthetic voice note; ``attach``: the note is the first message's attachment."""
    ident = uuid.uuid4()
    file_uid = uuid.uuid4()
    with w["engine"].begin() as c:
        c.execute(text("INSERT INTO phone_files (extraction_id, document_index, ordinal, file_uid, local_path, outcome, "
                       "body) VALUES (:e, 0, 9000, :f, 'voice/synthetic-note.ogg', 'match', CAST('[]' AS jsonb))"),
                  {"e": w["ext"], "f": file_uid})
        if attach:
            c.execute(text(
                "INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, mechanism, "
                "reference_text, file_document_index, file_ordinal, resolution, ambiguous) VALUES (:e, 0, 0, 'f', "
                "'extracted_path_value', 'voice/synthetic-note.ogg', 0, 9000, 'container_entry', false)"),
                {"e": w["ext"]})
        body = "\n".join(s["text"] for s in YO_SEG)
        c.execute(text(
            "INSERT INTO phone_derived_texts (id, case_id, extraction_id, file_uid, kind, state, text, text_folded, "
            "segments, model, model_version, finished_at, corrected_text) VALUES (:i, :c, :e, :f, 'transcript', "
            "'done', :t, lower(:t), CAST(:s AS jsonb), 'Whisper', 'base 20250625', :at, :ct)"),
            {"i": ident, "c": w["case"], "e": w["ext"], "f": file_uid, "t": body, "s": json.dumps(YO_SEG),
             "at": datetime(2026, 11, 3, tzinfo=timezone.utc), "ct": corrected})
    return str(ident), str(file_uid)


def _yoruba(models):
    """A Yoruba stand-in model beside the Spanish one."""
    import shutil

    from services.phone import translate_models as M
    yo = models / M.PAIRS["yo"]["folder"]
    shutil.copytree(models / M.PAIRS["es"]["folder"], yo)
    (yo / M.MANIFEST).write_text(json.dumps({"repo": M.PAIRS["yo"]["repo"], "revision": M.PAIRS["yo"]["revision"]}))


def test_a_transcript_is_translated_segment_by_segment_keeping_its_times(world, monkeypatch, models):
    from services.phone import translate
    from services.search import search as S
    _yoruba(models)
    FakeChild(monkeypatch)
    ident, file_uid = _transcript(world)
    req = _request(world, ident, "derived_text")
    assert translate.run_pending(world["engine"]) == [{"id": req["id"], "state": "done"}]
    got = _translations(world, [ident], "derived_text")[ident]
    assert got["segments"] == [
        {"start": 0.0, "end": 2.5, "source": YO_SEG[0]["text"], "text": "Good morning synthetic."},
        {"start": 2.5, "end": 5.0, "source": YO_SEG[1]["text"], "text": "I will come tomorrow."}]
    assert got["model"] == "opus-mt-yo-en" and got["detected_language_name"] == "Yoruba"
    with world["engine"].connect() as c:
        hits = {g["group"]: g for g in S.search(c, world["case"], "come tomorrow")["groups"]}
    [item] = hits["machine_text"]["items"]
    assert item["kind"] == "machine_translation" and item["machine_generated"]
    assert item["title"].endswith("machine translation of the transcript of synthetic-note.ogg")
    assert item["original"]["text"].startswith(YO_SEG[0]["text"]) and item["translated_from"] == "Yoruba"
    assert item["label"].startswith("Machine translation (local, opus-mt-yo-en f3d791b")
    assert item["open"] == {"screen": "media", "params": {"file_uid": file_uid, "extraction_id": str(world["ext"])}}
    assert hits["messages"]["total"] == 0  # a translation is never counted as a message


def test_a_translation_of_a_transcript_reading_displaced_since_is_not_searched(world, monkeypatch, models):
    """Search uses the reading in use for a file (a person's latest, else the latest finished; derive.IN_USE_ORDER):
    a translation of an older reading is not found once a newer reading is the one in use, and is found again when
    a person confirms the older reading."""
    from services.phone import translate
    from services.search import search as S
    _yoruba(models)
    FakeChild(monkeypatch)
    ident, file_uid = _transcript(world)
    _request(world, ident, "derived_text")
    translate.run_pending(world["engine"])

    def found():
        with world["engine"].connect() as c:
            return {g["group"]: g for g in S.search(c, world["case"], "come tomorrow")["groups"]}["machine_text"]
    assert found()["total"] == 1
    with world["engine"].begin() as c:  # a newer machine reading of the same file is now the one in use
        c.execute(text(
            "INSERT INTO phone_derived_texts (id, case_id, extraction_id, file_uid, kind, state, text, text_folded, "
            "model, model_version, finished_at) VALUES (gen_random_uuid(), :c, :e, :f, 'transcript', 'done', "
            "'synthetic newer words', 'synthetic newer words', 'Whisper', 'base 20250625', :at)"),
            {"c": world["case"], "e": world["ext"], "f": file_uid, "at": datetime(2026, 11, 4, tzinfo=timezone.utc)})
    assert found()["total"] == 0
    with world["engine"].begin() as c:  # a person confirms the older reading: it is in use again
        c.execute(text("UPDATE phone_derived_texts SET confirmed_at = now(), confirmed_by_name = 'Synthetic Reviewer' "
                       "WHERE id = :i"), {"i": ident})
    assert found()["total"] == 1


def test_search_finds_a_message_translation_labelled_and_citing_its_original(world, monkeypatch):
    from services.phone import translate
    from services.search import search as S
    FakeChild(monkeypatch)
    ev = world["evs"][0]["event_uid"]
    _request(world, ev)
    translate.run_pending(world["engine"])
    with world["engine"].connect() as c:
        hits = {g["group"]: g for g in S.search(c, world["case"], "blue package")["groups"]}
        page = S.group_page(c, world["case"], "blue package", "machine_text")
        other = {g["group"]: g for g in S.search(c, world["other"], "blue package")["groups"]}
    g = hits["machine_text"]
    assert g["total"] == 1 and page["total"] == 1 and other["machine_text"]["total"] == 0
    [item] = g["items"]
    assert item["kind"] == "machine_translation" and item["snippet"]["match"] == "blue package"
    assert item["original"] == {"text": ES, "clipped": False, "chars": len(ES)}
    assert item["label"].startswith("Machine translation (local, opus-mt-es-en c96e2c5")
    assert item["open"]["screen"] == "conversations" and item["open"]["params"]["event"] == ev
    assert hits["messages"]["total"] == 0  # the original is Spanish; the English words are only in the translation


def test_the_export_prints_the_translation_under_the_original_with_its_label_and_counts_it(world, monkeypatch):
    pytest.importorskip("weasyprint")
    from services.phone import translate
    from tests.test_phone_exports import _export
    FakeChild(monkeypatch)
    _request(world, world["evs"][0]["event_uid"])
    _request(world, world["evs"][1]["event_uid"])  # English: nothing printed for it
    translate.run_pending(world["engine"])
    state, _, txt = _export(world)
    words = " ".join(txt.split())
    original = words.index("Nos vemos mañana")
    assert words.index("Machine translation from Spanish: " + " ".join(ES_EN)) > original
    assert ("Machine translation (local, opus-mt-es-en c96e2c5, transformers 5.3.0), not checked by a person.") in words
    assert ("1 machine translation made on this server is printed under its original, each labelled and not checked "
            "by a person.") in words
    assert (state["counts"]["machine_translations"], state["counts"]["machine_translations_stale"]) == (1, 0)


def test_an_rsmf_file_says_the_translations_are_not_in_it_and_never_that_they_are_printed(world, monkeypatch):
    """RSMF carries the original messages only: its cover names the translations kept in Loupe and says they are not
    in the file, never the PDF's "printed under its original"."""
    import email

    from services.phone import translate
    from services.phone.exports.rsmf import SMTP
    from tests.test_phone_exports_rsmf import _rsmf_export
    FakeChild(monkeypatch)
    _request(world, world["evs"][0]["event_uid"])
    translate.run_pending(world["engine"])
    state, data, _ = _rsmf_export(world)
    body = " ".join(email.message_from_bytes(data, policy=SMTP).get_body(("plain",)).get_content().split())
    assert ("1 machine translation made on this server is kept in Loupe for these messages; an RSMF file carries the "
            "originals only, so it is not in this file.") in body
    assert "printed under" not in body and " ".join(ES_EN) not in body
    assert state["counts"]["machine_translations"] == 1


def test_the_export_says_a_transcript_translation_made_from_an_earlier_text_is_of_a_transcript(
        world, monkeypatch, models):
    pytest.importorskip("weasyprint")
    from services.phone import translate
    from tests.test_phone_exports import _export
    _yoruba(models)
    FakeChild(monkeypatch)
    ident, _ = _transcript(world, attach=True)
    _request(world, ident, "derived_text")
    translate.run_pending(world["engine"])
    with world["engine"].begin() as c:  # a person corrects the transcript after it was translated
        c.execute(text("UPDATE phone_derived_texts SET corrected_text = 'Synthetic corrected words.', corrected_at = "
                       "now(), corrected_by_name = 'Synthetic Reviewer', correction_reason = 'heard it' WHERE id = :i"),
                  {"i": ident})
    state, _, txt = _export(world)
    words = " ".join(txt.split())
    assert ("1 was made from an earlier text of a transcript or text read from an image corrected since, and says "
            "so.") in words
    assert "earlier text of a message" not in words
    assert "Made from an earlier text: the original has been corrected since" in words
    assert (state["counts"]["machine_translations"], state["counts"]["machine_translations_stale"]) == (1, 1)


def test_a_refused_provider_leaves_every_waiting_translation_waiting(world, monkeypatch):
    """The provider is settled before rows are claimed: a refusal never leaves rows running until they go stale."""
    from services.phone import derive, translate
    FakeChild(monkeypatch)
    _request(world, world["evs"][0]["event_uid"])

    def refuse(workload, case_setting=None):
        raise ValueError("Only the local provider is available for %s." % workload)
    monkeypatch.setattr(derive.phone_media(), "provider_for", refuse)
    with pytest.raises(ValueError):
        translate.run_pending(world["engine"])
    with world["engine"].connect() as c:
        assert c.execute(text("SELECT state, attempts FROM phone_translations")).one() == ("queued", 0)


def test_the_child_refuses_every_outbound_connection_before_it_loads_anything():
    from services.phone import derive, translate
    assert translate._CHILD.startswith(derive.GUARD)
    probe = translate._CHILD.split("from importlib import metadata")[0] + (
        "\nimport socket\n"
        "for f in (lambda: socket.create_connection(('192.0.2.1', 80), timeout=1),\n"
        "          lambda: socket.socket().connect(('192.0.2.1', 80))):\n"
        "    try:\n        f()\n    except OSError as e:\n        print(e)\n")
    out = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, timeout=60)
    assert out.stdout.count("outbound connections are refused while reading evidence") == 2


def test_pieces_keep_every_word_and_the_line_breaks():
    from services.phone import translate as T
    long = " ".join("palabra%d" % i for i in range(200))
    text_ = "Hola. ¿Qué tal?\n\n%s\n%s" % (long, "x" * 900)
    lines = T.pieces_of(text_)
    assert len(lines) == 4 and lines[0] == ["Hola.", "¿Qué tal?"] and lines[1] == []
    assert all(len(p) <= T.PIECE_CHARS for line in lines for p in line)
    assert " ".join(lines[2]).split() == long.split() and "".join(lines[3]) == "x" * 900


# ---- the real model ------------------------------------------------------------------------------------------------

def _real_ready():
    from services.phone import translate_models as M
    if not os.environ.get("LOUPE_TRANSLATION_MODEL_DIR"):
        return "Set LOUPE_TRANSLATION_MODEL_DIR to a folder holding the pinned opus-mt-es-en model"
    if not M.installed("es"):
        return "The pinned opus-mt-es-en model is not installed in LOUPE_TRANSLATION_MODEL_DIR"
    probe = subprocess.run([sys.executable, "-I", "-c", "import lingua, transformers, sentencepiece, torch"],
                           capture_output=True, timeout=300)
    return None if probe.returncode == 0 else "lingua, transformers, sentencepiece and torch are not installed here"


def test_the_real_child_translates_spanish_with_the_pinned_model_and_no_connection():
    why = _real_ready()
    if why:
        pytest.skip(why)
    from services.phone import translate
    from services.phone import translate_models as M
    got = translate.translate_text({"text": ES, "sha256": translate.sha256_text(ES), "segments": None})
    assert got["outcome"] == "translated" and got["detected_language"] == "es"
    assert got["weights_sha256"] == M.PAIRS["es"]["weights_sha256"]
    assert got["model_id"] == "Helsinki-NLP/opus-mt-es-en@" + M.PAIRS["es"]["revision"]
    assert len(got["segments"]) == 2 and all(s["text"] for s in got["segments"])
    assert "tomorrow" in got["text"].lower() and "blue" in got["text"].lower()
    assert translate.translate_text({"text": EN, "sha256": "x", "segments": None})["outcome"] == "already_english"


def test_an_unsure_result_made_under_the_old_setting_is_identified_again_when_asked(world, monkeypatch):
    """A text left "unsure" under the 0.5 setting is identified again under the setting in force; an "unsure" made
    under the current setting is given again, as any finished result of the same text is."""
    from services.phone import translate
    child = FakeChild(monkeypatch)
    ev = world["evs"][0]["event_uid"]
    child.lang[ES] = (None, None, 0.0)
    first = _request(world, ev)
    translate.run_pending(world["engine"])
    assert _translations(world, [ev])[ev]["outcome"] == "unsure"
    assert _translations(world, [ev])[ev]["asks_again"] is False
    assert _request(world, ev)["id"] == first["id"]  # same setting: the same result
    with world["engine"].begin() as c:
        c.execute(text("UPDATE phone_translations SET parameters = jsonb_set(parameters, '{min_confidence}', '0.5') "
                       "WHERE id = :i"), {"i": first["id"]})
    assert _translations(world, [ev])[ev]["asks_again"] is True
    child.lang[ES] = ("es", "Spanish", 0.41)
    again = _request(world, ev)
    assert again["id"] != first["id"]
    translate.run_pending(world["engine"])
    got = _translations(world, [ev])[ev]
    assert got["id"] == again["id"] and got["outcome"] == "translated"
    with world["engine"].begin() as c:
        counts = translate.request_thread(c, world["case"], world["thread"])
    assert counts["left_out"]["already_translated"] >= 1

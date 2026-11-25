"""A model's reading of phone texts into mentions, for a phone whose Outside services are allowed.

The model proposes; the rules decide. It is given a page of texts and returns, per text, the checkable mentions with
their kind and the exact words that say it. A mention whose words are not in the text is dropped. Who, when and where
are then read by the same rules as the word-rule reader (``services.mentions.reader``) from the model's quoted words,
so a model never sets a time, a place or a person by itself. Each mention is "Read by Loupe · not confirmed".

Every call goes through ``ai_cost_context`` with the run's description, so the run's cost is the sum of the cost
records the calls wrote (measured, not estimated).
"""
from __future__ import annotations

import json
import re

from services.mentions import kinds as K, reader as R

BATCH = 25
MAX_TEXT = 800

RULES = (
    "You read phone messages for an investigator and pick out each checkable mention: something said that the case's "
    "records could back up or contradict. Kinds: travel (a trip, driving, flying, arriving, on the way), meeting (meeting "
    "or seeing someone), at_place (being at a named place), home_away (being home, in bed, asleep, away, the phone off), "
    "plan (a planned time or arrangement), money (an amount, a payment, a refund, an invoice, money moving), sent (a thing "
    "sent, handed over, left or picked up), deleted (something deleted or to be deleted). Skip greetings, feelings, "
    "opinions and questions that assert nothing. Answer with JSON: {\"texts\": [{\"i\": int, \"mentions\": [{\"kind\": "
    "str, \"words\": str, \"about\": \"sender|recipient|both|other\", \"place_words\": str, \"time_words\": str}]}]}. "
    "\"words\" must be copied exactly from the text, a short clause. \"place_words\" and \"time_words\" are copied "
    "exactly from the text too, or empty. Never invent a place, a time or a person.")


class ModelReader:
    def __init__(self, db, *, zone, people, known, run_id=None, case_id=None):
        self.db, self.zone, self.people, self.known = db, zone, people, known
        self.run_id, self.case_id = run_id, case_id
        self.calls = self.tokens_in = self.tokens_out = 0
        self.cost_usd = 0.0
        self._pending: list[dict] = []

    def read(self, t: dict) -> list[dict]:
        """One text at a time for the run's loop; the texts are sent in batches by ``read_page``."""
        return self.read_page([t]).get(t["record_uid"], [])

    def read_page(self, page: list[dict]) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        uniq: dict[str, list[dict]] = {}
        for t in page:
            uniq.setdefault(" ".join(str(t["body"]).split())[:MAX_TEXT], []).append(t)
        bodies = list(uniq)
        for i in range(0, len(bodies), BATCH):
            chunk = bodies[i:i + BATCH]
            got = self._call(chunk)
            for j, body in enumerate(chunk):
                for t in uniq[body]:
                    out[t["record_uid"]] = [m for m in (self._mention(t, x) for x in got.get(j, [])) if m]
        return out

    def _call(self, bodies: list[str]) -> dict[int, list]:
        from services import writing_standard
        from services.ai_costs_service import ai_cost_context
        from postgres.models.cost_record import CostJobType
        from services.llm_service import LLMService
        ctx = LLMService().create_context()
        ctx.system_context = writing_standard.system_prompt(RULES, "data")
        prompt = "Texts:\n" + "\n".join(f"{j}. {json.dumps(b, ensure_ascii=False)}" for j, b in enumerate(bodies))
        with ai_cost_context(job_type=CostJobType.AI_ASSISTANT, case_id=self.case_id,
                             description=f"phone mentions run {self.run_id}", meter_calls=True):
            raw = ctx.call(prompt, temperature=0, json_mode=True)
        self.calls += 1
        u = ctx.last_usage or {}
        self.tokens_in += int(u.get("prompt_tokens") or 0)
        self.tokens_out += int(u.get("completion_tokens") or 0)
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        out = {}
        for t in data.get("texts") or []:
            if isinstance(t, dict) and isinstance(t.get("i"), int):
                out[t["i"]] = [m for m in t.get("mentions") or [] if isinstance(m, dict)]
        return out

    def _mention(self, t, x) -> dict | None:
        body = t["body"]
        words = str(x.get("words") or "").strip()
        kind = x.get("kind")
        if kind not in K.KINDS or not words:
            return None
        at = body.find(words)
        if at < 0:
            low = body.lower().find(words.lower())
            if low < 0:
                return None  # the model's words are not in the text: dropped, never repaired
            at = low
            words = body[at:at + len(words)]
        about = x.get("about")
        speaker, addressee = t.get("speaker"), list(t.get("addressee") or [])
        who = {"sender": [speaker], "recipient": addressee, "both": [speaker] + addressee}.get(about, [speaker])
        tw = str(x.get("time_words") or "")
        pw = str(x.get("place_words") or "")
        basis = " ".join(w for w in (words, tw if tw and tw in body else "") if w)
        where = R.read_where(pw if pw and pw in body else words, kind, self.known)
        with_ = [k for k in addressee if k not in who] if kind in ("meeting", "plan", "sent") else []
        return {"kind": kind, "phrase": words, "start": at, "end": at + len(words), "trigger": words, "question": False,
                "negated": bool(re.search(r"\b(not|never|didn't|won't)\b", words, re.I)),
                "who": [k for k in who if k], "who_words": about or "sender", "with": with_,
                "when": R.read_when(basis, t["at"], self.zone, kind), "where": where,
                "how": next((h for h, rx in R._HOW.items() if rx.search(words)), None) if kind == "travel" else None,
                "amounts_minor": R._amounts(words), "check_numbers": R._CHECKNO.findall(words),
                "words": R.content_words(words + (" " + pw if pw else ""), self.people),
                "reader": "model", "read_by": K.READ_BY}

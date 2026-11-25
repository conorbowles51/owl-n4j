"""What the mention checks read from a case: the phones' places, activity and messages (through the Corroborate
``CaseStore``), the ledger, and the documents' text. Every row carries a ``ref`` the screen opens.

A payment is read from every account in the case, not only accounts joined to a person, and is shown with the
holder name as the statement prints it: the check says whose account it was, it does not assume it.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import text

from services.corroborate import model as M
from services.corroborate.store import CaseStore


class CaseData:
    def __init__(self, db, case_id):
        self.db, self.case = db, str(case_id)
        self.store = CaseStore(db, case_id)
        self._homes: dict[str, dict | None] = {}

    def q(self, sql, **kw):
        return self.db.execute(text(sql), {"c": self.case, **kw})

    # -- people and places ---------------------------------------------------------------------------------------
    def zone(self) -> str:
        return self.store.zone()

    def people(self) -> list[dict]:
        return self.store.people()

    def known_places(self) -> list[dict]:
        try:
            return self.store.known_places()
        except Exception:  # noqa: BLE001 - a case with no labelled places reads none
            self.db.rollback()
            return []

    def home(self, person: str) -> dict | None:
        if person not in self._homes:
            self._homes[person] = self.store.routine_place(person, "home")
        return self._homes[person]

    def work(self, person: str) -> dict | None:
        return self.store.routine_place(person, "work")

    # -- phone records -------------------------------------------------------------------------------------------
    def phone_records(self, people: list[dict], lo: datetime, hi: datetime) -> list[dict]:
        if not any(p["phones"] for p in people):
            return []
        return self.store.phone_records(people, [(lo, hi)], self.people())

    def activity(self, person: dict, lo: datetime, hi: datetime) -> list[datetime]:
        acts = self.store.activity([person], [(lo, hi)]).get(person["key"], [])
        return [t for t in acts if lo <= t <= hi]

    def use_events(self, person: dict, lo: datetime, hi: datetime) -> list[tuple[datetime, str, str]]:
        """The phone's own records in the window as (instant, activity class, record type): ``interaction`` is the
        owner using it (sending, calling, opening an app); ``passive`` and ``device_state`` show it was on."""
        if not person["phones"]:
            return []
        return [(M.as_utc(t), c, rt) for t, c, rt in self.q(
            "SELECT instant_utc, activity_class, record_type FROM pol_activity_event WHERE case_id = :c AND "
            "extraction_id = ANY(CAST(:e AS uuid[])) AND instant_utc BETWEEN :lo AND :hi AND activity_class <> 'unknown' "
            "ORDER BY instant_utc", e=person["phones"], lo=lo, hi=hi)]

    def last_position_before(self, person: dict, at: datetime, hours: int = 12) -> dict | None:
        if not person["phones"]:
            return None
        row = self.q("SELECT record_uid, start_utc, lat, lon, radius_m FROM pol_place_observation WHERE case_id = :c AND "
                     "kind = 'presence' AND extraction_id = ANY(CAST(:e AS uuid[])) AND start_utc BETWEEN :lo AND :at "
                     "ORDER BY start_utc DESC LIMIT 1", e=person["phones"], lo=at - timedelta(hours=hours), at=at).first()
        if not row:
            return None
        return {"ref": f"phone_record:{row[0]}", "at": M.as_utc(row[1]),
                "place": {"lat": row[2], "lon": row[3], "radius_m": row[4]}}

    def comm_with_words(self, words: list[str], lo: datetime, hi: datetime, exclude_uid: str | None = None) -> list[dict]:
        """Messages and e-mails on any phone in the case, in the window, that hold one of the words."""
        if not words:
            return []
        rx = "(" + "|".join(re.escape(w) for w in words) + ")"
        out = []
        for uid, ext, kind, at, body, deleted in self.q(
                "SELECT record_uid, extraction_id, kind, sort_instant, body, deleted_state FROM phone_comm_events WHERE "
                "case_id = :c AND sort_instant BETWEEN :lo AND :hi AND body ~* :rx ORDER BY sort_instant LIMIT 50",
                lo=lo, hi=hi, rx=rx):
            if exclude_uid and str(uid) == exclude_uid:
                continue
            out.append({"ref": f"phone_record:{uid}", "phone": str(ext), "kind": kind, "at": M.as_utc(at),
                        "body": body or "", "deleted": bool(deleted and str(deleted).lower() != "intact")})
        return out

    # -- money ---------------------------------------------------------------------------------------------------
    def payments(self, lo_day, hi_day) -> list[dict]:
        out = []
        for tid, day, amount, direction, cp, desc, holder, inst in self.q(
                "SELECT t.id, COALESCE(t.transaction_date, t.posted_date), t.amount_minor, t.direction, t.counterparty_raw, "
                "t.description, a.holder_name, a.institution_name FROM financial_transactions t LEFT JOIN financial_accounts a "
                "ON a.id = t.account_id WHERE t.case_id = :c AND t.superseded_by_id IS NULL AND "
                "COALESCE(t.transaction_date, t.posted_date) BETWEEN :lo AND :hi ORDER BY 2", lo=lo_day, hi=hi_day):
            out.append({"ref": f"financial_transaction:{tid}", "day": day, "amount_minor": abs(int(amount or 0)),
                        "direction": direction, "words": " ".join(x for x in (cp, desc) if x).strip(),
                        "holder": holder or "", "institution": inst or ""})
        return out

    def ledger_span(self):
        row = self.q("SELECT min(COALESCE(transaction_date, posted_date)), max(COALESCE(transaction_date, posted_date)) "
                     "FROM financial_transactions WHERE case_id = :c AND superseded_by_id IS NULL").first()
        return (row[0], row[1]) if row and row[0] else None

    # -- documents -----------------------------------------------------------------------------------------------
    def documents_with_words(self, words: list[str]) -> list[dict]:
        """Documents whose text or name holds one of the words. A phone conversation kept as a document (it carries
        a ``thread_key``) is left out: its messages are the phone's own records, read as such."""
        if not words:
            return []
        rx = "(" + "|".join(re.escape(w) for w in words) + ")"
        out = []
        for fid, name, content in self.q(
                "SELECT f.id, f.original_filename, t.content FROM evidence_document_texts t JOIN evidence_files f ON "
                "f.id = t.evidence_file_id WHERE f.case_id = :c AND f.deleted_at IS NULL AND NOT (COALESCE(f.metadata, '{}'::jsonb) ? "
                "'thread_key') AND (t.content ~* :rx OR "
                "f.original_filename ~* :rx) LIMIT 20", rx=rx):
            out.append({"ref": f"evidence_file:{fid}", "name": name or "a document", "content": content or ""})
        return out

"""Run the parts for a subject: each part on its own, timed, a failure in one never hiding the others."""
from __future__ import annotations

import logging
import time

from services.elsewhere import documents, financial, phones, timeline
from services.elsewhere import words as W

log = logging.getLogger(__name__)
FAILED = {"phones": "The other phones could not be checked just now. Open the record again to retry.",
          "financial": "The financial records could not be checked just now. Open the record again to retry.",
          "documents": "The documents could not be checked just now. Open the record again to retry.",
          "timeline": "The case timeline could not be checked just now. Open the record again to retry."}


def _ledger_amounts(conn, case_id, subject):
    """``{check number: amount}`` the ledger gives, when every row of that check number gives the same amount."""
    out = {}
    if not subject.references:
        return out
    cond, params = financial._ref_cond(subject.references)
    rows = financial._rows(conn, case_id, cond, params)
    for ref in subject.references:
        amounts = {r.amount_minor for r in rows if ref in W.digits(r.description) or ref.lower() in
                   (r.description or "").lower()}
        if len(amounts) == 1:
            out[ref] = amounts.pop()
    return out


def run_part(conn, case_id, subject, name, zone) -> dict:
    started = time.monotonic()
    try:
        if name == "phones":
            out = phones.part(conn, case_id, subject, zone)
        elif name == "financial":
            out = financial.part(conn, case_id, subject, zone)
        elif name == "documents":
            out = documents.part(conn, case_id, subject, zone, _ledger_amounts(conn, case_id, subject))
        elif name == "timeline":
            out = timeline.part(conn, case_id, subject, zone)
        else:
            raise ValueError(name)
        state, items, searched = "done", W.sort_items(out["items"]), out["searched"]
    except Exception:  # noqa: BLE001 - one source failing must not hide the others; it is said, not silent
        log.exception("elsewhere part %s failed for case %s", name, case_id)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        state, items, searched = "failed", [], FAILED[name]
    for it in items:
        it.pop("_rank", None)
    return {"source": name, "label": W.PART_LABELS[name], "state": state,
            "ms": int((time.monotonic() - started) * 1000), "searched": searched, "items": items}


def run(conn, case_id, subject, parts=W.PARTS, zone="UTC") -> dict:
    done = [run_part(conn, case_id, subject, p, zone) for p in parts]
    every = [it for p in done for it in p["items"]]
    return {"subject": subject.as_dict(), "parts": done, "counts": W.counts(every),
            "complete": all(p["state"] == "done" for p in done) and tuple(parts) == W.PARTS}

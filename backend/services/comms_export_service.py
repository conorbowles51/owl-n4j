"""
Cellebrite comms → PDF export.

Renders filtered communications (between selected people, within a date range)
to a print-friendly HTML document. The router converts it to PDF bytes with
`financial_export_service.render_pdf` (WeasyPrint) — no new dependency.

Two modes:
  - 'timeline'      : flat chronological table of every comm (default).
  - 'conversation'  : grouped by thread, messages shown in reading order.

Attachments/media are NOT embedded (kept lightweight); a footer notes this.
Names already arrive device-lens-resolved from get_cellebrite_comms_between.
"""

from html import escape
from typing import List, Optional, Dict, Any

# Hard cap so a 70k-message thread can't blow up PDF render time / size.
# WeasyPrint layout is ~10ms/row, so this also bounds request latency
# (the typical "2 people + date range" export is far smaller and fast).
MAX_ITEMS = 2000


def _esc(val) -> str:
    return escape("" if val is None else str(val))


def _fmt_ts(ts: Optional[str]) -> str:
    if not ts:
        return ""
    s = str(ts).replace("T", " ")
    # Trim trailing timezone / fractional seconds for readability.
    if "+" in s:
        s = s.split("+")[0]
    if "." in s:
        s = s.split(".")[0]
    return s.strip()


def _party(p: Optional[Dict[str, Any]]) -> str:
    if not p:
        return "—"
    name = p.get("name") or p.get("key") or "—"
    return name + (" (owner)" if p.get("is_owner") else "")


def _recipients(item: Dict[str, Any]) -> str:
    recs = item.get("recipients") or []
    names = [r.get("name") or r.get("key") for r in recs if r]
    names = [n for n in names if n]
    return ", ".join(names) if names else "—"


def _content(item: Dict[str, Any]) -> str:
    t = item.get("type")
    if t == "call":
        dur = item.get("duration")
        d = item.get("direction") or "call"
        return f"{d}{f' · {dur}s' if dur else ''}"
    if t == "email":
        subj = item.get("subject") or ""
        body = item.get("body") or ""
        return (f"<b>{_esc(subj)}</b><br>" if subj else "") + _esc(body)
    return _esc(item.get("body") or "")


_CSS = """
@page { size: A4; margin: 1.4cm 1.2cm; }
* { box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
       color: #1f2a37; font-size: 11px; line-height: 1.45; }
h1 { font-size: 18px; margin: 0 0 2px; color: #15324a; }
.sub { color: #5b6b7b; font-size: 11px; margin: 0 0 10px; }
.meta { background: #f3f7fb; border: 1px solid #dce6f0; border-radius: 6px;
        padding: 8px 12px; margin: 0 0 14px; }
.meta b { color: #15324a; }
.counts span { display: inline-block; margin-right: 14px; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; background: #15324a; color: #fff; padding: 5px 7px;
     font-size: 10px; font-weight: 600; }
td { padding: 5px 7px; border-bottom: 1px solid #eef2f7; vertical-align: top; }
tr:nth-child(even) td { background: #fafcff; }
.tcol { white-space: nowrap; color: #5b6b7b; width: 120px; }
.kcol { white-space: nowrap; width: 64px; text-transform: capitalize; color: #6b21a8; }
.pcol { white-space: nowrap; width: 200px; }
/* pre-wrap: keep the message's own line breaks AND wrap long lines so a
   multi-line message reads the way it was sent, not as one run-on paragraph. */
.body { word-break: break-word; white-space: pre-wrap; }
.owner { color: #0f7b3f; }
.thread { margin: 0 0 16px; break-inside: avoid; }
.thread h3 { font-size: 12px; margin: 14px 0 4px; color: #15324a;
             border-bottom: 2px solid #dce6f0; padding-bottom: 3px; }
.msg { margin: 0 0 6px; padding: 5px 8px; border-radius: 6px; background: #f3f7fb; }
.msg .h { color: #5b6b7b; font-size: 10px; margin-bottom: 2px; }
.foot { margin-top: 18px; color: #8aa0b4; font-size: 9.5px;
        border-top: 1px solid #dce6f0; padding-top: 6px; }
.trunc { color: #b45309; font-weight: 600; margin: 8px 0; }
"""


def generate_comms_pdf(
    case_name: str,
    items: List[Dict[str, Any]],
    participants: List[Dict[str, Any]],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    mode: str = "timeline",
    filters_description: str = "",
    generated_at: Optional[str] = None,
) -> str:
    """Return a self-contained HTML document for the filtered comms."""
    truncated = len(items) > MAX_ITEMS
    shown = items[:MAX_ITEMS]

    counts: Dict[str, int] = {}
    for it in items:
        counts[it.get("type", "?")] = counts.get(it.get("type", "?"), 0) + 1

    people = ", ".join(_esc(p.get("name") or p.get("key")) for p in (participants or [])) or "all participants"
    date_range = ""
    if start_date or end_date:
        date_range = f"{_esc(start_date or '…')} → {_esc(end_date or '…')}"

    head = [
        f"<h1>Communications report</h1>",
        f"<div class='sub'>{_esc(case_name)}</div>",
        "<div class='meta'>",
        f"<div><b>Participants:</b> {people}</div>",
    ]
    if date_range:
        head.append(f"<div><b>Date range:</b> {date_range}</div>")
    if filters_description:
        head.append(f"<div><b>Filters:</b> {_esc(filters_description)}</div>")
    head.append(
        "<div class='counts' style='margin-top:5px'>"
        + "".join(f"<span><b>{counts.get(k, 0)}</b> {k}s</span>" for k in ("message", "call", "email"))
        + f"<span><b>{len(items)}</b> total</span></div>"
    )
    head.append(f"<div><b>Mode:</b> {_esc(mode)}</div>")
    head.append("</div>")
    if truncated:
        head.append(
            f"<div class='trunc'>Showing the first {MAX_ITEMS:,} of {len(items):,} "
            "communications — narrow the date range or participants for the rest.</div>"
        )

    body_parts: List[str] = []
    if mode == "conversation":
        # Group by thread_id; calls/emails (no thread) each form a singleton.
        groups: Dict[str, List[Dict[str, Any]]] = {}
        order: List[str] = []
        for it in shown:
            tid = it.get("thread_id") or f"{it.get('type')}:{it.get('id') or id(it)}"
            if tid not in groups:
                groups[tid] = []
                order.append(tid)
            groups[tid].append(it)
        for tid in order:
            rows = sorted(groups[tid], key=lambda i: i.get("timestamp") or "")
            head_app = rows[0].get("source_app") or rows[0].get("type", "thread")
            body_parts.append("<div class='thread'>")
            body_parts.append(f"<h3>{_esc(head_app)} · {len(rows)} item(s)</h3>")
            for it in rows:
                who = _party(it.get("sender"))
                cls = " owner" if (it.get("sender") or {}).get("is_owner") else ""
                body_parts.append(
                    f"<div class='msg'><div class='h'><span class='{cls.strip()}'>{_esc(who)}</span>"
                    f" → {_esc(_recipients(it))} · {_esc(_fmt_ts(it.get('timestamp')))}</div>"
                    f"<div class='body'>{_content(it)}</div></div>"
                )
            body_parts.append("</div>")
    else:
        body_parts.append(
            "<table><thead><tr><th>Time</th><th>Type</th><th>From → To</th><th>Content</th></tr></thead><tbody>"
        )
        for it in shown:
            body_parts.append(
                "<tr>"
                f"<td class='tcol'>{_esc(_fmt_ts(it.get('timestamp')))}</td>"
                f"<td class='kcol'>{_esc(it.get('type'))}</td>"
                f"<td class='pcol'>{_esc(_party(it.get('sender')))} → {_esc(_recipients(it))}</td>"
                f"<td class='body'>{_content(it)}</td>"
                "</tr>"
            )
        body_parts.append("</tbody></table>")

    foot = (
        f"<div class='foot'>Generated {_esc(generated_at or '')} · {len(shown):,} of {len(items):,} "
        "communications rendered · attachments/media omitted (review them in the Comms Center) · "
        "Confidential — attorney work product.</div>"
    )

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_CSS}</style></head><body>"
        + "".join(head) + "".join(body_parts) + foot
        + "</body></html>"
    )

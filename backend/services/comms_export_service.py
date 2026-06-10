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

import re
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


_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-")
_NUMERIC_NAME_RE = re.compile(r"^[+(]?\d[\d\s().\-]{5,}$")
_PHONE_KEY_RE = re.compile(r"^phone-(\d{7,15})$")


def _phone_from_key(key) -> str:
    m = _PHONE_KEY_RE.match(str(key or ""))
    return "+" + m.group(1) if m else ""


def _party(p: Optional[Dict[str, Any]]) -> str:
    """Render a party as "Name +number" — the app's number-alongside-name rule.
    Never prints a raw UUID/Neo4j key: when there's no human name we show
    "(unnamed)" (+ the number if it's a phone identity), and an app handle
    (snapchat/whatsapp username) is shown as-is."""
    if not p:
        return "?"
    name = p.get("name")
    key = p.get("key") or ""
    num = _phone_from_key(key)
    if name and not _NUMERIC_NAME_RE.match(str(name).strip()) and not _UUID_RE.match(str(name)):
        label = str(name)
    elif num:
        label = "(unnamed)"
    elif key and not _UUID_RE.match(key) and not key.startswith("phone-"):
        label = str(key)  # app handle / email identity (name was junk/missing)
    else:
        label = "(unnamed)"
    out = (label + (" " + num if num else "")).strip()
    return out + (" (owner)" if p.get("is_owner") else "")


def _recipients(item: Dict[str, Any]) -> str:
    recs = [r for r in (item.get("recipients") or []) if r]
    labels = [_party(r) for r in recs]
    labels = [x for x in labels if x and x != "?"]
    return ", ".join(labels) if labels else "?"


_MEDIA_LABEL = {
    "image": "Image", "images": "Image",
    "audio": "Voice note", "video": "Video",
    "document": "Document", "documents": "Document", "text": "Document",
    "application": "File", "archive": "File", "database": "File",
}


def _media_tags(item: Dict[str, Any]) -> list:
    """Human labels for a message's attachments so media-only rows aren't blank
    (e.g. "[Image: IMG-001.jpg]", "[Voice note]"). Uses the resolved
    `attachments` (category + filename); falls back to a bare count."""
    tags = []
    for a in (item.get("attachments") or []):
        if not a or a.get("missing"):
            continue
        cat = str(a.get("category") or "").strip().lower()
        label = _MEDIA_LABEL.get(cat, (a.get("category") or "Attachment"))
        fn = a.get("original_filename")
        tags.append("[" + label + (": " + str(fn) if fn else "") + "]")
    if not tags:
        n = len(item.get("attachment_file_ids") or [])
        if n:
            tags.append(f"[{n} attachment{'s' if n != 1 else ''}]")
    return tags


def _thumbs_html(item: Dict[str, Any], thumbnails: Optional[Dict[str, str]]) -> str:
    """<img> thumbnails for an item's image attachments, when a base64 data-URI
    was supplied for that evidence_id (thumbnails={evidence_id: data_uri})."""
    if not thumbnails:
        return ""
    imgs = []
    for a in (item.get("attachments") or []):
        if not a:
            continue
        uri = thumbnails.get(a.get("evidence_id"))
        if uri:
            alt = _esc(a.get("original_filename") or "image")
            imgs.append(f"<img class='thumb' src='{uri}' alt='{alt}' />")
    return f"<div class='thumbs'>{''.join(imgs)}</div>" if imgs else ""


def _content(item: Dict[str, Any]) -> str:
    """Escaped HTML for the message content + media labels (so a media-only
    message still reads as e.g. "[Image: x.jpg]" rather than blank)."""
    t = item.get("type")
    if t == "call":
        dur = item.get("duration")
        d = item.get("direction") or "call"
        return _esc(f"{d}{f' · {dur}' if dur else ''}".strip()) or "call"
    if t == "email":
        subj = item.get("subject") or ""
        body = item.get("body") or ""
        html = (f"<b>{_esc(subj)}</b>" + ("<br>" if body else "")) if subj else ""
        html += _esc(body)
    else:
        html = _esc(item.get("body") or "")
    tags = _media_tags(item)
    if tags:
        tag_html = " ".join(f"<span class='media'>{_esc(x)}</span>" for x in tags)
        html = (html + (" " if html else "") + tag_html).strip()
    return html or "—"


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
/* Timeline mode = stacked full-width records (no column table). Each record uses
   the whole page width so contacts and the message both wrap freely on A4. */
.rec { margin: 0 0 7px; padding: 5px 9px; border: 1px solid #e6edf4;
       border-left: 3px solid #15324a; border-radius: 5px; break-inside: avoid; }
.rh { font-size: 10px; color: #5b6b7b; margin-bottom: 3px;
      overflow-wrap: anywhere; word-break: break-word; }
.rh .t { color: #5b6b7b; }
.rh .k { color: #6b21a8; text-transform: capitalize; font-weight: 600; margin: 0 6px; }
.rh .ppl { color: #36506a; }
/* pre-wrap: keep the message's own line breaks AND wrap long lines so a
   multi-line message reads the way it was sent, not as one run-on paragraph. */
.body { overflow-wrap: anywhere; word-break: break-word; white-space: pre-wrap; }
.media { color: #6b21a8; font-size: 9.5px; overflow-wrap: anywhere; }
.thumbs { margin-top: 3px; }
.thumb { height: 84px; max-width: 120px; object-fit: cover; border: 1px solid #dce6f0;
         border-radius: 4px; margin: 2px 4px 0 0; vertical-align: top; }
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
    thumbnails: Optional[Dict[str, str]] = None,
) -> str:
    """Return a self-contained HTML document for the filtered comms — the WHOLE
    filtered conversation, never truncated.

    thumbnails: optional {evidence_id: data-URI} map; when given, image
    attachments render as embedded thumbnails."""
    shown = items  # render everything — no item cap

    counts: Dict[str, int] = {}
    for it in items:
        counts[it.get("type", "?")] = counts.get(it.get("type", "?"), 0) + 1

    people = ", ".join(_esc(_party(p)) for p in (participants or [])) or "all participants"
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
                    f"<div class='body'>{_content(it)}{_thumbs_html(it, thumbnails)}</div></div>"
                )
            body_parts.append("</div>")
    else:
        # Stacked blocks (NOT a column table). A column table cramped the message
        # into a sliver while a multi-recipient "From → To" ate the width — so the
        # body was unreadable. Here each record gets the FULL A4 width: a metadata
        # line (time · type · sender → recipients, wrapping) then the message body
        # on its own line(s), wrapping. Everything is visible regardless of how
        # many participants a row has.
        for it in shown:
            who = _party(it.get("sender"))
            owner = " owner" if (it.get("sender") or {}).get("is_owner") else ""
            body_parts.append(
                "<div class='rec'>"
                f"<div class='rh'><span class='t'>{_esc(_fmt_ts(it.get('timestamp')))}</span>"
                f"<span class='k'>{_esc(it.get('type'))}</span>"
                f"<span class='ppl'><span class='{owner.strip()}'>{_esc(who)}</span>"
                f" &rarr; {_esc(_recipients(it))}</span></div>"
                f"<div class='body'>{_content(it)}{_thumbs_html(it, thumbnails)}</div>"
                "</div>"
            )

    media_note = (
        "image thumbnails embedded; audio/video shown as labels"
        if thumbnails else
        "attachments shown as labels (enable 'with media' to embed image thumbnails)"
    )
    foot = (
        f"<div class='foot'>Generated {_esc(generated_at or '')} · {len(shown):,} "
        f"communications (complete conversation) · {media_note} · "
        "Confidential — attorney work product.</div>"
    )

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{_CSS}</style></head><body>"
        + "".join(head) + "".join(body_parts) + foot
        + "</body></html>"
    )

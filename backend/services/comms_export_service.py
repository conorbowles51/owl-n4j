"""
Comms PDF export service.

Two export modes:
  - timeline: cross-type chronological table (calls, messages, emails)
  - conversation: chat-bubble layout for a single thread
"""

from html import escape as _esc

from services.financial_export_service import render_pdf  # noqa: F401  re-export

_MAX_BODY = 500  # chars shown per message in timeline mode


def _fmt_ts(ts: str) -> str:
    if not ts:
        return ''
    return ts[:16].replace('T', ' ')


def _fmt_duration(seconds) -> str:
    if not seconds:
        return ''
    try:
        s = int(seconds)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h:
            return f'{h}h {m:02d}m {s:02d}s'
        if m:
            return f'{m}m {s:02d}s'
        return f'{s}s'
    except (TypeError, ValueError):
        return ''


def _person_name(person) -> str:
    """Display name for a sender/recipient.

    neo4j_service returns these as nested dicts ({key, name, is_owner}),
    not flat *_name strings. Fall back to the key, then to a bare string
    for any unexpected shape.
    """
    if not person:
        return ''
    if isinstance(person, dict):
        return person.get('name') or person.get('key') or ''
    return str(person)


def _recipients_name(item) -> str:
    """Comma-joined recipient names.

    Timeline items carry a `recipients` list; thread-detail call/email
    items carry a singular `recipient`. Accept either.
    """
    recips = item.get('recipients')
    if not recips:
        single = item.get('recipient')
        recips = [single] if single else []
    names = [_person_name(r) for r in recips]
    return ', '.join(n for n in names if n)


def _is_outbound(item) -> bool:
    """True when the phone owner is the sender (outbound bubble)."""
    sender = item.get('sender')
    if isinstance(sender, dict) and sender.get('is_owner'):
        return True
    return (item.get('direction') or '') in ('outbound', 'sent', 'out')


def _attachment_html(attachments) -> str:
    if not attachments:
        return ''
    lines = []
    for a in attachments:
        fname = a.get('original_filename') or a.get('file_id') or 'attachment'
        lines.append(f'&#128206; {_esc(fname)}')
    return '<br>'.join(lines)


_BASE_CSS = """
@page {
  size: A4 portrait;
  margin: 20mm;
  @bottom-right { content: counter(page) ' / ' counter(pages); font-size: 9pt; }
}
* { box-sizing: border-box; }
body { font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; font-size: 10pt; color: #1a1a1a; margin: 0; }
h1 { font-size: 16pt; font-weight: 700; margin: 0 0 4px; }
.subtitle { font-size: 9pt; color: #555; margin: 0 0 14px; }
.filters { background: #f5f6f8; border: 1px solid #dde; border-radius: 4px; padding: 8px 12px; font-size: 8.5pt; margin-bottom: 14px; line-height: 1.8; }
.filters strong { color: #333; }
.banner { background: #fef2f2; border: 1px solid #fca5a5; color: #991b1b; padding: 8px 12px; border-radius: 4px; font-size: 9pt; font-weight: 600; margin-bottom: 14px; }
"""

_TIMELINE_CSS = _BASE_CSS + """
table { width: 100%; border-collapse: collapse; }
thead { display: table-header-group; }
th { background: #1e3a5f; color: white; font-size: 8pt; font-weight: 600; padding: 5px 8px; text-align: left; }
tr { page-break-inside: avoid; }
td { padding: 4px 8px; font-size: 8.5pt; vertical-align: top; border-bottom: 1px solid #eee; }
tr:nth-child(even) td { background: #f9fafb; }
.t-msg { color: #1d4ed8; font-weight: 600; }
.t-call { color: #166534; font-weight: 600; }
.t-email { color: #7c3aed; font-weight: 600; }
.dir { color: #555; font-size: 8pt; }
.content { max-width: 300px; word-break: break-word; }
.att { color: #666; font-size: 8pt; margin-top: 2px; }
"""

_CONV_CSS = _BASE_CSS + """
.day-header { text-align: center; font-size: 8pt; color: #aaa; margin: 14px 0 6px; }
.bubble-wrap { margin-bottom: 8px; page-break-inside: avoid; }
.meta { font-size: 8pt; color: #666; margin-bottom: 2px; }
.meta .name { font-weight: 700; color: #111; margin-right: 6px; }
.bubble { background: #f0f4ff; border-radius: 6px; padding: 6px 10px; font-size: 9.5pt; word-break: break-word; display: inline-block; max-width: 85%; }
.bubble.out { background: #e8fce8; }
.att { font-size: 8pt; color: #555; margin-top: 3px; }
"""


def generate_timeline_pdf(
    items: list,
    filters_summary: dict,
    case_label: str,
    truncated: bool = False,
) -> str:
    parts = [
        '<!DOCTYPE html><html><head><meta charset="utf-8">',
        f'<style>{_TIMELINE_CSS}</style></head><body>',
        f'<h1>Comms Timeline Export</h1>',
        f'<p class="subtitle">Case: {_esc(case_label)}</p>',
    ]

    if truncated:
        parts.append(
            '<div class="banner">'
            '&#9888; Export limited to 2,000 items. Apply tighter filters to see all records.'
            '</div>'
        )

    filter_lines = []
    if filters_summary.get('participants'):
        filter_lines.append(f'<strong>Participants:</strong> {_esc(filters_summary["participants"])}')
    if filters_summary.get('date_range'):
        filter_lines.append(f'<strong>Date range:</strong> {_esc(filters_summary["date_range"])}')
    if filters_summary.get('types'):
        filter_lines.append(f'<strong>Types:</strong> {_esc(filters_summary["types"])}')
    if filters_summary.get('apps'):
        filter_lines.append(f'<strong>Apps:</strong> {_esc(filters_summary["apps"])}')
    if filter_lines:
        parts.append('<div class="filters">' + ' &nbsp;|&nbsp; '.join(filter_lines) + '</div>')

    parts.append(
        '<table><thead><tr>'
        '<th>Time</th><th>Type</th><th>Direction</th><th>From</th><th>To</th><th>Content</th>'
        '</tr></thead><tbody>'
    )

    for item in items:
        t = item.get('type', '')
        ts = _fmt_ts(item.get('timestamp', ''))
        direction = item.get('direction') or ''
        from_name = _esc(_person_name(item.get('sender')))
        to_name = _esc(_recipients_name(item))

        if t == 'call':
            dur = _fmt_duration(item.get('duration'))
            content = _esc(f'Call — {dur}' if dur else 'Call')
        elif t == 'email':
            subj = item.get('subject') or item.get('body') or ''
            content = _esc(subj[:_MAX_BODY])
        else:
            body = item.get('body') or ''
            content = _esc(body[:_MAX_BODY])
            if len(body) > _MAX_BODY:
                content += ' <span style="color:#aaa">[…]</span>'

        att = _attachment_html(item.get('attachments') or [])
        if att:
            content += f'<div class="att">{att}</div>'

        type_cls = {'message': 't-msg', 'call': 't-call', 'email': 't-email'}.get(t, '')

        parts.append(
            f'<tr>'
            f'<td style="white-space:nowrap">{ts}</td>'
            f'<td class="{type_cls}">{_esc(t)}</td>'
            f'<td class="dir">{_esc(direction)}</td>'
            f'<td>{from_name}</td>'
            f'<td>{to_name}</td>'
            f'<td class="content">{content}</td>'
            f'</tr>'
        )

    parts.append('</tbody></table></body></html>')
    return ''.join(parts)


def generate_conversation_pdf(
    thread: dict,
    messages: list,
    case_label: str,
    truncated: bool = False,
) -> str:
    app = thread.get('source_app') or thread.get('app') or ''
    thread_type = thread.get('thread_type') or thread.get('type') or ''
    participants = thread.get('participants') or []

    parts = [
        '<!DOCTYPE html><html><head><meta charset="utf-8">',
        f'<style>{_CONV_CSS}</style></head><body>',
        f'<h1>Conversation Export</h1>',
        f'<p class="subtitle">Case: {_esc(case_label)}</p>',
    ]

    if truncated:
        parts.append(
            '<div class="banner">'
            '&#9888; Export limited to 2,000 messages. Apply tighter filters to see all records.'
            '</div>'
        )

    info = []
    if participants:
        p_str = ', '.join(_esc(str(p)) for p in participants)
        info.append(f'<strong>Participants:</strong> {p_str}')
    if app:
        info.append(f'<strong>App:</strong> {_esc(app)}')
    if thread_type:
        info.append(f'<strong>Type:</strong> {_esc(thread_type)}')
    if info:
        parts.append('<div class="filters">' + ' &nbsp;|&nbsp; '.join(info) + '</div>')

    last_day = None
    for msg in messages:
        ts_raw = msg.get('timestamp') or ''
        day = ts_raw[:10] if ts_raw else ''

        if day and day != last_day:
            try:
                from datetime import date
                d = date.fromisoformat(day)
                day_str = d.strftime('%A, %B %-d, %Y')
            except Exception:
                day_str = day
            parts.append(f'<div class="day-header">&#8212; {_esc(day_str)} &#8212;</div>')
            last_day = day

        is_out = _is_outbound(msg)
        from_name = _esc(_person_name(msg.get('sender')))
        ts_display = _fmt_ts(ts_raw)

        t = msg.get('type', '')
        if t == 'call':
            dur = _fmt_duration(msg.get('duration'))
            body = _esc(f'Call — {dur}' if dur else 'Call')
        elif t == 'email':
            subj = msg.get('subject') or ''
            body_txt = msg.get('body') or ''
            combined = '\n'.join(p for p in (subj, body_txt) if p)
            body = _esc(combined).replace('\n', '<br>')
        else:
            body = _esc(msg.get('body') or '')

        att = _attachment_html(msg.get('attachments') or [])
        bubble_cls = 'bubble out' if is_out else 'bubble'

        parts.append(
            f'<div class="bubble-wrap">'
            f'<div class="meta"><span class="name">{from_name}</span>'
            f'<span style="color:#bbb">{_esc(ts_display)}</span></div>'
            f'<div class="{bubble_cls}">{body}'
            + (f'<div class="att">{att}</div>' if att else '')
            + '</div></div>'
        )

    parts.append('</body></html>')
    return ''.join(parts)

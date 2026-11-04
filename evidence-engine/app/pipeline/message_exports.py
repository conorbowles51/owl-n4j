"""Text-message exports uploaded as ordinary documents (BACKLOG FEAT-013).

Phone reports (Cellebrite UFDR or report folders) have their own reader. A text-message export a person saves from a
phone app and uploads as a document did not: a WhatsApp ``_chat.txt`` or an "SMS Backup & Restore" XML was read as
raw text, so the reader saw neither who sent each message, nor when, nor which conversation it belonged to.

This module recognises those two formats and rewrites them as one message per line with its time and sender, grouped
by conversation, headed by the participants, the message count and the period. Nothing is inferred and nothing is
dropped: a WhatsApp date is kept exactly as printed (the export does not say whether 03/04 is March or April), text
before the first message is kept, an SMS time is the phone's own epoch time written out in UTC, a picture or group
message keeps its text and counts its attachments, and a sender is the name or number the export records. A file that
is not clearly one of these formats is left to the plain-text reader unchanged.

Pure Python with no app imports, so it can be tested on its own.
"""
from __future__ import annotations

import re
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from xml.etree import ElementTree

# Only the two shapes WhatsApp writes: "[date, time] " (iOS) or "date, time - " (Android). A plain log line such as
# "03/04/2024 09:15 Subject: left" has neither the comma nor the bracket or dash, so it is not taken for a chat.
_DATE = r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
_TIME = r"\d{1,2}:\d{2}(?::\d{2})?(?:[\s ]?[APap]\.?[Mm]\.?)?"
_STAMP = (r"^‎?(?:\[(?P<bdate>" + _DATE + r"),\s(?P<btime>" + _TIME + r")\]\s"
          r"|(?P<adate>" + _DATE + r"),\s(?P<atime>" + _TIME + r")\s-\s)")
_WHATSAPP_LINE = re.compile(_STAMP + r"(?P<sender>[^:\n]{1,80}?):\s(?P<text>.*)$")
_WHATSAPP_NOTICE = re.compile(_STAMP + r"(?P<text>[^:]*)$")
NOTICE = "(WhatsApp notice)"
MIN_MESSAGES = 3
MIN_SHARE_OF_LINES = 0.6


def _stamp(match) -> str:
    return f"{match['bdate'] or match['adate']} {match['btime'] or match['atime']}".replace(" ", " ")


def _whatsapp(text: str):
    lines = [line.rstrip("\r") for line in text.split("\n")]
    messages, preamble, continuation = [], [], 0
    for line in lines:
        match = _WHATSAPP_LINE.match(line)
        notice = None if match else _WHATSAPP_NOTICE.match(line)
        if match:
            messages.append(dict(when=_stamp(match), sender=match["sender"].strip().lstrip("‎"),
                                 text=match["text"].strip()))
        elif notice:
            messages.append(dict(when=_stamp(notice), sender=NOTICE, text=notice["text"].strip()))
        elif messages and line.strip():
            continuation += 1
            messages[-1]["text"] += "\n    " + line.strip()  # a message running over several lines
        elif line.strip():
            preamble.append(line.strip())  # text before the first message is kept, never dropped
    real = [m for m in messages if m["sender"] != NOTICE]
    if len(real) < MIN_MESSAGES or len({m["sender"] for m in real}) < 2:
        return None  # a conversation has at least three messages from at least two people
    if len(messages) / max(1, len(messages) + len(preamble)) < MIN_SHARE_OF_LINES:
        return None
    senders = Counter(m["sender"] for m in real)
    body = (["Text before the first message:", *preamble, ""] if preamble else []) + [
        f"[{m['when']}] {m['sender']}: {m['text']}" for m in messages]
    header = [
        f"Text message export (WhatsApp chat export): {len(real)} messages, "
        f"first {messages[0]['when']}, last {messages[-1]['when']} (dates exactly as printed in the export).",
        "Participants: " + ", ".join(f"{name} ({count} messages)" for name, count in senders.most_common()) + ".",
        "Each line below is one message: [date and time as printed] sender: message.",
        "",
        "Conversation:",
    ]
    meta = dict(format="whatsapp_chat_txt", messages=len(real), notices=len(messages) - len(real),
                participants=[name for name, _ in senders.most_common()], conversations=1,
                first=messages[0]["when"], last=messages[-1]["when"], dates="as printed",
                lines_before_first_message=len(preamble))
    return "\n".join(header + body), meta


def _join_surrogates(text: str) -> str:
    """SMS Backup & Restore writes an emoji as two surrogate character references, which XML rejects; join them."""
    def joined(match):
        high, low = int(match[1]), int(match[2])
        if 0xD800 <= high <= 0xDBFF and 0xDC00 <= low <= 0xDFFF:
            return chr(0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00))
        return match[0]
    return re.sub(r"&#(\d{5});&#(\d{5});", joined, text)


DIRECTIONS = {"1": "received", "2": "sent", "3": "draft", "4": "outbox", "5": "failed", "6": "queued"}


def _sms_backup(text: str):
    if "<smses" not in text.lstrip()[:400].lower():
        return None
    try:
        root = ElementTree.fromstring(_join_surrogates(text).encode("utf-8", errors="replace"))
    except ElementTree.ParseError:
        return None
    if root.tag != "smses":
        return None
    threads: "OrderedDict[str, list]" = OrderedDict()
    names: dict = {}
    skipped = Counter()
    for item in root:
        if item.tag not in ("sms", "mms"):
            skipped[item.tag] += 1
            continue
        address = (item.get("address") or "").strip() or "(no number recorded)"
        contact = (item.get("contact_name") or "").strip()
        if contact and contact != "(Unknown)":
            names[address] = contact
        try:
            when = datetime.fromtimestamp(int(item.get("date")) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            when = None
        if item.tag == "sms":
            kind, body = item.get("type"), item.get("body") or ""
        else:
            # A picture or group message: its text parts are kept; attachments are counted and named, not read.
            kind = item.get("msg_box")
            parts = list(item.find("parts") if item.find("parts") is not None else [])
            texts = [p.get("text") for p in parts if (p.get("ct") or "").startswith("text/plain") and p.get("text")]
            files = [p.get("ct") for p in parts
                     if p.get("ct") and not p.get("ct").startswith(("text/plain", "application/smil"))]
            body = " ".join(texts)
            if files:
                body = (body + " " if body else "") + f"[{len(files)} attachment(s) not read: {', '.join(files)}]"
            if not body:
                body = "[picture or group message with no text]"
        subject = (item.get("subject") or "").strip()
        if subject and subject.lower() != "null":
            body = f"(subject: {subject}) {body}"
        direction = DIRECTIONS.get(kind, "type " + str(kind))
        threads.setdefault(address, []).append(dict(when=when, direction=direction, text=body))
    count = sum(len(v) for v in threads.values())
    if count < MIN_MESSAGES:
        return None
    stamp = lambda w: w.strftime("%Y-%m-%d %H:%M:%S UTC") if w else "time not recorded"  # noqa: E731
    times = [m["when"] for v in threads.values() for m in v if m["when"]]
    label = lambda address: f"{names[address]} ({address})" if address in names else address  # noqa: E731
    body = []
    for address, messages in threads.items():
        messages.sort(key=lambda m: (m["when"] is None, m["when"] or datetime.min.replace(tzinfo=timezone.utc)))
        body += ["", f"Conversation with {label(address)}: {len(messages)} messages"]
        for m in messages:
            who = (f"Phone owner to {label(address)}" if m["direction"] == "sent" else
                   f"{label(address)} to phone owner" if m["direction"] == "received" else
                   f"{m['direction']}, {label(address)}")
            body.append(f"[{stamp(m['when'])}] {who}: {m['text']}")
    header = [
        f"Text message export (SMS Backup & Restore): {count} messages in {len(threads)} conversations"
        + (f", first {stamp(min(times))}, last {stamp(max(times))}" if times else "") + ".",
        "Times are the phone's recorded times written in UTC. 'Phone owner' is the phone the backup was taken from.",
    ]
    if skipped:
        header.append("Not shown here: " + ", ".join(f"{n} {tag} item(s)" for tag, n in sorted(skipped.items()))
                      + " (items other than text and picture messages are not read by this step).")
    meta = dict(format="sms_backup_restore_xml", messages=count, conversations=len(threads),
                participants=[label(a) for a in threads], first=stamp(min(times)) if times else None,
                last=stamp(max(times)) if times else None, not_read=dict(skipped))
    return "\n".join(header + body), meta


def read_message_export(text: str, file_name: str = ""):
    """(rewritten text, metadata) when the file is a WhatsApp chat export or an SMS Backup & Restore XML; else None."""
    name = (file_name or "").lower()
    if name.endswith(".xml"):
        return _sms_backup(text)
    if name.endswith(".txt"):
        return _whatsapp(text)
    return None

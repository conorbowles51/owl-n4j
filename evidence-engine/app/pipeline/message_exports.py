"""Text-message exports uploaded as ordinary documents (BACKLOG FEAT-013).

Phone reports (Cellebrite UFDR or report folders) have their own reader. A text-message export a person saves from a
phone app and uploads as a document did not: a WhatsApp ``_chat.txt`` or an "SMS Backup & Restore" XML was read as
raw text, so the reader saw neither who sent each message, nor when, nor which conversation it belonged to.

This module recognises those two common formats and rewrites them as one message per line with its time and sender,
grouped by conversation, headed by the participants, the message count and the period. Nothing is inferred: a
WhatsApp date is kept exactly as printed (the export does not say whether 03/04 is March or April), an SMS time is the
phone's own epoch time written out in UTC, and a sender is the name or number the export records. A file that is not
clearly one of these formats is left to the plain-text reader unchanged.

Pure Python with no app imports, so it can be tested on its own.
"""
from __future__ import annotations

import re
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from xml.etree import ElementTree

# "[03/04/2024, 14:05:09] Name: text"  (iOS)   or   "03/04/2024, 14:05 - Name: text"  (Android)
_WHATSAPP_LINE = re.compile(
    r"^‎?\[?(?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{2,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:[\s ]?[APap]\.?[Mm]\.?)?)\]?\s*(?:-\s+)?"
    r"(?P<sender>[^:\n]{1,80}?):\s(?P<text>.*)$"
)
_WHATSAPP_SYSTEM = re.compile(
    r"^‎?\[?(?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{2,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:[\s ]?[APap]\.?[Mm]\.?)?)\]?\s*(?:-\s+)?(?P<text>[^:]*)$"
)
MIN_MESSAGES = 3
MIN_SHARE_OF_LINES = 0.6


def _whatsapp(text: str):
    lines = [line.rstrip("\r") for line in text.split("\n")]
    filled = [line for line in lines if line.strip()]
    if not filled:
        return None
    messages, starts = [], 0
    for line in lines:
        match = _WHATSAPP_LINE.match(line)
        if match:
            starts += 1
            messages.append(dict(when=f"{match['date']} {match['time']}".replace(" ", " "),
                                 sender=match["sender"].strip().lstrip("‎"), text=match["text"].strip()))
        elif _WHATSAPP_SYSTEM.match(line):
            starts += 1
            system = _WHATSAPP_SYSTEM.match(line)
            messages.append(dict(when=f"{system['date']} {system['time']}".replace(" ", " "),
                                 sender="(WhatsApp notice)", text=system["text"].strip()))
        elif messages and line.strip():
            messages[-1]["text"] += "\n    " + line.strip()  # a message running over several lines
    real = [m for m in messages if m["sender"] != "(WhatsApp notice)"]
    # Continuation lines count with the message they belong to; the share is of message starts among non-empty
    # lines that are not continuations of a recognised message.
    if len(real) < MIN_MESSAGES or starts / max(1, len([line for line in filled if not line.startswith(" ")])) < MIN_SHARE_OF_LINES:
        return None
    senders = Counter(m["sender"] for m in real)
    body = [f"[{m['when']}] {m['sender']}: {m['text']}" for m in messages]
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
                first=messages[0]["when"], last=messages[-1]["when"], dates="as printed")
    return "\n".join(header + body), meta


def _sms_backup(text: str):
    head = text.lstrip()[:400].lower()
    if "<smses" not in head and "<sms " not in head[:400]:
        return None
    try:
        root = ElementTree.fromstring(text.encode("utf-8", errors="replace"))
    except ElementTree.ParseError:
        return None
    if root.tag != "smses":
        return None
    threads: "OrderedDict[str, list]" = OrderedDict()
    names: dict = {}
    skipped = Counter()
    for item in root:
        if item.tag != "sms":
            skipped[item.tag] += 1
            continue
        address = (item.get("address") or "").strip() or "(no number recorded)"
        contact = (item.get("contact_name") or "").strip()
        if contact and contact != "(Unknown)":
            names[address] = contact
        try:
            when = datetime.fromtimestamp(int(item.get("date")) / 1000, tz=timezone.utc)
        except (TypeError, ValueError):
            when = None
        kind = item.get("type")
        direction = {"1": "received", "2": "sent", "3": "draft", "4": "outbox", "5": "failed", "6": "queued"}.get(kind, "type " + str(kind))
        threads.setdefault(address, []).append(dict(when=when, direction=direction, text=item.get("body") or ""))
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
            who = f"Phone owner to {label(address)}" if m["direction"] == "sent" else (
                f"{label(address)} to phone owner" if m["direction"] == "received" else f"{m['direction']}, {label(address)}")
            body.append(f"[{stamp(m['when'])}] {who}: {m['text']}")
    header = [
        f"Text message export (SMS Backup & Restore): {count} text messages in {len(threads)} conversations"
        + (f", first {stamp(min(times))}, last {stamp(max(times))}" if times else "") + ".",
        "Times are the phone's recorded times written in UTC. 'Phone owner' is the phone the backup was taken from.",
    ]
    if skipped:
        header.append("Not shown here: " + ", ".join(f"{n} {tag} item(s)" for tag, n in sorted(skipped.items()))
                      + " (picture messages and other items are not read by this step).")
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

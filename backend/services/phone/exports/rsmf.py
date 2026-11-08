"""RSMF export of phone conversations (docs/cellebrite/03 section 12.4).

Relativity Short Message Format, version 2.0.0, as Relativity publishes it (03 section 20.8):

* the file is an RFC 5322 message with the ``.rsmf`` extension and the header ``X-RSMF-Version``; the optional
  headers ``X-RSMF-Generator``, ``X-RSMF-BeginDate``, ``X-RSMF-EndDate`` (ISO 8601, earliest and latest event) and
  ``X-RSMF-EventCount`` are written; ``From`` names one participant; the body text is extracted by Relativity;
* it carries exactly one attachment, base64, ``Content-Disposition: attachment; filename="rsmf.zip"``;
* ``rsmf.zip`` holds ``rsmf_manifest.json`` and every attachment the manifest names, by the attachment ``id``;
* the manifest is ``{version, participants, conversations, events}`` and validates against Relativity's schema
  ``rsmf_schema_2_0_0.json`` (copied unchanged under ``rsmf_spec/``); every manifest is validated before delivery.

One file holds the whole filtered period, never one per day (plan 13): every row the screen shows for the filter,
in screen order. Participants carry the name shown on screen and every identifier; conversations carry the app as
``platform`` and ``direct`` or ``channel``; events carry the UTC time, direction, body, deleted flag, attachments and
custom fields with the phone, record id, badges and copies. A call is an event of type ``message`` whose body says
what the call was (RSMF has no call type), with the custom field ``Kind`` set to ``Call``. An attachment whose bytes
are not in the production, or cannot be read, is still listed on its event with the reason in a custom field and is
counted; nothing is dropped silently. Every file in the zip is listed with its SHA-256 in the event's custom fields.

A reply sets the standard ``parent`` to the message it answers when that message is an event of the same conversation
in this file, the only place the format lets it point (the schema: "another event in the same conversation"). RSMF has
no forward field and no quote field, so a forward, a quote, and a reply whose message is elsewhere are stated in the
custom fields ``Forward`` and ``Reply``, in the words the PDF prints. The event's ``participant`` stays the party that
sent this copy, never a forward's first author.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path

from services.phone import labels as L
from services.phone.replies import reply_words

VERSION = "2.0.0"
GENERATOR = "Loupe"
SCHEMA_PATH = Path(__file__).parent / "rsmf_spec" / "rsmf_schema_2_0_0.json"
BLOCK = 1024 * 1024
BASE64_LINE = 57  # 76 characters once encoded, the line length of the email package
RECOMMENDED_MAX_EVENTS = 10_000  # Relativity's recommended ceiling per file; above it the export says so


_DATE_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)")


class RsmfInvalid(ValueError):
    pass


def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def validate(manifest: dict) -> None:
    """Relativity's schema, with formats checked (``date-time``); raises ``RsmfInvalid`` naming every problem."""
    import jsonschema
    v = jsonschema.Draft7Validator(schema(), format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER)
    problems = ["%s: %s" % ("/".join(str(p) for p in e.absolute_path) or "manifest", e.message)
                for e in sorted(v.iter_errors(manifest), key=lambda e: list(e.absolute_path))]
    # jsonschema checks ``date-time`` only when an optional package is installed; check it here so it never depends
    for i, ev in enumerate(manifest.get("events") or []):
        stamps = [("timestamp", ev.get("timestamp"))] + [("edits/timestamp", x.get("timestamp"))
                                                         for x in ev.get("edits") or []]
        for name, ts in stamps:
            if ts is not None and not (isinstance(ts, str) and _DATE_TIME.fullmatch(ts)):
                problems.append("events/%d/%s: %r is not an RFC 3339 date-time" % (i, name, ts))
    if problems:
        raise RsmfInvalid("; ".join(problems[:20]))


def _utc(iso: str | None) -> str | None:
    if not iso:
        return None
    return iso.replace("+00:00", "Z") if iso.endswith("+00:00") else iso


def _custom(pairs) -> list:
    return [{"name": n, "value": str(v)} for n, v in pairs if v not in (None, "", [])]


class _Participants:
    def __init__(self):
        self.by_key, self.items = {}, []

    def key_of(self, label: dict | None) -> str | None:
        if not label:
            return None
        ident = L.identifier_text(label.get("identifier"))
        key = label.get("identity_key") or ("raw:%s" % ident if ident else "name:%s" % (label.get("name") or ""))
        if key not in self.by_key:
            pid = "p%d" % (len(self.items) + 1)
            self.by_key[key] = pid
            idents = sorted({ident} - {None})
            self.items.append({"id": pid, "display": L.label_text(label),
                               "custom": _custom([("Identifier", ", ".join(idents)),
                                                  ("Phone owner", "Yes" if label.get("is_owner") else None)])})
        return self.by_key[key]


def _call_body(row) -> str:
    c = row.get("call") or {}
    return c.get("words") or "Call"


def _spool(data, folder: str) -> tuple:
    """An attachment on disk beside the export, read a block at a time. ``data`` is bytes or a callable that opens a
    stream. Returns (path, size, sha256): a video of 2 GB costs 1 MB of memory here, not 2 GB."""
    digest, size = hashlib.sha256(), 0
    handle, path = tempfile.mkstemp(dir=folder)
    with os.fdopen(handle, "wb") as out, (data() if callable(data) else io.BytesIO(data)) as source:
        for block in iter(lambda: source.read(BLOCK), b""):
            digest.update(block)
            size += len(block)
            out.write(block)
    return path, size, digest.hexdigest()


def _write_message(msg: EmailMessage, zip_path: str, out) -> None:
    """``msg`` as ``as_bytes`` gives it with the zip as its attachment, encoded a block at a time."""
    msg.add_attachment(b"", maintype="application", subtype="zip", filename="rsmf.zip")
    head = msg.as_bytes()
    closing = ("--%s--" % msg.get_boundary()).encode()
    at = head.rindex(closing)
    before = head[:at]
    assert before.endswith(b"\r\n\r\n\r\n")  # headers, blank line, then the empty body's own line break
    out.write(before[:-2])
    with open(zip_path, "rb") as source:
        for block in iter(lambda: source.read(BASE64_LINE * 1024), b""):
            for start in range(0, len(block), BASE64_LINE):
                out.write(base64.b64encode(block[start:start + BASE64_LINE]) + b"\r\n")
    out.write(b"\r\n" + head[at:])


def build(rows: list, *, title: str, contains: list, read_file=None, out=None, spool_dir=None) -> tuple:
    """One RSMF file. ``read_file(file_uid)`` gives (bytes or a stream opener, reason). The attachments, the zip and
    the message are written through files in ``spool_dir``, so memory does not grow with what the rows carry. With
    ``out`` (a binary stream) the file goes there and the first value returned is None."""
    with tempfile.TemporaryDirectory(dir=spool_dir, prefix=".rsmf-") as folder:
        sink = out if out is not None else io.BytesIO()
        counts = _build(rows, title, contains, read_file, sink, folder)
        return (None if out is not None else sink.getvalue()), counts


def _build(rows, title, contains, read_file, sink, spool) -> dict:
    """``rows``: the screen's rows in screen order. ``read_file(file_uid) -> (bytes, None) | (None, reason)``.
    Returns the ``.rsmf`` bytes and the counts (events, attachments included and not included)."""
    people = _Participants()
    convs, conv_members, conv_of = {}, {}, {}
    events, files, missing = [], {}, 0
    attachments_total = 0
    times = []
    used = {}
    first_event, wanted_parent = {}, []
    for row in rows:
        thread = row.get("thread") or {}
        ckey = thread.get("thread_key") or "loose:%s:%s" % (row["phone"]["extraction_id"], row.get("app") or "")
        if ckey not in convs:
            cid = "c%d" % (len(convs) + 1)
            conv_of[ckey] = cid
            convs[ckey] = {"id": cid, "display": thread.get("title") or row.get("line") or "Conversation",
                           "platform": row.get("app") or "Phone", "participants": [],
                           "custom": _custom([("Phone", row["phone"].get("label"))])}
            conv_members[ckey] = []
        sender = people.key_of(row.get("from"))
        recipients = [people.key_of(t) for t in row.get("to") or []]
        for p in [sender] + recipients:
            if p and p not in conv_members[ckey]:
                conv_members[ckey].append(p)
        flags = row.get("flags") or []
        # a record printed at more than one event time (a Timeline lens entry per time value) keeps one id per event
        eid = row["record_uid"]
        used[eid] = used.get(eid, 0) + 1
        if used[eid] > 1:
            eid = "%s-%d" % (eid, used[eid])
        first_event.setdefault(row["record_uid"], (eid, conv_of[ckey]))
        ev = {"id": eid, "type": "message", "conversation": conv_of[ckey],
              "body": (_call_body(row) if row.get("kind") == "call" else (row.get("body") or "")) + "".join(
                  "\nSensitive field %s: %s" % (v["field"], v["value"] or "") for v in row.get("sensitive") or []),
              "deleted": "Deleted" in flags}
        if sender:
            ev["participant"] = sender
        stamp = _utc((row.get("time") or {}).get("instant"))
        if stamp:
            ev["timestamp"] = stamp
            times.append(stamp)
        if row.get("direction") in ("incoming", "outgoing"):
            ev["direction"] = row["direction"]
        atts, att_custom = [], []
        for a in row.get("attachments") or []:
            attachments_total += 1
            name = a.get("filename") or "file"
            aid = "%s-%d-%s" % (row["record_uid"][:8], attachments_total, "".join(
                ch if ch.isalnum() or ch in "._-" else "_" for ch in name)[:80])
            data, reason = (None, "The report refers to a file that is not in the production.")
            if a.get("file_uid") and read_file is not None:
                data, reason = read_file(a["file_uid"])
            item = {"id": aid, "display": name}
            if data is not None:
                try:
                    files[aid], item["size"], digest = _spool(data, spool)
                except OSError:
                    data, reason = None, "The file could not be read from the production."
            if data is not None:
                att_custom.append(("File %s SHA-256" % name, digest))
            else:
                missing += 1
                att_custom.append(("File %s not included" % name, reason))
            atts.append(item)
        if atts:
            ev["attachments"] = atts
        copies = row.get("copies") or {}
        words = reply_words(row)
        linked = next((x["target"]["record_uid"] for x in row.get("replies") or []
                       if x["kind"] == "reply" and x.get("target")), None)
        if linked:
            wanted_parent.append((ev, linked))
        ev["custom"] = _custom([
            ("Kind", "Call" if row.get("kind") == "call" else row.get("kind", "").capitalize()),
            ("Phone", row["phone"].get("label")), ("Record id", row["record_uid"]),
            ("Recipients", ", ".join(L.label_text(t) for t in row.get("to") or [])),
            ("Subject", row.get("subject")),
            ("Time", None if stamp else "No time recorded"),
            ("Badges", "; ".join(flags)),
            ("Copies", copies.get("count") if (copies.get("count") or 1) > 1 else None),
            ("Forward", words[0] if row.get("forward") else None),
            ("Reply", "; ".join(words[1:] if row.get("forward") else words)),
        ] + att_custom)
        events.append(ev)
    for ev, target in wanted_parent:
        parent, conversation = first_event.get(target, (None, None))
        if conversation == ev["conversation"] and parent != ev["id"]:
            ev["parent"] = parent
    for ckey, c in convs.items():
        c["participants"] = conv_members[ckey]
        c["type"] = "direct" if len(conv_members[ckey]) <= 2 else "channel"
    manifest = {"version": VERSION, "participants": people.items, "conversations": list(convs.values()),
                "events": events}
    validate(manifest)
    zip_path = os.path.join(spool, "rsmf.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        z.writestr("rsmf_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for aid, path in files.items():
            z.write(path, aid)
            os.unlink(path)
    msg = EmailMessage(policy=SMTP)
    first = people.items[0]["display"] if people.items else "Loupe"
    msg["From"] = '"%s" <>' % first.replace('"', "'")
    msg["Subject"] = title
    msg["X-RSMF-Version"] = VERSION
    msg["X-RSMF-Generator"] = GENERATOR
    if times:
        msg["X-RSMF-BeginDate"] = min(times)
        msg["X-RSMF-EndDate"] = max(times)
    msg["X-RSMF-EventCount"] = str(len(events))
    msg.set_content("\n".join([title, ""] + list(contains)))
    _write_message(msg, zip_path, sink)
    return {"events": len(events), "conversations": len(convs), "participants": len(people.items),
              "attachments": attachments_total, "attachments_included": attachments_total - missing,
              "attachments_not_included": missing, "over_recommended_size": len(events) > RECOMMENDED_MAX_EVENTS}


def read(data: bytes) -> tuple[dict, dict, dict]:
    """(headers, manifest, files) of an ``.rsmf``: the reverse of ``build``, used by the tests and the self-check."""
    import email
    msg = email.message_from_bytes(data, policy=SMTP)
    parts = [p for p in msg.iter_attachments()]
    if len(parts) != 1 or parts[0].get_filename() != "rsmf.zip":
        raise RsmfInvalid("an RSMF file carries exactly one attachment named rsmf.zip")
    z = zipfile.ZipFile(io.BytesIO(parts[0].get_content()))
    manifest = json.loads(z.read("rsmf_manifest.json"))
    files = {n: z.read(n) for n in z.namelist() if n != "rsmf_manifest.json"}
    return {k: v for k, v in msg.items()}, manifest, files

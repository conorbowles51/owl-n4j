"""The phone fixture builder (01 section 12, 07 section 12.1 item A, UXD-33: no second generator).

Writes synthetic phone reports with **invented content** at the structure and scale of the real
reports, plus the two case shapes 07 needs:

* ``phones_only_case()``: three synthetic phones and no other evidence (07 sections 8 and 10.1);
* ``training_case()``: two synthetic phones and a small synthetic ledger (07 section 9).

Structure comes only from structure-only sources: the record types, field names, value kinds,
named-value sets and per-type counts in ``docs/cellebrite/measurements/catalogue-14-phones.json``,
the nesting table in 02 section 3.6 and the report sections in 01 section 1.2. Every value is
invented here: people from the name lists below, numbers in the fictional ``555-01xx`` range,
mail at ``example.com``/``.org``/``.net`` (RFC 2606), text from the phrase bank, coordinates
generated around an invented centre. No value is read from a real report.

Standard library only, deterministic for a given seed, so the same call gives the same bytes.

Command line (writes report folders, ``manifest.json`` and ``ui-fixture.json``)::

    python3 fixture_builder.py phones-only OUT_DIR [--scale 0.02]
    python3 fixture_builder.py training OUT_DIR
    python3 fixture_builder.py phone OUT_DIR --like P08 --scale 1.0   # one phone at real scale

Other forms (zip, split sections, protected single-file reports) are added to this module by the
units that test them (01 unit 1.2); they are not separate generators.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

NS = "http://pa.cellebrite.com/report/2.0"
REPORT_VERSION = "7.48.0.0"
REPO = Path(__file__).resolve().parents[3]
CATALOGUE = REPO / "docs" / "cellebrite" / "measurements" / "catalogue-14-phones.json"
SYNTHETIC_MARK = "SYNTHETIC: invented data, no real case material"

# ---------------------------------------------------------------------------------------------
# Invented vocabularies. These names are made up for fixtures; any likeness is accidental.
FIRST = ["Avery", "Blair", "Corin", "Dara", "Ellis", "Fenna", "Garnet", "Hollis", "Ilse", "Jory",
         "Kestrel", "Linden", "Marlo", "Nell", "Orrin", "Perrin", "Quill", "Rowan", "Sable", "Tamsin",
         "Ulla", "Vesper", "Wren", "Yarrow", "Zeno", "Alder", "Bryony", "Cassia", "Dorian", "Emrys"]
LAST = ["Ashdown", "Brackley", "Corwood", "Dunmere", "Eastlake", "Fallowby", "Greywell", "Harrowgate",
        "Inchmore", "Juniper", "Kettering", "Larkspur", "Merriweather", "Northcott", "Oakhurst",
        "Pennywhistle", "Quarrington", "Ravensworth", "Stillwater", "Thistlewood"]
APPS = ["WhatsApp", "Telegram", "Signal", "Native Messages"]
PHRASES = [
    "are we still on for later", "running about ten minutes behind", "call me when you can",
    "did you get the package", "not tonight, tomorrow works", "ok", "on my way",
    "can you send the address again", "left it by the side door", "thanks, got it",
    "who else is coming", "meet at the usual place", "that price is too high",
    "let me check and come back to you", "see you at 7", "phone was off, sorry",
    "need the number for the landlord", "half now, half on Friday", "keep this between us",
    "lol", "where are you", "picked up the keys", "the car is outside", "invoice sent",
]
EDGE_TEXTS = [
    "",  # empty body (01 1.6 / 07 J-8 edge case)
    "path a/b/c and +15550100 with 50% off",  # slashes and plus signs (S-10)
    "emoji \U0001F600 and accents café naïve",  # non-BMP and accents
    "long " + " ".join(["synthetic"] * 400),  # long text
]
CATEGORIES_LOC = ["Wireless Networks", "Locations", "Cell Towers", "Media"]
CENTRE = (39.2904, -76.6122)  # an invented centre for generated coordinates


def _number(i: int) -> str:
    """A fictional North American number: 555-0100 to 555-0199 under varied area codes."""
    area = [201, 302, 410, 443, 571, 703, 908, 917][(i // 100) % 8]
    return f"+1{area}5550{100 + i % 100:03d}"


@dataclass
class Person:
    key: str
    name: str
    numbers: list[str]
    accounts: dict[str, str]
    email: str


@dataclass
class PhoneSpec:
    label: str
    like: str = "P06"  # catalogue phone whose per-type counts and fields set the shape
    scale: float = 0.02
    owner: str | None = "p0"  # person key; None = no owner number in the report
    zone: str | None = "America/New_York"  # None = no timeZoneConfigurations (zone unknown)
    extraction_date: dt.date = dt.date(2024, 5, 3)
    period_days: int = 180
    gap: tuple[int, int] | None = (70, 84)  # days with no data (powered off), kept apart from quiet
    contacts: list[str] = field(default_factory=list)  # person keys this phone talks to
    seed: int = 1
    # a newer report of the same phone (07 J-13b Replace): every record of the original, plus ``later_messages``
    # in the busiest thread dated in the ``later_days`` after the original extraction, which moves that much later
    later_days: int = 0
    later_messages: int = 0
    # bank alerts for some of the case ledger's payments in this phone's period (05 approach 1: money on the phones)
    bank_alerts: bool = False
    # voice notes (cb-media): bytes of audio files given to the first present attachments, in order, as Audio files;
    # the caller supplies invented speech. Empty leaves every fixture exactly as before.
    voice_notes: tuple = ()
    # extra invented typed and searched values (cb-vocab, 05 approaches 7 and 9): ``(model_type, field, text)`` for
    # DictionaryWord Word, Autofill Value or SearchedItem Value, written last. Empty leaves every fixture as before.
    typed_values: tuple = ()
    report_name: str = "Report.xml"


@dataclass
class CaseSpec:
    name: str
    people: list[Person]
    phones: list[PhoneSpec]
    ledger: bool = False
    seed: int = 7


def invent_people(n: int, seed: int) -> list[Person]:
    rng = random.Random(seed)
    names: set[str] = set()
    people = []
    i = 0
    while len(people) < n:
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name in names:
            continue
        names.add(name)
        handle = name.lower().replace(" ", ".")
        nums = [_number(i * 2)] + ([_number(i * 2 + 1)] if rng.random() < 0.25 else [])
        accounts = {"Telegram": f"@{handle.replace('.', '_')}", "Signal": nums[0]}
        people.append(Person(f"p{i}", name, nums, accounts, f"{handle}@example.{['com', 'org', 'net'][i % 3]}"))
        i += 1
    return people


# ---------------------------------------------------------------------------------------------
# Catalogue (structure only)


def load_catalogue(path: Path = CATALOGUE) -> dict[str, dict]:
    data = json.loads(path.read_text())
    return {p["p_label"]: p for p in data["phones"]}


def catalogue_fields(phone: dict) -> dict[str, list[tuple[str, str, str]]]:
    """type -> [(field name, kind, value type)] in catalogue order."""
    out: dict[str, list[tuple[str, str, str]]] = {}
    for mtype, fname, kind, vtypes in phone["catalog"]:
        vtype = max(vtypes.items(), key=lambda kv: kv[1])[0]
        out.setdefault(mtype, []).append((fname, kind, vtype))
    return out


# Types that only occur nested in a parent (02 section 3.6); never written top-level.
NESTED_ONLY = {"Party", "Coordinate", "StreetAddress", "PhoneNumber", "UserID", "EmailAddress",
               "ProfilePicture", "WebAddress", "KeyValueModel", "Attachment", "MessageLabel",
               "ReplyMessageData", "ForwardedMessageData", "QuotedMessageData", "ContactPhoto",
               "ChatActivity", "InstantMessage"}
BUILT = {"Chat", "Call", "Contact", "Location"}  # written with invented relational content


# ---------------------------------------------------------------------------------------------
# XML writing helpers


class Ids:
    def __init__(self, seed: int):
        self.rng = random.Random(seed * 7919)

    def guid(self) -> str:
        return "%08x-%04x-%04x-%04x-%012x" % tuple(self.rng.getrandbits(b) for b in (32, 16, 16, 16, 48))


def ts(instant: dt.datetime, with_offset: bool = True) -> str:
    text = instant.strftime("%Y-%m-%dT%H:%M:%S.") + f"{instant.microsecond // 1000:03d}"
    return text + ("+00:00" if with_offset else "")


def formatted(instant: dt.datetime) -> str:
    hour = instant.hour % 12 or 12
    ampm = "AM" if instant.hour < 12 else "PM"
    return f"{instant.month}/{instant.day}/{instant.year} {hour}:{instant.minute:02d}:{instant.second:02d} {ampm}(UTC+0)"


def value(vtype: str, text: str, instant: dt.datetime | None = None) -> str:
    if vtype == "TimeStamp" and instant is not None:
        return f'<value type="TimeStamp" formattedTimestamp="{formatted(instant)}">{text}</value>'
    return f'<value type="{vtype}">{escape(text)}</value>'


def fld(name: str, vtype: str, text, instant: dt.datetime | None = None) -> str:
    if text is None:
        return f'<field name="{name}" />'
    return f'<field name="{name}">{value(vtype, str(text), instant)}</field>'


def tfield(name: str, instant: dt.datetime | None, with_offset: bool = True) -> str:
    if instant is None:
        return f'<field name="{name}" />'
    return fld(name, "TimeStamp", ts(instant, with_offset), instant)


@dataclass
class Counter:
    top: dict[str, int] = field(default_factory=dict)
    nested: dict[str, int] = field(default_factory=dict)
    facts: dict[str, int] = field(default_factory=dict)

    def add(self, mtype: str, nested: bool) -> None:
        d = self.nested if nested else self.top
        d[mtype] = d.get(mtype, 0) + 1

    def fact(self, key: str, n: int = 1) -> None:
        self.facts[key] = self.facts.get(key, 0) + n


class Model:
    """One <model> element under construction."""

    def __init__(self, ctx: "PhoneBuild", mtype: str, nested: bool, deleted: str = "Intact",
                 file_id: str | None = None):
        self.ctx, self.mtype, self.parts = ctx, mtype, []
        ctx.count.add(mtype, nested)
        ctx.serial += 1
        attrs = (f'type="{mtype}" id="{ctx.ids.guid()}" deleted_state="{deleted}" '
                 f'decoding_confidence="High" isrelated="False" source_index="0" extractionId="0"')
        if file_id:
            attrs += f' file_id="{file_id}"'
        self.head = f"<model {attrs}>"

    def f(self, *a, **k) -> "Model":
        self.parts.append(fld(*a, **k))
        return self

    def t(self, name: str, instant, with_offset: bool = True) -> "Model":
        self.parts.append(tfield(name, instant, with_offset))
        return self

    def nest(self, kind: str, name: str, models: list["Model"]) -> "Model":
        inner = "".join(m.xml() for m in models)
        self.parts.append(f'<{kind} name="{name}">{inner}</{kind}>')
        return self

    def xml(self) -> str:
        return self.head + "".join(self.parts) + "</model>"


# ---------------------------------------------------------------------------------------------


class PhoneBuild:
    def __init__(self, spec: PhoneSpec, people: dict[str, Person], catalogue: dict[str, dict]):
        self.spec, self.people = spec, people
        self.rng = random.Random(spec.seed)
        self.ids = Ids(spec.seed)
        self.count = Counter()
        self.serial = 0
        self.cat = catalogue[spec.like]
        self.fields = catalogue_fields(self.cat)
        self.enums = self.cat.get("enums", {})
        end = dt.datetime.combine(spec.extraction_date, dt.time(9, 30))
        self.end = end
        self.reported_end = end + dt.timedelta(days=spec.later_days)
        self.start = end - dt.timedelta(days=spec.period_days)
        self.files: list[dict] = []
        self.ui_threads: list[dict] = []
        self.ui_messages: list[dict] = []
        self.ui_calls: list[dict] = []
        self.alert_rows: list[dict] = []

    # -- counts ---------------------------------------------------------------------------
    def target(self, mtype: str, minimum: int = 0) -> int:
        n = self.cat["model_types"].get(mtype, 0)
        return max(minimum, int(round(n * self.spec.scale))) if n or minimum else 0

    def instant(self) -> dt.datetime:
        """A time inside the period, weighted to waking hours, never inside the no-data gap."""
        while True:
            day = self.rng.randrange(self.spec.period_days)
            if self.spec.gap and self.spec.gap[0] <= day < self.spec.gap[1]:
                continue
            hour = int(self.rng.triangular(7, 24, 16)) % 24
            t = self.start + dt.timedelta(days=day, hours=hour, minutes=self.rng.randrange(60),
                                          seconds=self.rng.randrange(60),
                                          milliseconds=self.rng.randrange(1000))
            if t < self.end:
                return t

    def owner(self) -> Person | None:
        return self.people.get(self.spec.owner) if self.spec.owner else None

    def party(self, person: Person, role: str | None, is_owner: bool, app: str) -> Model:
        m = Model(self, "Party", True)
        ident = person.numbers[0] if app in ("Native Messages", "Phone", "Signal", "WhatsApp") \
            else person.accounts.get(app, person.numbers[0])
        if app == "WhatsApp":
            ident = person.numbers[0].lstrip("+") + "@s.whatsapp.net"
        m.f("Identifier", "String", ident)
        if role:
            m.f("Role", "PartyRole", role)
        m.f("Name", "String", person.name)
        m.f("IsPhoneOwner", "Boolean", "True" if is_owner else "False")
        return m

    def owner_party(self, role: str | None, app: str) -> Model:
        own = self.owner()
        if own is None:  # report without an owner number: the owner side has no identifier
            m = Model(self, "Party", True)
            if role:
                m.f("Role", "PartyRole", role)
            m.f("IsPhoneOwner", "Boolean", "True")
            return m
        return self.party(own, role, True, app)

    # -- records --------------------------------------------------------------------------
    def chats(self) -> list[str]:
        n_msgs = self.target("InstantMessage", 40)
        n_chats = max(3, self.target("Chat", 3))
        contacts = [self.people[k] for k in self.spec.contacts]
        weights = [1 / (i + 1) ** 1.1 for i in range(n_chats)]  # a few busy threads, a long tail
        total_w = sum(weights)
        sizes = [max(1, int(n_msgs * w / total_w)) for w in weights]
        sizes[0] += n_msgs - sum(sizes)
        out = []
        for c in range(n_chats):
            app = APPS[c % len(APPS)] if c else APPS[0]
            group = c % 9 == 4 and len(contacts) >= 3
            members = self.rng.sample(contacts, 3) if group else [contacts[c % len(contacts)]]
            out.append(self.chat(c, app, members, sizes[c], group))
        return out

    def chat(self, c: int, app: str, members: list[Person], size: int, group: bool) -> str:
        thread_id = f"{self.spec.label}-t{c}"
        chat = Model(self, "Chat", False)
        chat.f("Source", "String", app).f("Id", "String", self.ids.guid())
        times = sorted(self.instant() for _ in range(size))
        later = []
        if c == 0 and self.spec.later_messages:  # drawn apart, so every other record stays exactly as it was
            lr = random.Random(self.spec.seed * 31 + 1)
            span = max(1, self.spec.later_days * 86400 - 3600)
            later = sorted(self.end + dt.timedelta(seconds=60 + lr.randrange(span)) for _ in range(self.spec.later_messages))
        if times:
            chat.t("StartTime", times[0]).t("LastActivity", (later or times)[-1])
        chat.f("ChatType", "ChatType", "Group" if group else "OneOnOne")
        if group:
            chat.f("Name", "String", f"Group {c} (synthetic)")
        parts = [self.owner_party(None, app)] + [self.party(p, None, False, app) for p in members]
        chat.nest("multiModelField", "Participants", parts)
        msgs = []
        for i, t in enumerate(times):
            msgs.append(self.message(thread_id, app, members, t, i))
        # messages with no time are listed at the end (07 J-4 failure state)
        if c == 0:
            for j in range(max(1, size // 50)):
                msgs.append(self.message(thread_id, app, members, None, len(times) + j))
        if later:
            kept = (self.rng, self.ids)
            self.rng, self.ids = random.Random(self.spec.seed * 31 + 2), Ids(self.spec.seed * 31 + 3)
            try:
                for j, t in enumerate(later):
                    msgs.append(self.message(thread_id, app, members, t, len(msgs) + j))
            finally:
                self.rng, self.ids = kept
        chat.nest("multiModelField", "Messages", msgs)
        self.ui_threads.append({"id": thread_id, "phone": self.spec.label, "app": app, "group": group,
                                "participants": [p.key for p in members], "count": len(msgs)})
        return chat.xml()

    def message(self, thread_id: str, app: str, members: list[Person], t: dt.datetime | None,
                i: int) -> Model:
        outgoing = self.rng.random() < 0.45
        other = self.rng.choice(members)
        r = self.rng.random()
        deleted = "Deleted" if r < 0.012 else ("Trash" if r < 0.014 else ("Unknown" if r < 0.05 else "Intact"))
        if deleted != "Intact":
            self.count.fact(f"messages_{deleted.lower()}")
        body = self.rng.choice(EDGE_TEXTS) if self.rng.random() < 0.01 else self.rng.choice(PHRASES)
        m = Model(self, "InstantMessage", True, deleted)
        m.f("Source", "String", app)
        m.f("Body", "String", body) if body else m.f("Body", "String", None)
        if t is None:
            m.parts.append('<field name="TimeStamp" />')
            self.count.fact("messages_no_time")
        else:
            m.t("TimeStamp", t)
        m.f("Status", "MessageStatus", "Sent" if outgoing else "Read")
        m.f("Type", "InstantMessageType", "Sms" if app == "Native Messages" else "AppMessage")
        m.f("Platform", "Platform", "Mobile")
        sender = self.owner_party("From", app) if outgoing else self.party(other, "From", False, app)
        m.nest("modelField", "From", [sender])
        to = [self.party(p, "To", False, app) for p in members] if outgoing else [self.owner_party("To", app)]
        m.nest("multiModelField", "To", to)
        extra = []
        if i and self.rng.random() < 0.03:
            rep = Model(self, "ReplyMessageData", True)
            rep.f("Label", "Label", "Reply").f("OriginalMessageID", "String", self.ids.guid())
            extra.append(rep)
        if self.rng.random() < 0.01:
            fwd = Model(self, "ForwardedMessageData", True)
            fwd.f("Label", "Label", "Forwarded")
            extra.append(fwd)
        if extra:
            m.nest("multiModelField", "MessageExtraData", extra)
        if self.rng.random() < 0.06:
            m.nest("multiModelField", "Attachments", [self.attachment(t)])
        self.count.fact("messages")
        sender_key = (self.spec.owner or "owner") if outgoing else other.key
        self.ui_messages.append({
            "id": f"{thread_id}-m{i}", "thread": thread_id, "phone": self.spec.label, "app": app,
            "time": ts(t) if t else None, "from": sender_key,
            "to": [p.key for p in members] if outgoing else [self.spec.owner or "owner"],
            "direction": "outgoing" if outgoing else "incoming", "body": body, "deleted": deleted,
        })
        return m

    def attachment(self, t: dt.datetime | None) -> Model:
        present = self.rng.random() < 0.8  # some attachments are referenced but not in the report
        file_id = self.ids.guid()
        voiced = sum(1 for f in self.files if f.get("kind") == "Audio")
        if present and voiced < len(self.spec.voice_notes):
            name = f"PTT-{voiced + 1:05d}.opus"
            a = Model(self, "Attachment", True, file_id=file_id)
            a.f("Filename", "String", name).f("ContentType", "String", "audio/ogg")
            path = f"files\\Audio\\{name}"
            a.f("attachment_extracted_path", "String", path)
            self.files.append({"id": file_id, "name": name, "path": path, "time": t or self.end, "kind": "Audio",
                               "data": self.spec.voice_notes[voiced]})
            self.count.fact("attachments_present")
            return a
        name = f"IMG_{len(self.files):05d}.jpg"
        a = Model(self, "Attachment", True, file_id=file_id if present else None)
        a.f("Filename", "String", name).f("ContentType", "String", "image/jpeg")
        if present:
            path = f"files\\Image\\{name}"
            a.f("attachment_extracted_path", "String", path)
            self.files.append({"id": file_id, "name": name, "path": path, "time": t or self.end})
            self.count.fact("attachments_present")
        else:
            self.count.fact("attachments_missing")
        return a

    def calls(self) -> list[str]:
        out = []
        contacts = [self.people[k] for k in self.spec.contacts]
        for _ in range(self.target("Call", 10)):
            other = self.rng.choice(contacts)
            t = self.instant()
            outgoing = self.rng.random() < 0.5
            status = self.rng.choice(self.enums.get("TelephonyCallStatus", ["Established", "Missed"]))
            c = Model(self, "Call", False)
            c.f("Source", "String", "Phone").f("Direction", "ModelDirections", "Outgoing" if outgoing else "Incoming")
            c.f("Status", "TelephonyCallStatus", status).t("TimeStamp", t)
            dur = self.rng.randrange(0, 1800) if status == "Established" else 0
            c.f("Duration", "TimeSpan", f"{dur // 3600:02d}:{dur % 3600 // 60:02d}:{dur % 60:02d}")
            frm = self.owner_party("From", "Phone") if outgoing else self.party(other, "From", False, "Phone")
            to = self.party(other, "To", False, "Phone") if outgoing else self.owner_party("To", "Phone")
            c.nest("multiModelField", "Parties", [frm, to])
            self.ui_calls.append({"phone": self.spec.label, "time": ts(t), "other": other.key,
                                  "direction": "outgoing" if outgoing else "incoming", "status": status,
                                  "seconds": dur})
            out.append(c.xml())
        return out

    def contacts(self) -> list[str]:
        out = []
        people = [self.people[k] for k in self.spec.contacts]
        n = self.target("Contact", len(people))
        for i in range(n):
            if i < len(people):
                p = people[i]
                # this phone's own name for the person: sometimes a nickname (the phone's view)
                saved = p.name if i % 4 else p.name.split()[0] + " (work)"
                nums = p.numbers
            else:
                saved = f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)[0]}."
                nums = [_number(1000 + self.spec.seed * 300 + i)]
            c = Model(self, "Contact", False)
            c.f("Source", "String", "Phone").f("Name", "String", saved)
            entries = []
            for num in nums:
                e = Model(self, "PhoneNumber", True)
                e.f("Category", "String", "Mobile").f("Value", "String", num).f("Domain", "String", "Phone")
                entries.append(e)
            c.nest("multiModelField", "Entries", entries)
            out.append(c.xml())
        return out

    def locations(self) -> list[str]:
        out = []
        for i in range(self.target("Location", 6)):
            t = self.instant()
            loc = Model(self, "Location", False)
            loc.f("Source", "String", "Synthetic Maps")
            # a few location times carry no offset (01 1.6)
            loc.t("TimeStamp", t, with_offset=(i % 40 != 7))
            loc.f("Category", "String", self.rng.choice(CATEGORIES_LOC))
            if i % 5 != 3:  # some Locations have no Position (not positionable)
                lat = CENTRE[0] + self.rng.gauss(0, 0.05)
                lon = CENTRE[1] + self.rng.gauss(0, 0.05)
                co = Model(self, "Coordinate", True)
                co.f("Longitude", "Double", f"{lon:.6f}").f("Latitude", "Double", f"{lat:.6f}")
                loc.nest("modelField", "Position", [co])
                self.count.fact("locations_positioned")
            out.append(loc.xml())
        return out

    def generic(self, mtype: str) -> list[str]:
        """Other record types at catalogue scale, fields and value kinds from the catalogue."""
        out = []
        for _ in range(self.target(mtype)):
            m = Model(self, mtype, False)
            for fname, kind, vtype in self.fields.get(mtype, []):
                if self.rng.random() < 0.15:
                    continue
                text = self.generic_value(mtype, fname, vtype)
                if kind == "multiField":
                    m.parts.append(f'<multiField name="{fname}">{value(vtype, text)}</multiField>')
                elif vtype == "TimeStamp":
                    m.t(fname, self.instant())
                else:
                    m.f(fname, vtype, text)
            out.append(m.xml())
        return out

    def generic_value(self, mtype: str, fname: str, vtype: str) -> str:
        if vtype in self.enums:
            return self.rng.choice(self.enums[vtype])
        if vtype == "Boolean":
            return self.rng.choice(["True", "False"])
        if vtype in ("Int32", "Int64", "UInt32"):
            return str(self.rng.randrange(0, 5000))
        if vtype == "Double":
            return f"{self.rng.random() * 100:.4f}"
        if vtype == "TimeSpan":
            return "00:00:%02d" % self.rng.randrange(60)
        if fname.lower() in ("url", "domain"):
            return f"https://site{self.rng.randrange(40)}.example.com/page"
        drawn = self.rng.randrange(10_000)  # drawn for every text value, so the rest of a report keeps its content
        if vtype == "DecodingSourceOptions":  # a named set with one value (02 section 3.5), absent from the enums
            return "Decoding"
        return f"synthetic {mtype.lower()} {fname.lower()} {drawn}"

    # -- document -------------------------------------------------------------------------
    def write(self, out: Path) -> dict:
        out.mkdir(parents=True, exist_ok=True)
        model_types: dict[str, list[str]] = {
            "Chat": self.chats(), "Call": self.calls(), "Contact": self.contacts(),
            "Location": self.locations()}
        for mtype in self.cat["model_types"]:
            if mtype not in NESTED_ONLY and mtype not in BUILT:
                model_types[mtype] = self.generic(mtype)
        # the report id is drawn here, before any bank alert, so a phone with alerts keeps the id it had without them
        project_id = self.ids.guid()
        if self.alert_rows:
            # written last, so every other record keeps the ids and content it had before alerts existed
            model_types.setdefault("Notification", [])
            model_types["Notification"] = list(model_types["Notification"]) + self.bank_alerts()
        for mtype, fname, text in self.spec.typed_values:
            m = Model(self, mtype, False)
            m.f(fname, "String", text)
            if mtype == "Autofill":
                m.f("Key", "String", "synthetic field")
            model_types.setdefault(mtype, [])
            model_types[mtype] = list(model_types[mtype]) + [m.xml()]
            self.count.fact("typed_values")
        files_xml = self.tagged_files(out)
        top = sum(len(v) for v in model_types.values())
        spec = self.spec
        own = self.owner()
        device = [("DeviceInfoSelectedManufacturer", "Synthetic"), ("DeviceInfoSelectedDeviceName", f"Phone {spec.label}"),
                  ("DeviceInfoOSType", "Android"), ("DeviceInfoExtractionStartDateTime", self.reported_end.strftime("%m/%d/%Y %I:%M:%S %p +00:00"))]
        if own:
            device.append(("MSISDN", own.numbers[0]))
        with open(out / spec.report_name, "w", encoding="utf-8", newline="\n") as fh:
            w = fh.write
            w('<?xml version="1.0" encoding="utf-8"?>\n')
            w(f'<project id="{project_id}" name="Synthetic {spec.label}" reportVersion="{REPORT_VERSION}" '
              f'containsGarbage="False" extractionType="FileSystem" NodeCount="{len(self.files)}" '
              f'ModelCount="{top}" xmlns="{NS}">\n')
            w(f'  <sourceExtractions>\n    <extractionInfo id="0" name="File System" isCustomName="False" '
              f'type="FileSystem" deviceName="Phone {spec.label}" fullName="Synthetic phone {spec.label}" index="0" '
              f'IsPartialData="False" IsSelectiveExtraction="False" IsStoppedByUser="False" />\n  </sourceExtractions>\n')
            w("  <caseInformation>\n")
            for name in ["Case number", "Case name", "Evidence number", "Examiner name", "Department",
                         "Location", "Crime type", "Notes", "Device"]:
                w(f'    <field name="{name}" isSystem="True" isRequired="False" fieldType="{name.replace(" ", "")}" '
                  f'multipleLines="False">{escape(SYNTHETIC_MARK) if name == "Notes" else "Synthetic"}</field>\n')
            w("  </caseInformation>\n")
            w('  <metadata section="Additional Fields">\n    <item name="UFED_PA_Version">Synthetic 0.0</item>\n  </metadata>\n')
            w('  <metadata section="Extraction Data">\n')
            for k, v in device:
                w(f'    <item name="{k}" sourceExtraction="0">{escape(v)}</item>\n')
            w("  </metadata>\n  <images />\n  <HashSetsInfo />\n  <MalwareScanner ScanPerformed=\"False\" />\n")
            w("  <taggedFiles>\n" + files_xml + "  </taggedFiles>\n  <decodedData>\n")
            for mtype, models in model_types.items():
                if not models:
                    continue
                w(f'    <modelType type="{mtype}">\n')
                for m in models:
                    w("      " + m + "\n")
                w("    </modelType>\n")
            w("  </decodedData>\n  <carvedFiles />\n  <infectedFiles />\n  <extraInfos />\n")
            if spec.zone:
                w(f'  <projectConfigurations>\n    <timeZoneConfigurations enableAutomaticallyConvertToUTC="True" '
                  f'selectedTimeZone="_{spec.zone}" />\n  </projectConfigurations>\n')
            w("</project>\n")
        return {
            "label": spec.label, "like": spec.like, "scale": spec.scale, "owner": spec.owner,
            "owner_number_in_report": bool(own), "zone": spec.zone,
            "extraction_date": self.reported_end.date().isoformat(), "period_start": ts(self.start),
            "period_end": ts(self.end), "no_data_days": list(spec.gap) if spec.gap else None,
            "top_level": dict(sorted(self.count.top.items())), "nested": dict(sorted(self.count.nested.items())),
            "facts": dict(sorted(self.count.facts.items())), "files": len(self.files),
            "top_level_total": top,
        }

    def bank_alerts(self) -> list[str]:
        """One notification per chosen ledger row, the same day at 10:00 UTC: the amount, money in or out, the
        statement's account ending and the payee as the statement prints it. Invented bank, invented people."""
        out = []
        for r in self.alert_rows:
            amount = float(r["Amount"])
            month, day, year = r["Date"].split("/")
            when = dt.datetime(int(year), int(month), int(day), 10, 0)
            who = r["Description"].split(" ", 2)[-1].title()
            body = (f"Synthetic Community Bank: account ending 0100, USD {abs(amount):,.2f} "
                    f"{'sent to' if amount < 0 else 'received from'} {who}.")
            m = Model(self, "Notification", False)
            m.f("ServiceIdentifier", "String", "test.synthcommunity.bank").f("Body", "String", body)
            m.t("TimeStamp", when)
            out.append(m.xml())
            self.count.fact("bank_alerts")
        return out

    def tagged_files(self, out: Path) -> str:
        parts = []
        for f in self.files:
            kind = f.get("kind", "Image")
            folder = out / "files" / kind
            folder.mkdir(parents=True, exist_ok=True)
            data = f.get("data") or _tiny_png(f["name"])
            (folder / f["name"]).write_bytes(data)
            t = f["time"]
            parts.append(
                f'    <file fs="Synthetic" fsid="0" path="/sdcard/DCIM/{f["name"]}" size="{len(data)}" id="{f["id"]}" '
                f'extractionId="0" deleted="Intact" embedded="false" isrelated="False">'
                f'<accessInfo><timestamp name="CreationTime">{ts(t)}</timestamp></accessInfo>'
                f'<metadata section="File"><item name="Local Path">{escape(f["path"])}</item>'
                f'<item name="SHA256">{hashlib.sha256(data).hexdigest()}</item>'
                f'<item name="MD5">{hashlib.md5(data).hexdigest()}</item><item name="Tags">{kind}</item></metadata>'
                f"</file>\n")
        return "".join(parts)


def _tiny_png(seed_text: str) -> bytes:
    """A valid 1x1 PNG whose colour depends on the name (distinct bytes, distinct hashes)."""
    import struct
    import zlib
    h = hashlib.sha256(seed_text.encode()).digest()
    raw = b"\x00" + h[:3]

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------------------------------------
# Case shapes


def phones_only_case(scale: float = 0.02) -> CaseSpec:
    """Three synthetic phones and no other evidence. C2 has no owner number and no zone."""
    people = invent_people(24, seed=11)
    ring = [p.key for p in people[1:16]]
    phones = [
        PhoneSpec("C1", like="P06", scale=scale, owner="p0", contacts=ring[:12], seed=101),
        PhoneSpec("C2", like="P09", scale=scale * 2, owner=None, zone=None, contacts=["p0"] + ring[4:14], seed=102,
                  extraction_date=dt.date(2024, 5, 9), gap=None),
        PhoneSpec("C3", like="P05", scale=scale, owner="p1", contacts=["p0"] + ring[8:15], seed=103,
                  extraction_date=dt.date(2024, 6, 1)),
    ]
    return CaseSpec("Phones-only check (synthetic)", people, phones, ledger=False, seed=11)


def training_case() -> CaseSpec:
    """Two synthetic phones that talk to each other, and a small synthetic ledger."""
    people = invent_people(14, seed=23)
    phones = [
        PhoneSpec("C5", like="P12", scale=0.08, owner="p0", contacts=[p.key for p in people[1:10]], seed=201,
                  bank_alerts=True),
        PhoneSpec("C6", like="P09", scale=0.05, owner="p1", contacts=["p0"] + [p.key for p in people[5:13]], seed=202,
                  extraction_date=dt.date(2024, 5, 10)),
    ]
    return CaseSpec("Phone training (synthetic)", people, phones, ledger=True, seed=23)


def write_ledger(case: CaseSpec, out: Path, phones_period: tuple[dt.datetime, dt.datetime]) -> dict:
    """A small bank statement as CSV: payments to and from some of the same invented people."""
    rng = random.Random(case.seed)
    start, end = phones_period
    payees = [p.name for p in case.people[2:7]] + ["Northcott Storage Ltd", "Synthetic Grocers"]
    rows, balance = [], 2500.00
    day = start.date()
    while day <= end.date():
        if rng.random() < 0.35:
            payee = rng.choice(payees)
            amount = round(rng.choice([-1, -1, -1, 1]) * rng.uniform(15, 900), 2)
            if balance + amount < 100:  # the account never goes overdrawn: an invented payment in instead
                amount = abs(amount)
            balance = round(balance + amount, 2)
            kind = "TRANSFER TO" if amount < 0 else "TRANSFER FROM"
            rows.append({"Date": day.strftime("%m/%d/%Y"), "Description": f"{kind} {payee.upper()}",
                         "Amount": f"{amount:.2f}", "Balance": f"{balance:.2f}"})
        day += dt.timedelta(days=1)
    path = out / "ledger" / "synthetic-statement.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["Date", "Description", "Amount", "Balance"])
        w.writeheader()
        w.writerows(rows)
    # One single-page PDF statement per calendar month, the shape Financial's intake reads (item I).
    pdfs, opening = [], 2500.00
    months = sorted({(dt.datetime.strptime(r["Date"], "%m/%d/%Y").year, dt.datetime.strptime(r["Date"], "%m/%d/%Y").month) for r in rows})
    for year, month in months:
        first = dt.date(year, month, 1)
        last = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1))
        month_rows = [r for r in rows if r["Date"].startswith(f"{month:02d}/") and r["Date"].endswith(str(year))]
        pdf = out / "ledger" / "statements" / f"statement-{year}-{month:02d}.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        write_statement_pdf(month_rows, pdf, opening=opening, start=first, end=last)
        opening = float(month_rows[-1]["Balance"])
        pdfs.append(str(pdf.relative_to(out)))
    return {"file": str(path.relative_to(out)), "pdfs": pdfs, "rows": len(rows), "payees_on_phones": payees[:5]}


def _pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_statement_pdf(rows: list[dict], path: Path, *, opening: float, start: dt.date, end: dt.date,
                        per_page: int = 34) -> None:
    """The same ledger as a text-layer PDF bank statement, so the training case's ledger goes through Loupe's real
    Financial intake (Evidence upload, statement detection, statement reading). Stdlib only and deterministic:
    no creation date, fixed fonts. Every name and number in it is invented (SYNTHETIC_MARK is printed)."""
    closing = float(rows[-1]["Balance"]) if rows else opening

    def right(edge: float, text: str, size: int = 9) -> float:  # right-align digits (Helvetica digits are 0.556 em)
        return round(edge - sum(0.278 if c in ".," else 0.556 for c in text) * size, 3)

    head = [
        (25, 810, 14, "BANK STATEMENT"),
        (25, 793, 8, f"{SYNTHETIC_MARK}. No real customer or payment."),
        (25, 775, 10, "Account Name: EMRYS JUNIPER"),
        (25, 757, 10, "Account Number: 000555010/0100"),
        (25, 739, 10, "Bank: Synthetic Community Bank"),
        (25, 721, 10, f"Statement Period: {start:%Y-%m-%d} - {end:%Y-%m-%d}"),
        (25, 703, 10, "Currency: USD"),
    ]
    body = [(dict(date=start.strftime("%Y-%m-%d"), desc="Opening Balance", credit="", debit="", balance=f"{opening:.2f}"))]
    for r in rows:
        amount = float(r["Amount"])
        month, day, year = r["Date"].split("/")
        body.append(dict(date=f"{year}-{month}-{day}", desc=r["Description"].title()[:40],
                         credit=f"{amount:.2f}" if amount > 0 else "", debit=f"{-amount:.2f}" if amount < 0 else "",
                         balance=f"{float(r['Balance']):.2f}"))
    body.append(dict(date=end.strftime("%Y-%m-%d"), desc="Closing Balance", credit="", debit="", balance=f"{closing:.2f}"))
    pages = []
    if len(body) > 26:
        raise ValueError("a statement page holds 24 payments; split by month")
    parts = [body]
    for n, part in enumerate(parts):
        lines = list(head) if n == 0 else []
        y = 660 if n == 0 else 800
        lines += [(31, y, 9, "Date"), (113, y, 9, "Description"), (391, y, 9, "Credit"), (464, y, 9, "Debit"), (537, y, 9, "Balance")]
        y -= 26
        for row in part:
            lines += [(31, y, 9, row["date"]), (113, y, 9, row["desc"])]
            if row["credit"]:
                lines.append((right(452, row["credit"]), y, 9, row["credit"]))
            if row["debit"]:
                lines.append((right(525, row["debit"]), y, 9, row["debit"]))
            lines.append((right(598, row["balance"]), y, 9, row["balance"]))
            y -= 20
        stream = "\n".join(f"BT /F1 {size} Tf 1 0 0 1 {x} {yy} Tm ({_pdf_text(text)}) Tj ET" for x, yy, size, text in lines)
        pages.append(stream.encode("latin-1"))
    objects: list[bytes] = []
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for i, stream in enumerate(pages):
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 623 842] /Resources << /Font << /F1 3 0 R >> >> "
                       f"/Contents {5 + 2 * i} 0 R >>".encode())
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects):
        offsets.append(len(data))
        data += f"{i + 1} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    data += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    data += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(data))


def build_case(case: CaseSpec, out: Path) -> dict:
    catalogue = load_catalogue()
    people = {p.key: p for p in case.people}
    manifest = {"case": case.name, "synthetic": SYNTHETIC_MARK, "phones": [], "ledger": None}
    ui = {"case": case.name, "synthetic": True,
          "people": [{"key": p.key, "name": p.name, "numbers": p.numbers, "email": p.email} for p in case.people],
          "phones": [], "threads": [], "messages": [], "calls": []}
    builds = [PhoneBuild(spec, people, catalogue) for spec in case.phones]
    periods = [(b.start, b.end) for b in builds]
    if case.ledger:
        # the ledger first (its own seed; the phones' periods only), so a phone can carry alerts for its payments
        manifest["ledger"] = write_ledger(case, out, (min(p[0] for p in periods), max(p[1] for p in periods)))
        with open(out / manifest["ledger"]["file"], newline="") as fh:
            rows = list(csv.DictReader(fh))
        for b in builds:
            if b.spec.bank_alerts:
                inside = [r for r in rows if b.start.date() <= dt.datetime.strptime(r["Date"], "%m/%d/%Y").date()
                          < b.end.date()]
                b.alert_rows = inside[::4]
    for spec, b in zip(case.phones, builds):
        info = b.write(out / spec.label)
        manifest["phones"].append(info)
        ui["phones"].append({k: info[k] for k in ("label", "owner", "zone", "extraction_date", "period_start",
                                                  "period_end", "no_data_days")}
                            | {"messages": info["facts"].get("messages", 0), "calls": len(b.ui_calls),
                               "contacts": info["top_level"].get("Contact", 0), "files": info["files"],
                               "records": info["top_level_total"]})
        ui["threads"] += b.ui_threads
        ui["messages"] += b.ui_messages
        ui["calls"] += b.ui_calls
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    (out / "ui-fixture.json").write_text(json.dumps(ui, indent=1, ensure_ascii=False))
    return manifest


# -- intake forms (01 unit 1.2): zip, split sections, UFDR and protected single-file reports ------------------
# These rewrap a report folder; they invent nothing. Given a synthetic folder from this module the result is
# synthetic; given a server folder (corpus acceptance runs only, written under /mnt/owl-data/cellebrite-corpus)
# it is labelled synthetic as a form, and never committed.

PROTECTED_MAGIC = bytes.fromhex("2D06526D")


def _report_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.name != "owl_ingest_report.json")


def zip_folder(folder: Path, out: Path, *, wrapper: str | None = "", mac_extras: bool = True,
               compress: bool = True) -> dict:
    """A zip of a report folder as a Mac makes one: one wrapping folder, ``__MACOSX/`` AppleDouble copies of
    every entry and a ``.DS_Store``. Returns entry counts."""
    import zipfile
    folder = Path(folder)
    wrapper = folder.name if wrapper == "" else wrapper
    files = _report_files(folder)
    counts = {"files": 0, "macosx": 0, "ds_store": 0}
    mode = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(out, "w", mode, allowZip64=True) as zf:
        for f in files:
            rel = f.relative_to(folder).as_posix()
            name = f"{wrapper}/{rel}" if wrapper else rel
            zf.write(f, name)
            counts["files"] += 1
            if mac_extras:
                parent, _, base = name.rpartition("/")
                zf.writestr(f"__MACOSX/{parent + '/' if parent else ''}._{base}", b"\x00\x05\x16\x07" + b"\x00" * 78)
                counts["macosx"] += 1
        if mac_extras:
            zf.writestr(f"{wrapper + '/' if wrapper else ''}.DS_Store", b"\x00\x00\x00\x01Bud1" + b"\x00" * 24)
            counts["ds_store"] += 1
    return counts


def _find(fh, needle: bytes, start: int = 0) -> int:
    """Byte offset of the first ``needle`` at or after ``start``, streaming."""
    fh.seek(start)
    pos, tail = start, b""
    while True:
        b = fh.read(1 << 20)
        if not b:
            return -1
        buf = tail + b
        i = buf.find(needle)
        if i >= 0:
            return pos - len(tail) + i
        tail = buf[-(len(needle) - 1):] if len(needle) > 1 else b""
        pos += len(b)


def _copy_range(src, dst, start: int, end: int) -> None:
    src.seek(start)
    left = end - start
    while left > 0:
        b = src.read(min(1 << 20, left))
        if not b:
            break
        dst.write(b)
        left -= len(b)


def split_sections(report: Path, out_dir: Path, stem: str = "Synthetic_Report", *,
                   truncate_tagged_fraction: float | None = None) -> dict:
    """Split a full report into the C8 shape (01 section 1.1): ``.xmlModel`` holds ``decodedData`` with no
    declaration and no namespace; ``.xmlTagged`` holds the rest under ``project``; six empty siblings. With
    ``truncate_tagged_fraction`` the tagged section is cut at that fraction of its bytes (inside the tagged
    files when the fraction is small enough), as C8's was."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(report, "rb") as fh:
        a = _find(fh, b"<decodedData")
        b = _find(fh, b"</decodedData>", a)
        if a < 0 or b < 0:
            raise ValueError("no decodedData section")
        b += len(b"</decodedData>")
        size = fh.seek(0, 2)
        with open(out_dir / f"{stem}.xmlModel", "wb") as m:
            _copy_range(fh, m, a, b)
        tagged = out_dir / f"{stem}.xmlTagged"
        with open(tagged, "wb") as t:
            _copy_range(fh, t, 0, a)
            _copy_range(fh, t, b, size)
    if truncate_tagged_fraction is not None:
        n = tagged.stat().st_size
        with open(tagged, "r+b") as t:
            t.truncate(int(n * truncate_tagged_fraction))
    for suffix in ("xmlExtra", "xmlLast", "xmlMdfSource", "xmlModelSource", "xmlNodeSource", "xmlTranslation"):
        (out_dir / f"{stem}.{suffix}").write_bytes(b"")
    return {"model": (out_dir / f"{stem}.xmlModel").stat().st_size, "tagged": tagged.stat().st_size, "empty": 6}


def ufdr_from_folder(folder: Path, out: Path) -> dict:
    """A readable UFDR: a zip whose root holds ``report.xml`` and the report folder's files."""
    import zipfile
    folder = Path(folder)
    files = _report_files(folder)
    full = [f for f in files if f.parent == folder and f.suffix.lower() == ".xml"]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for f in files:
            name = "report.xml" if full and f == full[0] else f.relative_to(folder).as_posix()
            zf.write(f, name)
    return {"files": len(files)}


def protected_ufdr(out: Path, kind: str, seed: int = 7) -> None:
    """A protected single-file report, with invented bytes. ``kind``:

    - ``magic``: ``report.xml`` starts ``2D 06 52 6D`` (``protected_no_password``);
    - ``encrypted``: the entry's encryption flag is set (``protected_password``);
    - ``no_header``: random bytes with none of the header strings, the shape of both real protected UFDRs
      measured (they start ``24 65 2E 01`` and ``2E 0F C8 E8``; 01 section 2.1 note) (``protected_or_invalid``).
    """
    import zipfile
    rng = random.Random(seed)
    body = bytes(rng.randrange(256) for _ in range(4096))
    if kind == "magic":
        body = PROTECTED_MAGIC + body
    elif kind == "no_header":
        body = bytes.fromhex("24652E01") + body
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("report.xml", body)
        zf.writestr("files/Image/a.bin", bytes(rng.randrange(256) for _ in range(64)))
    if kind == "encrypted":  # zipfile cannot write encrypted entries: set the flag bit in both headers
        data = bytearray(out.read_bytes())
        assert data[:4] == b"PK\x03\x04"
        data[6] |= 0x1
        cd = data.find(b"PK\x01\x02")
        assert data[cd + 46:cd + 56] == b"report.xml"
        data[cd + 8] |= 0x1
        out.write_bytes(bytes(data))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("shape", choices=["phones-only", "training", "phone", "c1-later"])
    ap.add_argument("out", type=Path)
    ap.add_argument("--scale", type=float, default=0.02)
    ap.add_argument("--like", default="P06")
    ap.add_argument("--label", default="S1")
    ap.add_argument("--typed", action="append", default=[],
                    help="MODEL_TYPE:FIELD:TEXT, an extra invented typed or searched value (phone shape only)")
    a = ap.parse_args(argv)
    if a.shape == "phones-only":
        case = phones_only_case(a.scale)
    elif a.shape == "c1-later":  # a newer report of the phones-only C1: the same records and 3 later messages
        case = phones_only_case(a.scale)
        c1 = case.phones[0]
        c1.later_days, c1.later_messages = 10, 3
        case.phones = [c1]
    elif a.shape == "training":
        case = training_case()
    else:
        people = invent_people(40, seed=31)
        case = CaseSpec(f"Synthetic {a.like} at scale {a.scale}", people,
                        [PhoneSpec(a.label, like=a.like, scale=a.scale, contacts=[p.key for p in people[1:]], seed=301,
                                   typed_values=tuple(tuple(t.split(":", 2)) for t in a.typed))])
    m = build_case(case, a.out)
    print(json.dumps({"case": m["case"], "phones": [{"label": p["label"], "top_level_total": p["top_level_total"],
                                                      "messages": p["facts"].get("messages", 0)} for p in m["phones"]],
                      "ledger_rows": (m["ledger"] or {}).get("rows")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

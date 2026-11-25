"""Readings as plain sentences about what the phone did (Phones › Set up, screen 6).

A reading's stored ``summary`` names the report's types and fields ("In each instant message, the party marked from
is the sender."). The person checking it reads instead one sentence about what the phone did and how Loupe reads
it, and one sentence on what changes if that is wrong. Both are written here from the reading's own mapping data
(``phone_mapping_judgements.rule_part``, ``rule_id`` and ``evidence``), never from a model, and contain no type or
field name as the report spells it (tests/test_phone_reading_words.py checks every part against the catalogue).
"""
from __future__ import annotations

import re

# type -> (one, many, what the phone did). A type not listed reads as "records of one kind".
NOUNS = {
    "InstantMessage": ("message", "messages", "sent or received a message"),
    "Chat": ("chat", "chats", "took part in a chat"),
    "ChatActivity": ("chat event", "chat events", "recorded something happening in a chat"),
    "ForwardedMessageData": ("forwarded message", "forwarded messages", "forwarded a message"),
    "Call": ("call", "calls", "made or took a call"),
    "Voicemail": ("voicemail", "voicemails", "held a voicemail"),
    "Email": ("email", "emails", "sent or received an email"),
    "Contact": ("contact", "contacts", "held a contact"),
    "Party": ("person named on a record", "people named on records", "named a person on a record"),
    "Location": ("place", "places", "recorded a place"),
    "Journey": ("journey", "journeys", "recorded a journey"),
    "CellTower": ("mobile mast", "mobile masts", "recorded a mobile mast"),
    "WirelessNetwork": ("WiFi network", "WiFi networks", "saw or joined a WiFi network"),
    "DeviceConnectivity": ("connection to another device", "connections to other devices",
                           "connected to another device"),
    "NetworkUsage": ("period of data use", "periods of data use", "used mobile data or WiFi"),
    "DeviceEvent": ("change on the phone", "changes on the phone", "changed a setting or state"),
    "PoweringEvent": ("switch on or off", "switches on or off", "was switched on or off"),
    "ActivitySensorDataSample": ("movement count", "movement counts", "counted the owner's movement"),
    "ActivitySensorData": ("movement summary", "movement summaries", "summed up the owner's movement"),
    "AppsUsageLog": ("app use", "app uses", "had an app in use"),
    "ApplicationUsage": ("app use summary", "app use summaries", "summed up how an app was used"),
    "InstalledApplication": ("installed app", "installed apps", "installed or held an app"),
    "Notification": ("notification", "notifications", "showed a notification"),
    "VisitedPage": ("web page visit", "web page visits", "visited a web page"),
    "WebBookmark": ("bookmark", "bookmarks", "saved a bookmark"),
    "Cookie": ("website cookie", "website cookies", "stored a website cookie"),
    "SearchedItem": ("search", "searches", "searched for something"),
    "Autofill": ("saved form entry", "saved form entries", "saved something typed into a form"),
    "Password": ("saved password", "saved passwords", "saved a password"),
    "UserAccount": ("account", "accounts", "held an account"),
    "User": ("user of the phone", "users of the phone", "listed a user"),
    "RemoteServiceSession": ("session on another device", "sessions on other devices",
                             "had an account session on another device"),
    "SocialMediaActivity": ("social media post", "social media posts", "posted on social media"),
    "CalendarEntry": ("calendar entry", "calendar entries", "held a calendar entry"),
    "Note": ("note", "notes", "held a note"),
    "Recording": ("recording", "recordings", "made a recording"),
    "FileUpload": ("upload", "uploads", "uploaded a file"),
    "FileDownload": ("download", "downloads", "downloaded a file"),
    "LogEntry": ("system log line", "system log lines", "wrote a line to its system log"),
    "MobileCard": ("SIM card", "SIM cards", "held a SIM card"),
    "CreditCard": ("saved payment card", "saved payment cards", "saved a payment card"),
    "DeviceInfoEntry": ("detail about the phone", "details about the phone", "listed a detail about itself"),
}
OTHER = ("record of one kind", "records of one kind", "recorded something")

# report field -> plain words, for the fields readings name (event time, end time, text, time meanings).
FIELDS = {
    "AdditionalInfo": "extra details", "Body": "text", "Creation": "creation time", "CreationTime": "creation time",
    "DateCreated": "creation date", "DateDeleted": "deletion date", "DateDelivered": "delivery time",
    "DateEnded": "end time", "DateLastModified": "last change", "DateLastUsed": "last use", "DateModified": "last change",
    "DatePlayed": "time played", "DateRead": "time read", "DateSampled": "time of the count",
    "DateStarted": "start time", "DeletedDate": "deletion date", "Description": "description", "Details": "details",
    "DeviceName": "device name", "Duration": "length", "EndDate": "end date", "EndTime": "end time",
    "ExpirationDate": "expiry date", "Expiry": "expiry date", "From": "sender", "InstallDate": "install date",
    "LastAccessed": "last use", "LastAccessTime": "last use", "LastActivity": "last activity",
    "LastAutoConnection": "last automatic connection", "LastConnection": "last connection", "LastLaunch": "last opening",
    "LastModified": "last change", "LastUsedDate": "last use", "LastVisited": "last visit",
    "Modification": "last change", "ModifyTime": "last change", "Name": "name", "Notes": "notes",
    "PurchaseDate": "purchase date", "PurchaseTime": "purchase time", "Reminders": "reminder time",
    "RepeatUntil": "last repeat", "SearchResults": "search results", "Snippet": "preview text",
    "SSId": "network name", "StartDate": "start date", "StartTime": "start time", "Subject": "subject",
    "Summary": "summary", "SystemMessageBody": "system message", "SystemMessageTimeStamp": "system message time",
    "TimeCreated": "creation time", "TimeLastLoggedIn": "last sign-in", "TimeModified": "last change",
    "Timestamp": "time", "TimeStamp": "time", "Title": "title", "To": "recipient", "Url": "web address",
    "Value": "value",
}

ROLE_KEY = {"From": "the from line", "To": "the to line", "Cc": "the copy line", "Bcc": "the blind copy line"}
ROLE = {"sender": "the person who sent it", "recipient": "a person it was sent to",
        "caller": "the person who made the call", "callee": "the person who was called",
        "cc": "a person copied in", "bcc": "a person copied in without the others knowing",
        "unknown": "a person whose side is not known"}
KIND = {"message": "a message in a conversation", "call": "a call", "email": "an email", "voicemail": "a voicemail",
        "chat_activity": "something that happened in a chat", "thread": "a conversation of its own",
        "record": "a record of its own kind, outside the conversations"}
CLASS = {"interaction": "someone using the phone", "device_state": "a change in the phone's state",
         "passive": "recorded without anyone using the phone", "unknown": "not settled either way"}
ACTOR = {"owner": "the owner", "counterpart": "the other person", "other_device": "another device",
         "account": "the account", "unknown": None}
FLAG = {"synced_from_account": "it may have come from the account on another device",
        "affiliation_unknown": "the report does not say whether this phone recorded it",
        "other_device_platform": "it was sent from a web or computer session, not the phone",
        "account_level": "it was recorded on the account and the device that did it is not shown",
        "user_mapping_other": "it is linked to a different user or source",
        "wearable": "it was recorded by a paired watch or band",
        "deleted_record": "it was recovered after being deleted",
        "deleted_state_unknown": "it is not known whether it was deleted"}

# what a person loses if the reading is wrong, per part
IF_WRONG = {
    "event_time": "If this is wrong, these records sit at the wrong time on the timeline and in every check of when "
                  "the phone was in use.",
    "meaning": "If this is wrong, these records sit at the wrong time on the timeline and in every check of when "
               "the phone was in use.",
    "end_time": "If this is wrong, how long each one lasted is wrong, and so is every check of what overlapped it.",
    "role": "If this is wrong, the wrong person shows as sending or receiving, in the conversations, the contact "
            "counts and every check of who talked to whom.",
    "owner_implicit": "If this is wrong, the owner shows as sending what they received, or the reverse.",
    "text": "If this is wrong, search misses words in these records, or shows words that are not part of them.",
    "thread": "If this is wrong, these records sit in the wrong conversation, and the conversation lists and counts "
              "are wrong.",
    "record": "If this is wrong, these records are counted as the wrong kind: in the conversations, the call lists "
              "or on their own.",
    "activity": "If this is wrong, these records count, or fail to count, as signs that someone was using the "
                "phone, in the daily pattern and every check of who held it.",
    "attribution": "If this is wrong, these records show as done on this phone when they may come from elsewhere, "
                   "or the reverse.",
}
UNTIMED = {"scheduled", "expiry", "duration", "aggregate_bucket", "unknown", "counterpart_action"}

CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def nouns(type_name):
    return NOUNS.get(type_name, OTHER)


def field_words(name):
    return FIELDS.get(name) or "one of the report's times"


def value_words(v):
    """A value as the report gives it, quoted; a run-together value is split into words."""
    s = str(v)
    if CAMEL.search(s) and " " not in s:
        s = CAMEL.sub(" ", s).lower()
    return "“%s”" % s


def _either(values):
    vs = [value_words(v) for v in (values if isinstance(values, list) else [values])]
    return vs[0] if len(vs) == 1 else ", ".join(vs[:-1]) + " or " + vs[-1]


def _cond(p):
    """One condition of a mapping row as a clause after "that" ("are incoming"), or None when it adds nothing."""
    f, op, v = p.get("field") or p.get("name"), p.get("op"), p.get("value")
    lv = str(v).lower() if isinstance(v, str) else v
    if f in ("direction", "Direction") and op == "eq":
        return {"incoming": "came in", "outgoing": "went out"}.get(lv, "have no direction recorded")
    if f == "party_is_owner":
        return "name the owner" if lv in (True, "true") else "do not name the owner"
    if op == "absent":
        return {"Platform": "have no platform recorded", "EndTime": "have no end time",
                "Status": "have no status", "Folder": "have no folder", "Action": "have no action recorded",
                "DeviceLocationAffiliation": "do not say where they came from"}.get(f, "leave one field empty")
    if f == "Platform":
        return "were made on a platform marked %s" % _either(v)
    if f == "UsageMode":
        return "ran in the %s" % str(v).lower()
    if f == "EventType":
        return "are of the kind %s" % _either(v)
    if f == "ConnectivityNature":
        return "are marked %s" % _either(v)
    if f == "DeviceLocationAffiliation":
        return {"Synced": "are marked as synced", "Unknown": "do not say where they came from"}.get(
            v, "are marked %s" % _either(v))
    if f == "Folder":
        if op == "contains_any":
            return "sit in a drafts folder"
        return "sit in the folder %s" % _either(v)
    if f == "Source":
        return "come from %s" % _either(v)
    if f == "Action":
        return {"Launch": "record an app being opened", "Close": "record an app being closed"}.get(
            v, "record the action %s" % _either(v))
    if f == "ActiveTime" and op == "gt":
        return "show the app in use for some time"
    if op == "gt":
        return "have a value above %s" % v
    return "are marked %s" % _either(v)


def _that(row):
    conds = [c for c in (_cond(p) for p in (row.get("predicates") or []) + (row.get("context") or [])) if c]
    if not conds:
        return ""
    return " that " + (conds[0] if len(conds) == 1 else ", ".join(conds[:-1]) + " and " + conds[-1])


def _lead(label, type_name, row):
    """"When C1 sent or received a message" or "For C1's messages that came in"."""
    one, many, did = nouns(type_name)
    that = _that(row or {})
    return ("For %s’s %s%s" % (label, many, that)) if that else ("When %s %s" % (label, did))


def _low(s):
    s = (s or "").strip().rstrip(".")
    return s[:1].lower() + s[1:] if s[:2] != s[:2].upper() or len(s) < 2 else s


def plain(label, part, type_name, rule_id, evidence, meaning_of=None) -> dict:
    """``{"sentence", "if_wrong"}`` for one reading. ``meaning_of``: ``{field: meaning}`` for this phone and type,
    so an event-time reading says what its time means rather than naming the field."""
    ev = evidence or {}
    row = ev.get("row") or {}
    choice = ev.get("choice")
    one, many, did = nouns(type_name)
    fields = [f.get("field") for f in (ev.get("fields") or []) if isinstance(f, dict)]
    if part == "event_time":
        m = (meaning_of or {}).get(choice) if isinstance(choice, str) else None
        what = _low(m) if m else "its %s as the report gives it" % field_words(choice)
        s = "%s, the time Loupe puts on the timeline is %s." % (_lead(label, type_name, None), what)
    elif part == "meaning":
        o = row.get("outputs") or {}
        f = fields[0] if fields else None
        lead = _lead(label, type_name, row)
        what = _low(o.get("meaning")) or "not settled"
        if o.get("semantics") in UNTIMED:
            s = "%s, the %s on the record means: %s." % (lead, field_words(f), what)
        else:
            s = "%s, the %s on the record is %s." % (lead, field_words(f), what)
    elif part == "end_time":
        c = choice if isinstance(choice, dict) else {}
        if c.get("field"):
            s = "Each of %s’s %s ends at its %s as the report gives it." % (label, many, field_words(c["field"]))
        else:
            s = "Each of %s’s %s ends at its start plus the length the report gives." % (label, many)
    elif part == "role":
        key = (rule_id or "").rsplit(".role.", 1)[-1]
        s = "In %s’s %s, the person on %s is %s." % (label, many, ROLE_KEY.get(key, "one of the report's lines"),
                                                    ROLE.get(choice, "a person in the conversation"))
    elif part == "owner_implicit":
        side = ("the person who made an outgoing call and the person called on an incoming one" if one == "call"
                else "the sender of an outgoing %s and a recipient of an incoming one" % one)
        s = "When one of %s’s %s does not say which person is the owner, Loupe takes the owner to be %s." % (
            label, many, side)
    elif part == "text":
        cs = choice if isinstance(choice, list) else []
        named = [FIELDS[c] for c in cs if c in FIELDS]
        rest = len(cs) - len(named)
        if rest:
            named.append("%d more of the report's fields" % rest if rest > 1 else "one more of the report's fields")
        src = named[0] if len(named) == 1 else ", ".join(named[:-1]) + " and " + named[-1] if named else \
            "the report's own fields"
        s = "The words Loupe shows and searches for each of %s’s %s are its %s." % (label, many, src)
    elif part == "thread":
        c = choice if isinstance(choice, dict) else {}
        how = {"parent_chat": "the chat it sits in" + (", or by who else is in it when it is in no chat"
                                                       if c.get("fallback") == "counterpart_set" else ""),
               "counterpart_set": "who else is in it and the app it came through",
               "field": "its folder and its subject, ignoring reply and forward marks",
               "self": "putting them all in one list for the phone"}.get(c.get("strategy"), "the report's own grouping")
        s = "Loupe groups %s’s %s into conversations by %s." % (label, many, how)
    elif part == "record":
        s = "Loupe reads each of %s’s %s as %s." % (label, many, KIND.get(choice, KIND["record"]))
    elif part == "activity":
        o = row.get("outputs") or {}
        lead = _lead(label, type_name, row)
        it = "each one" if lead.startswith("For ") else "it"
        cls, actor = o.get("class"), o.get("actor")
        if cls == "interaction":
            what = {"owner": "the owner using the phone", "counterpart": "the other person acting, not the owner",
                    "other_device": "someone using another device", "account": "someone using the account"}.get(
                actor, "someone using the phone")
        elif cls == "device_state":
            what = "a change in the phone's state" + (", made by the owner" if actor == "owner" else "")
        elif cls == "passive":
            what = "recorded without anyone using the phone"
        else:
            what = None
        moved = ", with the phone moving" if o.get("physical") else ""
        s = ("%s, Loupe counts %s as %s%s." % (lead, it, what, moved)) if what else (
            "%s, Loupe does not count %s either way as a sign of someone using the phone." % (lead, it))
    elif part == "attribution":
        o = row.get("outputs") or {}
        s = "%s, Loupe marks that %s." % (_lead(label, type_name, row), FLAG.get(o.get("flag"),
                                                                              "it may not come from this phone"))
        if s.startswith("For "):
            s = s.replace(", Loupe marks that it ", ", Loupe marks that each one ", 1)
    else:
        s = "Loupe reads %s’s %s in one way that no person has checked yet." % (label, many)
    return {"sentence": s[:1].upper() + s[1:], "if_wrong": IF_WRONG.get(part, IF_WRONG["record"])}


def meanings(conn, extraction_ids) -> dict:
    """``{(extraction_id, type, field): meaning}`` from the time-meaning readings without conditions."""
    from sqlalchemy import text
    ids = [str(e) for e in extraction_ids]
    if not ids:
        return {}
    out = {}
    for e, t, ev in conn.execute(text(
            "SELECT j.extraction_id, j.type_name, j.evidence FROM phone_mapping_judgements j JOIN "
            "phone_interpretation_state s ON s.extraction_id = j.extraction_id AND s.generation = j.generation "
            "WHERE j.extraction_id = ANY(CAST(:e AS uuid[])) AND j.rule_part = 'meaning' ORDER BY j.records_touched"),
            {"e": ids}):
        row = (ev or {}).get("row") or {}
        if row.get("predicates") or row.get("context"):
            continue
        f = ((ev or {}).get("fields") or [{}])[0].get("field")
        m = (row.get("outputs") or {}).get("meaning")
        if f and m:
            out[(str(e), t, f)] = m
    return out


def for_row(label, r, means=None) -> dict:
    """``plain`` for a judgement row with extraction_id, rule_part, type_name, rule_id and evidence."""
    m = {f: v for (e, t, f), v in (means or {}).items() if e == str(r.extraction_id) and t == r.type_name}
    return plain(label, r.rule_part, r.type_name, r.rule_id, r.evidence, m)

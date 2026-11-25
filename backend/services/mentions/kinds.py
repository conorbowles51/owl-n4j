"""The kinds of checkable mention Loupe picks out of messages, in the words the screen uses, and how each is checked.

The order is the order of the screen's table. ``HOW`` is the strip "How each kind of mention is checked"; each line
says only what ``services.mentions.checks`` actually reads for that kind.
"""
from __future__ import annotations

KINDS = ("travel", "meeting", "at_place", "home_away", "plan", "money", "sent", "deleted")

LABELS = {
    "travel": "Travel",
    "meeting": "Meeting someone",
    "at_place": "Being at a place",
    "home_away": "Home, asleep, away",
    "plan": "Plans and times",
    "money": "Money",
    "sent": "Sent or handed over",
    "deleted": "Deleted",
}

HOW = [
    {"kind": "travel", "label": "Travel",
     "how": "the phone's places on the way and at the far end, distance from its usual night-time place, photos' "
            "places, and payments in the window that name the place"},
    {"kind": "meeting", "label": "Meeting someone",
     "how": "both people's phones near each other at the time, and calls or messages between them just before"},
    {"kind": "at_place", "label": "Being at a place",
     "how": "the phone's places in the window against the place, when the place is on the map, and payments there"},
    {"kind": "home_away", "label": "Home, asleep, away",
     "how": "the phone's places against its usual night-time place, and whether the phone was in use"},
    {"kind": "plan", "label": "Plans and times",
     "how": "whether what was planned shows up at the planned time: the people together, a payment, a message"},
    {"kind": "money", "label": "Money",
     "how": "the ledger and statements, and bank alerts on the phones, for the amount or the words in the window"},
    {"kind": "sent", "label": "Sent or handed over",
     "how": "the message, e-mail or payment itself on any phone or in the case's records"},
    {"kind": "deleted", "label": "Deleted",
     "how": "whether a phone in the case still holds the thing, or holds it marked deleted"},
]

# Outcomes, computed by rules only (services.mentions.checks.outcome). "Against" in the table counts both contradicts.
OUTCOMES = ("contradicts", "contradicts_weakly", "fits_strongly", "fits_weakly", "cant_tell")
OUTCOME_LABELS = {
    "fits_strongly": "Fits, fairly strongly",
    "fits_weakly": "Fits weakly",
    "contradicts": "Contradicts",
    "contradicts_weakly": "Contradicts weakly",
    "cant_tell": "Can't tell",
}
TABLE_COLUMN = {"fits_strongly": "fits", "fits_weakly": "fits", "contradicts": "against",
                "contradicts_weakly": "against", "cant_tell": "unknown"}

SOURCES = {"places": "Places", "financial": "Financial", "device": "Device", "photos": "Photos",
           "other_phones": "Other phones", "messages": "Messages", "documents": "Documents"}
VERDICTS = ("fits", "fits_weakly", "contradicts", "contradicts_weakly", "context", "nothing")
VERDICT_LABELS = {"fits": "Fits", "fits_weakly": "Fits weakly", "contradicts": "Contradicts",
                  "contradicts_weakly": "Contradicts weakly", "context": "Context", "nothing": "Nothing found"}

READ_BY = "Read by Loupe · not confirmed"

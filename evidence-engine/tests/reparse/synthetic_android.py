"""A synthetic Android file-system tree for re-parse tests: an SMS database and a call log at their usual paths.

Every value is invented. Times are milliseconds since 1970 (UTC), as Android stores them."""
from __future__ import annotations

import os
import sqlite3

SMS_PATH = "data/data/com.android.providers.telephony/databases/mmssms.db"
CALLS_PATH = "data/data/com.android.providers.contacts/databases/calllog.db"

# (id, thread, address, date ms, type 1 received / 2 sent, body)
SMS = [
    (1, 1, "+12025550143", 1678820832000, 1, "synthetic one"),
    (2, 1, "+12025550143", 1678821000000, 2, "synthetic two"),
    (3, 2, "+12025550188", 1678900000000, 1, "synthetic three"),
]
# (date ms, number, type 1 incoming / 2 outgoing / 3 missed, duration s)
CALLS = [
    (1678820000000, "+12025550143", 2, 61),
    (1678830000000, "+12025550188", 3, 0),
]


def build(root: str) -> dict:
    """Write the tree under ``root``; returns {original path: local path}."""
    out = {}
    p = os.path.join(root, SMS_PATH)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE sms (_id INTEGER PRIMARY KEY, thread_id INTEGER, address TEXT, person INTEGER, date INTEGER,"
              " date_sent INTEGER, protocol INTEGER, read INTEGER, status INTEGER, type INTEGER, body TEXT,"
              " service_center TEXT, locked INTEGER, error_code INTEGER, seen INTEGER)")
    c.executemany("INSERT INTO sms (_id, thread_id, address, person, date, date_sent, read, type, body, service_center, "
                  "error_code) VALUES (?, ?, ?, NULL, ?, ?, 1, ?, ?, NULL, 0)",
                  [(i, t, a, d, d - 2000, ty, b) for i, t, a, d, ty, b in SMS])
    c.commit()
    c.close()
    out["/" + SMS_PATH] = p
    p = os.path.join(root, CALLS_PATH)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE calls (_id INTEGER PRIMARY KEY, number TEXT, date INTEGER, duration INTEGER, type INTEGER,"
              " name TEXT, countryiso TEXT, geocoded_location TEXT, phone_account_address TEXT, _data TEXT,"
              " mime_type TEXT, transcription TEXT, deleted INTEGER, subscription_id TEXT,"
              " subscription_component_name TEXT)")
    c.executemany("INSERT INTO calls (number, date, duration, type, countryiso, deleted) VALUES (?, ?, ?, ?, 'US', 0)",
                  [(n, d, du, ty) for d, n, ty, du in CALLS])
    c.commit()
    c.close()
    out["/" + CALLS_PATH] = p
    return out

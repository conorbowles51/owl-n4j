"""The Significant layer on phone screens (07 section 7.2 XF-11, 7.3): a toggle, never a silent narrowing.

Significant holds graph keys. A phone identity counts when its own node ``phone-identity:<key>`` is in the case's
manifest, or when it is linked to a person whose entity is. ``summary`` gives the sentence's two counts; both come
from the same set the filter narrows by, so the sentence and the list agree.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import text

PREFIX = "phone-identity:"


def identity_keys(conn, case_id) -> list:
    """The case's identity keys the Significant manifest covers, sorted."""
    return sorted(r[0] for r in conn.execute(text(
        "SELECT i.identity_key FROM phone_identities i WHERE i.case_id = CAST(:c AS uuid) AND EXISTS (SELECT 1 FROM "
        "significant_entities s WHERE s.case_id = i.case_id AND s.removed_at IS NULL AND s.entity_key = CAST(:p AS text) "
        "|| i.identity_key) "
        "UNION SELECT i.identity_key FROM phone_identities i JOIN phone_identity_links l ON l.identity_id = i.id "
        "JOIN case_profiles p ON p.id = l.dossier_id JOIN significant_entities s ON s.case_id = i.case_id AND "
        "s.removed_at IS NULL AND s.entity_key = p.canonical_entity_key WHERE i.case_id = CAST(:c AS uuid)"), {"c": case_id, "p": PREFIX}))


def manifest_mark(conn, case_id) -> str:
    """Changes when the manifest does, so a window asked for under an older manifest is refused (03 D-3)."""
    r = conn.execute(text(
        "SELECT count(*), max(updated_at) FROM significant_entities WHERE case_id = CAST(:c AS uuid) AND "
                      "removed_at IS NULL"), {"c": case_id}).one()
    return hashlib.sha256(("%s|%s" % (r[0], r[1])).encode()).hexdigest()[:16]


def summary(conn, case_id) -> dict:
    total = conn.execute(text("SELECT count(*) FROM phone_identities WHERE case_id = CAST(:c AS uuid)"),
                         {"c": case_id}).scalar() or 0
    n = len(identity_keys(conn, case_id))
    return {"case_id": str(case_id), "significant": n, "total": int(total),
            "words": "Phone screens show all records. %s of %s phone identities %s significant." % (
                "{:,}".format(n), "{:,}".format(int(total)), "is" if n == 1 else "are")}

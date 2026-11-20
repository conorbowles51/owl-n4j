"""Dossier addresses through the case's address lookup (followups, 20 Nov; Neil's decision of 20 Nov).

Fails on the code before: no dossier address was ever looked up (demo case: 3 dossier addresses, 0 positions), so a
statement naming one could not be placed on the map."""
from __future__ import annotations

import json
import unittest
import uuid
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services import address_lookup, dossier_addresses as DA, geo_rescan_service

FOUND = [{"lat": "39.29", "lon": "-76.61", "importance": 0.5, "type": "house",
          "display_name": "4410, Calder Mill Road, Baltimore, Maryland, 21201, United States",
          "address": {"state": "Maryland"}}]


def _answer(payload):
    r = MagicMock()
    r.read.return_value = json.dumps(payload).encode()
    r.__enter__ = lambda self: self
    r.__exit__ = lambda self, *a: False
    return r


def _contact(value, label="Garage", cid=None):
    return {"id": cid or str(uuid.uuid4()), "kind": "address", "label": label, "value": value,
            "evidence_file_id": None, "record_source": {"type": "manual"}, "recorded_by_user_id": "person-1"}


class FakeDb:
    def __init__(self, profiles):
        self.profiles = {p.id: p for p in profiles}
        self.commits = 0

    def scalars(self, _stmt):
        return list(self.profiles.values())

    def get(self, _model, pid):
        return self.profiles.get(pid)

    def commit(self):
        self.commits += 1


class DossierAddressLookupTests(unittest.TestCase):
    def setUp(self):
        self.ruiz = SimpleNamespace(id=uuid.uuid4(), case_id=uuid.uuid4(), contacts=[
            _contact("Ruiz Auto & Tire, 4410 Calder Mill Road, Baltimore, MD 21201"),
            _contact("Nowhere Lane 99, Atlantis, MD"),
            {"id": "p1", "kind": "phone", "value": "+14105550161"}])
        self.db = FakeDb([self.ruiz])

        @contextmanager
        def session():
            yield self.db
        for item in (patch.object(DA, "get_background_session", session),
                     patch.object(DA, "flag_modified", lambda obj, key: None),
                     patch.object(DA, "_region", lambda case_id, db: "Maryland"),
                     patch.object(geo_rescan_service, "_rate_limit"),
                     patch.object(geo_rescan_service, "_get_cached_geocode", return_value=(False, None)),
                     patch.object(geo_rescan_service, "_save_geocode_cache")):
            item.start()
            self.addCleanup(item.stop)

    def _run(self, answers, auto=True):
        with patch.object(geo_rescan_service.urllib.request, "urlopen",
                          side_effect=[_answer(a) for a in answers]) as sent:
            counts = DA.look_up_waiting(str(self.ruiz.case_id), still_auto=lambda: auto)
        return counts, sent

    def test_an_automatic_case_places_a_dossier_address_as_loupes_reading_not_the_persons(self):
        counts, sent = self._run([FOUND, []])
        self.assertEqual(sent.call_count, 2)
        self.assertEqual(counts, {"placed": 1, "no_match": 1})
        placed, missed, phone = self.ruiz.contacts
        pos = placed["position"]
        self.assertEqual((pos["lat"], pos["lon"]), (39.29, -76.61))
        self.assertEqual(pos["value"], placed["value"])
        self.assertEqual((pos["read_by"], pos["confirmed"], pos["words"]), ("Loupe", False, "Read by Loupe, not confirmed"))
        self.assertEqual(pos["requested_by"], geo_rescan_service.AUTOMATIC)
        self.assertEqual(pos["service"], geo_rescan_service.LOOKUP_SERVICE_NAME)
        # the person's entry is untouched
        self.assertEqual(placed["recorded_by_user_id"], "person-1")
        self.assertNotIn("lat", placed)
        self.assertEqual(missed["lookup"]["outcome"], "no_match")
        self.assertNotIn("position", phone)
        # one request per new address: a second pass sends nothing
        counts, sent = self._run([])
        sent.assert_not_called()
        self.assertEqual(counts, {})

    def test_a_case_that_waits_for_a_person_sends_nothing(self):
        counts, sent = self._run([], auto=False)
        sent.assert_not_called()
        self.assertEqual(counts, {"stopped": 1})
        self.assertFalse(any("position" in c or "lookup" in c for c in self.ruiz.contacts))

    def test_an_answer_outside_the_cases_state_is_not_pinned(self):
        texas = [dict(FOUND[0], display_name="Calder Mill Road, Austin, Texas, United States", address={"state": "Texas"})]
        self.ruiz.contacts = [_contact("Calder Mill Road")]
        counts, _ = self._run([texas])
        self.assertEqual(counts, {"outside_case_region": 1})
        self.assertNotIn("position", self.ruiz.contacts[0])

    def test_a_person_clicking_look_up_places_it_as_loupes_reading_with_who_asked(self):
        user = SimpleNamespace(id="person-2", name="Ann")
        cid = self.ruiz.contacts[0]["id"]
        with patch.object(geo_rescan_service.urllib.request, "urlopen", side_effect=[_answer(FOUND)]), \
                patch.object(address_lookup, "case_mode", return_value=("flag", "flag")):
            c = DA.look_up_one(self.db, dossier=self.ruiz, contact_id=cid, user=user)
        self.assertEqual((c["position"]["requested_by"], c["position"]["mode"]), ("person-2", "flag"))
        self.assertFalse(c["position"]["confirmed"])
        self.assertEqual(self.ruiz.contacts[0]["position"]["lat"], 39.29)
        self.assertEqual(c["recorded_by_user_id"], "person-1")


class DossierAddressEditTests(unittest.TestCase):
    def test_an_edited_address_drops_the_position_read_for_its_old_words(self):
        from services import dossier_service as S
        old = _contact("Ruiz Auto & Tire, 4410 Calder Mill Road", cid="a1")
        old["position"] = {"value": old["value"], "lat": 1.0, "lon": 2.0}
        user = SimpleNamespace(id="person-1")
        kept = S._contacts(None, uuid.uuid4(), user, [dict(old, position=None)], [old])
        self.assertEqual(kept[0]["position"]["lat"], 1.0)  # same words: kept, whatever the editor sent back
        moved = S._contacts(None, uuid.uuid4(), user, [dict(old, value="18 Wexmoor Court")], [old])
        self.assertNotIn("position", moved[0])


class DossierAddressClaimTests(unittest.TestCase):
    def test_a_sentence_naming_a_placed_dossier_address_is_located_and_says_whose_reading(self):
        from services.corroborate.store import CaseStore
        from services.relations import claims
        store = CaseStore.__new__(CaseStore)
        store.q = lambda *a, **k: []
        store.people = lambda: [{"key": "person:1", "label": "Mateo Ruiz", "phones": []}]
        c = _contact("Ruiz Auto & Tire, 4410 Calder Mill Road")
        c["position"] = {"value": c["value"], "lat": 39.29, "lon": -76.61}
        store._contacts = {"person:1": [c]}
        chip = claims.read_where("I was at Ruiz Auto & Tire that night.", store, [])
        self.assertTrue(chip["value"]["located"])
        self.assertEqual((chip["value"]["lat"], chip["value"]["lon"]), (39.29, -76.61))
        self.assertIn("Read by Loupe, not confirmed", chip["value"]["how"])

"""Automatic address lookups send only text that names a place, bounded to the case's own state (lx-demo
m111022392114579: on the synthetic demo case all 24 automatic pins were wrong, 'gate house' in Norwich, 'Dock 3' in
Dubai, '4410 Calder Mill Road' in New Zealand). Demo strings and invented addresses only."""
import unittest
from unittest.mock import MagicMock, patch

from services import address_auto_rules as R

DEMO_FRAGMENTS = ["gate house", "east fence", "Dock 3", "bay 2", "service bay 4", "Sector 4471-2", "Staff entrance",
                  "Emergency Department", "His house", "headquarters", "MCG", "JP 2", "mother's residence", "in apt"]


class RuleTests(unittest.TestCase):
    def test_site_fragments_are_never_sent(self):
        for text in DEMO_FRAGMENTS:
            with self.subTest(text=text):
                self.assertEqual(R.plan(text, "Maryland").action, R.NOT_A_PLACE)

    def test_a_bare_place_gets_the_cases_state_or_is_not_sent(self):
        p = R.plan("4410 Calder Mill Road", "Maryland")
        self.assertEqual((p.action, p.query, p.expect_state, p.region_added),
                         (R.SEND, "4410 Calder Mill Road, Maryland, United States", "Maryland", True))
        self.assertEqual(R.plan("4410 Calder Mill Road", None).action, R.NO_CASE_REGION)
        self.assertEqual(R.plan("12 Elm Court, Calder County, USA", "Maryland").query,
                         "12 Elm Court, Calder County, Maryland, United States")

    def test_text_naming_its_state_is_sent_as_it_is_and_must_land_there(self):
        self.assertEqual(R.plan("100 Main St, Springfield, IL 62701", "Maryland"),
                         R.Plan(R.SEND, "100 Main St, Springfield, IL 62701", "Illinois"))
        self.assertEqual(R.plan("County of Kent, State of Delaware", None).expect_state, "Delaware")
        self.assertEqual(R.plan("North Carolina", None).action, R.SEND)
        self.assertEqual(R.plan("Galway, Ireland", None), R.Plan(R.SEND, "Galway, Ireland"))

    def test_a_house_number_is_not_a_zip_and_a_state_street_is_not_a_state(self):
        self.assertEqual(R.plan("14211 Elm Tree Ln #44", None).action, R.NO_CASE_REGION)
        self.assertEqual(R.states_named("1600 Pennsylvania Ave, Washington, DC 20500"), ["District of Columbia"])
        self.assertEqual(R.states_named("Silver Lake Police (MD) Station"), ["Maryland"])

    def test_the_answer_must_lie_in_the_state_as_a_whole_part_of_its_address(self):
        rhode_island = {"formatted_address": "Delaware Avenue, Warwick, Kent County, Rhode Island, United States"}
        self.assertFalse(R.in_state(rhode_island, "Delaware"))
        self.assertTrue(R.in_state({"formatted_address": "Kent County, Delaware, United States"}, "Delaware"))
        self.assertTrue(R.in_state({"state": "Maryland", "formatted_address": ""}, "Maryland"))

    def test_case_region_needs_a_clear_majority(self):
        md = ["Rockville, MD 20850", "Silver Spring, Maryland", "1 Elm St, Bethesda, MD", "Charlotte, NC"]
        self.assertEqual(R.case_region(md)[0], "Maryland")
        self.assertIsNone(R.case_region(["Rockville, MD", "Charlotte, NC", "Dover, DE"])[0])
        self.assertIsNone(R.case_region(DEMO_FRAGMENTS)[0])


class RecheckTests(unittest.TestCase):
    """Existing automatic pins go through the same rule; a withdrawn pin stays on the entity."""

    def test_recheck_withdraws_what_the_rule_would_not_have_pinned_and_keeps_the_rest(self):
        from services import address_lookup
        neo = MagicMock()
        neo.case_address_texts.return_value = ["Rockville, MD 20850", "Silver Spring, Maryland", "Bethesda, MD"]
        neo.automatic_pins.return_value = [
            {"key": "a", "address": "gate house", "formatted_address": "Gatehouse, Dereham Road, Norwich, England"},
            {"key": "b", "address": "Calder County", "formatted_address": "Calder, Shoshone County, Idaho, United States"},
            {"key": "c", "address": "Silver Spring", "formatted_address": "Silver Spring, Montgomery County, Maryland, "
                                                                          "United States"},
            {"key": "d", "address": "Kent County, State of Delaware",
             "formatted_address": "Delaware Avenue, Warwick, Kent County, Rhode Island, United States"},
        ]
        with patch("services.neo4j_service.neo4j_service", neo):
            dry = address_lookup.recheck_automatic_pins("case-1")
            neo.withdraw_automatic_pin.assert_not_called()
            done = address_lookup.recheck_automatic_pins("case-1", apply=True)
        self.assertEqual((dry["region"], dry["pins"], dry["kept"], dry["look_up_again"], dry["withdrawn"]),
                         ("Maryland", 4, 1, 1, {"not_a_place": 1, "outside_case_region": 1}))
        calls = {c.args[0]: (c.kwargs["status"], c.kwargs["outcome"]) for c in neo.withdraw_automatic_pin.call_args_list}
        self.assertEqual(calls, {"a": ("failed", "not_a_place"), "b": ("not_run", None),
                                 "d": ("failed", "outside_case_region")})
        self.assertEqual(done["withdrawn"], dry["withdrawn"])


if __name__ == "__main__":
    unittest.main()

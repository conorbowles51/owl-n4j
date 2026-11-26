"""Set the owner lists each number once (live 25 Nov: case 4aa79795 phone C3 listed +1 201-555-0102 twice, once per
tier, 'seen 1 time' and 'seen 306 times'; 33 of 38 live phones had the same doubling)."""
from services.phone.profile import owner_choices


def _row(key, tier, n, basis):
    return {"candidate_kind": "number", "identity_key": key, "tier": tier, "occurrences": n, "basis": basis}


def test_a_number_in_both_tiers_is_one_choice_with_where_it_was_found():
    key = "phone:+12015550102"
    cands = [_row(key, 1, 1, "extracted"), _row(key, 2, 306, "inferred"),
             _row("phone:+12015550150", 2, 4, "inferred"),
             {"candidate_kind": "name", "identity_key": None, "tier": None, "occurrences": 3, "basis": "name"}]
    got = owner_choices(cands, {key: "+1 201-555-0102"})
    assert got == [
        {"identity_key": key, "text": "+1 201-555-0102", "tier": 1, "occurrences": 306, "in_device_info": True,
         "basis": "extracted"},
        {"identity_key": "phone:+12015550150", "text": "phone:+12015550150", "tier": 2, "occurrences": 4,
         "in_device_info": False, "basis": "inferred"},
    ]


def test_a_number_only_in_the_device_information_counts_no_sightings():
    got = owner_choices([_row("phone:+1", 1, 1, "extracted")], {})
    assert got[0]["in_device_info"] is True and got[0]["occurrences"] == 0

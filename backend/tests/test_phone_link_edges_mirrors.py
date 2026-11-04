"""lx-matchgrades E (A13): a debit and a credit that may be one payment seen twice, further apart than the mirror
rule's 3 days, are listed as possible mirrors with a strength; both still count, nothing is collapsed."""
from services.phone.link_edges import collapse_mirrored, money_totals


def _r(n, debit, day, account, side):
    return {"id": "00000000-0000-0000-0000-%012d" % n, "ref_id": "R%d" % n, "account_id":
            "00000000-0000-0000-0000-0000000000a%d" % account, "direction": "ab", "amount_minor": 250000,
            "currency": "USD", "proof_class": "p1", "ordering_date": "2024-03-%02d" % day,
            "ordering_date_source": "transaction", "_debit": debit, "_side": side}


def test_mirror_within_three_days_collapses_as_before_and_one_ten_days_apart_is_a_listed_possible_mirror():
    near = collapse_mirrored([_r(1, True, 1, 1, "a"), _r(2, False, 2, 2, "b")])
    assert len(near) == 1 and near[0]["mirrored_by"]["id"].endswith("2") and "possible_mirrors" not in near[0]
    far = collapse_mirrored([_r(1, True, 1, 1, "a"), _r(2, False, 11, 2, "b")])
    assert len(far) == 2   # nothing collapsed: both rows still count
    a, b = far
    assert a["possible_mirrors"] == [{"id": b["id"], "ref_id": "R2", "days_apart": 10, "level": "weak",
                                      "reason": a["possible_mirrors"][0]["reason"]}]
    assert b["possible_mirrors"][0]["id"] == a["id"] and "counted separately" in a["possible_mirrors"][0]["reason"]
    assert all(not k.startswith("_") for r in far for k in r)
    totals = money_totals(far)
    assert totals and totals[0]["paid_ab_minor"] == 500000

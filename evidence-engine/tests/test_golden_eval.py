from app.evaluation.golden_claims import score_decisions


def test_golden_score_counts_missing_decisions_as_failures() -> None:
    report = score_decisions(
        expected={"a": "verified", "b": "rejected", "c": "uncertain"},
        actual={"a": "verified", "b": "uncertain"},
    )

    assert report["total"] == 3
    assert report["correct"] == 1
    assert report["accuracy"] == 0.3333
    assert report["mismatches"] == {
        "b": {"expected": "rejected", "actual": "uncertain"},
        "c": {"expected": "uncertain", "actual": "missing"},
    }

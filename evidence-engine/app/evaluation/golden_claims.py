import json
from pathlib import Path
from typing import Any

from app.pipeline.extract_entities import RawEntity
from app.pipeline.verify_claims import verify_grounded_claims


DEFAULT_GOLDEN_PATH = (
    Path(__file__).resolve().parents[2] / "evals" / "golden_claim_verification.json"
)


def load_golden_cases(path: Path = DEFAULT_GOLDEN_PATH) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Golden claim evaluation must contain a non-empty cases array")
    return [dict(case) for case in cases]


def score_decisions(
    *,
    expected: dict[str, str],
    actual: dict[str, str],
) -> dict[str, Any]:
    mismatches: dict[str, dict[str, str]] = {}
    correct = 0
    for case_id, expected_status in expected.items():
        actual_status = actual.get(case_id, "missing")
        if actual_status == expected_status:
            correct += 1
        else:
            mismatches[case_id] = {
                "expected": expected_status,
                "actual": actual_status,
            }
    total = len(expected)
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "mismatches": mismatches,
    }


async def run_golden_claim_eval(
    path: Path = DEFAULT_GOLDEN_PATH,
) -> dict[str, Any]:
    cases = load_golden_cases(path)
    entities: list[RawEntity] = []
    expected: dict[str, str] = {}
    location = {
        "source_document_id": "golden-eval",
        "revision_id": "v1",
        "source_file": "golden-eval.txt",
        "chunk_index": 0,
        "coordinate_space": "document_text",
        "quote_start_char": 0,
        "quote_end_char": 1,
    }
    for index, case in enumerate(cases):
        case_id = case["id"]
        expected[case_id] = case["expected"]
        entities.append(
            RawEntity(
                temp_id=case_id,
                category="Other",
                specific_type="GoldenClaim",
                name=case.get("subject", case_id),
                source_quote=case["quote"],
                source_location=location,
                verified_facts=[
                    {
                        "text": case["statement"],
                        "quote": case["quote"],
                        "source_location": location,
                        "importance": 3,
                    }
                ],
                confidence=0.8,
            )
        )

    result = await verify_grounded_claims(entities, [])
    actual = {
        entity.temp_id: str(entity.verified_facts[0].get("verification_status", "missing"))
        for entity in result.entities
    }
    report = score_decisions(expected=expected, actual=actual)
    report["model"] = "configured openai_quality_model"
    report["dataset"] = str(path)
    return report

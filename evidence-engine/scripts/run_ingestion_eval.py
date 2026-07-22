import argparse
import asyncio
import json
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from app.evaluation.golden_claims import DEFAULT_GOLDEN_PATH, run_golden_claim_eval


async def _run(path: Path, minimum_accuracy: float) -> int:
    report = await run_golden_claim_eval(path)
    print(json.dumps(report, indent=2))
    return 0 if report["accuracy"] >= minimum_accuracy else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the golden evidence-claim release evaluation")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_GOLDEN_PATH)
    parser.add_argument("--minimum-accuracy", type=float, default=0.85)
    args = parser.parse_args()
    return asyncio.run(_run(args.dataset, args.minimum_accuracy))


if __name__ == "__main__":
    raise SystemExit(main())

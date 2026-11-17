"""Write the active ratings of agent answers as relevance test items (lx-agenttools D20).

    python -m scripts.export_answer_rating_cases OUT.json [--case CASE_ID]

Read-only. The file holds real case questions: keep it outside the repository.
"""
import argparse
import json
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--case", default=None)
    args = parser.parse_args(argv)
    from postgres.session import get_background_session
    from services.agent.answer_ratings import export_document
    with get_background_session() as db:
        doc = export_document(db, case_id=args.case)
    Path(args.out).write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    print("%d rated answer(s) written to %s" % (len(doc["queries"]), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

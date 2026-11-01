"""Write the TypeScript form of the link-type registry (backend/postgres/link_types.py).

    cd backend && python3 -m scripts.generate_link_types          # write
    cd backend && python3 -m scripts.generate_link_types --check  # exit 1 if the file is out of date

`tests/test_link_types.py` runs the check, so the frontend list cannot drift from the backend one.
"""
from __future__ import annotations

import sys
from pathlib import Path

from postgres import link_types

TARGET = Path(__file__).resolve().parents[2] / "frontend_v2" / "src" / "generated" / "link-types.ts"


def _const(name: str, values: tuple[str, ...]) -> str:
    body = "".join(f'  "{value}",\n' for value in values)
    return f"export const {name} = [\n{body}] as const\n"


def render() -> str:
    parts = [
        "// Generated from backend/postgres/link_types.py by `python3 -m scripts.generate_link_types`.\n",
        "// Do not edit by hand: change the registry and run the generator.\n\n",
        _const("PHONE_LINK_TYPES", link_types.PHONE_TYPES),
        "export type PhoneLinkType = (typeof PHONE_LINK_TYPES)[number]\n\n",
        _const("WORKSPACE_LINK_TYPES", link_types.WORKSPACE_TYPES),
        "export type WorkspaceLinkType = (typeof WORKSPACE_LINK_TYPES)[number]\n\n",
        _const("DOSSIER_LINK_TYPES", link_types.DOSSIER_TYPES),
        "export type DossierLinkType = (typeof DOSSIER_LINK_TYPES)[number]\n\n",
        _const("NOTEBOOK_LINK_TYPES", link_types.NOTEBOOK_TYPES),
        "export type NotebookLinkType = (typeof NOTEBOOK_LINK_TYPES)[number]\n\n",
        _const("TASK_LINK_TYPES", link_types.TASK_TYPES),
        "export type TaskLinkType = (typeof TASK_LINK_TYPES)[number]\n\n",
        _const("INTERVIEW_EVIDENCE_LINK_TYPES", link_types.INTERVIEW_EVIDENCE_TYPES),
        "export type InterviewEvidenceLinkType = (typeof INTERVIEW_EVIDENCE_LINK_TYPES)[number]\n\n",
        "export function isPhoneLinkType(value: string): value is PhoneLinkType {\n",
        "  return (PHONE_LINK_TYPES as readonly string[]).includes(value)\n",
        "}\n",
    ]
    return "".join(parts)


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print(f"{TARGET} is out of date; run python3 -m scripts.generate_link_types", file=sys.stderr)
            return 1
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

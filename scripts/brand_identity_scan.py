#!/usr/bin/env python3
"""Scan the repository for production identity drift.

The scanner is intentionally small and explicit: known customer-visible blockers
are documented here, internal technical identifiers are documented here, and any
new customer-visible legacy identity should stand out as a regression.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]

TEXT_SUFFIXES = {
    ".bat",
    ".cfg",
    ".css",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mdx",
    ".mjs",
    ".py",
    ".service",
    ".sh",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

ASSET_SUFFIXES = {".ico", ".png", ".svg", ".webp"}
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "playwright-report",
    "test-results",
}
SKIP_FILENAMES = {
    "package-lock.json",
}

BRAND_PATTERNS = {
    "cleared_loupe": re.compile(r"\bLoupe\b|loupe-logo|ease-loupe", re.IGNORECASE),
    "legacy_owl": re.compile(
        r"\bOWL\b|\bOwl\b|\bowl\b|owl[-_.:][A-Za-z0-9_.:-]+|@owl/ui",
        re.IGNORECASE,
    ),
    "legacy_deduce": re.compile(r"\bDeduce\b", re.IGNORECASE),
    "alternate_arclight": re.compile(r"\bArclight\b", re.IGNORECASE),
}
BRAND_ASSET_PATTERN = re.compile(r"owl|loupe|logo|favicon", re.IGNORECASE)
EMAIL_MARKER_PATTERN = re.compile(
    r"smtp|sendmail|EmailMessage|mailto|noreply|from_email|send_email|reply-to",
    re.IGNORECASE,
)

DOCUMENTED_OPEN_CUSTOMER_VISIBLE = (
    (
        re.compile(r"^scripts/generate_user_guide_pdf\.(py|js)$"),
        "Legacy generated user guide branding; owner DKT-512/513.",
    ),
    (
        re.compile(r"^frontend_v2/public/owl\.webp$"),
        "Orphaned legacy Owl asset; owner DKT-512.",
    ),
    (
        re.compile(r"^landing/"),
        "Landing app uses the non-cleared Arclight identity; owner DKT-513.",
    ),
    (
        re.compile(r"^backend/services/agent/graph\.py$"),
        "Agent system prompt self-identifies as OWL; output-adjacent review for DKT-513.",
    ),
)

INTERNAL_ONLY = (
    (re.compile(r"^BACKLOG\.md$"), "Internal backlog."),
    (re.compile(r"^CHANGELOG\.md$"), "Internal release history."),
    (re.compile(r"^INTEGRATION_PLAN\.md$"), "Internal implementation plan."),
    (re.compile(r"^WORKING_CHANGELOG\.md$"), "Internal working log."),
    (re.compile(r"^backend/config\.py$"), "Internal configuration default."),
    (re.compile(r"^backend/routers/triage\.py$"), "Internal API docstring; not response copy."),
    (re.compile(r"^backend/services/evidence_engine_client\.py$"), "Internal service docstring."),
    (re.compile(r"^backend/services/geocoder\.py$"), "Internal HTTP user-agent default."),
    (re.compile(r"^backend/services/neo4j/"), "Internal service implementation."),
    (re.compile(r"^backend/services/platform_update_service\.py$"), "Internal deployment service name."),
    (re.compile(r"^backend/services/triage/"), "Internal triage service docstring."),
    (re.compile(r"^backend/tests/"), "Test fixture or assertion."),
    (re.compile(r"^deploy/"), "Deployment-only service and path identifiers."),
    (re.compile(r"^docker-compose\.yml$"), "Local container and database identifiers."),
    (re.compile(r"^docs/"), "Internal documentation, brand research, or audit evidence."),
    (re.compile(r"^evidence-engine/"), "Internal service implementation."),
    (re.compile(r"^frontend_v2/src/.+\.test\.(ts|tsx)$"), "Frontend test fixture or assertion."),
    (re.compile(r"^frontend_v2/src/hooks/use-global-shortcuts\.ts$"), "Internal browser event names."),
    (re.compile(r"^frontend_v2/src/lib/theme-provider\.tsx$"), "Internal localStorage migration key."),
    (re.compile(r"^frontend_v2/src/stores/"), "Internal persisted store key."),
    (re.compile(r"^frontend_v2/src/features/.+/stores/"), "Internal persisted store key."),
    (re.compile(r"^frontend_v2/src/features/admin/platform-update-status\.test\.ts$"), "Frontend test fixture."),
    (re.compile(r"^frontend_v2/src/features/agent/components/AgentPage\.tsx$"), "Internal preference key."),
    (re.compile(r"^frontend_v2/src/styles/globals\.css$"), "Internal CSS variable alias."),
    (re.compile(r"^frontend_v2/src/stories/"), "Storybook-only developer surface."),
    (
        re.compile(r"^frontend_v2/e2e/brand-smoke\.spec\.ts$"),
        "Brand smoke spec references legacy identifiers as scanner fixtures.",
    ),
    (re.compile(r"^scripts/brand_identity_scan\.py$"), "The scan implementation and allowlist."),
)

CUSTOMER_VISIBLE_PATHS = (
    re.compile(r"^frontend_v2/index\.html$"),
    re.compile(r"^frontend_v2/public/"),
    re.compile(r"^frontend_v2/src/"),
    re.compile(r"^landing/"),
    re.compile(r"^scripts/generate_user_guide_pdf\.(py|js)$"),
)

EMAIL_SCAN_ROOTS = (
    "backend",
    "evidence-engine",
    "frontend_v2/src",
    "landing/src",
    "scripts",
)

EMAIL_SCAN_IGNORES = (
    re.compile(r"^backend/tests/"),
    re.compile(r"^evidence-engine/tests/"),
    re.compile(r"^frontend_v2/src/.+\.test\.(ts|tsx)$"),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    token: str
    status: str
    note: str
    text: str


@dataclass(frozen=True)
class ScanResult:
    findings: list[Finding]
    email_markers: list[Finding]

    @property
    def undocumented_customer_visible_legacy(self) -> list[Finding]:
        return [
            finding
            for finding in self.findings
            if finding.status == "unexpected_customer_visible"
        ]

    @property
    def documented_open(self) -> list[Finding]:
        return [
            finding
            for finding in self.findings
            if finding.status == "documented_open"
        ]

    @property
    def cleared_loupe(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.status == "cleared"]

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total_findings": len(self.findings),
                "cleared_loupe": len(self.cleared_loupe),
                "documented_open": len(self.documented_open),
                "retained_internal": len(
                    [finding for finding in self.findings if finding.status == "retained_internal"]
                ),
                "undocumented_customer_visible_legacy": len(
                    self.undocumented_customer_visible_legacy
                ),
                "email_markers": len(self.email_markers),
            },
            "findings": [asdict(finding) for finding in self.findings],
            "email_markers": [asdict(finding) for finding in self.email_markers],
        }


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.name in SKIP_FILENAMES:
            continue
        if path.is_file():
            yield path


def rel_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_text_file(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES


def is_brand_asset(path: Path) -> bool:
    return path.suffix in ASSET_SUFFIXES and bool(BRAND_ASSET_PATTERN.search(path.name))


def first_matching_note(path: str, patterns: Iterable[tuple[re.Pattern[str], str]]) -> str | None:
    for pattern, note in patterns:
        if pattern.search(path):
            return note
    return None


def is_customer_visible_path(path: str) -> bool:
    return any(pattern.search(path) for pattern in CUSTOMER_VISIBLE_PATHS)


def classify(path: str, token: str) -> tuple[str, str]:
    if token == "cleared_loupe" or token == "cleared_loupe_asset":
        return "cleared", "Cleared production identity."

    documented_open = first_matching_note(path, DOCUMENTED_OPEN_CUSTOMER_VISIBLE)
    if documented_open:
        return "documented_open", documented_open

    internal_only = first_matching_note(path, INTERNAL_ONLY)
    if internal_only:
        return "retained_internal", internal_only

    if is_customer_visible_path(path):
        return "unexpected_customer_visible", "Customer-visible legacy identity is not documented."

    return "retained_internal", "Not in a customer-visible release surface."


def scan_text_file(path: Path, root: Path) -> list[Finding]:
    relative = rel_path(path, root)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for token, pattern in BRAND_PATTERNS.items():
            if pattern.search(line):
                status, note = classify(relative, token)
                findings.append(
                    Finding(
                        path=relative,
                        line=line_number,
                        token=token,
                        status=status,
                        note=note,
                        text=line.strip(),
                    )
                )
    return findings


def scan_asset_file(path: Path, root: Path) -> list[Finding]:
    relative = rel_path(path, root)
    lower_name = path.name.lower()
    if "loupe" in lower_name:
        token = "cleared_loupe_asset"
    elif "owl" in lower_name:
        token = "legacy_owl_asset"
    else:
        token = "favicon_asset"

    status, note = classify(relative, token)
    return [
        Finding(
            path=relative,
            line=0,
            token=token,
            status=status,
            note=note,
            text=f"[asset] {path.name}",
        )
    ]


def scan_email_markers(root: Path) -> list[Finding]:
    markers: list[Finding] = []
    for scan_root in EMAIL_SCAN_ROOTS:
        base = root / scan_root
        if not base.exists():
            continue
        for path in iter_files(base):
            relative = rel_path(path, root)
            if (
                relative == "scripts/brand_identity_scan.py"
                or not is_text_file(path)
                or any(pattern.search(relative) for pattern in EMAIL_SCAN_IGNORES)
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if EMAIL_MARKER_PATTERN.search(line):
                    markers.append(
                        Finding(
                            path=relative,
                            line=line_number,
                            token="email_marker",
                            status="email_copy_review",
                            note="Outbound email copy or mail transport marker requires brand inventory review.",
                            text=line.strip(),
                        )
                    )
    return markers


def run_scan(root: Path = REPO_ROOT) -> ScanResult:
    root = root.resolve()
    findings: list[Finding] = []
    seen_assets: set[str] = set()

    for path in iter_files(root):
        if is_text_file(path):
            findings.extend(scan_text_file(path, root))
        if is_brand_asset(path):
            relative = rel_path(path, root)
            if relative not in seen_assets:
                findings.extend(scan_asset_file(path, root))
                seen_assets.add(relative)

    findings.sort(key=lambda finding: (finding.path, finding.line, finding.token))
    email_markers = scan_email_markers(root)
    email_markers.sort(key=lambda finding: (finding.path, finding.line, finding.token))
    return ScanResult(findings=findings, email_markers=email_markers)


def format_text(result: ScanResult) -> str:
    lines = [
        "Brand identity scan",
        "===================",
        f"Total brand findings: {len(result.findings)}",
        f"Cleared Loupe findings: {len(result.cleared_loupe)}",
        f"Documented open customer-visible findings: {len(result.documented_open)}",
        f"Undocumented customer-visible legacy findings: {len(result.undocumented_customer_visible_legacy)}",
        f"Outbound email markers: {len(result.email_markers)}",
        "",
    ]

    if result.undocumented_customer_visible_legacy:
        lines.append("Undocumented customer-visible legacy findings:")
        for finding in result.undocumented_customer_visible_legacy:
            lines.append(
                f"- {finding.path}:{finding.line} [{finding.token}] {finding.text}"
            )
        lines.append("")

    if result.email_markers:
        lines.append("Email copy markers requiring review:")
        for finding in result.email_markers:
            lines.append(
                f"- {finding.path}:{finding.line} {finding.text}"
            )
        lines.append("")

    if result.documented_open:
        lines.append("Documented open customer-visible findings:")
        for finding in result.documented_open[:40]:
            lines.append(
                f"- {finding.path}:{finding.line} [{finding.token}] {finding.note}"
            )
        if len(result.documented_open) > 40:
            lines.append(f"- ... {len(result.documented_open) - 40} more")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan brand identity occurrences.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero for undocumented customer-visible legacy terms or email markers.",
    )
    args = parser.parse_args()

    result = run_scan(args.root)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_text(result))

    if args.strict and (
        result.undocumented_customer_visible_legacy or result.email_markers
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

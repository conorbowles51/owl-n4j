"""The evidence engine image keeps no compiler or kernel headers after its build (12 Nov image scan: 2 HIGH CVEs in
linux-libc-dev, pulled in by build-essential, across the 5 evidence images)."""
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "evidence-engine" / "Dockerfile"


def _runs():
    lines, current = [], ""
    for line in DOCKERFILE.read_text().splitlines():
        if line.lstrip().startswith("#"):
            continue
        current += line.rstrip("\\").strip() + " "
        if not line.rstrip().endswith("\\"):
            if current.strip():
                lines.append(current.strip())
            current = ""
    return lines


def test_build_tools_are_purged_after_the_last_install():
    steps = _runs()
    installs = [i for i, step in enumerate(steps) if "build-essential" in step and "install" in step]
    purges = [i for i, step in enumerate(steps) if "purge" in step and "build-essential" in step and "--auto-remove" in step]
    native_builds = [i for i, step in enumerate(steps) if "pip install" in step or "install.sh" in step]
    assert installs, "the image no longer installs build-essential; drop this test"
    assert purges, "build-essential (and with it linux-libc-dev) stays in the image"
    assert purges[-1] > max(native_builds), "the purge must come after every step that builds native packages"

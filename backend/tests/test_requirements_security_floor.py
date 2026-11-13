"""The backend pins every package the dependency scan found a fixed release for (989217d8, 13 Nov 2026).

Unpinned, these came in at whatever version the venv first got, below the fix. A floor here fails when a pin is
removed or moved back below the release that fixed the advisory.
"""
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"

# package: (lowest fixed release, advisory)
FLOORS = {
    "pyjwt": ("2.15.0", "PYSEC-2026-4145"),
    "brotli": ("1.2.1", "PYSEC-2026-4322"),
    "dnspython": ("2.9.0", "CVE-2026-114605"),
    "mako": ("1.3.12", "PYSEC-2026-2617"),
    "langsmith": ("0.8.18", "CVE-2026-59152"),
}


def _version(text):
    return tuple(int(part) for part in text.split("."))


def _pins():
    pins = {}
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" in line:
            name, version = line.split("==", 1)
            pins[name.strip().lower()] = version.strip()
    return pins


def test_packages_with_a_fixed_release_are_pinned_at_or_above_it():
    pins = _pins()
    below = {name: (pins.get(name), floor, advisory) for name, (floor, advisory) in FLOORS.items()
             if name not in pins or _version(pins[name]) < _version(floor)}
    assert not below, f"not pinned at or above the fixed release: {below}"

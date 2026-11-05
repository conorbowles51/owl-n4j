"""deploy/rotate-secrets.sh, with a stand-in release and rekey, on a temporary .env."""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHIPPED = "loupe-development-ai-credentials-change-me"


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "backend" / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "backend" / "secret_check.py", root / "backend")
    (root / "backend" / "scripts" / "rekey_ai_credentials.py").write_text(
        "import sys\nopen('../rekey.log', 'a').write(' '.join(sys.argv[1:]) + '\\n')\nprint('stand-in rekey')\n")
    (root / ".env").write_text("OPENAI_API_KEY=keep-me\nAI_CREDENTIAL_ENCRYPTION_KEY=" + SHIPPED + "\n")
    return root


def _run(root: Path, mode: str):
    environment = {**os.environ, "ROOT_DIR": str(root), "PYTHON_BIN": sys.executable,
                   "RELEASE_COMMAND": f"touch {root}/released"}
    return subprocess.run(["bash", str(REPO / "deploy" / "rotate-secrets.sh"), mode], env=environment,
                          capture_output=True, text=True, timeout=120)


def _values(root: Path) -> dict:
    return dict(line.split("=", 1) for line in (root / ".env").read_text().splitlines())


def test_check_writes_nothing_and_names_what_it_would_replace(tmp_path):
    root = _root(tmp_path)
    before = (root / ".env").read_text()
    done = _run(root, "--check")
    assert done.returncode == 0, done.stderr
    assert "AUTH_SECRET_KEY" in done.stdout and "Nothing written" in done.stdout
    assert (root / ".env").read_text() == before
    assert not (root / "released").exists()


def test_apply_replaces_the_secrets_releases_then_rekeys_and_never_prints_a_value(tmp_path):
    root = _root(tmp_path)
    done = _run(root, "--apply")
    assert done.returncode == 0, done.stderr
    values = _values(root)
    assert values["OPENAI_API_KEY"] == "keep-me"
    assert values["LOUPE_ENV"] == "production"
    assert values["AI_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS"] == SHIPPED
    assert (root / "released").exists()
    assert (root / "rekey.log").read_text().splitlines() == ["", "--apply"]  # read first, moved after the release
    for name in ("AUTH_SECRET_KEY", "AI_CREDENTIAL_ENCRYPTION_KEY", "EVIDENCE_ENGINE_API_KEY"):
        assert len(values[name]) >= 32 and values[name] not in done.stdout + done.stderr
    assert stat.S_IMODE((root / ".env").stat().st_mode) == 0o640
    copies = list(root.glob(".env.before-secrets-*"))
    assert len(copies) == 1 and SHIPPED in copies[0].read_text()


def test_a_second_apply_keeps_the_values_in_place(tmp_path):
    root = _root(tmp_path)
    assert _run(root, "--apply").returncode == 0
    first = _values(root)
    done = _run(root, "--apply")
    assert done.returncode == 0, done.stderr
    assert _values(root) == first

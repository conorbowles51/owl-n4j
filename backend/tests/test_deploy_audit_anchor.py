"""Each release installs the daily audit-chain time-stamp from deploy/audit-anchor.conf (Neil 8 Nov: switch it on)."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _project(tmp_path, wanted):
    project = tmp_path / "project"
    (project / "deploy").mkdir(parents=True)
    for name in ("audit-anchor.sh", "owl-audit-anchor.service", "owl-audit-anchor.timer"):
        shutil.copy(ROOT / "deploy" / name, project / "deploy" / name)
    (project / "deploy" / "audit-anchor.conf").write_text(f"# switch\n{wanted}\n")
    units = tmp_path / "units"
    units.mkdir()
    log = tmp_path / "systemctl.log"
    stub = tmp_path / "systemctl"
    stub.write_text(f"#!/bin/sh\necho \"$@\" >> {log}\n")
    stub.chmod(0o755)
    return project, units, log, stub


def _install(project, units, stub, tmp_path):
    return subprocess.run(["bash", str(project / "deploy" / "audit-anchor.sh"), "install"], capture_output=True,
        text=True, env={"PATH": "/usr/bin:/bin", "PROJECT_DIR": str(project), "AUDIT_ANCHOR_UNIT_DIR": str(units),
                        "SYSTEMCTL": str(stub), "AUDIT_ANCHOR_OUTPUT": str(tmp_path / "anchors")})


def test_on_installs_the_units_and_enables_the_timer(tmp_path):
    project, units, log, stub = _project(tmp_path, "on")
    out = _install(project, units, stub, tmp_path)
    assert out.returncode == 0, out.stderr
    assert (units / "owl-audit-anchor.timer").read_text() == (ROOT / "deploy/owl-audit-anchor.timer").read_text()
    assert log.read_text().splitlines() == ["daemon-reload", "enable --now owl-audit-anchor.timer"]
    assert (tmp_path / "anchors").is_dir()
    # A second release with nothing changed reloads nothing.
    log.write_text("")
    _install(project, units, stub, tmp_path)
    assert log.read_text().splitlines() == ["enable --now owl-audit-anchor.timer"]


def test_off_disables_an_installed_timer(tmp_path):
    project, units, log, stub = _project(tmp_path, "off")
    (units / "owl-audit-anchor.timer").write_text("x")
    assert _install(project, units, stub, tmp_path).returncode == 0
    assert log.read_text().splitlines() == ["disable --now owl-audit-anchor.timer"]


def test_the_service_sends_to_the_chosen_authority_with_the_pinned_root():
    service = (ROOT / "deploy/owl-audit-anchor.service").read_text()
    assert "--tsa-url http://timestamp.digicert.com" in service
    assert "deploy/tsa/digicert-trusted-root-g4.pem" in service
    root = subprocess.run(["openssl", "x509", "-in", str(ROOT / "deploy/tsa/digicert-trusted-root-g4.pem"), "-noout",
                           "-fingerprint", "-sha256"], capture_output=True, text=True, check=True).stdout
    assert "55:2F:7B:DC:F1:A7:AF:9E:6C:E6:72:01:7F:4F:12:AB:F7:72:40:C7:8E:76:1A:C2:03:D1:D9:D2:0A:C8:99:88" in root
    assert "audit-anchor.sh\" install" in (ROOT / "deploy/deploy.sh").read_text()

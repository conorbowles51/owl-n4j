"""deploy/ci/scan-head.sh compares a scan with the last complete scan, never with a partial one.

9 Nov: two scans whose image scans failed held 3,593 of 11,789 findings and became the baseline, so the next
complete scans reported 8,196 new findings (1,252 high), every one already present two scans earlier.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

CI = Path(__file__).resolve().parents[2] / 'deploy' / 'ci'

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='needs git')

# Stand-in scanners: the deps and secret scans find nothing; the container scan writes one trivy report per image
# named in IMAGES, and lists the images in SKIPPED as failed (a partial result).
DEPS = '#!/bin/bash\necho "{}" > "$2/deps-counts.json"\n'
SECRET = '#!/bin/bash\necho "[]" > "$2/gitleaks.json"\n'
CONTAINER = '''#!/bin/bash
out=$1
for img in $IMAGES; do
  cat > "$out/trivy-$img.json" <<EOF
{"Results": [{"Vulnerabilities": [{"PkgName": "lib-$img", "VulnerabilityID": "CVE-1-$img", "Severity": "HIGH"}]}]}
EOF
done
for img in $SKIPPED; do echo "$img  trivy failed (exit 1)" >> "$out/containers-skipped.txt"; done
echo "{}" > "$out/container-counts.json"
'''


@pytest.fixture
def ci(tmp_path):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for name, body in (('deps-scan.sh', DEPS), ('secret-scan.sh', SECRET), ('container-scan.sh', CONTAINER)):
        (bin_dir / name).write_text(body)
    tell = tmp_path / 'tell.sh'
    tell.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$(dirname "$0")/told.txt"\n')
    tell.chmod(0o755)
    repo = tmp_path / 'repo'
    repo.mkdir()
    git = ['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t']
    subprocess.run(git + ['init', '-q'], check=True)
    manifests = ['backend/requirements.txt', 'frontend_v2/package.json', 'frontend_v2/package-lock.json',
                 'landing/package.json', 'landing/package-lock.json']
    for path in manifests:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text('{}\n')
    shas = []
    for i in range(4):
        (repo / 'f.txt').write_text(str(i))
        subprocess.run(git + ['add', 'f.txt', *manifests], check=True)
        subprocess.run(git + ['commit', '-qm', str(i)], check=True)
        shas.append(subprocess.run(git + ['rev-parse', 'HEAD'], check=True, capture_output=True,
                                   text=True).stdout.strip())
    reports = tmp_path / 'reports'
    reports.mkdir()

    def scan(sha, images, skipped=''):
        env = {**os.environ, 'CI_REPORTS_DIR': str(reports), 'CI_SCAN_BIN': str(bin_dir), 'CI_TELL_SH': str(tell),
               'IMAGES': images, 'SKIPPED': skipped}
        result = subprocess.run(['bash', str(CI / 'scan-head.sh'), sha, str(repo)], env=env, capture_output=True,
                                text=True, timeout=120)
        out = reports / sha[:12]
        return result, out

    return scan, shas, reports, tmp_path / 'told.txt'


def test_a_partial_scan_is_not_the_baseline_and_says_partial(ci):
    scan, shas, reports, told = ci
    scan(shas[0], 'a b c')
    first_told = told.read_text() if told.exists() else ''
    result, out = scan(shas[1], 'a', skipped='b c')
    assert (reports / '.last-completed').read_text().strip() == shas[0][:12], result.stderr
    assert 'PARTIAL scan' in (out / 'report.md').read_text()
    assert 'partial=yes' in (reports / 'scans.log').read_text().splitlines()[-1]
    result, out = scan(shas[2], 'a b c')
    assert (out / 'new-findings.txt').read_text() == '', result.stderr
    assert (out / 'new-high.txt').read_text() == ''
    assert (told.read_text() if told.exists() else '') == first_told  # no alarm for findings already known
    assert (reports / '.last-completed').read_text().strip() == shas[2][:12]


def test_a_partial_scan_with_a_really_new_high_still_alerts_and_is_marked(ci):
    scan, shas, reports, told = ci
    scan(shas[0], 'a b')
    result, out = scan(shas[1], 'a d', skipped='b')
    assert (out / 'new-high.txt').read_text().strip() == 'img:d:lib-d:CVE-1-d:HIGH', result.stderr
    assert told.read_text().splitlines()[-1].startswith('coordinator ci-scan PARTIAL scan of live head')

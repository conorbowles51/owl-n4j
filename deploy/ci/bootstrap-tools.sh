#!/usr/bin/env bash
# Install the scan/provision tools into CI_TOOLS_DIR (idempotent; checksum-verified).
# Tools: pip-audit (venv), gitleaks, trivy, terraform. Versions pinned in ci-lib.sh.
set -euo pipefail
. "$(dirname "$0")/ci-lib.sh"

mkdir -p "$CI_TOOLS_DIR"
cd "$CI_TOOLS_DIR"

# github.com/<repo>/releases/download/ sometimes 504s while api.github.com works
# (seen 8 Nov 2026); the API asset endpoint with Accept: octet-stream serves the
# same files, so it is the fallback.
gh_release_file() { # gh_release_file <owner/repo> <tag> <file>
  local repo=$1 tag=$2 file=$3
  curl -fsSL -o "$file" "https://github.com/$repo/releases/download/$tag/$file" && return 0
  local id
  id=$(curl -fsSL "https://api.github.com/repos/$repo/releases/tags/$tag" \
    | python3 -c "import json,sys; r=json.load(sys.stdin); print([a['id'] for a in r['assets'] if a['name']=='$file'][0])")
  curl -fsSL -H "Accept: application/octet-stream" -o "$file" \
    "https://api.github.com/repos/$repo/releases/assets/$id"
}

fetch_gh_verified() { # fetch_gh_verified <owner/repo> <tag> <file> <checksums-file>
  local repo=$1 tag=$2 file=$3 sums=$4
  [ -f "$file" ] || gh_release_file "$repo" "$tag" "$file"
  gh_release_file "$repo" "$tag" "$sums"
  grep -E "([ /]|^)$file\$" "$sums" | sed "s#[^ ]*/$file\$#$file#" | sha256sum -c --quiet -
}

# pip-audit in its own venv
if [ ! -x "$(pip_audit_bin)" ]; then
  python3 -m venv venv
  ./venv/bin/pip install --quiet pip-audit
fi
"$(pip_audit_bin)" --version

# gitleaks
if [ ! -x gitleaks ] || ! ./gitleaks version 2>/dev/null | grep -q "$GITLEAKS_VERSION"; then
  fetch_gh_verified gitleaks/gitleaks "v${GITLEAKS_VERSION}" \
    "gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" "gitleaks_${GITLEAKS_VERSION}_checksums.txt"
  tar -xzf "gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" gitleaks
fi
./gitleaks version

# trivy
if [ ! -x trivy ] || ! ./trivy --version 2>/dev/null | grep -q "Version: $TRIVY_VERSION"; then
  fetch_gh_verified aquasecurity/trivy "v${TRIVY_VERSION}" \
    "trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" "trivy_${TRIVY_VERSION}_checksums.txt"
  tar -xzf "trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" trivy
fi
./trivy --version | head -1

# terraform
if [ ! -x terraform ] || ! ./terraform version 2>/dev/null | grep -q "v${TERRAFORM_VERSION}\b"; then
  [ -f "terraform_${TERRAFORM_VERSION}_linux_amd64.zip" ] || curl -fsSL \
    -o "terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
    "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip"
  curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_SHA256SUMS" \
    | grep linux_amd64.zip | sha256sum -c --quiet -
  python3 -c "import zipfile; zipfile.ZipFile('terraform_${TERRAFORM_VERSION}_linux_amd64.zip').extract('terraform')"
  chmod +x terraform
fi
./terraform version | head -1

ci_log "all tools ready in $CI_TOOLS_DIR"

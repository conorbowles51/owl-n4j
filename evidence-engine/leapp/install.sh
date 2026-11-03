#!/bin/sh
# 05 section 17.3: install each pinned LEAPP tool into its own venv under /opt/leapp/<tool>-<version>/.
# The clone must be at the pinned commit, its licence file must be MIT, or the build fails.
set -eu
unset PYTHONPATH  # the engine image puts its own code on the path; a tool venv must not see it
PINS=${1:-/opt/leapp/pins.json}
for tool in $(python3 -c "import json,sys;print(' '.join(json.load(open('$PINS'))))" ); do
  eval "$(python3 -c "import json;p=json.load(open('$PINS'))['$tool'];print('REPO=%s VER=%s COMMIT=%s ENTRY=%s'%(p['repo'],p['version'],p['commit'],p['entry']))")"
  DEST=/opt/leapp/$tool-$VER
  git clone --quiet --depth 1 --branch "$VER" "$REPO" "$DEST/src"
  GOT=$(git -C "$DEST/src" rev-parse HEAD)
  [ "$GOT" = "$COMMIT" ] || { echo "$tool: commit $GOT is not the pinned $COMMIT" >&2; exit 1; }
  head -1 "$DEST/src/LICENSE" | grep -q "MIT License" || { echo "$tool: licence is not MIT" >&2; exit 1; }
  rm -rf "$DEST/src/.git" "$DEST/src/whl_files"
  python3 -m venv "$DEST/venv"
  "$DEST/venv/bin/pip" install --no-cache-dir --quiet -r "$DEST/src/requirements.txt"
  python3 -c "import json;p=json.load(open('$PINS'))['$tool'];p['installed_commit']='$GOT';json.dump(p,open('$DEST/PIN.json','w'),indent=1)"
  (cd "$DEST/src" && "$DEST/venv/bin/python" "$ENTRY" --version)
done

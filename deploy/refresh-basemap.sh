#!/usr/bin/env bash
# Fetch or refresh the base map Loupe serves from this server (nginx /basemap/, deploy/nginx-loupe-frontend.conf).
#
# The map's tiles come from one PMTiles file built from OpenStreetMap by Protomaps (a published daily build of the
# whole world). Downloading a build reveals nothing about any case: every copy is the same file. The fonts and symbols
# the labels use come from the Protomaps basemaps-assets repository at a pinned commit. After this script the map
# reads only from this server.
#
#   deploy/refresh-basemap.sh                      newest daily build, whole world, every zoom (about 140 GB)
#   deploy/refresh-basemap.sh --build 20261103     a given daily build
#   deploy/refresh-basemap.sh --bbox W,S,E,N --maxzoom 15   only an area (pmtiles extract); outside it the map
#                                                  shows "Detailed map not held on this server for this area"
#   deploy/refresh-basemap.sh --dry-run            print what would be fetched and its size; fetch nothing
#
# Layout under BASEMAP_ROOT (default /mnt/owl-data/loupe-basemap):
#   builds/<build>/world.pmtiles, builds/<build>/assets/{fonts,sprites}, builds/<build>/BUILD.txt
#   current -> builds/<build>        switched in one step once the new copy is verified; nginx needs no reload
#   bin/pmtiles                      the pinned pmtiles command (go-pmtiles, checked against its release digest)
# and LOUPE_BASEMAP_LINK (default <checkout>/../loupe-basemap) -> BASEMAP_ROOT, the path nginx is configured with.
# The previous build is removed only after the new one is verified and live. Runs under nice/ionice; no timer.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASEMAP_ROOT="${BASEMAP_ROOT:-/mnt/owl-data/loupe-basemap}"
LOUPE_BASEMAP_LINK="${LOUPE_BASEMAP_LINK:-$(cd "${PROJECT_DIR}/.." && pwd)/loupe-basemap}"
APP_OWNER="${APP_OWNER:-1001:1002}"
BUILDS_URL="https://build.protomaps.com"
BUILDS_INDEX="https://build-metadata.protomaps.dev/builds.json"
PMTILES_VERSION="1.31.2"
PMTILES_SHA256="3ed7dbf4ec2e6dfe5e25b6f70d1ffc932729f93c86db353bf514dd71010a312f"
ASSETS_COMMIT="028c18f713baecad011301ff7a69acc39bcc2ae7"
ASSETS_SHA256="57e40e8c512bd8042d0a3a251f19d0d1c8523ad963c666c3c6643bada4dc92d0"
MAX_BYTES=$((150 * 1000 * 1000 * 1000))   # a whole-world file over this needs a narrower area, not more disk

BUILD="" BBOX="" MAXZOOM="" DRY_RUN=false
while [ $# -gt 0 ]; do
    case "$1" in
        --build) BUILD="$2"; shift 2 ;;
        --bbox) BBOX="$2"; shift 2 ;;
        --maxzoom) MAXZOOM="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

say() { echo "$(date -u +%FT%TZ) $*"; }
low() { nice -n 15 ionice -c3 "$@"; }

mkdir -p "${BASEMAP_ROOT}/bin" "${BASEMAP_ROOT}/builds" "${BASEMAP_ROOT}/incoming"
PMTILES="${BASEMAP_ROOT}/bin/pmtiles"
if ! "${PMTILES}" version 2>/dev/null | grep -q "pmtiles ${PMTILES_VERSION}"; then
    dl="${BASEMAP_ROOT}/incoming/go-pmtiles-${PMTILES_VERSION}"
    mkdir -p "${dl}"
    curl -fsSL -o "${dl}/pmtiles.tar.gz" \
        "https://github.com/protomaps/go-pmtiles/releases/download/v${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION}_Linux_x86_64.tar.gz"
    echo "${PMTILES_SHA256}  ${dl}/pmtiles.tar.gz" | sha256sum -c --quiet
    tar -xzf "${dl}/pmtiles.tar.gz" -C "${dl}" pmtiles
    install -m 755 "${dl}/pmtiles" "${PMTILES}"
    rm -rf "${dl}"
fi

# Which build, and its size and checksum as published.
index="$(curl -fsS "${BUILDS_INDEX}")"
read -r BUILD SIZE MD5 <<<"$(python3 -c '
import json, sys
builds = json.loads(sys.argv[1]); want = sys.argv[2]
pick = [b for b in builds if b["key"] == want + ".pmtiles"] if want else builds[-1:]
if not pick: sys.exit("no build " + want)
b = pick[0]; print(b["key"].removesuffix(".pmtiles"), b["size"], b.get("md5sum", "-"))
' "${index}" "${BUILD}")"
SOURCE="${BUILDS_URL}/${BUILD}.pmtiles"
say "build ${BUILD}: ${SIZE} bytes ($((SIZE / 1000000000)) GB) whole world, md5 ${MD5}"

if [ -z "${BBOX}" ] && [ -z "${MAXZOOM}" ] && [ "${SIZE}" -gt "${MAX_BYTES}" ]; then
    say "REFUSED: the whole world is over 150 GB; choose an area with --bbox and/or --maxzoom"
    exit 1
fi
if [ -n "${BBOX}${MAXZOOM}" ]; then
    low "${PMTILES}" extract "${SOURCE}" /dev/null --dry-run ${BBOX:+--bbox="${BBOX}"} ${MAXZOOM:+--maxzoom="${MAXZOOM}"} || true
fi
free=$(df -B1 --output=avail "${BASEMAP_ROOT}" | tail -1)
say "free on $(df --output=target "${BASEMAP_ROOT}" | tail -1): $((free / 1000000000)) GB"
if [ "${free}" -lt $((SIZE + 20 * 1000 * 1000 * 1000)) ] && [ -z "${BBOX}${MAXZOOM}" ]; then
    say "REFUSED: not enough room for a second copy beside the live one (needs size + 20 GB)"
    exit 1
fi
${DRY_RUN} && { say "dry run: nothing fetched"; exit 0; }

part="${BASEMAP_ROOT}/incoming/${BUILD}${BBOX:+-area}.pmtiles"
started=$(date +%s)
if [ -z "${BBOX}${MAXZOOM}" ]; then
    # The whole file, resumable, checked against the published md5.
    # HTTP/1.1 and a resume loop in the shell: a 139 GB download over HTTP/2 broke with "stream not closed cleanly"
    # (curl 92), and curl's own --retry restarts from the offset its run began at, rewriting what it already had.
    # Each pass here resumes from the file's real end.
    for attempt in $(seq 1 200); do
        low curl -fsS -L --http1.1 -C - --speed-limit 1000000 --speed-time 60 -o "${part}" "${SOURCE}" && break
        say "download interrupted at $(stat -c %s "${part}") bytes (attempt ${attempt}); resuming"
        sleep 5
    done
    got=$(stat -c %s "${part}")
    [ "${got}" = "${SIZE}" ] || { say "FAILED: ${got} bytes, expected ${SIZE}"; exit 1; }
    if [ "${MD5}" != "-" ]; then
        actual=$(low md5sum "${part}" | cut -d' ' -f1 | xxd -r -p | base64)
        [ "${actual}" = "${MD5}" ] || { say "FAILED: md5 ${actual}, published ${MD5}"; exit 1; }
        say "md5 matches the published build"
    fi
else
    rm -f "${part}"
    low "${PMTILES}" extract "${SOURCE}" "${part}" ${BBOX:+--bbox="${BBOX}"} ${MAXZOOM:+--maxzoom="${MAXZOOM}"}
fi
low "${PMTILES}" verify "${part}"
say "fetched and verified in $(( $(date +%s) - started )) s"

target="${BASEMAP_ROOT}/builds/${BUILD}${BBOX:+-area}"
rm -rf "${target}.new"; mkdir -p "${target}.new/assets"
assets_tar="${BASEMAP_ROOT}/incoming/basemaps-assets-${ASSETS_COMMIT}.tar.gz"
[ -s "${assets_tar}" ] || curl -fsSL -o "${assets_tar}" "https://codeload.github.com/protomaps/basemaps-assets/tar.gz/${ASSETS_COMMIT}"
echo "${ASSETS_SHA256}  ${assets_tar}" | sha256sum -c --quiet
tar -xzf "${assets_tar}" -C "${target}.new/assets" --strip-components=1 --wildcards '*/fonts/*' '*/sprites/v4/*'
mv "${part}" "${target}.new/world.pmtiles"
{
    echo "source=${SOURCE}"
    echo "build=${BUILD}"
    echo "published_size=${SIZE}"
    echo "published_md5=${MD5}"
    echo "bbox=${BBOX:-world}"
    echo "maxzoom=${MAXZOOM:-all}"
    echo "assets=protomaps/basemaps-assets@${ASSETS_COMMIT}"
    echo "fetched_at=$(date -u +%FT%TZ)"
    "${PMTILES}" show "${target}.new/world.pmtiles" 2>/dev/null | grep -E "^(min|max)zoom|^bounds|^tile type|^tile compression" || true
} > "${target}.new/BUILD.txt"
chown -R "${APP_OWNER}" "${target}.new"
find "${target}.new" -type d -exec chmod 755 {} +
find "${target}.new" -type f -exec chmod 644 {} +
rm -rf "${target}"; mv "${target}.new" "${target}"
chmod 755 "${BASEMAP_ROOT}" "${BASEMAP_ROOT}/builds"

previous="$(readlink "${BASEMAP_ROOT}/current" 2>/dev/null || true)"
ln -sfn "builds/$(basename "${target}")" "${BASEMAP_ROOT}/current.next"
mv -T "${BASEMAP_ROOT}/current.next" "${BASEMAP_ROOT}/current"
[ -e "${LOUPE_BASEMAP_LINK}" ] || ln -sfn "${BASEMAP_ROOT}" "${LOUPE_BASEMAP_LINK}"
say "live: ${BASEMAP_ROOT}/current -> builds/$(basename "${target}") ($(du -sh "${target}" | cut -f1))"
if [ -n "${previous}" ] && [ "${previous}" != "builds/$(basename "${target}")" ]; then
    rm -rf "${BASEMAP_ROOT:?}/${previous}"
    say "removed the previous copy ${previous}"
fi

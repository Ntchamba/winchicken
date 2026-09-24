#!/usr/bin/env bash
# Builds the platform-independent part of the installer: resources/ with the Docker images
# (so a farm needs no internet to install Winchicken itself), the production compose file and
# the version. The launcher binary and the .exe/.pkg wrapping are added per platform (CI).
#
# Usage: installer/scripts/build-bundle.sh [OUT_DIR]      (default: installer/dist/bundle)
# Version: frontend/package.json "version" — the number the app already shows in its sidebar.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:-$ROOT/installer/dist/bundle}"
VERSION="$(sed -n 's/^  "version": "\(.*\)",$/\1/p' "$ROOT/frontend/package.json")"
[ -n "$VERSION" ] || { echo "version introuvable dans frontend/package.json" >&2; exit 1; }

PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"
IMAGES=(
  "winchicken/backend:$VERSION"
  "winchicken/frontend:$VERSION"
  # Must match docker-compose.prod.yml exactly: the launcher starts it with --pull never.
  "postgres:16-alpine"
  "redis:7-alpine"
)

echo "== Winchicken $VERSION ($PLATFORM) -> $OUT"
docker build --platform "$PLATFORM" -t "winchicken/backend:$VERSION" "$ROOT/backend"
docker build --platform "$PLATFORM" --target prod -t "winchicken/frontend:$VERSION" "$ROOT/frontend"
docker pull --platform "$PLATFORM" postgres:16-alpine
docker pull --platform "$PLATFORM" redis:7-alpine

rm -rf "$OUT/resources"
mkdir -p "$OUT/resources/images"
cp "$ROOT/docker-compose.prod.yml" "$OUT/resources/"
echo "$VERSION" > "$OUT/resources/VERSION"
printf '%s\n' "${IMAGES[@]}" > "$OUT/resources/images/images.txt"
# gzip -6: the images are mostly compressed layers already; higher levels cost minutes for ~1 %.
docker save "${IMAGES[@]}" | gzip -6 > "$OUT/resources/images/winchicken-images.tar.gz"

du -sh "$OUT/resources/images/winchicken-images.tar.gz"
echo "== prêt : $OUT/resources"

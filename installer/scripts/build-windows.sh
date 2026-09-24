#!/usr/bin/env bash
# Builds Winchicken-Setup-<version>.exe on Linux, with Docker only (no Windows machine, no sudo):
# 1. the bundle (images + compose + VERSION), 2. the launcher cross-compiled for Windows in a
# Rust container, 3. the NSIS installer in a Debian container. CI runs this same script.
#
# Usage: installer/scripts/build-windows.sh [OUT_DIR]     (default: installer/dist)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:-$ROOT/installer/dist}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
VERSION="$(sed -n 's/^  "version": "\(.*\)",$/\1/p' "$ROOT/frontend/package.json")"

"$ROOT/installer/scripts/build-bundle.sh" "$OUT/bundle"

echo "== launcher (x86_64-pc-windows-gnu)"
docker run --rm -v "$ROOT/installer/launcher":/src -w /src -e CARGO_TARGET_DIR=/src/target-win \
  rust:1-slim-bookworm sh -c '
    apt-get update -qq >/dev/null && apt-get install -y -qq gcc-mingw-w64-x86-64 >/dev/null &&
    rustup target add x86_64-pc-windows-gnu >/dev/null 2>&1 &&
    cargo build --release --locked --target x86_64-pc-windows-gnu'

echo "== installateur NSIS"
docker run --rm -v "$ROOT/installer":/installer -v "$OUT":/out -w /installer/windows debian:trixie-slim sh -c "
    apt-get update -qq >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nsis >/dev/null &&
    makensis -V2 -DVERSION=$VERSION -DBUNDLE=/out/bundle \
      -DLAUNCHER=/installer/launcher/target-win/x86_64-pc-windows-gnu/release/winchicken-launcher.exe \
      -DOUTDIR=/out winchicken.nsi"

ls -la "$OUT/Winchicken-Setup-$VERSION.exe"

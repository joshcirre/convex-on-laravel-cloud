#!/usr/bin/env bash
#
# Laravel Cloud build command for the self-hosted Convex backend.
#
# Downloads the prebuilt `convex-local-backend` binary (Rust, from
# github.com/get-convex/convex-backend releases) into ./bin. Cloud keeps build
# filesystem changes in the image, so start.sh can run it directly.
#
# CONVEX_BACKEND_VERSION pins the release tag. Keep it in step with the
# `convex` npm package the web app deploys with (see upgrading notes in the
# convex-backend repo before bumping).
#
set -euo pipefail
cd "$(dirname "$0")"

VERSION="${CONVEX_BACKEND_VERSION:-precompiled-2026-09-26-27ef234}"

case "$(uname -m)" in
  x86_64 | amd64) target="x86_64-unknown-linux-gnu" ;;
  aarch64 | arm64) target="aarch64-unknown-linux-gnu" ;;
  *)
    echo "build: unsupported architecture $(uname -m)" >&2
    exit 1
    ;;
esac

# Diagnostics: the binary needs glibc >= 2.35, and "use node" actions need
# node v20/v22/v24 on PATH at runtime.
echo "build: arch=$(uname -m) target=$target version=$VERSION"
echo "build: $(ldd --version 2>&1 | head -1 || echo 'ldd unavailable')"
echo "build: node $(node --version 2>/dev/null || echo 'not found')"

url="https://github.com/get-convex/convex-backend/releases/download/${VERSION}/convex-local-backend-${target}.zip"
zip="$(mktemp -d)/backend.zip"
echo "build: downloading $url"
curl --fail --location --silent --show-error --retry 3 -o "$zip" "$url"

mkdir -p bin
rm -f bin/convex-local-backend
# unzip isn't guaranteed in the build image; fall back to python3's zipfile.
if command -v unzip >/dev/null 2>&1; then
  unzip -o -q "$zip" -d bin
elif command -v python3 >/dev/null 2>&1; then
  python3 -m zipfile -e "$zip" bin
else
  echo "build: need unzip or python3 to extract the backend binary" >&2
  exit 1
fi
chmod +x bin/convex-local-backend
rm -f "$zip"

# Fails here (instead of at boot) if the image's glibc is too old.
bin/convex-local-backend --help >/dev/null
echo "build: convex-local-backend ready"

#!/usr/bin/env bash
# Writes apps/api/requirements.txt, the exact version and hashes of every Python package the API
# image installs (docs/adr/0044). The image installs only what this file says, so a new release of a
# library reaches production only after someone runs this script, commits the result and CI passes.
#
#   apps/api/scripts/lock.sh            # after editing a dependency in a pyproject.toml: keeps
#                                       # every other version as it is
#   apps/api/scripts/lock.sh --upgrade  # takes the newest version each pyproject.toml allows
#
# It resolves inside the image's own base (Linux, Python 3.13, x86-64 like the server), so the
# versions are the ones that run in production. Needs Docker.
set -euo pipefail

cd "$(dirname "$0")/../../.."
base="$(sed -n 's/^FROM \(python:[^ ]*\) AS build$/\1/p' apps/api/Dockerfile)"
if [[ -z "$base" ]]; then
  echo "no 'FROM python:... AS build' line in apps/api/Dockerfile" >&2
  exit 1
fi
# macOS ships bash 3.2, where an empty array trips `set -u`: one word or none.
upgrade=""
case "${1:-}" in
  "") ;;
  --upgrade) upgrade="--upgrade" ;;
  *) echo "usage: $0 [--upgrade]" >&2; exit 2 ;;
esac

# uv resolves; its own version is pinned so two runs on the same inputs agree.
docker run --rm --platform linux/amd64 -v "$PWD:/src" -w /src/apps/api "$base" sh -euc '
  pip install --quiet --root-user-action=ignore --disable-pip-version-check "uv==$0"
  uv pip compile requirements.in $1 \
    --python-version 3.13 --generate-hashes \
    --no-emit-package zyrcle-protocol --no-emit-package zyrcle-sim --no-emit-package zyrcle-api \
    --custom-compile-command "apps/api/scripts/lock.sh" \
    --output-file requirements.txt
  rm -rf build ../../packages/protocol/build ../../device/simulator/build
' "${UV_VERSION:-0.13.9}" "$upgrade"
echo "apps/api/requirements.txt: $(grep -c '^[a-z0-9]' apps/api/requirements.txt) packages"

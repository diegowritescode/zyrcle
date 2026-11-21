#!/usr/bin/env bash
# Install the pinned Avalanche CLI into ~/bin (no sudo), verifying the release checksum.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source-path=SCRIPTDIR/.. source=params.env
source "$here/params.env"

v="${AVALANCHE_CLI_FUJI_VERSION:-1.9.7}"
os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"; case "$arch" in x86_64) arch=amd64 ;; aarch64|arm64) arch=arm64 ;; esac
asset="avalanche-cli_${v}_${os}_${arch}.tar.gz"
base="https://github.com/ava-labs/avalanche-cli/releases/download/v${v}"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/$asset" "$base/$asset"
curl -fsSL -o "$tmp/checksums.txt" "$base/avalanche-cli_${v}_checksums.txt"
(cd "$tmp" && grep " $asset\$" checksums.txt | sha256sum -c -)
mkdir -p "$HOME/bin"
tar -xzf "$tmp/$asset" -C "$tmp" avalanche
install -m 0755 "$tmp/avalanche" "$HOME/bin/avalanche"
"$HOME/bin/avalanche" --version

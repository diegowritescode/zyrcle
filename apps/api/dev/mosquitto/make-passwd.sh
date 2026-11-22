#!/usr/bin/env bash
# Development broker credentials: user "api" and the simulated devices ctr-0001..ctr-0004, all with
# the password "dev-password". Never use these outside a laptop or CI.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
rm -f "$here/passwd"; touch "$here/passwd"
for user in api ctr-0001 ctr-0002 ctr-0003 ctr-0004; do
  docker run --rm -v "$here:/m" eclipse-mosquitto:2 mosquitto_passwd -b /m/passwd "$user" dev-password
done
chmod 644 "$here/passwd"

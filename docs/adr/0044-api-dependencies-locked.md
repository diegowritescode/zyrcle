# ADR 0044: The API image installs a lock file, with exact versions and hashes

- Status: accepted (2026-11-27)
- Decided by: Diego asked on 2026-11-27 to do this first, before M20 and M21, as the first item in
  the order Claude proposed ("continuemos con tu orden en un bloque grande"). Claude chose how
  (uv, resolving inside the image's base, pip check in the build). Diego confirmed it on
  2026-11-27: "confirmo los adrs y autorizo unir a main y desplegar".

## Context
`apps/api/pyproject.toml` gives each dependency a lower bound, and the Dockerfile installed them
with `pip install`, so every image took the newest release of each library. On 2026-11-26
sentry-sdk 3.0.1 reached production this way, and the API stopped starting as soon as its Sentry
DSN was set ([ADR 0033](0033-error-reports-and-uptime.md), amendments). Sentry was capped below 3;
the other 76 packages could do the same at any build. CI did not protect against it: it also
installed the newest versions, on the day it ran, which need not be the day the image is built.

## Decision
- **`apps/api/requirements.txt` is the lock file.** It names every package the API image installs,
  dependencies of dependencies included, at one exact version, with the SHA-256 hashes of the
  files PyPI publishes for it. The image installs it with `pip install --require-hashes`, so pip
  refuses any other version and any file whose content changed. Our three packages (protocol,
  simulator, API) are installed on top with `--no-deps`.
- **`pip check` runs in the image build.** When a `pyproject.toml` asks for a package or a version
  the lock file does not have, the build fails, in CI before it can reach production.
- **`apps/api/scripts/lock.sh` writes the lock file.** It runs uv (pinned, 0.13.9) inside the
  image's own base image (Linux, Python 3.13, x86-64), so the versions are the ones that run in
  production. Without arguments it keeps every version it can and changes only what a
  `pyproject.toml` edit requires; `--upgrade` takes the newest version each `pyproject.toml`
  allows. `apps/api/requirements.in` lists what is resolved: the three packages, as in the image.
- **CI installs the same versions.** The `api` and `e2e` jobs install `requirements.txt` first and
  then `requirements-dev.txt`, so the tests run against what production runs. The test tools
  (pytest, ruff and the like) stay unlocked: they never reach the image.
- **The first lock file is production as it was.** The packages are the ones in the image of
  `0d41852`, which production ran on 2026-11-26, checked with `pip freeze`. Only httpx was newer
  on PyPI (0.29.0); it stays at 0.28.1. An image built from the lock file has the same 77 packages
  at the same versions.
- **Updates are deliberate.** Someone runs `lock.sh --upgrade`, reads the diff, and the change goes
  through CI like any other. Dependabot is not used for this file: its support for files written
  by uv could not be confirmed on 2026-11-27.

## Consequences
- A new release of a library reaches production only after a commit that changes the lock file.
  The sentry-sdk 3.0 outage cannot repeat by itself.
- Security fixes in dependencies arrive only when someone runs `lock.sh --upgrade`. GitHub's
  dependency graph reads `requirements.txt`, so its security alerts point at the exact versions
  that run.
- To hold one package at a version, replace its block in `requirements.txt` (the version line and
  its hashes) with a bare `name==version` line and run `lock.sh`. Changing only the version number
  keeps the old hashes, and the image build then refuses the file (tried on 2026-11-27).
- The build tools for our three packages (setuptools) are still fetched at their newest version
  while the image is built. They run only during the build and do not end up in what the API
  imports.
- The lower bounds in `pyproject.toml`, and the sentry-sdk cap below 3, stay: they say what the code
  needs, and `pip check` holds the lock file to them.

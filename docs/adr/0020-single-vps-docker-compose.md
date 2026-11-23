# ADR 0020: Host everything on one VPS with Docker Compose; images by full commit SHA

- Status: accepted (2026-11-22), recorded 2026-11-22
- Decided by: Claude proposed; Diego provided the VPS (`aitera-vps`, shared with his other
  projects behind its Traefik) and the `deviego.xyz` domain.

## Context
The project needs a public demo, its own L1 validator and a backend with a database and a broker,
on a personal budget.

## Decision
- One VPS runs the L1 node (`infra/l1`) and the application stack (`deploy/compose.yml`): Postgres,
  Mosquitto, the API, the simulator and the web app, behind the VPS's existing Traefik with TLS.
  Domains: `zyrcle.deviego.xyz` (web), `zyrcle-backend.deviego.xyz` (API),
  `rpc.zyrcle.deviego.xyz` (public RPC).
- GitHub Actions builds the images after CI passes on `main` and pushes them to GHCR, tagged with
  the **full 40-character commit SHA**; `latest` is never used. `deploy/deploy.sh <api-sha> <web-sha>`
  is idempotent: pull, migrate, seed, start.
- The host has no `python3-venv` and installing it needs sudo, so the backend's CLI runs inside
  `python:3.13-slim` (`infra/l1/scripts/zyrcle-api-docker.sh`). Installing anything on the VPS
  needs Diego's approval (ADR 0022).

## Consequences
- One machine is a single point of failure for the demo and the validator.
- Nothing backs up the database yet (roadmap M7).
- Every running container can be traced to the exact commit that built it.

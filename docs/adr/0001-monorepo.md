# ADR 0001: One monorepo with the hackathon history imported

- Status: accepted (2026-11-21)

## Context
The hackathon produced two repos, `zyrcle-backend` and `zyrcle-frontend`, the second one also
holding the contracts. The rebuild adds a mobile app, a device simulator and L1 infrastructure.
Spread over separate repos, a protocol change would have to land in several places at once.

## Decision
One repo, `zyrcle`, with `apps/api`, `apps/web`, `apps/mobile`, `contracts`, `device` and `infra`.
Both old repos are imported with their full history (`git filter-repo` into subdirectories) and the
import point is tagged `v0-hackathon`.

## Consequences
- One CI run checks every component against the same commit.
- The git history shows where the project came from, which is part of the story it tells.
- The two old repos get archived once this one is published.

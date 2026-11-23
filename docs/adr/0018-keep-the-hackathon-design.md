# ADR 0018: Keep the hackathon's visual design; Spanish copy without invented numbers

- Status: accepted (2026-11-22), recorded 2026-11-22
- Decided by: Diego (he likes the design and asked that nothing visual replace it); Claude decided
  the copy rules.

## Context
The hackathon web app had a finished look (eco forest, lime and emerald palette, shadcn/ui
components, 3D models) but showed made-up figures and English leftovers from the generator it was
started with.

## Decision
- The web app keeps the hackathon design. New screens (the dashboards of hosts and sites, the
  operator console) and the mobile app use the same palette and components.
- User-facing copy is Spanish (Colombia), plain and without jargon.
- No invented figures: every number on a page comes from the API (platform totals, dashboards), or
  is not shown.

## Consequences
- The mobile app reproduces the palette with React Native `StyleSheet` (ADR 0024).
- Pages show empty states until there is real data.

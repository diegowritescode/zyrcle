# ADR 0024: Monorepo tooling: no npm workspaces, a shared TypeScript client, StyleSheet on mobile

- Status: accepted (2026-11-22), recorded 2026-11-22
- Decided by: Claude, while building phase 3.

## Context
The web app (Vite, React 18) and the mobile app (Expo SDK 58, React 19) need the same API client,
Sign-In with Ethereum message, QR parsing and Spanish labels. npm workspaces hoist dependencies and
two React majors in one tree break both apps. The hackathon palette must also exist on mobile.

## Decision
- No npm workspaces. Each app has its own `package.json` and lockfile.
- `packages/client` holds the shared TypeScript (no runtime dependencies) and is consumed as a
  `file:` dependency; Metro is told to watch the folder (`apps/mobile/metro.config.js`).
- Python packages are installed per app (`apps/api`, `packages/protocol`, `device/simulator`), each
  with its own `pyproject.toml`; the API's virtualenv installs the other two in editable mode.
- Mobile styles use React Native `StyleSheet` with the eco palette (`apps/mobile/src/ui/theme.ts`).
  NativeWind was dropped because it did not work with Reanimated 4.

## Consequences
- A change to `packages/client` is picked up by both apps without publishing anything.
- Each app upgrades its own dependencies independently.

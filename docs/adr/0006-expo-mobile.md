# ADR 0006: Expo (React Native) for the resident app

- Status: accepted (2026-11-21)

## Context
The resident flow needs the camera (QR), push notifications and secure key storage. The team
already works in TypeScript and React.

## Decision
Build `apps/mobile` with Expo. The wallet key is generated on the device and kept in secure
storage. The resident sees balances in COP and never handles a seed phrase.

## Consequences
- Native capabilities without a separate Swift/Kotlin codebase.
- Key recovery needs a design of its own before launch.

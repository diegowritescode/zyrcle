# ADR 0005: MQTT between container and backend, WebSocket between backend and app

- Status: accepted (2026-11-21)

## Context
The backend has to command the container (open the lock) and receive a stream of readings, over
connections that may drop. Plain HTTP from the board only lets the device ask; the server cannot
push.

## Decision
- Container ↔ backend: MQTT over TLS, per-device credentials, QoS 1, signed and sequenced payloads.
- Backend ↔ resident app: WebSocket for the live session.
- The phone never talks to the container directly.

## Consequences
- Adds a broker (Mosquitto) to the stack.
- The device protocol is documented in `device/` and implemented first by the simulator.

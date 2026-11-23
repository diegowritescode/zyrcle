# ADR 0026: v1 is one university campus closing the loop, delivered in two reviewed blocks

- Status: accepted (2026-11-22)
- Decided by: Diego chose to start with a university and to work in two blocks he reviews; Claude
  proposed the scope and the milestones.

## Context
After phases 0 to 5, Zyrcle paid for deposits but nothing happened to the material afterwards, ZYR
could not be spent, and nothing gave the host a reason to say yes. Diego has little time to follow
the work step by step.

## Decision
- v1 is a pilot-ready system that closes its loop at least once on a university campus: deposit,
  collection, sale, bank match, settlement, spending on campus, and a monthly impact certificate for
  the host ([roadmap](../roadmap-v1.md)). The first host is a university with several campuses that
  Diego is joining as a student; the public documents do not name it.
- Hosts get a share of each sale (ADR 0013) and verifiable impact certificates. Tradable carbon or
  plastic credits come in v2, aggregating sites, because they need an approved methodology, a
  third-party audit and scale.
- Delivery in two blocks. Block 1: M1 to M4 (hosts and sites, collection, sale and settlement, the
  operator console). Block 2: M5 to M7 (impact certificates, spending on campus, pilot readiness).
  Claude builds each block on its own; Diego reviews, confirms decisions and approves the deploy.

## Consequences
- Each block ends with a list of decisions to confirm (ADR 0025).
- Hardware (a staffed weighing station) is a parallel track that can be a student project.

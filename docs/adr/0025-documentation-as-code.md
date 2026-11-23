# ADR 0025: Documentation lives in the repository and changes with the code

- Status: accepted (2026-11-22)
- Decided by: Diego asked for complete, always up-to-date documentation from the project's start;
  Claude proposed the structure.

## Context
Work happens in autonomous blocks that Diego reviews afterwards. He needs to see what exists, how it
runs and why it is that way, without relying on chat history.

## Decision
- Documentation is Markdown in `docs/` (map in `docs/README.md`) and a README per app.
- Diagrams are Mermaid blocks, so GitHub draws them and they change in the same diff as the code.
- Every decision has an ADR, with who decided and how it was confirmed (`docs/adr/README.md`).
- A commit that changes behaviour, schema, configuration or operation updates the affected
  documents in the same commit.
- Repository documents are in English; the apps' user-facing copy is in Spanish (ADR 0018).

## Consequences
- Reviews check documentation like code.
- Decisions taken before this log existed were recorded afterwards (ADRs 0016 to 0024), with the
  date they were taken.

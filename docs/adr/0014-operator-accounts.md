# ADR 0014: Operator accounts and the operations console

- Status: accepted (2026-11-22)
- Decided by: Claude proposed in v1 block 1; Diego answered "sí, ok, te autorizo" to the list of
  block 1 decisions on 2026-11-22.

## Context
Every operator action (reviewing deposits, resolving incidents, recording sales, confirming the bank
match) went through the API with one shared token. Nobody could tell who did what, the token could
not be taken away from one person, and there were no screens: a pilot cannot be run like that
([roadmap](../roadmap-v1.md), M4). Recording a sale now mints ZYR (ADR 0013), so the person who
confirmed it must be on record.

## Decision
- **Named operators, signed in by email code.** An `operator` has an email, a name, a role
  (`admin` or `operator`) and can be deactivated. They sign in with a six-digit code sent to that
  email through the existing outbox and Resend (ADR 0010): codes are stored as HMACs, last 10
  minutes, die after 5 wrong guesses, and are limited to one a minute and ten a day per address.
  Asking for a code answers the same whether or not the address belongs to an operator.
- **Operator sessions are separate from participants'.** The JWT says `role: operator`, lasts 8
  hours, and is checked against the operator's row on every request, so deactivating someone ends
  their session at once. A participant's token is never accepted for operator routes, nor the
  reverse.
- **Every action is signed with the operator's email.** Reviews, incident resolutions, recorded
  and confirmed sales store who did them.
- **The shared token stays, for machines.** Deploy scripts, the seed and the tests use it; it acts
  as an admin named `token`. People use their own accounts. Only admins add, deactivate or promote
  operators; the first admin is added with the shared token.
- **The console is part of the web app** (`/console`), in the hackathon design: a summary, the
  review queue, incidents, collections and bags (with printable labels), sales with the bank match
  and the settlement report, hosts and sites, and prices.

## Consequences
- The shared token is now a deployment secret only; leaking it is as serious as before, and it
  should be rotated once operators have their own accounts.
- An operator needs a working mailbox to sign in. An admin who loses theirs is recovered with the
  shared token.

## Details decided while building it (v1 block 1, same confirmation)
- Operators sign in again after **8 hours**; participants' sessions last 24 hours.
- An admin cannot demote or deactivate themselves, so the console always keeps one admin.
- The console keeps the operator's session in the browser's storage so a reload does not sign them
  out; it is cleared on "Salir" or when the server answers 401.

## Amendments
- **2026-11-22, Claude (documentation review):** with email off, a sign-in code is not written to the
  email outbox at all, so no plaintext code waits there.
- **2026-11-22, Claude:** a wrong code answers 401 at operator sign-in (an authentication failure)
  and 422 on participants' email routes, where the caller is already signed in.

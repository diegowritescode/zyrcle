# ADR 0017: Proprietary license, all rights reserved

- Status: accepted (2026-11-22), recorded 2026-11-22
- Decided by: Diego ("que nadie lo pueda vender, es un proyecto cerrado").

## Context
The repository is public so that it can be read and evaluated (portfolio, partners, a future pilot
host). Without a license, rights are reserved by default but intent is unclear; an open-source
license would let anyone run or sell it.

## Decision
- `LICENSE` is proprietary: the code may be read and evaluated, not used, copied, modified or sold
  without written permission.
- Solidity files declare `SPDX-License-Identifier: UNLICENSED`. Third-party libraries keep their own
  licenses.

## Consequences
- Contributions from outside need an explicit agreement first.
- A pilot partner who wants to run it needs a written license from Diego.

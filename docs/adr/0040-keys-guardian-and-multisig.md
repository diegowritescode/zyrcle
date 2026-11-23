# ADR 0040: The guardian gets its own key; admin powers move to a 2-of-3 Safe

- Status: proposed (2026-11-23)
- Decided by: Claude, building block 3 (M17) under ADR 0030, which Diego confirmed. Not yet
  confirmed. The guardian part is built; the multisig part waits for Diego's choice of signers.

## Context
One L1 admin key, kept on the VPS, holds every admin power on ZyrcleChain:

| Power | Where |
|---|---|
| Who may mint ZYR | NativeMinter precompile `0x0200…0001` (admin) |
| Who may deploy contracts | ContractDeployerAllowList `0x0200…0000` (admin) |
| Gas price rules | FeeManager `0x0200…0003` (admin) |
| Where fees go | RewardManager `0x0200…0004` (admin) |
| Who validates the chain | Validator manager `0x0Feedc0de…` (owner) |
| Treasury shares, pause, roles | Treasury `DEFAULT_ADMIN_ROLE` |
| The factory's guardian | AccountFactory `DEFAULT_ADMIN_ROLE` |

Whoever takes that file controls the chain and the money. The AccountFactory guardian, which relays
every signed payment, also shared the oracle key (ADR 0028 asked to separate it).

## Decision
- **The guardian gets its own key** (built). `zyrcle-api keys new` writes a new key file readable only
  by its owner and prints just the address; the API mounts it as `guardian.key`, defaulting to the
  oracle key until runbook 9.13 moves the factory's guardian to it; the health report watches its
  gas. Keys that must sign on their own stay on the server with the least power each needs: the
  oracle (advances, capped by the contract), the operator (sales, settlements, anchors) and the
  guardian (recoveries with a 48-hour wait, relayed payments the phone signed).
- **Every admin power moves to a Safe** (to build once the signers are chosen):
  - Audited Safe contracts, version 1.4.1, deployed on ZyrcleChain; a Safe with three owners and a
    threshold of two.
  - The L1 admin key grants each power in the table to the Safe; the Safe, with two signatures,
    proves it can act; then the Safe removes the admin key from each precompile and the admin key
    renounces its contract roles. The validator manager's ownership is transferred.
  - Safe transactions are proposed from the command line and signed by each owner, with a browser
    wallet in the console or offline with a key file, depending on what the owners use.
  - The L1 admin key then leaves the VPS for Diego's offline inventory, encrypted (ADR 0034).
- **What stays out:** the P-Chain key that tops up the validator's balance is not an EVM account and
  cannot be a Safe; it stays offline, used a few times a year.

## Consequences
- After the move, no single key on the server can mint, change roles, change fees or touch the
  validators.
- Every admin change needs two of three people and a few minutes; an emergency pause too.
- Losing two of the three signer keys locks the admin powers for good: the signers need backups.

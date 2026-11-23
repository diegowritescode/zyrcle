# ADR 0040: The guardian gets its own key; admin powers move to a 2-of-3 Safe

- Status: accepted (2026-11-23)
- Decided by: Claude, building block 3 (M17) under ADR 0030, which Diego confirmed. The guardian
  part is built; the multisig part follows, with the signers he chose. Diego confirmed it on
  2026-11-23: "confirmo todos los adrs". For the multisig he chose the signers the same day: "vamos
  con la opcion 3, una mezlca entre mi metamask, mi celular y una clave en papel".

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

## Amendments
- **2026-11-23, Claude (building the multisig with the signers Diego chose):**
  - Safe v1.4.1 is vendored unchanged in `chain/lib/safe-smart-account` and compiled with the
    project's solc 0.8.30 (the audited release was built with 0.7.6; the source is the same).
  - Eight powers, not seven: the validator manager is a transparent proxy whose proxy admin, able to
    upgrade it, is also owned by the admin key. The handover reads the proxy admin from the EIP-1967
    slot. Precompiles the chain does not enable (the transaction allow list) are skipped: an enabled
    one reports the code `0x01`.
  - The order keeps a way back until the end: (1) the admin key grants the Safe every role and
    precompile admin, (2) the Safe proves it acts, with two signatures, by granting itself a role it
    already has, (3) the ownerships move, (4) the Safe takes the admin key off the precompiles in one
    batched transaction (MultiSendCallOnly), (5) the admin key renounces its contract roles, which
    the command refuses while the Safe does not hold them.
  - Proposals travel as JSON files carrying the EIP-712 data and the Safe's transaction hash; a
    changed byte is refused. The web app's `/multisig` page signs with the wallet's
    `eth_signTypedData_v4`, adding the ZyrcleChain network if needed; the command line signs with a
    key file or with a key typed at a prompt (the paper key). Both check that a signature is an
    owner's over that proposal.
  - Tested on anvil (two signatures, the threshold, tampering, the five steps leaving the admin key
    with nothing) and end to end in a browser with a stand-in wallet.
- **2026-11-23, Diego (the handover, done):** with his approval ("autorizo desplegar el Safe y mover
  los poderes en Fuji") the Safe `0x607c011C6921eA75C1e38223a5E5514eDbA7E43b` was deployed with his Core wallet
  (`0xEBf7…656F`), his phone's MetaMask (`0xA8a5…1646`) and a paper key (`0x8548…8C6F`), threshold
  two. He signed both proposals with Core on the multisig page and with the paper key on the
  command line: the proof (`0xddeed673…1fe7`) and the removal of the admin key from the
  precompiles (`0x6ba1915b…0ecf`). Checked on the public RPC afterwards: the Safe holds the eight
  powers, the L1 admin key none, and the Treasury still mints. The signed proposals are in
  `infra/l1/safe/`. The admin key keeps the genesis ZYR float for gas; it is moved off the VPS once
  that float has another holder. Changing the guardian is now a Safe proposal
  (`safe propose --what guardian`).


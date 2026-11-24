# ZyrcleChain contracts

Foundry project for the contracts that run on ZyrcleChain. Design and reasons:
[ADR 0007](../docs/adr/0007-on-chain-treasury.md).

| Contract | Purpose |
|---|---|
| `src/Treasury.sol` | Mints ZYR (native coin, 1 ZYR = 1 COP) only against recorded seed capital and confirmed sales; pays advances, settlements, collectors and hosts; holds merchants' redemptions until the operator pays the pesos (ADR 0029) |
| `src/ZyrcleAccount.sol` | A resident's account: holds their ZYR, obeys their phone key, and moves to a new key after a 48-hour guardian recovery the owner can cancel ([ADR 0010](../docs/adr/0010-smart-accounts-and-recovery.md)) |
| `src/AccountFactory.sol` | Creates accounts as CREATE2 clones whose address depends only on the first owner key; names the guardian of every account |
| `src/SafeImports.sol` | Deploys nothing: it names the Safe contracts so they compile with the project and their artifacts are exported ([ADR 0040](../docs/adr/0040-keys-guardian-and-multisig.md)) |
| `lib/safe-smart-account/` | Safe v1.4.1, vendored unchanged ([its README](lib/safe-smart-account/README.md)): the multisig that holds every admin power of ZyrcleChain |

The hackathon's Hardhat contracts were removed ([ADR 0019](../docs/adr/0019-remove-legacy-code.md));
they are at the tag `v0-hackathon` ([history](../docs/history.md)).

```bash
forge soldeer install
forge test            # unit, fuzz and invariant tests
python3 export-artifacts.py   # refresh the ABI/bytecode the backend deploys (CI checks this)
```

`export-artifacts.py` writes the Treasury, AccountFactory, ZyrcleAccount and the four Safe
contracts (SafeL2, SafeProxyFactory, CompatibilityFallbackHandler, MultiSendCallOnly) into
`apps/api/src/zyrcle_api/contracts`, and two test mocks into `apps/api/tests/fixtures`.

## On ZyrcleChain (Fuji)

| | |
|---|---|
| Treasury | `0xd7052201140224018b123ecFF7b83B4251790Aeb` (on the NativeMinter allow list), with the host share ([ADR 0013](../docs/adr/0013-sale-and-settlement.md)) and redemptions ([ADR 0029](../docs/adr/0029-closed-loop-payments.md)). The earlier ones, `0xBc5035341C075CBd75508ff1a3a5EC0241e58201` and `0xB843946A42F2791B8b932F8c0205C9D277E351B1`, are no longer used and can no longer mint |
| Treasury admin (`DEFAULT_ADMIN_ROLE`: shares, pause, roles) | the admin Safe `0x607c011C6921eA75C1e38223a5E5514eDbA7E43b`, 2 of 3, since 2026-11-23 ([ADR 0040](../docs/adr/0040-keys-guardian-and-multisig.md)) |
| Operator | `0x528815e03Aa80b045B32840f3e26B394D0838d0d` |
| Oracle (backend) | `0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50` |
| Shares | 65% residents, 15% collector, 10% host, 10% operations ([ADR 0013](../docs/adr/0013-sale-and-settlement.md)) |
| Advance limits | 5,000 COP per deposit, 20,000 COP per resident per day |
| Seed capital | 1,000,000 COP, **simulated** (testnet) |
| AccountFactory | `0x0bE806Ca77340aA50AF6586CDC2FE2561668DaEA` (admin: the Safe; guardian: the oracle, on the deployer allow list, until it gets its own key) |
| ZyrcleAccount implementation | `0x008094fd22255b4d91846eb93042d0f05212b79f`, deployed by the factory |

Every address, the Safe's helpers included, is in [infra/l1/fuji.env](../infra/l1/fuji.env). On the
VPS, `infra/l1/scripts/zyrcle-api-docker.sh chain state` prints the live books.

## Deploying

Deployment goes through the backend so keys stay in files on the server
([docs/infrastructure.md](../docs/infrastructure.md), section 7.5). On a new chain, while the L1
admin key still holds the genesis powers:

```bash
cd ../apps/api
ZYRCLE_CHAIN_RPC_URL=... .venv/bin/zyrcle-api chain deploy \
  --admin-key-file <precompile admin key> --operator 0x... --oracle 0x...
ZYRCLE_CHAIN_RPC_URL=... ZYRCLE_TREASURY_ADDRESS=0x... .venv/bin/zyrcle-api chain seed \
  --operator-key-file <operator key> --amount-cop 1000000 --ref "bank transfer 123"
```

`chain deploy` makes the deploying key the Treasury's admin, grants the operator and oracle roles
and puts the Treasury on the NativeMinter allow list. The account factory takes the precompile
admin key too: it deploys the factory and puts the guardian on the ContractDeployerAllowList, since
accounts are deployed in the guardian's transactions. Then set `ACCOUNT_FACTORY` in `deploy/.env`.

```bash
ZYRCLE_CHAIN_RPC_URL=... .venv/bin/zyrcle-api chain accounts-deploy \
  --admin-key-file <precompile admin key> --guardian <oracle or guardian address>
```

Then the admin powers move to a Safe (`zyrcle-api safe …`, runbook 9.14 of
[docs/infrastructure.md](../docs/infrastructure.md)).

**On Fuji since 2026-11-23** no key file holds those powers: the L1 admin key is on no allow list
and the Safe has no key file. `chain deploy` and `chain accounts-deploy` cannot finish with it, and
their admin steps (allowing a deployer, enabling the minter, naming the guardian, retiring an old
Treasury) are Safe proposals signed by two owners (`safe propose --what call|guardian`, then
`safe exec`). The redeploy is not scripted yet (runbook 9.6).

Note: Foundry scripts cannot call Subnet-EVM precompiles. Their placeholder code (`0x01`) runs as an
`ADD` opcode in Foundry's local EVM and underflows the stack, which is why deployment is not a
`forge script`.

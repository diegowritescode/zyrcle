# ZyrcleChain contracts

Foundry project for the contracts that run on ZyrcleChain. Design and reasons:
[ADR 0007](../docs/adr/0007-on-chain-treasury.md).

| Contract | Purpose |
|---|---|
| `src/Treasury.sol` | Mints ZYR (native coin, 1 ZYR = 1 COP) only against recorded seed capital and confirmed sales; pays advances and settlements |
| `src/ZyrcleAccount.sol` | A resident's account: holds their ZYR, obeys their phone key, and moves to a new key after a 48-hour guardian recovery the owner can cancel ([ADR 0010](../docs/adr/0010-smart-accounts-and-recovery.md)) |
| `src/AccountFactory.sol` | Creates accounts as CREATE2 clones whose address depends only on the first owner key; names the guardian of every account |

The older Hardhat contracts in `../contracts` are the hackathon reconstruction, still used by the
legacy web app.

```bash
forge soldeer install
forge test            # unit, fuzz and invariant tests
python3 export-artifacts.py   # refresh the ABI/bytecode the backend deploys (CI checks this)
```

## On ZyrcleChain (Fuji)

| | |
|---|---|
| Treasury | `0xBc5035341C075CBd75508ff1a3a5EC0241e58201` (on the NativeMinter allow list), with the host share ([ADR 0013](../docs/adr/0013-sale-and-settlement.md)). The first one, `0xB843946A42F2791B8b932F8c0205C9D277E351B1`, is no longer used |
| Operator | `0x528815e03Aa80b045B32840f3e26B394D0838d0d` |
| Oracle (backend) | `0xd3cBCecC587Bd5f9504bFdea1D3B7e198E66ca50` |
| Shares | 65% residents, 15% collector, 10% host, 10% operations ([ADR 0013](../docs/adr/0013-sale-and-settlement.md)) |
| Advance limits | 5,000 COP per deposit, 20,000 COP per resident per day |
| Seed capital | 1,000,000 COP, **simulated** (testnet) |
| AccountFactory | `0x0bE806Ca77340aA50AF6586CDC2FE2561668DaEA` (admin: the L1 admin; guardian: the oracle, on the deployer allow list) |

On the VPS, `infra/l1/scripts/zyrcle-api-docker.sh chain state` prints the live books.

## Deploying

Deployment goes through the backend so keys stay in files on the server:

```bash
cd ../apps/api
ZYRCLE_CHAIN_RPC_URL=... .venv/bin/zyrcle-api chain deploy \
  --admin-key-file <precompile admin key> --operator 0x... --oracle 0x...
ZYRCLE_CHAIN_RPC_URL=... ZYRCLE_TREASURY_ADDRESS=0x... .venv/bin/zyrcle-api chain seed \
  --operator-key-file <operator key> --amount-cop 1000000 --ref "bank transfer 123"
```

The account factory takes the precompile admin key too: it deploys the factory and puts the
guardian on the ContractDeployerAllowList, since accounts are deployed in the guardian's
transactions. Then set `ACCOUNT_FACTORY` in `deploy/.env`.

```bash
ZYRCLE_CHAIN_RPC_URL=... .venv/bin/zyrcle-api chain accounts-deploy \
  --admin-key-file <precompile admin key> --guardian <oracle or guardian address>
```

Note: Foundry scripts cannot call Subnet-EVM precompiles. Their placeholder code (`0x01`) runs as an
`ADD` opcode in Foundry's local EVM and underflows the stack, which is why deployment is not a
`forge script`.

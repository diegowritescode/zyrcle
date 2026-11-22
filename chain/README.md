# ZyrcleChain contracts

Foundry project for the contracts that run on ZyrcleChain. Design and reasons:
[ADR 0007](../docs/adr/0007-on-chain-treasury.md).

| Contract | Purpose |
|---|---|
| `src/Treasury.sol` | Mints ZYR (native coin, 1 ZYR = 1 COP) only against recorded seed capital and confirmed sales; pays advances and settlements |

The older Hardhat contracts in `../contracts` are the hackathon reconstruction, still used by the
legacy web app.

```bash
forge soldeer install
forge test            # unit, fuzz and invariant tests
python3 export-artifacts.py   # refresh the ABI/bytecode the backend deploys (CI checks this)
```

Deployment goes through the backend so keys stay in files on the server:

```bash
cd ../apps/api
ZYRCLE_CHAIN_RPC_URL=... .venv/bin/zyrcle-api chain deploy \
  --admin-key-file <precompile admin key> --operator 0x... --oracle 0x...
ZYRCLE_CHAIN_RPC_URL=... ZYRCLE_TREASURY_ADDRESS=0x... .venv/bin/zyrcle-api chain seed \
  --operator-key-file <operator key> --amount-cop 1000000 --ref "bank transfer 123"
```

Note: Foundry scripts cannot call Subnet-EVM precompiles. Their placeholder code (`0x01`) runs as an
`ADD` opcode in Foundry's local EVM and underflows the stack, which is why deployment is not a
`forge script`.

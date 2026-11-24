# Security

What Zyrcle protects, from whom, and how. Keys by name and location are in
[infrastructure.md](infrastructure.md#6-secrets-and-keys); the rules about who may change
production are [ADR 0022](adr/0022-keys-secrets-and-production-changes.md).

## What matters most

| Asset | What an attacker gains | Main defences |
|---|---|---|
| Minting ZYR | Money out of nothing | The Treasury mints only while ZYR in circulation (minted minus retired) stays within `backing` (ADR 0007, 0029); only seed capital and bank-confirmed sales raise it, and paid redemptions lower it (ADR 0013, 0029); invariant tests |
| Payments | Moving a participant's ZYR | Only an EIP-712 `Execute` signed by the account's own key moves it; the account checks the signature and its nonce; the backend only relays (ADR 0029) |
| A participant's account | Their balance | Smart account controlled by a key in the phone's secure storage; recovery needs the verified email and waits 48 hours with warnings to the owner (ADR 0010) |
| Weights | Payment for material never delivered | Signed, sequenced device messages (protocol); verification score; container, collection and bag mass balances that open incidents (ADR 0012, 0013) |
| A certificate | Claiming impact twice or inventing it | Only sold material, one claim per gram, root anchored on chain and verifiable by anyone; with Pinata on, a permanent copy on IPFS whose CID is on chain too, so it can be checked without Zyrcle (ADR 0027 and its amendment) |
| Operator powers | Approving deposits, recording sales | Named operator accounts with email codes, sessions checked on every request, every action signed (ADR 0014) |
| ZyrcleChain's admin powers | Minting outside the backing rule, changing fees, deployers, validators, contract roles and the guardian | A 2-of-3 Safe holds all eight since 2026-11-23; its owners are Diego's Core wallet, his phone's MetaMask and a paper key; each proposal carries a plain description and the Safe's hash, and the signing page, the command line and the Safe itself check every signature (ADR 0040) |
| The backend's keys (oracle, operator, guardian) | Paying advances, recording fake sales, starting recoveries | Least power each: advances capped per deposit and per resident per day, sales tied to evidence and the bank match, recoveries wait 48 hours; the Safe can pause the Treasury, revoke a role or replace the guardian; the health report watches their gas (ADR 0007, 0010, 0013, 0040) |
| Backups | The whole database; with the keys bundle, every key on the server | Dumps are `0600` files in a `0700` folder; off-site copies are encrypted with `age` before they leave, the private key only with Diego, and the bucket's lock keeps a stolen token from deleting them (ADR 0028, 0034) |
| The API's capacity | Flooding emailed codes, sign-ins or writes | Rate limits per IP and per account in the API (ADR 0035), and Traefik's per-router limit |

## Static analysis of the contracts

Slither, run on 2026-11-23 against `chain/src` (tests and libraries excluded, informational findings
excluded). First run: 22 results in 7 detectors. After the Treasury of ADR 0029 (redemptions, and
the settlement books updated before minting): 21 results in 6 detectors; `reentrancy-no-eth` is gone.

| Detector | Where | Verdict |
|---|---|---|
| `arbitrary-send-eth` | `ZyrcleAccount._run` | By design: only the owner (directly or by signature) chooses the calls of their own account |
| `reentrancy-no-eth` (first run only), `reentrancy-events`, `calls-loop` | `Treasury.settleResidents`, `payCollector`, `payHost` | The external call is the NativeMinter precompile, which credits a balance and runs no code at the recipient, so it cannot re-enter. The Treasury of ADR 0029 updates `residentsSettled` before minting anyway (checks-effects-interactions) |
| `uninitialized-local` | `settleResidents` counters | Solidity starts them at zero; intended |
| (none) | `Treasury.refundRedemption` | Sends ZYR back with a low-level call, after marking the redemption refunded and lowering `pendingRedemptions`, and only the operator calls it |
| `unused-return` | `AccountFactory.createAccount`, `_signedByOwner` | The clone address is predicted and checked separately; the recover error is checked together with the signer |
| `timestamp` | `ZyrcleAccount` recovery and deadlines | Intended: the 48-hour recovery wait and signature deadlines are measured in block time; minutes of skew do not matter |

`SafeImports.sol` only names the vendored Safe v1.4.1 contracts, which the `lib` filter leaves out:
they are Safe's audited release, unchanged (ADR 0040).

Run it again before every redeploy:

```bash
python3 -m venv .slither && .slither/bin/pip install slither-analyzer
cd chain && ../.slither/bin/slither . --filter-paths "test|lib|dependencies" --exclude-informational
```

## Known weaknesses

- Every admin power (minting rights, deployers, fees, validators, contract roles) belongs to a
  2-of-3 Safe since 2026-11-23 (ADR 0040). Losing two of its three keys would lock them for good, so
  each needs its own backup. An emergency pause needs two signers too, which takes minutes.
- The oracle key is still also the recovery guardian. The API mounts a separate guardian key, but it
  points at the oracle key until runbook 9.13 of [infrastructure.md](infrastructure.md) runs
  (ADR 0028, 0040).
- The oracle and operator keys are hot: files on the VPS, mounted into the API. Whoever controls the
  server can use them within the limits above.
- The L1 admin key, which held every admin power until the handover, is still on the VPS. It holds
  none now, only the genesis gas float (about 48 ZYR); ADR 0040 moves it off once the float has
  another holder.
- The P-Chain key that funds the validator is a single key, still on the VPS; it is not an EVM
  account and cannot move to the Safe (ADR 0040 and its amendment).
- The demo router publishes live QR codes; a pilot with real containers must run without it
  (ADR 0028).
- One VPS and one validator. The encrypted off-site copy is built (ADR 0034) but waits for its
  bucket and age key, so on 2026-11-23 the backups still stay on the same machine.
- The off-site keys bundle will hold every key on the server and `deploy/.env`, encrypted; whoever
  had both a bundle and the private age key would hold the backend's keys, not the Safe's owners.
- Ticket photos go to Anthropic to be read, once its key is set (ADR 0038). They show a collection
  center's ticket, not participants; the photo, the reading and who accepted it stay in the database.
- Error reports go to Sentry, a third party, once its DSNs are set. They are scrubbed before they
  leave (emails, long hex strings, tokens, request bodies, cookies, headers, the user), but stack
  traces and account addresses remain (ADR 0033).
- The certificate page trusts the IPFS gateway to return the bytes of the CID read from the chain;
  it does not recompute the CID. Fetching the same CID from another gateway or an own IPFS node
  removes that trust (ADR 0027, amendment).
- A Pinata key from 2025 sat in a public `VITE_*` variable of the old web app ([history](history.md)).
  Diego revoked it on 2026-11-23; the rebuild uses a new JWT that stays on the VPS.

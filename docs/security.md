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

Run it again before every redeploy:

```bash
python3 -m venv .slither && .slither/bin/pip install slither-analyzer
cd chain && ../.slither/bin/slither . --filter-paths "test|lib|dependencies" --exclude-informational
```

## Known weaknesses

- The L1 admin key can mint ZYR directly through the NativeMinter, bypassing the Treasury. It is the
  most powerful key and lives on the VPS (infrastructure, section 6).
- The oracle key is also the recovery guardian; it should get its own key before the pilot
  (ADR 0028).
- The demo router publishes live QR codes; a pilot with real containers must run without it
  (ADR 0028).
- One VPS and one validator; backups stay on the same machine until an off-site copy is decided
  (ADR 0028).
- Error reports go to Sentry, a third party, when its DSNs are set. They are scrubbed before they
  leave (emails, long hex strings, tokens, request bodies, cookies, headers, the user), but stack
  traces and account addresses remain (ADR 0033).
- The certificate page trusts the IPFS gateway to return the bytes of the CID read from the chain;
  it does not recompute the CID. Fetching the same CID from another gateway or an own IPFS node
  removes that trust (ADR 0027, amendment).
- A Pinata key from 2025 sat in a public `VITE_*` variable of the old web app ([history](history.md)).
  Diego revoked it on 2026-11-23; the rebuild uses a new JWT that stays on the VPS.

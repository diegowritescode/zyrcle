# ADR 0029: Paying campus merchants with ZYR, and merchants redeeming it for pesos

- Status: accepted (2026-11-23)
- Decided by: Claude proposed in v1 block 2 (M6), following ADR 0004 (closed loop first). Diego confirmed it on 2026-11-23: "confirmo 0015, 0027, 0028 y 0029".
  Treasury v3 was deployed the same day.

## Context
A balance nobody can spend stops people from coming back. ADR 0004 chose a closed loop: participants
spend ZYR with partner merchants, and merchants turn ZYR back into pesos with the Treasury, with KYC
on businesses only. Participants' ZYR lives in smart accounts that are usually not deployed yet
(ADR 0010), and participants hold no gas.

## Decision
- **Merchants are participants with a role**, like collectors (ADR 0012). The operator names a
  participant's account a merchant with its business name, its tax id (NIT) as the KYC reference
  checked off line, and optionally the host whose campus it serves. ZYR paid to a merchant lands in
  that account.
- **A payment starts at the merchant.** The merchant creates a charge (amount in pesos, a short
  concept); the app shows a QR `zyrcle://p/<id>`, valid 10 minutes. The participant scans it, sees
  the merchant and the amount, and confirms.
- **The participant signs; the backend relays.** Confirming signs an EIP-712 `Execute` for the
  participant's smart account with one call: send the amount to the merchant's account. The backend
  relays it with the guardian key, which pays the gas, and deploys the account first if it is not
  deployed yet (the guardian is on the ContractDeployerAllowList, ADR 0010). The account checks the
  owner's signature and its nonce, so the backend can neither change the amount nor replay it. One
  payment at a time per participant, so nonces do not collide. The relay goes through an outbox, like
  every other call to the chain.
- **Redeeming retires ZYR, then the operator pays pesos.** A merchant asks to redeem an amount; the
  app signs an `Execute` that sends that ZYR to the Treasury's `redeem(ref)`. The Treasury holds it as
  a pending redemption. The operator pays the pesos to the merchant's bank account and confirms with
  the bank reference; the backend calls `settleRedemption`, which lowers `backing` by the amount and
  counts the ZYR as retired. If the operator cannot pay (unknown business, wrong amount),
  `refundRedemption` returns the ZYR to the account that sent it.
- **The supply rule becomes: ZYR in circulation never exceeds the pesos behind it.** In circulation
  means minted minus redeemed-and-paid. A pending redemption frees no minting capacity, so a refund
  can never break the rule. The invariant tests cover redeem, settle and refund.
- **The Treasury is redeployed once more** for redemptions, together with the settlement order that
  Slither flagged (update the books before minting, docs/security.md). The settlement worker already
  subtracts advances paid by an earlier Treasury (ADR 0013, amendments).
- **Who may redeem is checked off chain.** Anyone can send ZYR to `redeem`, but the operator only
  pays merchants with completed KYC; anything else is refunded.

## Consequences
- Participants never need gas or a deployed account to pay; the guardian key's gas pays for it, so
  its balance matters more (the health alert watches it, ADR 0028).
- A merchant waits for the operator's bank transfer to get pesos; until then their ZYR is pending.
- Paying from the web app is left for later; v1 pays from the phone.

# ADR 0010: Smart accounts with guardian recovery, proven by a recovery email

- Status: accepted (2026-11-22)
- Decided by: Diego chose the smart account and an email code sent with Resend; Claude designed it.

## Context
A resident's ZYR was paid to the address of a key that exists only in their phone's secure storage
(ADR 0006). Losing the phone lost the balance, the deposit history and the turns. Residents are not
crypto users: a seed phrase to write down is not an option, and "the phone is the account" is not
acceptable for money.

## Decision
- **The account is a contract, the phone is its key.** Each resident gets a `ZyrcleAccount`: a
  minimal clone (EIP-1167) created by `AccountFactory` at a CREATE2 address salted with the first
  owner key. The Treasury pays that address. Its owner (the phone key) can spend directly or sign an
  EIP-712 `Execute` that anyone submits, since the owner rarely holds ZYR for gas. It also answers
  ERC-1271, with messages wrapped in its own domain so a signature does not carry over to another
  account of the same key.
- **Deployed only when needed.** The address is known before any contract exists: the backend
  computes it offline (`chain.account_address`, checked against `AccountFactory.predict` in the
  tests) and the Treasury mints to it. The guardian deploys the account in the transaction of its
  first recovery. The ContractDeployerAllowList checks `tx.origin`, so the guardian key is put on it.
- **Guardian recovery with a 48-hour wait.** The guardian (a backend key; by default the oracle key)
  can call `startRecovery(newOwner)`. Anyone can call `finishRecovery()` once `RECOVERY_DELAY` has
  passed. Until then the owner (directly or through a signed `Execute`) or the guardian can cancel.
  The balance never moves; only the key that controls it changes. The factory names the guardian
  for every account, so a leaked guardian key is replaced in one transaction by the factory admin.
- **Identity is a verified email.** While they have their phone, residents confirm an email with a
  six-digit code. On a new phone, the app signs in with a new key (a new, empty resident) and asks
  for a code at that email. Codes are stored as HMACs bound to the address, the purpose and the
  resident who asked; they last 10 minutes, die after 5 wrong guesses, and are limited to one a
  minute and five a day per address. Asking for a code answers the same whether or not the email
  has an account. SMS was not chosen: it costs per message and SIM swapping makes it weaker.
- **The current owner is warned.** Starting a recovery pushes and emails the account's owner, with
  the date it takes effect and a cancel button in the app.
- **The new phone waits idle.** It cannot deposit or book during the wait: whatever it earned would
  go to its own empty account. When the recovery completes, its resident is folded into the account
  (same id, history, balance and turns), the old phone's push tokens are deleted, and sessions name
  the key that signed in, so the old phone's session ends at once. A key whose account moved away
  cannot sign in again (`key_retired`).
- **Email through Resend's HTTP API.** An outbox (`email_message`) is written in the same transaction
  as its cause and sent by a worker with an `Idempotency-Key`. HTTPS rather than SMTP: VPS providers
  often block outgoing SMTP ports, and the API reports quota errors by name (`daily_quota_exceeded`
  waits for midnight UTC). Code bodies are cleared once sent. The free plan (100 emails a day, 3,000
  a month) covers a pilot many times over.
- **Existing residents** keep their key as owner and get their account address on their next
  sign-in. The app moves whatever the key itself holds into the account, after checking on its own
  that the account is the one predicted for its key.

## Consequences
- Zyrcle can take over an account whose owner ignores the push and the email for 48 hours. That
  is the price of recovery without seed phrases. Anyone who also controls the resident's email gets
  the same power, so the warning goes to both the phone and the email.
- A thief with an unlocked phone controls the account like the owner does, and can cancel
  recoveries. The key is readable only while the phone is unlocked
  (`WHEN_UNLOCKED_THIS_DEVICE_ONLY`).
- If the backend is compromised, it could refuse to submit an owner's signed cancellation. The
  owner can still have anyone else submit it, or call `cancelRecovery` from a key holding gas.
- Owner changes made on chain without the backend (`transferOwnership`, or a recovery cancelled by
  a signed message) are noticed by the recovery worker but not yet synced for sign-in. Moving to a
  new phone while still holding the old one, without the 48-hour wait, is the next step.
- A new phone waits two days to deposit. Verifying the resident in person (the residence's
  administrator) could shorten the wait later.

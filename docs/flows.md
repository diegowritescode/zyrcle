# Flows

Each flow below is drawn from the code as it is. Participant = a resident, student or staff member
who recycles. Operator = a person running Zyrcle from the console. Container = the device with the
scale and sensors (simulated until hardware exists). Treasury = the contract that mints ZYR
(1 ZYR = 1 COP) on ZyrcleChain.

- [Sign in](#sign-in)
- [Deposit](#deposit)
- [Booking a turn](#booking-a-turn)
- [Collection](#collection)
- [Sale and settlement](#sale-and-settlement)
- [Impact certificate](#impact-certificate)
- [Paying a campus merchant](#paying-a-campus-merchant)
- [Lost-phone recovery](#lost-phone-recovery)
- [Push notifications](#push-notifications)
- [The money](#the-money)

## Sign in

The phone generates a key on first launch and keeps it in secure storage (ADR 0006). There is no
password and no seed phrase.

```mermaid
sequenceDiagram
    autonumber
    participant App as App (phone or web)
    participant API
    participant DB as Postgres
    App->>API: POST /v1/auth/nonce
    API->>DB: store nonce (expires)
    API-->>App: nonce
    App->>App: build a Sign-In with Ethereum message, sign it with the phone key
    App->>API: POST /v1/auth/verify {message, signature}
    API->>API: check domain, chain id, nonce, expiry, signature
    API->>DB: find the participant by key, or create one with its smart account address
    API-->>App: JWT {sub, key}, account address, key
    Note over App,API: Every request checks the JWT's key still owns the account (ADR 0010)
```

Operators sign in differently: a six-digit code sent to their email, then a JWT with
`role: operator` that lasts 8 hours (ADR 0014).

## Deposit

```mermaid
sequenceDiagram
    autonumber
    actor P as Participant
    participant App
    participant API
    participant C as Container
    participant W as Payout worker
    participant T as Treasury
    C->>C: shows a QR with a code that rotates every 30 s
    P->>App: scans the QR, picks the material
    App->>API: POST /v1/sessions {qr, material}
    API->>API: lock the container row, code valid, online, accepts material, no other session or collection, a turn or walk-in spot
    API-->>App: session (authorized)
    API->>C: MQTT command unlock (after commit)
    C->>API: event lock_opened {tare}
    App->>API: WebSocket /v1/sessions/{id}/live
    loop every 500 ms while open
        C->>API: reading {weight, fill, metal}
        API-->>App: live weight
    end
    P->>App: "Terminé" (or idle timeout)
    App->>API: POST /v1/sessions/{id}/finish
    API->>C: MQTT command lock
    C->>API: measurement {tare, final, fill before/after, metal, camera label}
    API->>API: verification score: density, metal, camera (architecture, section 6)
    alt score high
        API->>API: state verified, payout row written in the same transaction (outbox)
        W->>T: payAdvance(deposit, account, amount)
        T-->>W: ZYR minted to the participant's account
        W->>API: payout confirmed, push "Te pagamos"
    else score low
        API->>API: state review, push "en revisión"
        Note over API: an operator approves (advance paid) or rejects in the console
    end
```

Every device message is signed with the container's key and carries a sequence number; unsigned,
replayed or out-of-order messages are dropped (`docs/device-protocol.md`).

## Booking a turn

```mermaid
flowchart LR
    A[Participant opens Turnos] --> B[GET /v1/containers/id/slots]
    B --> C{Spot free this hour?}
    C -- yes --> D[POST /v1/bookings: spot guaranteed]
    C -- no --> E[Pick another hour]
    D --> F[Phone schedules a local reminder 10 min before]
    G[Participant arrives without a turn] --> H{Hour has room?}
    H -- yes --> I[Walk-in spot taken at deposit start]
    H -- no --> J[409 slot_full: offer to book]
```

ADR 0009. Spots per container and hour, and opening hours, belong to the site (ADR 0011).

## Collection

ADR 0012. Nobody types a weight: the container's own scale weighs every bag.

```mermaid
sequenceDiagram
    autonumber
    actor Co as Collector
    participant App
    participant API
    participant C as Container
    Co->>App: scans the container QR
    App->>API: POST /v1/collections {qr}
    API->>API: collector role? lock container, no deposit or other collection active
    API->>C: unlock (the container sees one more session)
    C->>API: lock_opened {weight}
    API->>API: container balance: weight vs previous collection + deposits since
    opt does not balance (50 g or 2 %)
        API->>API: incident container_balance
    end
    loop one material at a time
        Co->>App: scans a bag QR
        App->>API: POST /v1/collections/{id}/fills {bag}
        API->>API: start = latest scale reading
        Co->>C: takes that material out
        Co->>App: "Listo"
        App->>API: POST /v1/collections/{id}/fills/{fill}/done
        API->>API: bag grams += start - latest reading (below 10 g counts as empty)
    end
    Co->>App: "Sacar residuo", then "Terminar y cerrar"
    App->>API: POST /v1/collections/{id}/finish
    API->>C: lock
    C->>API: measurement {tare, final}
    API->>API: link the deposits made here since the last collection, collection balance: removed vs bags + residue
    opt does not balance
        API->>API: incident collection_balance naming the bags
    end
    Co->>App: seals a full bag
    App->>API: POST /v1/bags/{code}/seal
```

## Sale and settlement

ADR 0013. Nothing reaches the chain before the money reaches the bank.

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant Console
    participant API
    participant W as Settlement worker
    participant T as Treasury
    Op->>Console: types the buyer's ticket: per bag, buyer's weight and pesos
    Console->>API: POST /v1/operator/sales
    API->>API: bags sealed and free of incidents, bags become sold
    opt buyer's weight differs from the bag's (100 g or 5 %)
        API->>API: incident bag_balance (line waits)
    end
    Op->>Console: sees the transfer in the bank, enters reference and amount
    Console->>API: POST /v1/operator/sales/{id}/confirm
    API->>API: amount equals the ticket total? sale confirmed
    loop each bag (sale line), checking the chain before every step
        W->>W: wait if an incident names the bag, a deposit is in review, or an advance is being paid
        W->>T: recordSale(line, amount, evidence hash) with the operator key
        W->>T: settleResidents(deposits, accounts, shares) in chunks of 40
        Note right of T: each deposit gets its share minus the advance it already got
        W->>T: payCollector(collector account, 15 %)
        W->>T: payHost(host address, 10 % pro rata to grams from its sites)
        W->>API: line settled, bag settled, push "Se vendió tu material"
    end
```

Shares: 65 % participants (pro rata to verified grams), 15 % collector, 10 % host, 10 % operations
(stays in pesos). A host without a payout address waits; its part is paid when it is set.

## Impact certificate

ADR 0027. Only material that reached a buyer counts, and each gram is claimed once.

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant API
    participant W as Anchor worker
    participant L1 as ZyrcleChain
    actor V as Anyone
    Op->>API: preview {host, site?, month}
    API->>API: credited deposits of that host whose bag's sale settled in the month, co2e not claimed
    API-->>Op: kg per material, CO2e avoided (EPA WARM v16), Merkle root
    Op->>API: issue
    API->>API: certificate + one impact_claim per deposit, in one transaction
    W->>L1: transaction to itself, data = ZYRCLE-CERT-1 + certificate id + root
    W->>API: anchored, tx hash
    V->>API: GET /v1/certificates/{id} (leaves included)
    V->>V: recompute the root in the browser
    V->>L1: read the anchor transaction from the public RPC
    V->>V: same root? verified
```

## Paying a campus merchant

ADR 0029. The participant needs no gas and no deployed account; the backend cannot change what was
signed.

```mermaid
sequenceDiagram
    autonumber
    actor M as Merchant
    actor P as Participant
    participant App as Participant's app
    participant API
    participant R as Relay worker (guardian key)
    participant A as Participant's smart account
    participant T as Treasury
    M->>API: POST /v1/merchant/charges {amount, concept}
    API-->>M: QR zyrcle://p/<id> (10 min)
    P->>App: scans the QR
    App->>API: POST /v1/payments/{id}/intent
    API-->>App: EIP-712 Execute: send amount to the merchant's account, nonce, deadline
    App->>App: sign with the phone key
    App->>API: POST /v1/payments/{id}/pay {signature}
    API->>API: recover the signer, must be the payer's key
    R->>A: deploy the account first if needed (factory)
    R->>A: executeSigned(calls, deadline, signature)
    A->>A: check owner signature and nonce, transfer ZYR to the merchant
    API-->>M: push "Recibiste"
    Note over M,T: later, to get pesos
    M->>API: redeem X (signed Execute calling Treasury.redeem)
    R->>A: executeSigned
    A->>T: redeem(ref) with X ZYR: pending
    actor Op as Operator
    Op->>Op: transfers X pesos to the merchant's bank
    Op->>API: settle {bank_ref}
    API->>T: settleRedemption(ref): backing -X, X retired
```

## Lost-phone recovery

ADR 0010. The balance never moves; only the key that controls the smart account changes.

```mermaid
sequenceDiagram
    autonumber
    actor P as Participant
    participant Old as Old phone
    participant New as New phone
    participant API
    participant G as Guardian (backend key)
    participant A as Smart account
    P->>Old: confirms a recovery email (6-digit code via Resend)
    Note over P,New: phone lost
    P->>New: installs the app (new key, new empty participant)
    New->>API: POST /v1/recovery/code {email}
    API-->>P: code by email (same answer whether or not the email has an account)
    New->>API: POST /v1/recovery {email, code}
    G->>A: startRecovery(new key) (deploys the account if needed)
    API-->>Old: push and email: your account moves in 48 h, cancel if it was not you
    alt the owner cancels within 48 h
        Old->>API: DELETE /v1/recovery/{id}
        G->>A: cancelRecovery()
    else 48 h pass
        G->>A: finishRecovery()
        API->>API: fold the new participant into the account, old key retired
    end
```

## Push notifications

ADR 0008.

```mermaid
flowchart LR
    E[Event in a DB transaction: payout confirmed, review, settlement, recovery] --> O[(notification outbox)]
    O --> W[Notification worker]
    W -->|batch of 100| X[Expo push service]
    X --> F[Firebase / APNs] --> Ph[Phone]
    W -->|15 min later| R[Expo receipts]
    R -->|DeviceNotRegistered| D[disable the token]
```

Turn reminders are not pushed by the server: the phone schedules them locally from its bookings.

## The money

```mermaid
flowchart LR
    S[Seed capital recorded] --> B[(Treasury backing)]
    Sale[Sale confirmed against the bank] -->|65 + 15 + 10 %| B
    Sale -->|10 % operations| Ops[Pesos kept by operations]
    B -->|mint| Adv[Advance at deposit time]
    B -->|mint| Set[Settlement: share minus advance]
    B -->|mint| Col[Collector part]
    B -->|mint| H[Host part]
    Adv & Set --> Acc[Participant smart accounts]
    Col --> CA[Collector account]
    H --> HA[Host address]
    Acc -->|pay with a QR| M[Campus merchants]
    M -->|redeem| T2[Treasury: ZYR retired, backing lowered when the pesos are paid]
```

The Treasury refuses any mint that would put more ZYR in circulation (`minted - retired`) than
`backing` (ADR 0007, ADR 0029).

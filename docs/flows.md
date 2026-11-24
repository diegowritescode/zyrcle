# Flows

Each flow below is drawn from the code as it is. Participant = a resident, student or staff member
who recycles. Operator = a person running Zyrcle from the console. Container = the device with the
scale and sensors (simulated until hardware exists). Treasury = the contract that mints ZYR
(1 ZYR = 1 COP) on ZyrcleChain.

Every HTTP request in these flows, though not the live WebSocket, goes through the API's rate
limits (ADR 0035): too many in a minute get a `429` with `Retry-After`, and the apps say so in
Spanish.

- [Sign in](#sign-in)
- [Deposit](#deposit)
- [Advance priced by the site's center](#advance-priced-by-the-sites-center)
- [Booking a turn](#booking-a-turn)
- [Collection](#collection)
- [Sale and settlement](#sale-and-settlement)
- [From a ticket photo to a sale](#from-a-ticket-photo-to-a-sale)
- [Matching the bank statement](#matching-the-bank-statement)
- [Impact certificate](#impact-certificate)
- [Paying a campus merchant](#paying-a-campus-merchant)
- [Lost-phone recovery](#lost-phone-recovery)
- [Signing a Safe proposal](#signing-a-safe-proposal)
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
replayed or out-of-order messages are dropped (`docs/device-protocol.md`). The advance's amount
depends on the price of the collection center the site sells to
([next flow](#advance-priced-by-the-sites-center)).

## Advance priced by the site's center

ADR 0037. Only the advance depends on this price; the final payment follows the real sale.

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant Console
    participant API
    participant DB as Postgres
    Op->>Console: Precios, Centros de acopio, adds a center {name, NIT, address, contact}
    Console->>API: POST /v1/operator/centers
    Op->>Console: picks the center each site sells to
    Console->>API: PUT /v1/operator/sites/{id}/center
    Console->>API: GET /v1/operator/centers/{id}/suggested-prices
    API->>DB: confirmed sales to that center in the last 90 days
    API-->>Console: median COP per kg of each material, from the buyer's weights
    Op->>Console: accepts the suggestion or types another price
    Console->>API: PUT /v1/operator/centers/{id}/prices/{material} {cop_per_kg, source}
    API->>DB: price, source sales or manual, who and when
    Note over API,DB: later, a deposit at one of that center's sites is verified
    API->>DB: the price of the site's center for the declared material
    alt the center has a price for it
        API->>API: advance = ratio x center price x kg, capped
    else no center, or no price for that material
        API->>API: advance = ratio x general table price x kg, capped
    end
    API->>DB: payout row in the same transaction (outbox), paid as in Deposit
```

A suggestion never changes a price by itself. A sale can also name the center that bought, which
is what the next suggestions are computed from.

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

ADR 0013. Nothing reaches the chain before the money reaches the bank. The ticket can be typed or
filled from a photo ([next flow](#from-a-ticket-photo-to-a-sale)), and the bank match can be typed
or confirmed from an uploaded statement
([matching the bank statement](#matching-the-bank-statement)).

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant Console
    participant API
    participant W as Settlement worker
    participant T as Treasury
    Op->>Console: the buyer's ticket, typed or read from a photo: per bag, buyer's weight and pesos
    Console->>API: POST /v1/operator/sales {buyer, center, ticket, lines}
    API->>API: bags sealed and free of incidents, bags become sold
    opt buyer's weight differs from the bag's (the larger of 100 g and 5 %)
        API->>API: incident bag_balance (line waits)
    end
    alt typed by hand
        Op->>Console: sees the transfer in the bank, enters reference and amount
        Console->>API: POST /v1/operator/sales/{id}/confirm
    else from the bank statement
        Op->>Console: confirms the credit the API proposed for this sale
        Console->>API: POST /v1/operator/bank-lines/{id}/match
    end
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
`recordSale` is signed with the operator key; the residents', collector's and host's parts with the
oracle key.

## From a ticket photo to a sale

ADR 0038. The model reads; the API checks and proposes; a person records the sale. Without an
Anthropic key the API answers `503` and the operator types the ticket.

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant Console
    participant API
    participant C as Anthropic API
    participant DB as Postgres
    Op->>Console: Ventas, takes a photo of the collection center's scale ticket
    Console->>Console: shrink the long side to 1600 px at most, as JPEG
    Console->>API: POST /v1/operator/ticket-scans {image, media type}
    API->>C: the photo, a fixed JSON schema, model claude-opus-5-5
    alt the ticket is readable
        C-->>API: center, ticket number, date, lines {material, kg, COP per kg, amount}, total
        API->>DB: ticket_scan read: photo, hash, model, request id, reading, who sent it
        API->>API: check kg x price against each amount and the lines against the total
        API->>API: propose the sealed bag of each line's material closest in weight, each bag once
        API->>API: match the center by name
        API-->>Console: reading, warnings, proposed bags, center
        Console->>Console: fill the sale form
    else unreadable, or the call fails
        API->>DB: ticket_scan failed: photo and the reason
        API-->>Console: the reason, and the operator types the ticket
    end
    Op->>Console: reviews and corrects every line
    Console->>API: POST /v1/operator/sales {center, ticket, lines, ticket scan id}
    API->>DB: sale recorded, the scan linked to it, bags sold
    Note over Op,DB: the sale then waits for its bank match, as in Sale and settlement
```

## Matching the bank statement

ADR 0039. The API proposes; nothing is confirmed until the operator clicks.

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant Console
    participant API
    participant W as Settlement worker
    participant T as Treasury
    Op->>Console: Ventas, uploads the statement exported from the bank, CSV or Excel
    Console->>API: POST /v1/operator/bank-statements {file name, content}
    API->>API: find the columns by their headers, read Colombian numbers and dates
    API->>API: a movement seen in an earlier statement is kept once, by its fingerprint
    API->>API: propose matches, each movement and each target once, best score first
    Note right of API: a credit for a sale waiting for its match, same amount, from a day before to ten days after the sale, more points for the ticket number or the buyer's name
    Note right of API: a debit for a redemption waiting for its transfer, same amount, up to ten days after the request, more points for the merchant's name or tax id
    API-->>Console: proposals with their score and reasons
    alt a credit for a sale
        Op->>Console: Confirmar
        Console->>API: POST /v1/operator/bank-lines/{id}/match {sale}
        API->>API: the same rule as confirming by hand, the movement's reference as bank reference
        W->>T: the sale settles bag by bag, as in Sale and settlement
    else a debit for a redemption
        Op->>Console: Confirmar
        Console->>API: POST /v1/operator/bank-lines/{id}/match {redemption}
        API->>T: settleRedemption(ref, bank reference) with the operator key
        API-->>Console: redemption settled, push "Te pagamos" to the merchant
    end
    API->>API: the movement records what it paid and who matched it
```

## Impact certificate

ADR 0027. Only material that reached a buyer counts, and each gram is claimed once. With Pinata
configured, a public copy is pinned on IPFS first and its CID goes on chain with the root
(amendment of 2026-11-22); without it, steps 6 and 7 and the IPFS reads are skipped and the data
starts with `ZYRCLE-CERT-1`.

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant API
    participant W as Anchor worker
    participant P as Pinata / IPFS
    participant L1 as ZyrcleChain
    actor V as Anyone
    Op->>API: preview {host, site?, month}
    API->>API: credited deposits of that host whose bag's sale settled in the month, co2e not claimed
    API-->>Op: kg per material, CO2e avoided (EPA WARM v16), Merkle root
    Op->>API: issue
    API->>API: certificate + one impact_claim per deposit, in one transaction
    W->>P: pin the certificate document (JSON, no personal data)
    P-->>W: CID, stored before anything goes on chain
    W->>L1: transaction to itself, data = ZYRCLE-CERT-2 + certificate id + root + CID
    W->>API: anchored, tx hash
    V->>API: GET /v1/certificates/{id} (leaves included)
    V->>V: recompute the root in the browser
    V->>L1: read the anchor transaction from the public RPC
    V->>V: same root? verified on chain
    V->>P: GET gateway/ipfs/CID, the CID read from the chain
    V->>V: the copy's own leaves give the anchored root too
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
    Op->>API: settle {bank_ref}, typed or from a statement match
    API->>T: settleRedemption(ref) with the operator key: backing -X, X retired
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

The guardian also relays signed payments. In production it is still the oracle key until runbook
9.13 gives it its own (ADR 0040); since the handover, naming a new guardian is a Safe proposal.

## Signing a Safe proposal

ADR 0040. Since 2026-11-23 a Safe with three owners (Diego's Core wallet, his phone's MetaMask and
a paper key) holds every admin power of ZyrcleChain, and two must sign each change. The handover
itself was signed this way: the proof that the Safe acts, then the removal of the admin key from
the precompiles, both kept in `infra/l1/safe/`.

```mermaid
sequenceDiagram
    autonumber
    actor A as Proposer
    participant CLI as zyrcle-api safe
    actor O1 as Owner with a wallet
    participant Page as Web page /multisig
    actor O2 as Owner with the paper key
    participant S as Safe on ZyrcleChain
    A->>CLI: safe propose --what proof, revoke, guardian or call --out FILE
    CLI->>S: read the chain id and the Safe's nonce
    CLI-->>A: proposal file, EIP-712 data and the Safe's transaction hash
    A->>O1: passes the file
    O1->>Page: loads or pastes the proposal
    Page->>Page: refuse it if a changed byte no longer gives its hash
    Page->>S: owners, threshold and nonce from the public RPC
    O1->>Page: Firmar con mi billetera
    Page->>O1: eth_signTypedData_v4, adding the ZyrcleChain network if needed
    Page->>Page: the signer must be an owner
    Page-->>O1: signed proposal, downloaded or copied
    O1->>O2: passes the file on
    O2->>CLI: safe sign --proposal FILE --key-file -
    CLI->>O2: asks for the key without showing it or writing it anywhere
    CLI->>CLI: the signer must be an owner, now 2 of 3
    A->>CLI: safe exec --proposal FILE --key-file of any funded key
    CLI->>S: same hash and nonce as on chain? execTransaction with both signatures
    S->>S: checks the signatures again, then runs the call
    Note over A,S: the executed proposal is committed in infra/l1/safe/
```

Either owner may sign first, on the page or on the command line.

## Push notifications

ADR 0008.

```mermaid
flowchart LR
    E[Event in a DB transaction: payout confirmed, review, settlement, recovery, payment received, redemption] --> O[(notification outbox)]
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

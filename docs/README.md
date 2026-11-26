# Zyrcle documentation

Start with the document that matches what you need. Everything here is kept current with the code
(ADR 0025): a change that moves behaviour, schema, configuration or operation updates these files in
the same commit.

> Status on 2026-11-25: v1 blocks 1 and 2 (M1 to M7) and block 3 (M8 to M17) are deployed; in block
> 4, M18 (participant) and M19 (collector) are deployed (2026-11-26, commit `72a875b`; production runs `0d41852`), and M20 to
> M23 are planned. Production: the web app at `https://zyrcle.deviego.xyz`, the API at
> `https://zyrcle-backend.deviego.xyz`, one VPS with Docker Compose, and ZyrcleChain v2, an
> Avalanche L1 on Fuji whose admin powers are held by a 2-of-3 Safe.

| I want to | Read |
|---|---|
| Understand what Zyrcle is and how its parts fit | [architecture.md](architecture.md) |
| Follow a deposit, a collection, a sale, a payment, a recovery or a Safe signature step by step | [flows.md](flows.md) |
| Know why something is the way it is, and who decided it | [adr/](adr/README.md): 40 records, 0001 to 0040 |
| See how the project got here, from the 2025 hackathon | [history.md](history.md) |
| Work on the code: layout, conventions, running it locally | [repository.md](repository.md) |
| Run every party's journey in a browser, as CI does | [e2e/README.md](../e2e/README.md) |
| Call or change the API | [api.md](api.md) |
| Understand the database: tables, states, migrations | [database.md](database.md) |
| Deploy, operate or rebuild the servers and the chain | [infrastructure.md](infrastructure.md) (runbooks in section 9); [deploy/README.md](../deploy/README.md) |
| See the admin changes the Safe has signed | [infra/l1/safe/](../infra/l1/safe/README.md) |
| Know what is protected and how; contract analysis | [security.md](security.md) |
| Build or replace a container's firmware | [device-protocol.md](device-protocol.md) |
| See what comes next | [roadmap-blocks-3-4.md](roadmap-blocks-3-4.md) (block 3 deployed, block 4 planned); [roadmap-v1.md](roadmap-v1.md) (v1, deployed) |

Each part also has its own README with its modules and commands:
[apps/api](../apps/api/README.md), [apps/web](../apps/web/README.md),
[apps/mobile](../apps/mobile/README.md), [chain](../chain/README.md),
[infra/l1](../infra/l1/README.md), [deploy](../deploy/README.md), [e2e](../e2e/README.md).

**Words used throughout**

| Word | Meaning |
|---|---|
| Participant, resident | A person who recycles: a resident of a complex, a student or staff member on a campus |
| Host | The institution whose sites hold the containers (a university, a residential complex) |
| Site | A place a host runs: a campus, a building. Called "residence" before ADR 0011 |
| Container | The device with a scale, distance, metal and camera sensors and a lock; simulated for now |
| Collector | A participant named by the operator to empty containers into bags |
| Collection center | The buyer of the material: weighs each bag on its own scale and pays the operator in pesos. A record with a price per material; each site sells to one (ADR 0037) |
| Scale ticket | The collection center's receipt for a purchase: per material, kilograms, price and amount. Read from a photo with Claude when the key is set (ADR 0038) |
| Bank statement | The file of movements the operator exports from the bank; its movements confirm sales and redemptions with one click (ADR 0039) |
| Merchant | A participant with the merchant role: a campus shop that charges in ZYR with a QR and redeems it for pesos (ADR 0029) |
| Redemption | A merchant handing ZYR back to the Treasury for pesos the operator transfers |
| Operator | A person running Zyrcle from the console |
| ZYR | ZyrcleChain's native coin; 1 ZYR = 1 Colombian peso |
| Treasury | The contract that mints ZYR, only against pesos received |
| Smart account | The participant's on-chain account, controlled by the phone's key and recoverable by the guardian (ADR 0010) |
| Guardian | The backend key that starts recoveries and relays payments the phone signed |
| Safe | The 2-of-3 multisig contract that holds every admin power of ZyrcleChain (ADR 0040) |
| Advance | What a deposit is paid when it is verified, before its material is sold |
| Settlement | What a deposit gets when its bag is sold: its share minus the advance |
| Incident | A mass balance that did not hold; its bags are held until an operator resolves it |
| Outbox | A table a transaction writes to, emptied by a worker that talks to the outside world |

# Zyrcle documentation

Start with the document that matches what you need. Everything here is kept current with the code
(ADR 0025): a change that moves behaviour, schema, configuration or operation updates these files in
the same commit.

| I want to | Read |
|---|---|
| Understand what Zyrcle is and how its parts fit | [architecture.md](architecture.md) |
| Follow a deposit, a collection, a sale or a recovery step by step | [flows.md](flows.md) |
| Know why something is the way it is, and who decided it | [adr/](adr/README.md) |
| See how the project got here, from the 2025 hackathon | [history.md](history.md) |
| Work on the code: layout, conventions, running it locally | [repository.md](repository.md) |
| Call or change the API | [api.md](api.md) |
| Understand the database: tables, states, migrations | [database.md](database.md) |
| Deploy, operate or rebuild the servers and the chain | [infrastructure.md](infrastructure.md) |
| Know what is protected and how; contract analysis | [security.md](security.md) |
| Build or replace a container's firmware | [device-protocol.md](device-protocol.md) |
| See what comes next | [roadmap-blocks-3-4.md](roadmap-blocks-3-4.md) (blocks 3 and 4); [roadmap-v1.md](roadmap-v1.md) (v1, deployed) |

Each app also has its own README with its modules and commands:
[apps/api](../apps/api/README.md), [apps/web](../apps/web/README.md),
[apps/mobile](../apps/mobile/README.md), [chain](../chain/README.md),
[infra/l1](../infra/l1/README.md), [deploy](../deploy/README.md).

**Words used throughout**

| Word | Meaning |
|---|---|
| Participant, resident | A person who recycles: a resident of a complex, a student or staff member on a campus |
| Host | The institution whose sites hold the containers (a university, a residential complex) |
| Site | A place a host runs: a campus, a building. Called "residence" before ADR 0011 |
| Container | The device with a scale, distance, metal and camera sensors and a lock; simulated for now |
| Collector | A participant named by the operator to empty containers into bags |
| Operator | A person running Zyrcle from the console |
| ZYR | ZyrcleChain's native coin; 1 ZYR = 1 Colombian peso |
| Treasury | The contract that mints ZYR, only against pesos received |
| Advance | What a deposit is paid when it is verified, before its material is sold |
| Settlement | What a deposit gets when its bag is sold: its share minus the advance |
| Incident | A mass balance that did not hold; its bags are held until an operator resolves it |
| Outbox | A table a transaction writes to, emptied by a worker that talks to the outside world |

# Zyrcle device protocol v1

How a container talks to the backend. The simulator in `device/simulator` implements it today;
firmware on real hardware must implement exactly the same messages. Reference code:
`packages/protocol` (Python), shared by the API and the simulator.

## Transport

MQTT, QoS 1. Today the broker listens on port 1883 without TLS, reachable only on the VPS's
internal Docker network, because the containers are simulated on the same machine
([deploy/mosquitto/mosquitto.conf](../deploy/mosquitto/mosquitto.conf)). Every uplink is still signed
by the device, so a reader of the network cannot forge readings. A physical container on a campus
network will need TLS on the broker (port 8883) before it connects (infrastructure, section 10).

| Direction | Topic | Content |
|---|---|---|
| container → backend | `zyrcle/v1/devices/<device_id>/up/<type>` | signed envelope |
| backend → container | `zyrcle/v1/devices/<device_id>/cmd` | command |

Each container logs in to the broker with its device id as username. The broker ACL lets it publish
only under its own `.../up/` and read only its own `.../cmd`
([apps/api/dev/mosquitto/acl](../apps/api/dev/mosquitto/acl)). The API reads uplinks through a
shared subscription (`$share/zyrcle-api/...`) so several replicas split the load.

## Device identity

Every container has an ECDSA P-256 key pair. On hardware the private key lives in an ATECC608
secure element and never leaves it; the backend stores the public key when the container is
registered (`POST /v1/operator/devices`).

## Envelope (container → backend)

```json
{"v": 1, "device_id": "ctr-0001", "seq": 1732231234000123, "ts": 1795315300123,
 "type": "reading", "body": {"session_id": "…", "weight_g": 4075, "fill_mm": 772, "metal": false},
 "sig": "MEUCIQ…"}
```

- `sig`: base64url ECDSA P-256 / SHA-256 signature over the **canonical form** of the object
  without `sig`: keys sorted, no whitespace, UTF-8.
- Only integers, strings, booleans, null, arrays and objects. **No floats**: weights are grams,
  distances millimetres, times milliseconds. This makes the canonical form identical in C and
  Python.
- `seq`: strictly increasing per device, kept across reboots (flash). The backend stores the last
  one seen and ignores anything not greater, which makes QoS 1 redeliveries and replays harmless.
- `ts`: device clock, unix milliseconds. Informational; the backend uses its own clock for timeouts.

### Message types

| type | when | body |
|---|---|---|
| `hello` | on every (re)connect and every 30 s as a heartbeat | `fw`, `area_mm2` |
| `event` | lid opened, lid closing | `name` (`lock_opened`, `lock_closing`), `session_id`; `lock_opened` also carries the tare: `weight_g`, `fill_mm` |
| `reading` | about every 500 ms while the lid is open | `session_id`, `weight_g`, `fill_mm`, `metal` |
| `measurement` | once, after the lid closed and the scale settled | `session_id`, `tare_g`, `final_g`, `fill_before_mm`, `fill_after_mm`, `metal`, `camera_label` |

`fill_mm` is the distance from the sensor down to the contents, so it **decreases** as the container
fills. `camera_label` is the vision model's material label for the deposit, or null.

## Commands (backend → container)

```json
{"v": 1, "cmd": "unlock", "session_id": "…", "expires_ts": 1795315315000}
```

| cmd | fields | the container must |
|---|---|---|
| `display` | `code` | show `zyrcle://c/<device_id>?code=<code>` as a QR on its screen |
| `unlock` | `session_id` | open the lid, send `event/lock_opened` with the tare, stream `reading`s |
| `lock` | `session_id` | close the lid, wait for the scale to settle, send `measurement` |

A container ignores commands past `expires_ts` (late delivery after a reconnect), an `unlock` while
a session is open, and a `lock` for a session that is not the open one.

A session is either a participant's deposit or a collector's emptying
([ADR 0012](adr/0012-collection-and-bags.md)). The container does not need to know which: it opens,
streams readings and measures the same way, and the backend weighs each bag from the readings.

## Sequence of a deposit

```
app          API                      broker        container
 |  POST /v1/sessions (QR, material)    |               |
 |------------>| unlock ───────────────>|──────────────>|  lid opens
 |             |<──────── event/lock_opened (tare) ─────|
 |             |<──────── reading … reading ────────────|  resident drops material
 |  WS live <──|                                        |
 |  POST finish|  lock ────────────────>|──────────────>|  lid closes, scale settles
 |             |<──────── measurement ──────────────────|
 |  verified / review / empty                           |
```

If the resident walks away, the API closes the session itself after the idle timeout and still
credits what the measurement shows.

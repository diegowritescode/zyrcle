# ADR 0008: Push notifications through an outbox and Expo's push service

- Status: accepted (2026-11-22)

## Context
Some outcomes reach the resident after they have left the container: the advance is confirmed on
chain seconds or minutes later, a suspicious deposit waits for an operator, and the operator's
verdict can take hours. The resident should hear about them without opening the app. Turn reminders
(ADR 0009) must arrive at a set time even if the phone is offline then.

## Decision
- **Server push for events, through Expo's push service.** The API sends to Expo push tokens over
  HTTPS; Expo talks to APNs and FCM. One integration for both platforms, no Firebase or Apple SDK
  in the backend. The Expo access token ("enhanced security for push") is supported and optional.
- **Outbox.** Whatever causes a notification writes it to the `notification` table in the same
  transaction: a payout turning `confirmed`, a session entering `review`, an operator rejecting it,
  or approving one that queued no advance. A crash can neither lose a notification nor send one for
  a change that was rolled back. `dedupe_key` (for example `payout_confirmed:<payout id>`) makes
  enqueueing idempotent, so a retried transaction never notifies twice.
- **Worker.** Claims due rows with `FOR UPDATE SKIP LOCKED` (safe with several replicas), sends up to
  100 messages per request, and keeps the rows locked until the tickets are recorded. Network
  errors, HTTP 429/5xx and `MessageRateExceeded` retry with exponential backoff (6 attempts);
  request-level errors fail the row. Delivery is at least once.
- **Receipts.** About 15 minutes after sending, the worker asks Expo for the receipts, which say
  whether Apple or Google accepted each message. `DeviceNotRegistered`, at send time or in a
  receipt, disables the token. Registering it again (a reinstall) re-enables it.
- **One token per installation, owned by the wallet now on the phone.** `PUT /v1/me/push-token`
  upserts it; registering a token that belonged to another wallet moves it, because only the wallet
  on that phone should be notified.
- **Turn reminders are local.** The app schedules them with `expo-notifications` and keeps them in
  step with `GET /v1/bookings` (schedule missing ones, cancel stale ones). The wallet key lives only
  on one phone (ADR 0006), so every booking was made there and the phone alone can keep them right,
  even offline.
- Android channels per kind (`payments`, `deposits`, `turns`) so a resident can mute reminders and
  keep payments. Notification taps open the screen in `data.url`, from an allow list.

## Consequences
- Remote push needs a development or store build: Expo Go on Android dropped it in SDK 53. Local
  reminders work in Expo Go.
- Android push needs a Firebase project (`google-services.json`, kept out of git) and its FCM v1
  service account key uploaded to EAS. iOS needs an Apple Developer account.
- Expo's push service is a dependency. If it is down, notifications queue and retry; nothing else
  in the deposit flow depends on it.
- Without a registered token, a notification is marked `skipped`, not kept: a payment notice that
  arrives a day later is noise.

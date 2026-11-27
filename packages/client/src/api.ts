/** Typed client for the Zyrcle API (apps/api), shared by the web app and the mobile app. */
import { hourLabel } from "./format";

export interface Totals {
  containers: number;
  deposits_verified: number;
  kg_verified: number;
  residents: number;
  payouts_confirmed: number;
  paid_cop: number;
}

export interface ContainerInfo {
  id: string;
  name: string;
  site_id: string;
  site_name?: string;
  host_id?: string;
  host_name?: string;
  accepted_materials: string[];
  online: boolean;
  busy: boolean;
  last_seen_at: string | null;
}

export interface DashboardContainer extends ContainerInfo {
  fill_pct: number | null;
  weight_kg: number | null;
  deposits_verified: number;
  kg_verified: number;
  paid_cop: number;
  last_deposit_at: string | null;
}

export type HostKind = "university" | "residential" | "business" | "public";

export interface HostRef {
  id: string;
  name: string;
  kind: HostKind;
}

export interface SiteRef {
  id: string;
  name: string;
}

/** Daily kilos (by declared material) and pesos paid, in the deployment's time zone. */
export interface DailySeries {
  activity: { day: string; kg: Record<string, number> }[];
  payouts: { day: string; cop: number }[];
}

/** A site's dashboard (GET /v1/sites/{id}/dashboard). */
export interface Dashboard extends DailySeries {
  site: SiteRef;
  host: HostRef;
  timezone: string;
  totals: Totals;
  containers: DashboardContainer[];
}

/** A host's dashboard: its totals across sites and each site's (GET /v1/hosts/{id}/dashboard). */
export interface HostDashboard extends DailySeries {
  host: HostRef;
  timezone: string;
  totals: Totals;
  sites: (SiteRef & { totals: Totals })[];
}

/** One month of a host or a site: credited kilograms and the people who recycled. */
export interface MonthFigures {
  period: string;
  kg: number;
  participants: number;
}

/** A site against its goal, this month and the last months (GET /v1/hosts/{id}/progress). */
export interface SiteProgress extends MonthFigures {
  id: string;
  name: string;
  goal_kg: number | null;
  kg_per_participant: number | null;
  progress_pct: number | null;
  months: MonthFigures[];
}

/** A host's goals and the comparison between its sites (docs/adr/0046). `period` is this month,
 * still running. */
export interface HostProgress {
  host: HostRef;
  timezone: string;
  period: string;
  goal_kg: number | null;
  kg: number;
  participants: number;
  progress_pct: number | null;
  months: MonthFigures[];
  sites: SiteProgress[];
}

/** A host's impact certificate for a month (docs/adr/0027). */
export interface Certificate {
  id: string;
  host: HostRef;
  site: SiteRef | null;
  /** YYYY-MM, in the deployment's time zone. */
  period: string;
  factors_version: string;
  deposits: number;
  participants: number;
  grams: number;
  /** Grams of CO2e avoided against landfilling, EPA WARM v16. */
  co2e_g: number;
  by_material: Record<string, { grams: number; co2e_g: number }>;
  merkle_root: string;
  status: "issued" | "anchored" | "failed";
  anchor_tx: string | null;
  /** CID of the certificate's permanent public copy on IPFS, when Pinata is configured. */
  ipfs_cid: string | null;
  /** Where a browser can read that copy (the deployment's IPFS gateway). */
  ipfs_url: string | null;
  issued_by: string;
  created_at: string;
  anchored_at: string | null;
  /** Only on GET /v1/certificates/{id}: what the root is built from. */
  leaves?: { deposit_id: string; material: string; grams: number }[];
}

/** A merchant's charge, paid with a participant's signed transfer (docs/adr/0029). */
export interface Payment {
  id: string;
  qr: string;
  merchant: string;
  amount_cop: number;
  concept: string;
  status: "open" | "paying" | "paid" | "failed" | "expired";
  tx_hash: string | null;
  expires_at: string;
  created_at: string;
  paid_at: string | null;
}

export interface Redemption {
  id: string;
  amount_cop: number;
  status: "requested" | "pending" | "settled" | "refunded" | "failed";
  request_tx: string | null;
  decision_tx: string | null;
  bank_ref: string | null;
  decided_by: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface MerchantHome {
  name: string;
  charges: Payment[];
  redemptions: Redemption[];
}

/** The EIP-712 `Execute` a smart account's owner signs (docs/adr/0029); big numbers as strings. */
export interface TypedExecute {
  types: Record<string, { name: string; type: string }[]>;
  primaryType: "Execute";
  domain: { name: string; version: string; chainId: number; verifyingContract: string };
  message: { calls: { target: string; value: string; data: string }[]; nonce: string; deadline: string };
}

export interface SignedExecute {
  signature: string;
  deadline: number;
  nonce: number;
}

/** A host and its sites (GET /v1/hosts). */
export interface HostSummary extends HostRef {
  sites: (SiteRef & { containers: number })[];
}

/** A demo container as its screen would show it, QR included (demo mode only). */
export interface DemoContainer {
  id: string;
  name: string;
  accepted_materials: string[];
  online: boolean;
  busy: boolean;
  qr: string | null;
}

export interface DemoItem {
  name: string;
  weight_g: number;
  volume_ml: number;
  label: string;
}

export interface Session {
  id: string;
  container_id: string;
  state: string;
  declared_material: string;
  tare_g: number | null;
  deposited_g: number | null;
  score: number | null;
  reasons: string[];
  close_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface PayoutInfo {
  amount_cop: number;
  status: string;
  tx_hash: string | null;
}

/** One step of a deposit on its way from the lid to the settlement (docs/adr/0041). */
export interface DepositStep {
  key: "deposited" | "verified" | "advance" | "collected" | "sold" | "paid";
  status: "done" | "pending" | "failed" | "skipped";
  at: string | null;
  /** The advance; for `paid`, what came on top of the advance. */
  amount_cop: number | null;
  /** For `paid`: the deposit's whole share of the sale. */
  share_cop: number | null;
  tx_hash: string | null;
  /** The buyer for `sold`, the review note for a rejection, or a code: approved_after_review,
   * deferred, covered_by_advance. */
  note: string | null;
}

export interface HistoryEntry extends Session {
  container_name: string;
  payout: PayoutInfo | null;
  /** Paid on top of the advance when the deposit's bag was sold (docs/adr/0013). */
  settled_cop?: number | null;
  /** Empty for deposits that never got measured; absent from servers before ADR 0041. */
  steps?: DepositStep[];
}

/** Grams and CO2e avoided (only by what was sold, ADR 0027's factors). */
export interface ImpactFigures {
  verified_g: number;
  sold_g: number;
  co2e_g: number;
}

export interface PersonalImpact {
  factors_version: string;
  deposits: number;
  totals: ImpactFigures;
  materials: (ImpactFigures & { material: string })[];
  /** The last 12 months, oldest first, "YYYY-MM". */
  months: (ImpactFigures & { month: string })[];
}

/** A campus merchant that takes ZYR (GET /v1/merchants, docs/adr/0041). */
export interface MerchantListing {
  name: string;
  host: { id: string; name: string };
  site: { id: string; name: string } | null;
  place: string | null;
  hours: string | null;
  offer: string | null;
}

export interface Me {
  resident_id: string;
  /** The resident's account: where their ZYR lives. */
  address: string;
  /** The phone key that controls the account. */
  owner: string;
  email: string | null;
  /** Their collector name, when the operator named them a collector (docs/adr/0012). */
  collector: string | null;
  /** The data-processing policy they accepted, and the one in force (Ley 1581, docs/adr/0028). */
  privacy_version: string | null;
  privacy_current: string;
  /** Their business name, when the operator named them a merchant (docs/adr/0029). */
  merchant: string | null;
  /** On-chain balance, in pesos; may carry fractions of a peso. */
  balance_cop: number | null;
  payouts: { session_id: string; kind: string; amount_cop: number; status: string; tx_hash: string | null; created_at: string }[];
  sessions: HistoryEntry[];
}

/** A bag with a printed QR, holding one material (docs/adr/0012). */
export interface Bag {
  id: string;
  code: string;
  qr: string;
  material: string;
  status: "open" | "sealed" | "sold" | "settled";
  /** What the containers' scales measured into it. */
  grams: number;
  created_at: string;
  sealed_at: string | null;
}

/** One material taken out during a collection: into a bag, or as residue. */
export interface CollectionFill {
  id: string;
  bag_code: string | null;
  material: string | null;
  residue: boolean;
  start_g: number;
  end_g: number | null;
  grams: number | null;
  done: boolean;
}

/** A collector emptying one container (docs/adr/0012). */
export interface Collection {
  id: string;
  container_id: string;
  container_name: string;
  accepted_materials: string[];
  state: "authorized" | "open" | "closing" | "closed" | "expired" | "failed";
  tare_g: number | null;
  /** The scale's latest reading. */
  weight_g: number | null;
  final_g: number | null;
  expected_g: number | null;
  /** What left the container: opening weight minus closing weight. */
  removed_g: number | null;
  fills: CollectionFill[];
  open_fill_id: string | null;
  created_at: string;
  closed_at: string | null;
}

/** A container as a collector plans the round: fullest first (docs/adr/0042). */
export interface CollectorContainer {
  id: string;
  name: string;
  site: { id: string; name: string };
  accepted_materials: string[];
  /** 0 to 100 from the distance sensor; null without a reading. */
  fill_pct: number | null;
  last_emptied_at: string | null;
  deposits_since: number;
}

export interface CollectorHome {
  name: string;
  current: Collection | null;
  bags: Bag[];
  /** Absent from servers before ADR 0042. */
  containers?: CollectorContainer[];
}

export interface CollectorEarnings {
  collections: {
    id: string;
    container_name: string;
    closed_at: string | null;
    grams: number;
    earned_cop: number;
    /** Grams in bags not sold and settled yet. */
    pending_g: number;
    month: string | null;
  }[];
  /** The last 6 months, oldest first, "YYYY-MM". */
  months: { month: string; collections: number; grams: number; earned_cop: number }[];
  total_cop: number;
}

export interface SignIn {
  token: string;
  resident_id: string;
  address: string;
  owner: string;
}

/** A lost-phone recovery (docs/adr/0010-smart-accounts-and-recovery.md). */
export interface Recovery {
  id: string;
  status: "starting" | "waiting" | "cancelling" | "done" | "cancelled" | "failed";
  ready_at: string;
  /** "sábado 28 de noviembre, 3:15 p. m." in the API's time zone. */
  ready_label: string;
  cancelled_by: "owner" | "new_phone" | "chain" | "replaced" | null;
  created_at: string;
}

/** GET /v1/me/account: recovery email and recoveries this resident is part of. */
export interface AccountSecurity {
  address: string;
  owner: string;
  email: string | null;
  email_verified_at: string | null;
  email_available: boolean;
  recovery_available: boolean;
  /** Whether this phone may recover an older account (it has no history of its own). */
  can_recover: boolean;
  /** Someone is moving this account to another phone. */
  incoming: Recovery | null;
  /** This phone is waiting for an older account (or its request recently ended). */
  outgoing: Recovery | null;
  /** Set during the day after this account arrived on this phone. */
  recovered_at: string | null;
}

export interface CodeSent {
  sent_to: string;
  expires_in_s: number;
  resend_in_s: number;
}

/** A container in the booking list (GET /v1/containers). */
export interface ContainerSummary extends ContainerInfo {
  site_name: string;
  host_name: string;
}

/** One hour of one container. `state` is relative to now. */
export interface Slot {
  starts_at: string;
  ends_at: string;
  hour: number;
  taken: number;
  capacity: number;
  mine: boolean;
  state: "past" | "now" | "future";
  available: boolean;
}

export interface DaySlots {
  container_id: string;
  container_name: string;
  site_name: string;
  timezone: string;
  opens_hour: number;
  closes_hour: number;
  capacity: number;
  /** The bookable days (today first), as YYYY-MM-DD in the site's time zone. */
  days: string[];
  day: string;
  slots: Slot[];
}

export interface Booking {
  id: string;
  container_id: string;
  container_name: string;
  site_name: string;
  starts_at: string;
  ends_at: string;
  /** YYYY-MM-DD and hour of day, in the site's time zone. */
  day: string;
  hour: number;
  state: "upcoming" | "now" | "used" | "missed" | "cancelled";
  walk_in: boolean;
}

export type LiveEvent =
  | ({ type: "state" } & Partial<Session>)
  | { type: "reading"; weight_g: number; fill_mm: number | null };

/** What the apps say when the API answers 429 (docs/adr/0035). */
export const TOO_FAST = "Vas muy rápido: espera unos segundos e inténtalo de nuevo.";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
  }
}

const post = (body?: unknown): RequestInit => ({
  method: "POST",
  body: body === undefined ? undefined : JSON.stringify(body),
});

/** Everything the apps call, bound to one API base URL. */
/** A file the API sent: what `merchantExport` returns. */
export interface DownloadedFile {
  name: string;
  type: string;
  bytes: Uint8Array;
}

export type ExportFormat = "csv" | "xlsx";

/** Local days, both included, as YYYY-MM-DD. */
export interface Period {
  start: string;
  end: string;
}

export function exportQuery(period: Period, format: ExportFormat): string {
  return new URLSearchParams({ start: period.start, end: period.end, format }).toString();
}

export function createApi(baseUrl: string) {
  async function call<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
    let res: Response;
    try {
      res = await fetch(`${baseUrl}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
    } catch {
      throw new ApiError(0, "No hay conexión con el servidor de Zyrcle.");
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) fail(res, body);
    return body as T;
  }

  function fail(res: Response, body: { detail?: { detail?: string; code?: string } | string }): never {
    const detail = (typeof body?.detail === "object" ? body.detail.detail : undefined) ?? body?.detail ?? res.statusText;
    const code = typeof body?.detail === "object" ? body.detail.code : undefined;
    if (res.status === 429 && code === "rate_limited") throw new ApiError(429, TOO_FAST, "rate_limited");
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail), code);
  }

  /** A file the API sends as an attachment (an export): its bytes and the name the API gave it. */
  async function file(path: string, token: string): Promise<DownloadedFile> {
    let res: Response;
    try {
      res = await fetch(`${baseUrl}${path}`, { headers: { Authorization: `Bearer ${token}` } });
    } catch {
      throw new ApiError(0, "No hay conexión con el servidor de Zyrcle.");
    }
    if (!res.ok) fail(res, await res.json().catch(() => ({})));
    const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1];
    return {
      name: name ?? path.split("?")[0].split("/").pop() ?? "zyrcle",
      type: res.headers.get("Content-Type") ?? "application/octet-stream",
      bytes: new Uint8Array(await res.arrayBuffer()),
    };
  }

  const api = {
    nonce: () => call<{ nonce: string }>("/v1/auth/nonce", post()),
    verify: (message: string, signature: string) => call<SignIn>("/v1/auth/verify", post({ message, signature })),

    stats: () => call<Totals>("/v1/stats"),
    hosts: () => call<HostSummary[]>("/v1/hosts"),
    hostCertificates: (hostId: string) => call<Certificate[]>(`/v1/hosts/${hostId}/certificates`),
    hostProgress: (hostId: string, months = 6) => call<HostProgress>(`/v1/hosts/${hostId}/progress?months=${months}`),
    /** The certificate as a PDF with a QR to its verification page (docs/adr/0046): a link, not a call. */
    certificatePdfUrl: (id: string) => `${baseUrl}/v1/certificates/${id}/pdf`,
    certificate: (id: string) => call<Certificate>(`/v1/certificates/${id}`),
    hostDashboard: (hostId: string, days = 14) =>
      call<HostDashboard>(`/v1/hosts/${hostId}/dashboard?days=${days}`),
    dashboard: (siteId: string, days = 14) => call<Dashboard>(`/v1/sites/${siteId}/dashboard?days=${days}`),
    container: (id: string) => call<ContainerInfo>(`/v1/containers/${encodeURIComponent(id)}`),
    containers: () => call<ContainerSummary[]>("/v1/containers"),

    start: (token: string, qr: string, material: string) =>
      call<Session>("/v1/sessions", post({ qr, material }), token),
    finish: (token: string, id: string) => call<Session>(`/v1/sessions/${id}/finish`, post(), token),
    session: (token: string, id: string) => call<Session>(`/v1/sessions/${id}`, {}, token),
    me: (token: string) => call<Me>("/v1/me", {}, token),
    impact: (token: string) => call<PersonalImpact>("/v1/me/impact", {}, token),
    merchants: () => call<MerchantListing[]>("/v1/merchants"),
    acceptPrivacy: (token: string, version: string) =>
      call<{ privacy_version: string }>("/v1/me/consent", post({ version }), token),
    registerPushToken: (token: string, pushToken: string, platform: "ios" | "android") =>
      call<void>("/v1/me/push-token", { method: "PUT", body: JSON.stringify({ token: pushToken, platform }) }, token),

    account: (token: string) => call<AccountSecurity>("/v1/me/account", {}, token),
    sendEmailCode: (token: string, email: string) => call<CodeSent>("/v1/me/email", post({ email }), token),
    verifyEmail: (token: string, email: string, code: string) =>
      call<{ email: string; email_verified_at: string }>("/v1/me/email/verify", post({ email, code }), token),
    sendRecoveryCode: (token: string, email: string) => call<CodeSent>("/v1/recovery/code", post({ email }), token),
    startRecovery: (token: string, email: string, code: string) =>
      call<Recovery>("/v1/recovery", post({ email, code }), token),
    cancelRecovery: (token: string, id: string) => call<Recovery>(`/v1/recovery/${id}`, { method: "DELETE" }, token),

    slots: (token: string, containerId: string, day?: string) =>
      call<DaySlots>(
        `/v1/containers/${encodeURIComponent(containerId)}/slots${day ? `?day=${day}` : ""}`,
        {},
        token,
      ),
    bookings: (token: string) => call<Booking[]>("/v1/bookings", {}, token),
    book: (token: string, containerId: string, startsAt: string) =>
      call<Booking>("/v1/bookings", post({ container_id: containerId, starts_at: startsAt }), token),
    cancelBooking: (token: string, id: string) =>
      call<Booking>(`/v1/bookings/${id}`, { method: "DELETE" }, token),

    collector: (token: string) => call<CollectorHome>("/v1/collector", {}, token),
    earnings: (token: string) => call<CollectorEarnings>("/v1/collector/earnings", {}, token),
    startCollection: (token: string, qr: string) => call<Collection>("/v1/collections", post({ qr }), token),
    collection: (token: string, id: string) => call<Collection>(`/v1/collections/${id}`, {}, token),
    /** Start filling the bag with this QR or code; null takes out residue. */
    addFill: (token: string, id: string, bag: string | null) =>
      call<Collection>(`/v1/collections/${id}/fills`, post({ bag }), token),
    finishFill: (token: string, id: string, fillId: string) =>
      call<Collection>(`/v1/collections/${id}/fills/${fillId}/done`, post(), token),
    finishCollection: (token: string, id: string) =>
      call<Collection>(`/v1/collections/${id}/finish`, post(), token),
    sealBag: (token: string, code: string) => call<Bag>(`/v1/bags/${encodeURIComponent(code)}/seal`, post(), token),

    payment: (token: string, id: string) => call<Payment>(`/v1/payments/${id}`, {}, token),
    paymentIntent: (token: string, id: string) => call<TypedExecute>(`/v1/payments/${id}/intent`, post(), token),
    pay: (token: string, id: string, signed: SignedExecute) => call<Payment>(`/v1/payments/${id}/pay`, post(signed), token),
    merchant: (token: string) => call<MerchantHome>("/v1/merchant", {}, token),
    charge: (token: string, amount_cop: number, concept: string) =>
      call<Payment>("/v1/merchant/charges", post({ amount_cop, concept }), token),
    redemptionIntent: (token: string, amount_cop: number) =>
      call<{ id: string; typed_data: TypedExecute }>("/v1/merchant/redemptions", post({ amount_cop }), token),
    signRedemption: (token: string, id: string, signed: SignedExecute) =>
      call<Redemption>(`/v1/merchant/redemptions/${id}/sign`, post(signed), token),
    /** Charges and redemptions from `start` to `end` (YYYY-MM-DD, both included) for the
     * merchant's bookkeeping (docs/adr/0045). */
    merchantExport: (token: string, period: Period, format: ExportFormat) =>
      file(`/v1/merchant/export?${exportQuery(period, format)}`, token),

    demo: {
      containers: () => call<DemoContainer[]>("/v1/demo/containers"),
      items: () => call<DemoItem[]>("/v1/demo/items"),
      drop: (token: string, sessionId: string, item: string) =>
        call<{ ok: true }>(`/v1/demo/sessions/${sessionId}/drop`, post({ item }), token),
      /** Empty bags with their QR, standing in for printed labels. */
      bags: () => call<Bag[]>("/v1/demo/bags"),
      /** The collector's hands: take one kind of material out (null: everything left). */
      takeOut: (token: string, collectionId: string, kind: string | null) =>
        call<{ grams: number }>(`/v1/demo/collections/${collectionId}/take-out`, post({ kind }), token),
    },
  };

  /** WebSocket with the session's live weight and state changes (token in the query: browsers
   * cannot set WebSocket headers). */
  const liveUrl = (sessionId: string, token: string) =>
    `${baseUrl.replace(/^http/, "ws")}/v1/sessions/${sessionId}/live?token=${encodeURIComponent(token)}`;

  return { api, liveUrl };
}

export type Api = ReturnType<typeof createApi>["api"];

/** "the container is open from 06:00 to 22:00" -> "de 6:00 a. m. a 10:00 p. m.". */
function openingHours(detail: string): string | null {
  const m = /from (\d{2}):00 to (\d{2}):00/.exec(detail);
  if (!m) return null;
  const until = Number(m[2]) === 24 ? "medianoche" : hourLabel(Number(m[2]));
  return `de ${hourLabel(Number(m[1]))} a ${until}`;
}

/** Close a sentence without doubling the period of "p. m.". */
const end = (s: string) => (s.endsWith(".") ? s : `${s}.`);

/** Spanish message for a failed attempt to open a container. */
export function startErrorMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return "Algo salió mal. Intenta de nuevo.";
  if (e.code === "rate_limited") return TOO_FAST;
  const d = e.message;
  if (e.status === 0) return d;
  if (e.code === "closed") {
    const hours = openingHours(d);
    return hours ? `El contenedor está cerrado a esta hora. Abre ${end(hours)}` : "El contenedor está cerrado a esta hora.";
  }
  if (e.code === "slot_full")
    return "Todos los cupos de esta hora están reservados en este contenedor. Reserva otra hora o prueba en otro contenedor.";
  if (e.code === "recovery_pending") return RECOVERY_PENDING;
  if (e.code === "consent_required") return "Antes de reciclar, acepta la política de tratamiento de datos en Cuenta.";
  if (/invalid or expired/.test(d)) return "El código del QR ya cambió. Escanéalo de nuevo.";
  if (/offline/.test(d)) return "El contenedor está sin conexión.";
  if (/busy/.test(d)) return "Otra persona está usando este contenedor. Espera un momento.";
  if (/being emptied/.test(d)) return "Están vaciando este contenedor. Intenta en unos minutos.";
  if (/already have an open session/.test(d)) return "Ya tienes un depósito abierto. Termínalo antes de abrir otro.";
  if (/does not accept/.test(d)) return "Este contenedor no recibe ese material.";
  if (/could not reach/.test(d)) return "No pudimos comunicarnos con el contenedor. Intenta de nuevo.";
  if (/unknown container/.test(d)) return "Ese contenedor no existe.";
  return d;
}

/** Spanish message for a failed booking or cancellation. */
export function bookingErrorMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return "Algo salió mal. Intenta de nuevo.";
  if (e.code === "rate_limited") return TOO_FAST;
  switch (e.code) {
    case "slot_full":
      return "Esa hora se acaba de llenar. Elige otra.";
    case "already_booked":
      return "Ya tienes esa hora reservada.";
    case "too_many_bookings":
      return "Puedes tener hasta 3 turnos por delante. Cancela uno para reservar otro.";
    case "closed": {
      const hours = openingHours(e.message);
      return hours ? `A esa hora está cerrado. Abre ${end(hours)}` : "A esa hora está cerrado.";
    }
    case "forbidden":
      return "Ese turno ya se usó.";
    case "recovery_pending":
      return RECOVERY_PENDING;
    default:
      if (/over/.test(e.message)) return "Esa hora ya pasó.";
      return e.status === 0 ? e.message : "No pudimos guardar el turno. Intenta de nuevo.";
  }
}

const RECOVERY_PENDING =
  "Este teléfono está esperando tu cuenta anterior. Podrás depositar y reservar cuando termine la recuperación.";

/** Spanish message for a failed step with the recovery email or a recovery. */
export function accountErrorMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return "Algo salió mal. Intenta de nuevo.";
  if (e.code === "rate_limited") return TOO_FAST;
  switch (e.code) {
    case "invalid_email":
      return "Ese correo no parece válido. Revísalo.";
    case "too_soon": {
      const s = /wait (\d+) seconds/.exec(e.message)?.[1];
      return s ? `Espera ${s} segundos para pedir otro código.` : "Espera un minuto para pedir otro código.";
    }
    case "too_many_codes":
      return "Pediste demasiados códigos hoy. Intenta mañana.";
    case "code_invalid": {
      const left = /(\d+) attempts left/.exec(e.message)?.[1];
      if (left === "0") return "Ese código ya no sirve. Pide uno nuevo.";
      if (left) return `El código no es correcto. Te quedan ${left} ${left === "1" ? "intento" : "intentos"}.`;
      return "El código no es válido o ya venció. Pide uno nuevo.";
    }
    case "email_taken":
      return "Otra cuenta de Zyrcle ya usa ese correo.";
    case "phone_in_use":
      return "Esta app ya tiene depósitos, turnos o un correo propios, así que no puede recibir otra cuenta.";
    case "recovery_in_progress":
      return "Este teléfono ya está recuperando otra cuenta. Cancela esa primero.";
    case "recovery_unavailable":
      return "La recuperación de cuentas todavía no está activa en el servidor.";
    default:
      return e.status === 0 ? e.message : "No pudimos completar el paso. Intenta de nuevo.";
  }
}

/** Spanish message for a failed payment or redemption (docs/adr/0029). */
export function paymentErrorMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return "Algo salió mal. Intenta de nuevo.";
  if (e.code === "rate_limited") return TOO_FAST;
  const d = e.message;
  if (e.status === 0) return d;
  if (/not enough ZYR/.test(d)) return "No tienes saldo suficiente.";
  if (/no longer open/.test(d)) return "Este cobro ya no está abierto. Pide al comercio uno nuevo.";
  if (/another payment in progress/.test(d)) return "Tienes otro pago en curso. Espera a que termine.";
  if (/own charge/.test(d)) return "No puedes pagar tu propio cobro.";
  if (/signature/.test(d)) return "La firma no coincide con este teléfono.";
  if (/only merchants/.test(d)) return "Esta función es para comercios.";
  return d;
}

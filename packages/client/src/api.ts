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

export interface HistoryEntry extends Session {
  container_name: string;
  payout: PayoutInfo | null;
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
  balance_cop: number | null;
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

export interface CollectorHome {
  name: string;
  current: Collection | null;
  bags: Bag[];
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
    if (!res.ok) {
      const detail = body?.detail?.detail ?? body?.detail ?? res.statusText;
      throw new ApiError(
        res.status,
        typeof detail === "string" ? detail : JSON.stringify(detail),
        body?.detail?.code,
      );
    }
    return body as T;
  }

  const api = {
    nonce: () => call<{ nonce: string }>("/v1/auth/nonce", post()),
    verify: (message: string, signature: string) => call<SignIn>("/v1/auth/verify", post({ message, signature })),

    stats: () => call<Totals>("/v1/stats"),
    hosts: () => call<HostSummary[]>("/v1/hosts"),
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
  const d = e.message;
  if (e.status === 0) return d;
  if (e.code === "closed") {
    const hours = openingHours(d);
    return hours ? `El contenedor está cerrado a esta hora. Abre ${end(hours)}` : "El contenedor está cerrado a esta hora.";
  }
  if (e.code === "slot_full")
    return "Todos los cupos de esta hora están reservados en este contenedor. Reserva otra hora o prueba en otro contenedor.";
  if (e.code === "recovery_pending") return RECOVERY_PENDING;
  if (/invalid or expired/.test(d)) return "El código del QR ya cambió. Escanéalo de nuevo.";
  if (/offline/.test(d)) return "El contenedor está sin conexión.";
  if (/busy/.test(d)) return "Otra persona está usando este contenedor. Espera un momento.";
  if (/does not accept/.test(d)) return "Este contenedor no recibe ese material.";
  if (/could not reach/.test(d)) return "No pudimos comunicarnos con el contenedor. Intenta de nuevo.";
  if (/unknown container/.test(d)) return "Ese contenedor no existe.";
  return d;
}

/** Spanish message for a failed booking or cancellation. */
export function bookingErrorMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return "Algo salió mal. Intenta de nuevo.";
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

/** Typed client for the Zyrcle API (apps/api), shared by the web app and the mobile app. */

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
  residence_id: string;
  residence_name?: string;
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

export interface Dashboard {
  residence: { id: string; name: string };
  timezone: string;
  totals: Totals;
  containers: DashboardContainer[];
  activity: { day: string; kg: Record<string, number> }[];
  payouts: { day: string; cop: number }[];
}

export interface ResidenceSummary {
  id: string;
  name: string;
  containers: number;
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
  address: string;
  balance_cop: number | null;
  sessions: HistoryEntry[];
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
    verify: (message: string, signature: string) =>
      call<{ token: string; resident_id: string; address: string }>(
        "/v1/auth/verify",
        post({ message, signature }),
      ),

    stats: () => call<Totals>("/v1/stats"),
    residences: () => call<ResidenceSummary[]>("/v1/residences"),
    dashboard: (residenceId: string, days = 14) =>
      call<Dashboard>(`/v1/residences/${residenceId}/dashboard?days=${days}`),
    container: (id: string) => call<ContainerInfo>(`/v1/containers/${encodeURIComponent(id)}`),

    start: (token: string, qr: string, material: string) =>
      call<Session>("/v1/sessions", post({ qr, material }), token),
    finish: (token: string, id: string) => call<Session>(`/v1/sessions/${id}/finish`, post(), token),
    session: (token: string, id: string) => call<Session>(`/v1/sessions/${id}`, {}, token),
    me: (token: string) => call<Me>("/v1/me", {}, token),

    demo: {
      containers: () => call<DemoContainer[]>("/v1/demo/containers"),
      items: () => call<DemoItem[]>("/v1/demo/items"),
      drop: (token: string, sessionId: string, item: string) =>
        call<{ ok: true }>(`/v1/demo/sessions/${sessionId}/drop`, post({ item }), token),
    },
  };

  /** WebSocket with the session's live weight and state changes (token in the query: browsers
   * cannot set WebSocket headers). */
  const liveUrl = (sessionId: string, token: string) =>
    `${baseUrl.replace(/^http/, "ws")}/v1/sessions/${sessionId}/live?token=${encodeURIComponent(token)}`;

  return { api, liveUrl };
}

export type Api = ReturnType<typeof createApi>["api"];

/** Spanish message for a failed attempt to open a container. */
export function startErrorMessage(e: unknown): string {
  if (!(e instanceof ApiError)) return "Algo salió mal. Intenta de nuevo.";
  const d = e.message;
  if (e.status === 0) return d;
  if (/invalid or expired/.test(d)) return "El código del QR ya cambió. Escanéalo de nuevo.";
  if (/offline/.test(d)) return "El contenedor está sin conexión.";
  if (/busy/.test(d)) return "Otra persona está usando este contenedor. Espera un momento.";
  if (/does not accept/.test(d)) return "Este contenedor no recibe ese material.";
  if (/could not reach/.test(d)) return "No pudimos comunicarnos con el contenedor. Intenta de nuevo.";
  if (/unknown container/.test(d)) return "Ese contenedor no existe.";
  return d;
}

/** The operator API (docs/adr/0014), used only by the console. Participants' calls live in
 * packages/client. Every call carries the operator's session token. */
import type { Bag, Collection, Session } from "@zyrcle/client";
import { API_URL } from "@/lib/config";

export class OperatorApiError extends Error {
    constructor(
        public status: number,
        message: string,
        public code?: string,
    ) {
        super(message);
    }
}

export interface OperatorMe {
    name: string;
    role: "admin" | "operator";
    id: string | null;
}

export interface OperatorAccount {
    id: string;
    email: string;
    name: string;
    role: "admin" | "operator";
    active: boolean;
    last_login_at: string | null;
}

export interface TreasuryState {
    address: string;
    backing_cop: number;
    minted_cop: number;
    available_cop: number;
    seed_capital_cop: number;
    operations_revenue_cop: number;
}

export interface Incident {
    id: string;
    kind: "container_balance" | "collection_balance" | "bag_balance";
    status: "open" | "resolved";
    container_id: string | null;
    collection_id: string | null;
    bag_ids: string[];
    expected_g: number;
    measured_g: number;
    difference_g: number;
    detail: Record<string, unknown> | null;
    created_at: string;
    resolved_at: string | null;
    resolved_by: string | null;
    resolution_note: string | null;
}

export interface OperatorBag extends Bag {
    collector: string | null;
}

export interface OperatorCollection extends Collection {
    collector: string | null;
}

export interface Collector {
    resident_id: string;
    address: string;
    name: string;
    active: boolean;
}

export interface SettlementRow {
    party: "deposit" | "collector" | "host";
    ref: string;
    address: string | null;
    grams: number;
    share_cop: number;
    paid_cop: number | null;
    tx_hash: string | null;
}

export interface SaleLine {
    id: string;
    bag_code: string;
    material: string;
    bag_g: number;
    buyer_g: number;
    amount_cop: number;
    status: "pending" | "waiting" | "settling" | "settled" | "failed";
    reason: string | null;
    residents_cop: number | null;
    collector_cop: number | null;
    host_cop: number | null;
    report_hash: string | null;
    txs: { step: string; tx: string; at: string }[];
    settled_at: string | null;
    settlements?: SettlementRow[];
}

export interface Sale {
    id: string;
    buyer: string;
    ticket_ref: string;
    sold_on: string;
    total_cop: number;
    evidence_hash: string;
    status: "recorded" | "confirmed";
    recorded_by: string;
    bank_ref: string | null;
    confirmed_by: string | null;
    confirmed_at: string | null;
    created_at: string;
    lines: SaleLine[];
}

export interface HostRow {
    id: string;
    name: string;
    kind: "university" | "residential" | "business" | "public";
    payout_address: string | null;
}

export interface SiteRow {
    id: string;
    host_id: string;
    host_name: string;
    name: string;
    opens_hour: number;
    closes_hour: number;
    slot_capacity: number;
}

export interface Price {
    material: string;
    cop_per_kg: number | null;
    source: string | null;
}

export interface ContainerBalance {
    container_id: string;
    name: string;
    last_collection_at: string | null;
    left_after_g: number | null;
    open_incidents: number;
}

const json = (method: string, body?: unknown): RequestInit => ({
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
});

export function operatorApi(token: string | null, onUnauthorized: () => void) {
    async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
        let res: Response;
        try {
            res = await fetch(`${API_URL}${path}`, {
                ...init,
                headers: {
                    "Content-Type": "application/json",
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
            });
        } catch {
            throw new OperatorApiError(0, "No hay conexión con el servidor de Zyrcle.");
        }
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
            if (res.status === 401 && token) onUnauthorized();
            const detail = body?.detail?.detail ?? body?.detail ?? res.statusText;
            throw new OperatorApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail), body?.detail?.code);
        }
        return body as T;
    }

    return {
        requestCode: (email: string) => call<{ sent_to: string; resend_in_s: number }>("/v1/operator/login/code", json("POST", { email })),
        login: (email: string, code: string) => call<{ token: string; operator: OperatorAccount }>("/v1/operator/login", json("POST", { email, code })),
        me: () => call<OperatorMe>("/v1/operator/me"),

        treasury: () => call<TreasuryState>("/v1/operator/treasury"),
        reviewQueue: () => call<Session[]>("/v1/operator/review"),
        review: (id: string, approve: boolean, note: string) => call<Session>(`/v1/operator/sessions/${id}/review`, json("POST", { approve, note: note || null })),

        incidents: (status: "open" | "resolved" | null = "open") => call<Incident[]>(`/v1/operator/incidents${status ? `?status=${status}` : ""}`),
        resolveIncident: (id: string, note: string) => call<Incident>(`/v1/operator/incidents/${id}/resolve`, json("POST", { note })),

        collections: () => call<OperatorCollection[]>("/v1/operator/collections?limit=30"),
        containersBalance: () => call<ContainerBalance[]>("/v1/operator/containers/balance"),
        bags: (status?: string) => call<OperatorBag[]>(`/v1/operator/bags${status ? `?status=${status}` : ""}`),
        createBags: (material: string, count: number) => call<Bag[]>("/v1/operator/bags", json("POST", { material, count })),
        collectors: () => call<Collector[]>("/v1/operator/collectors"),
        nameCollector: (address: string, name: string, active = true) => call<Collector>("/v1/operator/collectors", json("POST", { address, name, active })),

        sales: () => call<Sale[]>("/v1/operator/sales"),
        sale: (id: string) => call<Sale>(`/v1/operator/sales/${id}`),
        recordSale: (body: { buyer: string; ticket_ref: string; sold_on: string; lines: { bag: string; buyer_g: number; amount_cop: number }[] }) =>
            call<Sale>("/v1/operator/sales", json("POST", body)),
        confirmSale: (id: string, bank_ref: string, received_cop: number) => call<Sale>(`/v1/operator/sales/${id}/confirm`, json("POST", { bank_ref, received_cop })),

        hosts: () => call<HostRow[]>("/v1/operator/hosts"),
        createHost: (name: string, kind: HostRow["kind"]) => call<HostRow>("/v1/operator/hosts", json("POST", { name, kind })),
        setHostAddress: (id: string, payout_address: string | null) => call<HostRow>(`/v1/operator/hosts/${id}`, json("PATCH", { payout_address })),
        sites: () => call<SiteRow[]>("/v1/operator/sites"),
        createSite: (host_id: string, name: string) => call<SiteRow>("/v1/operator/sites", json("POST", { host_id, name })),
        setSchedule: (id: string, opens_hour: number, closes_hour: number, slot_capacity: number) =>
            call<SiteRow>(`/v1/operator/sites/${id}/schedule`, json("PUT", { opens_hour, closes_hour, slot_capacity })),

        prices: () => call<Price[]>("/v1/operator/prices"),
        setPrice: (material: string, cop_per_kg: number) => call<Price>(`/v1/operator/prices/${material}`, json("PUT", { cop_per_kg })),

        operators: () => call<OperatorAccount[]>("/v1/operator/operators"),
        addOperator: (email: string, name: string, role: "admin" | "operator") => call<OperatorAccount>("/v1/operator/operators", json("POST", { email, name, role })),
        updateOperator: (id: string, patch: Partial<Pick<OperatorAccount, "name" | "role" | "active">>) => call<OperatorAccount>(`/v1/operator/operators/${id}`, json("PATCH", patch)),
    };
}

export type OperatorApi = ReturnType<typeof operatorApi>;

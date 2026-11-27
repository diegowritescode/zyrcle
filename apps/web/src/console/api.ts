/** The operator API (docs/adr/0014), used only by the console. Participants' calls live in
 * packages/client. Every call carries the operator's session token. */
import { exportQuery, type Bag, type Certificate, type Collection, type DownloadedFile, type ExportFormat, type Period, type Redemption, type Session } from "@zyrcle/client";
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
    /** The host whose containers they empty; null: every host's (docs/adr/0042). */
    host_id: string | null;
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

/** What the model read from a ticket photo, and what the API made of it (docs/adr/0038). */
export interface TicketScan {
    id: string;
    status: "read" | "failed";
    reading: {
        readable: boolean;
        center_name: string | null;
        ticket_ref: string | null;
        date: string | null;
        lines: { material: string; label: string; kg: number | null; cop_per_kg: number | null; amount_cop: number | null }[];
        total_cop: number | null;
        notes: string;
    } | null;
    error: string | null;
    checks: { kind: string; detail: string; line?: number }[];
    proposed_bags: (string | null)[];
    center_id: string | null;
    sale_id: string | null;
}

/** A movement of the bank account and what the API proposes it pays (docs/adr/0039). */
export interface BankProposal {
    line: { id: string; posted_on: string; description: string; reference: string; amount_cop: number };
    kind: "sale" | "redemption";
    target_id: string;
    target: { ticket_ref?: string; buyer?: string; merchant?: string; nit?: string; amount_cop: number };
    score: number;
    why: string[];
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
    /** The collection center this site sells to (docs/adr/0037). */
    center_id: string | null;
}

/** A collection center and what it pays per material (docs/adr/0037). */
export interface Center {
    id: string;
    name: string;
    tax_id: string | null;
    address: string | null;
    contact: string | null;
    active: boolean;
    prices: Record<string, { cop_per_kg: number; source: "manual" | "sales"; updated_by: string; updated_at: string }>;
    sites: { id: string; name: string }[];
}

export interface Price {
    material: string;
    cop_per_kg: number | null;
    source: string | null;
}

export interface CertificatePreview {
    period: string;
    factors_version: string;
    deposits: number;
    participants: number;
    grams: number;
    co2e_g: number;
    by_material: Record<string, { grams: number; co2e_g: number }>;
    merkle_root: string;
}

export interface Health {
    checked_at: string;
    ok: boolean;
    warnings: { kind: string; text: string }[];
    outboxes: { name: string; pending: number; failed: number; oldest_pending_min: number | null; stuck: boolean }[];
    devices: { online: number; total: number };
    mqtt: boolean;
    chain: { block?: number; block_age_s?: number; waiting_s?: number | null; node_healthy?: boolean; available_cop?: number; keys: Record<string, { address: string; zyr: number }>; error?: string } | null;
}

export interface MerchantRow {
    resident_id: string;
    address: string;
    name: string;
    nit: string;
    host_id: string | null;
    active: boolean;
    /** Where participants find it (docs/adr/0041). */
    site_id: string | null;
    place: string | null;
    hours: string | null;
    offer: string | null;
}

export type MerchantIn = Pick<MerchantRow, "address" | "name" | "nit" | "host_id" | "site_id" | "place" | "hours" | "offer"> & { active?: boolean };

export interface OperatorRedemption extends Redemption {
    merchant: string;
    nit: string;
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
            if (res.status === 429 && body?.detail?.code === "rate_limited") {
                throw new OperatorApiError(429, "Vas muy rápido: espera unos segundos e inténtalo de nuevo.", "rate_limited");
            }
            throw new OperatorApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail), body?.detail?.code);
        }
        return body as T;
    }

    /** A file the API sends as an attachment, with the name it gave it (docs/adr/0045). */
    async function file(path: string): Promise<DownloadedFile> {
        let res: Response;
        try {
            res = await fetch(`${API_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
        } catch {
            throw new OperatorApiError(0, "No hay conexión con el servidor de Zyrcle.");
        }
        if (!res.ok) {
            if (res.status === 401 && token) onUnauthorized();
            const body = await res.json().catch(() => ({}));
            const detail = body?.detail?.detail ?? body?.detail ?? res.statusText;
            throw new OperatorApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail), body?.detail?.code);
        }
        const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? "zyrcle-export";
        return { name, type: res.headers.get("Content-Type") ?? "application/octet-stream", bytes: new Uint8Array(await res.arrayBuffer()) };
    }

    return {
        requestCode: (email: string) => call<{ sent_to: string; resend_in_s: number }>("/v1/operator/login/code", json("POST", { email })),
        login: (email: string, code: string) => call<{ token: string; operator: OperatorAccount }>("/v1/operator/login", json("POST", { email, code })),
        me: () => call<OperatorMe>("/v1/operator/me"),

        treasury: () => call<TreasuryState>("/v1/operator/treasury"),
        health: () => call<Health>("/v1/operator/health"),
        reviewQueue: () => call<Session[]>("/v1/operator/review"),
        review: (id: string, approve: boolean, note: string) => call<Session>(`/v1/operator/sessions/${id}/review`, json("POST", { approve, note: note || null })),

        incidents: (status: "open" | "resolved" | null = "open") => call<Incident[]>(`/v1/operator/incidents${status ? `?status=${status}` : ""}`),
        resolveIncident: (id: string, note: string) => call<Incident>(`/v1/operator/incidents/${id}/resolve`, json("POST", { note })),

        collections: () => call<OperatorCollection[]>("/v1/operator/collections?limit=30"),
        containersBalance: () => call<ContainerBalance[]>("/v1/operator/containers/balance"),
        bags: (status?: string) => call<OperatorBag[]>(`/v1/operator/bags${status ? `?status=${status}` : ""}`),
        createBags: (material: string, count: number) => call<Bag[]>("/v1/operator/bags", json("POST", { material, count })),
        collectors: () => call<Collector[]>("/v1/operator/collectors"),
        nameCollector: (address: string, name: string, host_id: string | null, active = true) =>
            call<Collector>("/v1/operator/collectors", json("POST", { address, name, host_id, active })),

        sales: () => call<Sale[]>("/v1/operator/sales"),
        sale: (id: string) => call<Sale>(`/v1/operator/sales/${id}`),
        centers: () => call<Center[]>("/v1/operator/centers"),
        createCenter: (body: { name: string; tax_id?: string | null }) => call<Center>("/v1/operator/centers", json("POST", body)),
        setCenterPrice: (id: string, material: string, cop_per_kg: number, source: "manual" | "sales") =>
            call<Center>(`/v1/operator/centers/${id}/prices/${material}`, json("PUT", { cop_per_kg, source })),
        centerSuggestions: (id: string) => call<Record<string, { cop_per_kg: number; lines: number }>>(`/v1/operator/centers/${id}/suggested-prices`),
        setSiteCenter: (siteId: string, center_id: string | null) => call<unknown>(`/v1/operator/sites/${siteId}/center`, json("PUT", { center_id })),
        uploadStatement: (filename: string, content_base64: string) =>
            call<{ movements: number; added: number; already_known: number; proposals: BankProposal[] }>("/v1/operator/bank-statements", json("POST", { filename, content_base64 })),
        bankProposals: () => call<BankProposal[]>("/v1/operator/bank-proposals"),
        matchBankLine: (lineId: string, kind: "sale" | "redemption", target_id: string) =>
            call<unknown>(`/v1/operator/bank-lines/${lineId}/match`, json("POST", { kind, target_id })),
        scanTicket: (image_base64: string, media_type: "image/jpeg" | "image/png" | "image/webp") =>
            call<TicketScan>("/v1/operator/ticket-scans", json("POST", { image_base64, media_type })),
        recordSale: (body: { buyer: string; center_id?: string | null; ticket_scan_id?: string | null; ticket_ref: string; sold_on: string; lines: { bag: string; buyer_g: number; amount_cop: number }[] }) =>
            call<Sale>("/v1/operator/sales", json("POST", body)),
        confirmSale: (id: string, bank_ref: string, received_cop: number) => call<Sale>(`/v1/operator/sales/${id}/confirm`, json("POST", { bank_ref, received_cop })),

        hosts: () => call<HostRow[]>("/v1/operator/hosts"),
        createHost: (name: string, kind: HostRow["kind"]) => call<HostRow>("/v1/operator/hosts", json("POST", { name, kind })),
        setHostAddress: (id: string, payout_address: string | null) => call<HostRow>(`/v1/operator/hosts/${id}`, json("PATCH", { payout_address })),
        sites: () => call<SiteRow[]>("/v1/operator/sites"),
        createSite: (host_id: string, name: string) => call<Omit<SiteRow, "host_name">>("/v1/operator/sites", json("POST", { host_id, name })),
        setSchedule: (id: string, opens_hour: number, closes_hour: number, slot_capacity: number) =>
            call<Omit<SiteRow, "host_name">>(`/v1/operator/sites/${id}/schedule`, json("PUT", { opens_hour, closes_hour, slot_capacity })),

        certificates: () => call<Certificate[]>("/v1/operator/certificates"),
        previewCertificate: (host_id: string, site_id: string | null, period: string) =>
            call<CertificatePreview>("/v1/operator/certificates/preview", json("POST", { host_id, site_id, period })),
        issueCertificate: (host_id: string, site_id: string | null, period: string) =>
            call<Certificate>("/v1/operator/certificates", json("POST", { host_id, site_id, period })),

        merchants: () => call<MerchantRow[]>("/v1/operator/merchants"),
        nameMerchant: (body: MerchantIn) => call<MerchantRow>("/v1/operator/merchants", json("POST", body)),
        merchantExport: (residentId: string, period: Period, format: ExportFormat) =>
            file(`/v1/operator/merchants/${residentId}/export?${exportQuery(period, format)}`),
        redemptions: (status?: string) => call<OperatorRedemption[]>(`/v1/operator/redemptions${status ? `?status=${status}` : ""}`),
        settleRedemption: (id: string, bank_ref: string) => call<Redemption>(`/v1/operator/redemptions/${id}/settle`, json("POST", { bank_ref })),
        refundRedemption: (id: string) => call<Redemption>(`/v1/operator/redemptions/${id}/refund`, json("POST")),

        prices: () => call<Price[]>("/v1/operator/prices"),
        setPrice: (material: string, cop_per_kg: number) => call<Price>(`/v1/operator/prices/${material}`, json("PUT", { cop_per_kg })),

        operators: () => call<OperatorAccount[]>("/v1/operator/operators"),
        addOperator: (email: string, name: string, role: "admin" | "operator") => call<OperatorAccount>("/v1/operator/operators", json("POST", { email, name, role })),
        updateOperator: (id: string, patch: Partial<Pick<OperatorAccount, "name" | "role" | "active">>) => call<OperatorAccount>(`/v1/operator/operators/${id}`, json("PATCH", patch)),
    };
}

export type OperatorApi = ReturnType<typeof operatorApi>;

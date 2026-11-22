import type { PrivateKeyAccount } from "viem/accounts";
import { API_URL, CHAIN_ID, SIWE_DOMAIN } from "./config";

export interface Container {
  id: string;
  name: string;
  accepted_materials: string[];
  online: boolean;
  busy: boolean;
  qr: string | null;
}

export interface Item {
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
  deposited_g: number | null;
  score: number | null;
  reasons: string[];
  close_reason: string | null;
}

export interface Payout {
  session_id: string;
  amount_cop: number;
  status: string;
  tx_hash: string | null;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = body?.detail?.detail ?? body?.detail ?? res.statusText;
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body as T;
}

/** Sign-In with Ethereum, in the exact format the backend expects (zyrcle_api.auth.build_siwe). */
export async function signIn(account: PrivateKeyAccount): Promise<string> {
  const { nonce } = await call<{ nonce: string }>("/v1/auth/nonce", { method: "POST" });
  const message = [
    `${SIWE_DOMAIN} wants you to sign in with your Ethereum account:`,
    account.address,
    "",
    "Sign in to Zyrcle.",
    "",
    `URI: https://${SIWE_DOMAIN}`,
    "Version: 1",
    `Chain ID: ${CHAIN_ID}`,
    `Nonce: ${nonce}`,
    `Issued At: ${new Date().toISOString()}`,
  ].join("\n");
  const signature = await account.signMessage({ message });
  const { token } = await call<{ token: string }>("/v1/auth/verify", {
    method: "POST",
    body: JSON.stringify({ message, signature }),
  });
  return token;
}

export const api = {
  containers: () => call<Container[]>("/v1/demo/containers"),
  items: () => call<Item[]>("/v1/demo/items"),
  start: (token: string, qr: string, material: string) =>
    call<Session>("/v1/sessions", { method: "POST", body: JSON.stringify({ qr, material }) }, token),
  drop: (token: string, id: string, item: string) =>
    call(`/v1/demo/sessions/${id}/drop`, { method: "POST", body: JSON.stringify({ item }) }, token),
  finish: (token: string, id: string) =>
    call<Session>(`/v1/sessions/${id}/finish`, { method: "POST" }, token),
  me: (token: string) => call<{ payouts: Payout[] }>("/v1/me", {}, token),
};

export function liveUrl(sessionId: string, token: string): string {
  return `${API_URL.replace(/^http/, "ws")}/v1/sessions/${sessionId}/live?token=${token}`;
}

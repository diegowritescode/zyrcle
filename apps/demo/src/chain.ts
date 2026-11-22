import { createPublicClient, defineChain, formatEther, http, type Address } from "viem";
import { generatePrivateKey, privateKeyToAccount, type PrivateKeyAccount } from "viem/accounts";
import { CHAIN_ID, RPC_URL } from "./config";

export const zyrcleChain = defineChain({
  id: CHAIN_ID,
  name: "ZyrcleChain (Fuji)",
  nativeCurrency: { name: "Zyrcle", symbol: "ZYR", decimals: 18 },
  rpcUrls: { default: { http: [RPC_URL] } },
  testnet: true,
});

const client = createPublicClient({ chain: zyrcleChain, transport: http() });
const KEY = "zyrcle-demo:key";

/** The visitor's throwaway wallet. It lives only in this browser, like an embedded wallet would. */
export function loadAccount(): PrivateKeyAccount {
  let key: `0x${string}` | null = null;
  try {
    key = localStorage.getItem(KEY) as `0x${string}` | null;
  } catch {
    /* storage blocked: a fresh key per visit */
  }
  if (!key) {
    key = generatePrivateKey();
    try {
      localStorage.setItem(KEY, key);
    } catch {
      /* ignore */
    }
  }
  return privateKeyToAccount(key);
}

export function resetAccount(): PrivateKeyAccount {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  return loadAccount();
}

/** ZYR balance, shown as pesos: 1 ZYR = 1 COP. */
export async function balancePesos(address: Address): Promise<number> {
  return Number(formatEther(await client.getBalance({ address })));
}

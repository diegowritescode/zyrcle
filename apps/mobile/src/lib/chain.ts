/** ZyrcleChain: the project's own Avalanche L1, whose native coin ZYR pays residents. */
import { createPublicClient, defineChain, formatEther, http, type Address } from "viem";
import { generatePrivateKey, privateKeyToAccount, type PrivateKeyAccount } from "viem/accounts";
import { CHAIN_ID, RPC_URL } from "./config";
import { deleteSecret, getSecret, setSecret } from "./secure";

export const zyrcleChain = defineChain({
  id: CHAIN_ID,
  name: "ZyrcleChain (Fuji)",
  nativeCurrency: { name: "Zyrcle", symbol: "ZYR", decimals: 18 },
  rpcUrls: { default: { http: [RPC_URL] } },
  testnet: true,
});

const client = createPublicClient({ chain: zyrcleChain, transport: http() });

/** ZYR balance in pesos (1 ZYR = 1 COP). */
export async function balancePesos(address: Address): Promise<number> {
  return Number(formatEther(await client.getBalance({ address })));
}

const KEY = "zyrcle.wallet.key";

/**
 * The resident's wallet: a key generated on this phone and kept in its secure storage. The
 * resident never sees a seed phrase (docs/adr/0006); recovery needs its own design before launch.
 */
export async function loadWallet(): Promise<PrivateKeyAccount> {
  let key = (await getSecret(KEY)) as `0x${string}` | null;
  if (!key || !/^0x[0-9a-f]{64}$/i.test(key)) {
    key = generatePrivateKey();
    await setSecret(KEY, key);
  }
  return privateKeyToAccount(key);
}

/** Testnet only: throw this wallet away and start a new one. */
export async function resetWallet(): Promise<PrivateKeyAccount> {
  await deleteSecret(KEY);
  return loadWallet();
}

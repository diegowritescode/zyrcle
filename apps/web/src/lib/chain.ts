/** ZyrcleChain: the project's own Avalanche L1, whose native coin ZYR pays residents. */
import { createPublicClient, defineChain, formatEther, http, numberToHex, type Address, type EIP1193Provider } from "viem";
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

/** ZYR balance in pesos (1 ZYR = 1 COP). */
export async function balancePesos(address: Address): Promise<number> {
  return Number(formatEther(await client.getBalance({ address })));
}

const KEY = "zyrcle:embedded-key";

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null; // blocked (private mode, sandboxed frame): the key lives for this visit only
  }
}

/**
 * The visitor's embedded wallet: a key generated in this browser and kept only here, so a
 * resident can recycle without installing anything. Testnet only.
 */
export function loadEmbeddedAccount(): PrivateKeyAccount {
  const store = storage();
  let key = store?.getItem(KEY) as `0x${string}` | null;
  if (!key || !/^0x[0-9a-f]{64}$/i.test(key)) {
    key = generatePrivateKey();
    store?.setItem(KEY, key);
  }
  return privateKeyToAccount(key);
}

export function resetEmbeddedAccount(): PrivateKeyAccount {
  storage()?.removeItem(KEY);
  return loadEmbeddedAccount();
}

/** The browser wallet extension (MetaMask, Core), if any. */
export function injectedProvider(): EIP1193Provider | null {
  return (window as unknown as { ethereum?: EIP1193Provider }).ethereum ?? null;
}

/** Ask the browser wallet to add ZyrcleChain, so it shows the ZYR balance. */
export async function addChainToWallet(provider: EIP1193Provider): Promise<void> {
  await provider.request({
    method: "wallet_addEthereumChain",
    params: [
      {
        chainId: numberToHex(CHAIN_ID),
        chainName: zyrcleChain.name,
        nativeCurrency: zyrcleChain.nativeCurrency,
        rpcUrls: [RPC_URL],
      },
    ],
  });
}

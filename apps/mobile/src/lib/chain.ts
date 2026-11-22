/** ZyrcleChain: the project's own Avalanche L1, whose native coin ZYR pays residents. */
import {
  concat,
  createPublicClient,
  createWalletClient,
  defineChain,
  formatEther,
  getContractAddress,
  http,
  pad,
  type Address,
} from "viem";
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

/**
 * The account first owned by `owner` (AccountFactory.predict), computed here so the app does not
 * have to trust the API for it: an EIP-1167 clone of the factory's first CREATE, at a CREATE2
 * address salted with the owner.
 */
export function predictAccount(factory: Address, owner: Address): Address {
  const implementation = getContractAddress({ from: factory, nonce: 1n });
  const bytecode = concat([
    "0x3d602d80600a3d3981f3363d3d373d3d3d363d73",
    implementation,
    "0x5af43d82803e903d91602b57fd5bf3",
  ]);
  return getContractAddress({ opcode: "CREATE2", from: factory, salt: pad(owner, { size: 32 }), bytecode });
}

/**
 * Move whatever the phone key itself holds into the resident's account, minus the gas. Wallets
 * from before smart accounts were paid to the key; from now on the account is paid (ADR 0010).
 * Returns the wei moved (0 if there was nothing worth moving).
 */
export async function sweepToAccount(owner: PrivateKeyAccount, to: Address): Promise<bigint> {
  const balance = await client.getBalance({ address: owner.address });
  if (balance === 0n) return 0n;
  const { maxFeePerGas, maxPriorityFeePerGas } = await client.estimateFeesPerGas();
  const gas = 21_000n;
  const fee = gas * maxFeePerGas;
  if (balance <= fee) return 0n;
  const wallet = createWalletClient({ account: owner, chain: zyrcleChain, transport: http() });
  const hash = await wallet.sendTransaction({ to, value: balance - fee, gas, maxFeePerGas, maxPriorityFeePerGas });
  await client.waitForTransactionReceipt({ hash });
  return balance - fee;
}

const KEY = "zyrcle.wallet.key";

/**
 * The key that controls the resident's account: generated on this phone and kept in its secure
 * storage. The resident never sees a seed phrase (docs/adr/0006). If the phone is lost, the
 * account moves to a new phone's key after a recovery (docs/adr/0010).
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

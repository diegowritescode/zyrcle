import { createContext, useContext } from "react";
import type { Address } from "viem";

export interface Wallet {
  /** Null until the key is read from (or created in) secure storage. */
  address: Address | null;
  /** ZYR balance in pesos; null while loading or if the chain is unreachable. */
  balance: number | null;
  /** The API session token once signed in. */
  token: string | null;
  signingIn: boolean;
  /** A valid API session token, signing in with SIWE first if needed (silent: the key is local). */
  ensureToken: () => Promise<string>;
  refreshBalance: () => void;
  /** Testnet only: replace this phone's wallet with a new one. */
  reset: () => Promise<void>;
}

export const WalletContext = createContext<Wallet | null>(null);

export function useWallet(): Wallet {
  const wallet = useContext(WalletContext);
  if (!wallet) throw new Error("useWallet must be used inside <WalletProvider>");
  return wallet;
}

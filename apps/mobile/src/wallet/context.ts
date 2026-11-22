import { createContext, useContext } from "react";
import type { Address } from "viem";

export interface Wallet {
  /** The resident's account, where their ZYR lives. Null until signed in. */
  address: Address | null;
  /** This phone's key, which controls the account. Null until read from secure storage. */
  key: Address | null;
  /** ZYR balance in pesos; null while loading or if the chain is unreachable. */
  balance: number | null;
  /** The API session token once signed in. */
  token: string | null;
  signingIn: boolean;
  /** This key's account was moved to another phone (a recovery): it cannot sign in again. */
  retired: boolean;
  /** A valid API session token, signing in with SIWE first if needed (silent: the key is local). */
  ensureToken: () => Promise<string>;
  refreshBalance: () => void;
  /** Replace this phone's key with a new one: a new, empty account. */
  reset: () => Promise<void>;
}

export const WalletContext = createContext<Wallet | null>(null);

export function useWallet(): Wallet {
  const wallet = useContext(WalletContext);
  if (!wallet) throw new Error("useWallet must be used inside <WalletProvider>");
  return wallet;
}

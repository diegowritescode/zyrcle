import { createContext, useContext } from "react";
import type { Address } from "viem";

export type WalletKind = "embedded" | "injected";

export interface Wallet {
  kind: WalletKind;
  address: Address;
  /** Browser wallet extension available (MetaMask, Core). */
  hasInjected: boolean;
  /** ZYR balance in pesos; null while loading or if the chain is unreachable. */
  balance: number | null;
  /** A valid API session token, signing in (SIWE) first if needed. */
  ensureToken: () => Promise<string>;
  signingIn: boolean;
  /** The current API session token, if already signed in (cached for this tab). */
  token: string | null;
  connectInjected: () => Promise<void>;
  switchToEmbedded: () => void;
  newEmbedded: () => void;
  addChain: () => Promise<void>;
  refreshBalance: () => void;
}

export const WalletContext = createContext<Wallet | null>(null);

export function useWallet(): Wallet {
  const wallet = useContext(WalletContext);
  if (!wallet) throw new Error("useWallet must be used inside <WalletProvider>");
  return wallet;
}

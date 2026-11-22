import { useQuery, useQueryClient } from "@tanstack/react-query";
import { buildSiweMessage, isFresh } from "@zyrcle/client";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { PrivateKeyAccount } from "viem/accounts";
import { api } from "@/lib/api";
import { balancePesos, loadWallet, resetWallet } from "@/lib/chain";
import { CHAIN_ID, SIWE_DOMAIN } from "@/lib/config";
import { WalletContext, type Wallet } from "./context";

/**
 * The resident's embedded wallet. The key never leaves the phone; the API session comes from a
 * Sign-In with Ethereum signature over the exact message the web app signs (@zyrcle/client).
 */
export function WalletProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<PrivateKeyAccount | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [signingIn, setSigningIn] = useState(false);
  const pending = useRef<Promise<string> | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    loadWallet().then(setAccount);
  }, []);

  const address = account?.address ?? null;

  const ensureToken = useCallback(async (): Promise<string> => {
    if (!account) throw new Error("La wallet todavía no está lista.");
    if (token && isFresh(token)) return token;
    if (pending.current) return pending.current;
    pending.current = (async () => {
      setSigningIn(true);
      try {
        const { nonce } = await api.nonce();
        const message = buildSiweMessage({
          domain: SIWE_DOMAIN,
          address: account.address,
          chainId: CHAIN_ID,
          nonce,
          issuedAt: new Date(),
        });
        const { token: fresh } = await api.verify(message, await account.signMessage({ message }));
        setToken(fresh);
        return fresh;
      } finally {
        setSigningIn(false);
        pending.current = null;
      }
    })();
    return pending.current;
  }, [account, token]);

  // Sign in as soon as the key is ready: it is silent, and every screen needs the session.
  useEffect(() => {
    if (account) ensureToken().catch(() => undefined);
  }, [account, ensureToken]);

  const balance = useQuery({
    queryKey: ["balance", address],
    queryFn: () => balancePesos(address!),
    enabled: address !== null,
    refetchInterval: 15_000,
    retry: 1,
  });

  const refreshBalance = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["balance", address] });
  }, [queryClient, address]);

  const reset = useCallback(async () => {
    setToken(null);
    setAccount(await resetWallet());
    queryClient.clear();
  }, [queryClient]);

  const value = useMemo<Wallet>(
    () => ({
      address,
      balance: balance.data ?? null,
      token,
      signingIn,
      ensureToken,
      refreshBalance,
      reset,
    }),
    [address, balance.data, token, signingIn, ensureToken, refreshBalance, reset],
  );

  return <WalletContext.Provider value={value}>{children}</WalletContext.Provider>;
}

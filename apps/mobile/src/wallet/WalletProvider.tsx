import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, buildSiweMessage, isFresh } from "@zyrcle/client";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Address } from "viem";
import type { PrivateKeyAccount } from "viem/accounts";
import { api } from "@/lib/api";
import { balancePesos, loadWallet, predictAccount, resetWallet, sweepToAccount } from "@/lib/chain";
import { ACCOUNT_FACTORY, CHAIN_ID, SIWE_DOMAIN } from "@/lib/config";
import { WalletContext, type Wallet } from "./context";

/**
 * The resident's key and account. The key never leaves the phone; the API session comes from a
 * Sign-In with Ethereum signature over the exact message the web app signs (@zyrcle/client). The
 * API answers with the resident's account, where their ZYR lives (docs/adr/0010).
 */
export function WalletProvider({ children }: { children: ReactNode }) {
  const [key, setKey] = useState<PrivateKeyAccount | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [address, setAddress] = useState<Address | null>(null);
  const [signingIn, setSigningIn] = useState(false);
  const [retired, setRetired] = useState(false);
  const pending = useRef<Promise<string> | null>(null);
  const swept = useRef(false);
  const tokenRef = useRef<string | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  useEffect(() => {
    loadWallet().then(setKey);
  }, []);

  const balance = useQuery({
    queryKey: ["balance", address],
    queryFn: () => balancePesos(address!),
    enabled: address !== null,
    refetchInterval: 15_000,
    retry: 1,
  });

  const refreshBalance = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["balance"] });
  }, [queryClient]);

  /** Coins paid to the key before smart accounts move to the account, once it is verified here. */
  const sweep = useCallback(
    async (owner: PrivateKeyAccount, account: Address) => {
      if (swept.current || !ACCOUNT_FACTORY || account.toLowerCase() === owner.address.toLowerCase()) return;
      if (predictAccount(ACCOUNT_FACTORY as Address, owner.address).toLowerCase() !== account.toLowerCase()) return;
      swept.current = true;
      try {
        if ((await sweepToAccount(owner, account)) > 0n) refreshBalance();
      } catch {
        swept.current = false; // try again on the next sign-in
      }
    },
    [refreshBalance],
  );

  const ensureToken = useCallback(async (): Promise<string> => {
    if (!key) throw new Error("La wallet todavía no está lista.");
    if (token && isFresh(token)) return token;
    if (pending.current) return pending.current;
    pending.current = (async () => {
      setSigningIn(true);
      try {
        const { nonce } = await api.nonce();
        const message = buildSiweMessage({
          domain: SIWE_DOMAIN,
          address: key.address,
          chainId: CHAIN_ID,
          nonce,
          issuedAt: new Date(),
        });
        const session = await api.verify(message, await key.signMessage({ message }));
        setToken(session.token);
        setAddress(session.address as Address);
        sweep(key, session.address as Address);
        return session.token;
      } catch (e) {
        if (e instanceof ApiError && e.code === "key_retired") setRetired(true);
        throw e;
      } finally {
        setSigningIn(false);
        pending.current = null;
      }
    })();
    return pending.current;
  }, [key, token, sweep]);

  // Sign in as soon as the key is ready: it is silent, and every screen needs the session.
  useEffect(() => {
    if (key && !retired) ensureToken().catch(() => undefined);
  }, [key, retired, ensureToken]);

  // A session can end on the server: after a recovery the old phone's key no longer owns the
  // account, and the new phone's temporary resident is folded into it. Sign in again.
  useEffect(
    () =>
      queryClient.getQueryCache().subscribe((event) => {
        const error = event.type === "updated" && event.action.type === "error" ? event.action.error : null;
        // Only for the current session: a late answer to a query of the previous one is ignored.
        const current = tokenRef.current !== null && event.query.queryKey.includes(tokenRef.current);
        if (error instanceof ApiError && error.status === 401 && current) setToken(null);
      }),
    [queryClient],
  );

  const reset = useCallback(async () => {
    setToken(null);
    setAddress(null);
    setRetired(false);
    swept.current = false;
    setKey(await resetWallet());
    queryClient.clear();
  }, [queryClient]);

  const value = useMemo<Wallet>(
    () => ({
      address,
      key: key?.address ?? null,
      balance: balance.data ?? null,
      token,
      signingIn,
      retired,
      ensureToken,
      refreshBalance,
      reset,
    }),
    [address, key, balance.data, token, signingIn, retired, ensureToken, refreshBalance, reset],
  );

  return <WalletContext.Provider value={value}>{children}</WalletContext.Provider>;
}

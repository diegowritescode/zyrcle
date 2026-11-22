import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createWalletClient, custom, getAddress, type Address } from "viem";
import { toast } from "sonner";
import { accountOf, buildSiweMessage } from "@zyrcle/client";
import { api } from "@/lib/api";
import {
  addChainToWallet,
  balancePesos,
  injectedProvider,
  loadEmbeddedAccount,
  resetEmbeddedAccount,
} from "@/lib/chain";
import { CHAIN_ID, SIWE_DOMAIN } from "@/lib/config";
import { WalletContext, type Wallet, type WalletKind } from "./context";
import { cacheToken, cachedToken, forgetToken } from "./token";

const KIND_KEY = "zyrcle:wallet-kind";

function savedKind(): WalletKind {
  try {
    return localStorage.getItem(KIND_KEY) === "injected" ? "injected" : "embedded";
  } catch {
    return "embedded";
  }
}

function saveKind(kind: WalletKind) {
  try {
    localStorage.setItem(KIND_KEY, kind);
  } catch {
    /* ignore */
  }
}

/**
 * Who the visitor is. By default an embedded wallet created in this browser, so anyone can try the
 * flow without installing anything; optionally their own MetaMask or Core. Either way the API
 * session comes from a Sign-In with Ethereum signature, made only when a page needs it.
 */
export function WalletProvider({ children }: { children: ReactNode }) {
  const [embedded, setEmbedded] = useState(loadEmbeddedAccount);
  const [kind, setKind] = useState<WalletKind>("embedded");
  const [injectedAddress, setInjectedAddress] = useState<Address | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [signingIn, setSigningIn] = useState(false);
  const pending = useRef<{ address: string; promise: Promise<string> } | null>(null);
  const queryClient = useQueryClient();
  const provider = injectedProvider();

  const address: Address = kind === "injected" && injectedAddress ? injectedAddress : embedded.address;

  // Restore a previously connected browser wallet without a popup (eth_accounts never prompts).
  useEffect(() => {
    if (!provider || savedKind() !== "injected") return;
    createWalletClient({ transport: custom(provider) })
      .getAddresses()
      .then((accounts) => {
        if (accounts[0]) {
          setInjectedAddress(getAddress(accounts[0]));
          setKind("injected");
        }
      })
      .catch(() => undefined);
  }, [provider]);

  useEffect(() => {
    if (!provider) return;
    const onAccounts = (accounts: string[]) => {
      if (accounts[0]) {
        setInjectedAddress(getAddress(accounts[0]));
      } else {
        setInjectedAddress(null);
        setKind("embedded");
        saveKind("embedded");
      }
    };
    provider.on("accountsChanged", onAccounts);
    return () => provider.removeListener("accountsChanged", onAccounts);
  }, [provider]);

  useEffect(() => setToken(cachedToken(address)), [address]);

  const sign = useCallback(
    async (message: string): Promise<`0x${string}`> => {
      if (kind === "injected" && provider && injectedAddress) {
        const client = createWalletClient({ account: injectedAddress, transport: custom(provider) });
        return client.signMessage({ account: injectedAddress, message });
      }
      return embedded.signMessage({ message });
    },
    [kind, provider, injectedAddress, embedded],
  );

  const ensureToken = useCallback(async (): Promise<string> => {
    const cached = cachedToken(address);
    if (cached) return cached;
    if (pending.current?.address === address) return pending.current.promise;
    const promise = (async () => {
      setSigningIn(true);
      try {
        const { nonce } = await api.nonce();
        const message = buildSiweMessage({
          domain: SIWE_DOMAIN,
          address,
          chainId: CHAIN_ID,
          nonce,
          issuedAt: new Date(),
        });
        const { token: fresh } = await api.verify(message, await sign(message));
        cacheToken(address, fresh);
        setToken(fresh);
        return fresh;
      } finally {
        setSigningIn(false);
        pending.current = null;
      }
    })();
    pending.current = { address, promise };
    return promise;
  }, [address, sign]);

  // ZYR goes to the resident's account, which the session names (docs/adr/0010). Before signing in,
  // or on an API without smart accounts, that is the key's own address.
  const account = ((token && accountOf(token)) || address) as Address;

  const balance = useQuery({
    queryKey: ["balance", account],
    queryFn: () => balancePesos(account),
    refetchInterval: 15_000,
    retry: 1,
  });

  const connectInjected = useCallback(async () => {
    if (!provider) {
      toast.error("No encontramos MetaMask ni Core", {
        description: "Instala una de las dos extensiones o sigue con la wallet de la demo.",
      });
      return;
    }
    try {
      const accounts = await createWalletClient({ transport: custom(provider) }).requestAddresses();
      if (!accounts[0]) return;
      setInjectedAddress(getAddress(accounts[0]));
      setKind("injected");
      saveKind("injected");
      toast.success("Wallet conectada", { description: "Firmarás para entrar cuando recicles." });
    } catch {
      toast.error("No se conectó la wallet", { description: "La solicitud fue rechazada." });
    }
  }, [provider]);

  const switchToEmbedded = useCallback(() => {
    setKind("embedded");
    saveKind("embedded");
  }, []);

  const newEmbedded = useCallback(() => {
    forgetToken(embedded.address);
    setEmbedded(resetEmbeddedAccount());
    setKind("embedded");
    saveKind("embedded");
  }, [embedded]);

  const addChain = useCallback(async () => {
    if (!provider) return;
    try {
      await addChainToWallet(provider);
      toast.success("ZyrcleChain agregada a tu wallet");
    } catch {
      toast.error("La wallet no agregó la red");
    }
  }, [provider]);

  const refreshBalance = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["balance", account] });
  }, [queryClient, account]);

  const value = useMemo<Wallet>(
    () => ({
      kind: kind === "injected" && injectedAddress ? "injected" : "embedded",
      address,
      account,
      hasInjected: provider !== null,
      balance: balance.data ?? null,
      ensureToken,
      signingIn,
      token,
      connectInjected,
      switchToEmbedded,
      newEmbedded,
      addChain,
      refreshBalance,
    }),
    [kind, injectedAddress, address, account, provider, balance.data, ensureToken, signingIn, token, connectInjected, switchToEmbedded, newEmbedded, addChain, refreshBalance],
  );

  return <WalletContext.Provider value={value}>{children}</WalletContext.Provider>;
}

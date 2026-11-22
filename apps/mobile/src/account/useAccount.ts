import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useWallet } from "@/wallet/context";

/** Recovery email and any recovery this resident is part of (GET /v1/me/account). */
export function useAccount() {
  const { token } = useWallet();
  return useQuery({
    queryKey: ["account", token],
    queryFn: () => api.account(token!),
    enabled: token !== null,
    refetchInterval: 30_000,
  });
}

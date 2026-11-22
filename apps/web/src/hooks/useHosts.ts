import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/** Every host and its sites (docs/adr/0011). */
export function useHosts() {
  return useQuery({ queryKey: ["hosts"], queryFn: api.hosts, staleTime: 60_000 });
}

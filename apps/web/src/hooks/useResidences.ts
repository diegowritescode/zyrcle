import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useResidences() {
  return useQuery({ queryKey: ["residences"], queryFn: api.residences, staleTime: 60_000 });
}

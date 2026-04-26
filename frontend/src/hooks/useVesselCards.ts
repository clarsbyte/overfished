import { useQuery } from "@tanstack/react-query";

import type { Risk } from "@/lib/api";

export interface VesselCard {
  mmsi: string;
  name?: string;
  flag?: string;
  vessel_type?: string;
  risk?: Risk;
  is_high_risk?: boolean;
  duration_hours?: number;
  image_path?: string;
  image_source_url?: string;
  summary?: string | null;
}

export type VesselCardsMap = Record<string, VesselCard>;

async function fetchVesselCards(): Promise<VesselCardsMap> {
  const url = "/data/vessel_cards.json";
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} (${url})`);
  }
  const data = (await res.json()) as unknown;
  if (data && typeof data === "object" && !Array.isArray(data)) {
    return data as VesselCardsMap;
  }
  throw new Error(`Invalid vessel_cards.json (expected object)`);
}

export function useVesselCards() {
  return useQuery<VesselCardsMap>({
    queryKey: ["vessel-cards"],
    queryFn: fetchVesselCards,
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

export function useVesselCard(mmsi: string | null | undefined): VesselCard | undefined {
  const { data } = useVesselCards();
  if (!mmsi || !data) return undefined;
  return data[mmsi];
}

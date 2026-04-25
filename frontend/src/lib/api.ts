import type { FeatureCollection } from "geojson";
import type { Vessel } from "@/types/schemas";

/** Empty or unset `VITE_API_URL` → same-origin `/api` (Vite proxy in dev). */
function resolveDemoApiBase(): string {
  const raw = import.meta.env.VITE_API_URL;
  if (raw == null || String(raw).trim() === "") return "/api";
  return String(raw).replace(/\/$/, "");
}

const BASE = resolveDemoApiBase();

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} (${path})`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : "{}",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} (${path})`);
  return res.json() as Promise<T>;
}

export type Risk = "safe" | "suspect" | "high_risk" | "confirmed_iuu";

export interface GlobalVesselTrack {
  mmsi: string;
  name: string;
  flag: string;
  risk: Risk;
  points: [number, number][];
}

export interface HeatmapPoint {
  lat: number;
  lon: number;
  hours: number;
}

export interface NotifyPortResponse {
  port: { name: string; un_locode: string; lat: number; lon: number };
  call: { call_id: string; status: string; recording_url: string };
  predictions: { name: string; un_locode: string; lat: number; lon: number; weight: number }[];
}

export type DemoSpecies = "cod" | "salmon" | "trout";

export interface SpeciesExposureRegion {
  region_id: string;
  name: string;
  risk: Risk;
  species_note: string;
}

export interface SpeciesFishingExposureResponse {
  species: string;
  disclaimer: string;
  regions: SpeciesExposureRegion[];
  geojson: FeatureCollection;
}

export const api = {
  health: () => get<{ status: string; use_fixtures: boolean }>("/health"),

  vessels: (regionId = "galapagos") => get<Vessel[]>(`/vessels?region_id=${regionId}`),
  vessel: (mmsi: string) => get<Vessel>(`/vessel/${mmsi}`),
  vesselTrack: (mmsi: string, hours = 24) =>
    get<[number, number][]>(`/vessel/${mmsi}/track?hours=${hours}`),

  globalVesselTracks: () => get<GlobalVesselTrack[]>("/vessel-tracks/global"),

  heatmap: (regionId = "galapagos") => get<HeatmapPoint[]>(`/heatmap?region_id=${regionId}`),

  speciesFishingExposure: (species: DemoSpecies) =>
    get<SpeciesFishingExposureResponse>(`/species-fishing-exposure?species=${encodeURIComponent(species)}`),

  notifyPort: (caseId: string) => post<NotifyPortResponse>(`/case/${caseId}/notify-port`),
};

export type { Vessel };

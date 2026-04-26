import type { FeatureCollection } from "geojson";
import type {
  CaseFile,
  DocumentArtifact,
  FineCalculation,
  IUURule,
  LegalCitation,
  RegionContext,
  RiskAssessment,
  Vessel,
  VesselDetection,
  VesselEvent,
} from "@/types/schemas";

export type Risk = "safe" | "suspect" | "high_risk" | "confirmed_iuu";

export interface GlobalVesselTrack {
  mmsi: string;
  name: string;
  flag: string;
  risk: Risk;
  points: [number, number][];
}

/** Empty or unset `VITE_API_URL` → same-origin `/api` (Vite proxy in dev). */
export function getDemoApiBase(): string {
  const raw = import.meta.env.VITE_API_URL;
  if (raw == null || String(raw).trim() === "") return "/api";
  return String(raw).replace(/\/$/, "");
}

const BASE = getDemoApiBase();

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

export const api = {
  health: () => get<{ status: string; use_fixtures: boolean }>("/health"),

  // Region
  defineRegion: (polygon: GeoJSON.Polygon) => post<RegionContext>("/region", polygon),

  // Vessels
  vessels: (regionId = "galapagos") => get<Vessel[]>(`/vessels?region_id=${regionId}`),
  vessel: (mmsi: string) => get<Vessel>(`/vessel/${mmsi}`),
  vesselEvents: (mmsi: string) => get<VesselEvent[]>(`/vessel/${mmsi}/events`),
  vesselTrack: (mmsi: string, hours = 24) => get<[number, number][]>(`/vessel/${mmsi}/track?hours=${hours}`),
  vesselRisk: (mmsi: string, regionId = "galapagos") =>
    get<RiskAssessment>(`/vessel/${mmsi}/risk?region_id=${regionId}`),

  // Heatmap
  heatmap: (regionId = "galapagos") =>
    get<{ lat: number; lon: number; hours: number }[]>(`/heatmap?region_id=${regionId}`),

  speciesFishingExposure: (species: DemoSpecies) =>
    get<SpeciesFishingExposureResponse>(
      `/species-fishing-exposure?species=${encodeURIComponent(species)}`,
    ),

  // Worldwide hex-region risk overlay
  fisheryRegions: () =>
    get<
      {
        region_id: string;
        name: string;
        risk: "confirmed_iuu" | "high_risk" | "suspect" | "safe";
        geometry: GeoJSON.Polygon;
      }[]
    >("/fishery-regions"),

  // Worldwide ambient vessel tracks
  globalVesselTracks: () => get<GlobalVesselTrack[]>("/vessel-tracks/global"),

  // Regulations / citations
  regulations: (regionId = "galapagos") => get<IUURule[]>(`/regulations?region_id=${regionId}`),
  citations: (regionId = "galapagos") => get<LegalCitation[]>(`/citations?region_id=${regionId}`),

  // Case actions
  caseFine: (caseId: string) => get<FineCalculation>(`/case/${caseId}/fine`),
  renderDocumentFamily: (caseId: string) => post<DocumentArtifact[]>(`/case/${caseId}/documents`),
  hailVessel: (caseId: string) => post<{ audio_url: string; script: string }>(`/case/${caseId}/hail`),
  notifyPort: (caseId: string) => post<NotifyPortResponse>(`/case/${caseId}/notify-port`),
};

export type { CaseFile, Vessel, VesselDetection, VesselEvent, RegionContext, DocumentArtifact };

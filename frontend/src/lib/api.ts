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

const BASE = (import.meta.env.VITE_API_URL as string) ?? "/api";

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
  globalVesselTracks: () =>
    get<
      {
        mmsi: string;
        name: string;
        flag: string;
        risk: "confirmed_iuu" | "high_risk" | "suspect" | "safe";
        points: [number, number][];
      }[]
    >("/vessel-tracks/global"),

  // Regulations / citations
  regulations: (regionId = "galapagos") => get<IUURule[]>(`/regulations?region_id=${regionId}`),
  citations: (regionId = "galapagos") => get<LegalCitation[]>(`/citations?region_id=${regionId}`),

  // Case actions
  caseFine: (caseId: string) => get<FineCalculation>(`/case/${caseId}/fine`),
  renderDocumentFamily: (caseId: string) => post<DocumentArtifact[]>(`/case/${caseId}/documents`),
  hailVessel: (caseId: string) => post<{ audio_url: string; script: string }>(`/case/${caseId}/hail`),
  notifyPort: (caseId: string) =>
    post<{
      port: { name: string; un_locode: string; lat: number; lon: number };
      call: { call_id: string; status: string; recording_url: string };
      predictions: { name: string; un_locode: string; lat: number; lon: number; weight: number }[];
    }>(`/case/${caseId}/notify-port`),
};

export type { CaseFile, Vessel, VesselDetection, VesselEvent, RegionContext, DocumentArtifact };

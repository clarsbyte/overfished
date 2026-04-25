// AUTO-GENERATED — DO NOT EDIT.
// Regenerate via: python3 scripts/generate_ts_types.py
// Source: backend/tools/schemas.py

export interface DocumentArtifact {
  artifact_id: string;
  case_id: string;
  doc_type: "notice_of_violation" | "cease_and_desist_order" | "port_inspection_order" | "evidence_package" | "combined_legal_package";
  html_url: string;
  pdf_url: string;
  sha256: string;
  rendered_at: string;
  page_count: number;
}

export interface IUURule {
  rule_id: string;
  source_doc: string;
  jurisdiction: string;
  category: "no_take_zone" | "seasonal_closure" | "gear_restriction" | "license_required" | "ais_required" | "catch_limit" | "size_limit" | "species_protected";
  description: string;
  machine_check: Record<string, unknown>;
  penalty_text?: string | null;
}

export interface LatLon {
  lat: number;
  lon: number;
}

export interface LegalCitation {
  instrument: string;
  layer: "international" | "national" | "rfmo" | "voluntary";
  full_title: string;
  role: string;
  excerpt?: string | null;
  source_url?: string | null;
}

export interface PenaltyLineItem {
  description: string;
  legal_basis: LegalCitation[];
  amount_usd: number;
  is_multiplier?: boolean;
  multiplier_value?: number | null;
}

export interface RegionContext {
  region_id: string;
  name: string;
  polygon_geojson: Record<string, unknown>;
  eez_country?: string | null;
  mpa_wdpa_ids?: number[];
  rfmo_ids?: string[];
  centroid: LatLon;
  area_km2: number;
}

export interface Vessel {
  mmsi: string;
  imo?: string | null;
  name?: string | null;
  flag?: string | null;
  gear_type?: string | null;
  length_m?: number | null;
  owner?: string | null;
  authorizations?: string[];
  last_position?: LatLon | null;
  last_seen?: string | null;
}

export interface VesselDetection {
  detection_id: string;
  timestamp: string;
  position: LatLon;
  confidence: number;
  estimated_length_m?: number | null;
  matched_mmsi?: string | null;
  source: "sar" | "optical";
  image_url: string;
}

export interface VesselEvent {
  event_id: string;
  mmsi: string;
  type: "FISHING" | "GAP" | "ENCOUNTER" | "LOITERING" | "PORT_VISIT";
  start: string;
  end?: string | null;
  position: LatLon;
  duration_hours?: number | null;
  metadata?: Record<string, unknown>;
}

export interface FineCalculation {
  vessel_mmsi: string;
  region_id: string;
  estimated_catch_kg: number;
  primary_species?: string | null;
  line_items: PenaltyLineItem[];
  subtotal_usd: number;
  multipliers: Record<string, number>;
  total_fine_usd: number;
  citations: LegalCitation[];
  breakdown_text: string;
}

export interface RiskAssessment {
  vessel: Vessel;
  region_id: string;
  risk_score: number;
  classification: "safe" | "suspect" | "high_risk" | "confirmed_iuu";
  triggered_rules: string[];
  evidence: VesselEvent[];
  reasoning: string;
}

export interface CaseFile {
  case_id: string;
  region: RegionContext;
  vessel: Vessel;
  events: VesselEvent[];
  detections?: VesselDetection[];
  rules: IUURule[];
  citations: LegalCitation[];
  risk?: RiskAssessment | null;
  fine?: FineCalculation | null;
  documents?: DocumentArtifact[];
  cease_desist_audio_url?: string | null;
  notified_port?: string | null;
  call_recording_url?: string | null;
  timeline?: Record<string, unknown>[];
}

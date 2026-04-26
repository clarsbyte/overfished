import type { Risk } from "@/lib/api";
import type { ModelRisk } from "@/lib/agentApi";

export type ShipSource =
  | "backend-galapagos"
  | "backend-global"
  | "sar-detections"
  | "sar-enriched";

export interface Ship {
  mmsi: string;
  name?: string;
  flag?: string;
  lon: number;
  lat: number;
  source: ShipSource;
  risk?: Risk;
  vesselType?: string;
  confidence?: number;
  timestamp?: string;
  isHighRisk?: boolean;
  durationHours?: number;
  modelRisk?: ModelRisk;
  modelConfidence?: number;
  modelAliasMmsi?: string | null;
  modelMatchRate?: number;
  modelNarration?: string;
}

export const SOURCE_LABEL: Record<ShipSource, string> = {
  "backend-galapagos": "Galapagos fleet",
  "backend-global": "Global tracks",
  "sar-detections": "SAR detections",
  "sar-enriched": "SAR enriched",
};

export const SOURCE_COLOR: Record<ShipSource, string> = {
  "backend-galapagos": "#00d4ff",
  "backend-global": "#7a8398",
  "sar-detections": "#ffaa00",
  "sar-enriched": "#ff3b3b",
};

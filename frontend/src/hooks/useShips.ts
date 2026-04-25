import { useQueries } from "@tanstack/react-query";
import type { Feature, FeatureCollection, LineString } from "geojson";
import { useMemo } from "react";

import { api, type GlobalVesselTrack, type Risk } from "@/lib/api";
import { bool, fetchCSV, num } from "@/lib/csv";
import type { Ship, ShipSource } from "@/types/ship";

interface ShipsResult {
  ships: Ship[];
  tracks: FeatureCollection<LineString, { mmsi: string; risk: Risk }>;
  isLoading: boolean;
  isFetching: boolean;
  errors: string[];
  bySource: Record<ShipSource, number>;
}

const SOURCE_PRIORITY: Record<ShipSource, number> = {
  "sar-enriched": 4,
  "backend-galapagos": 3,
  "backend-global": 2,
  "sar-detections": 1,
};

const validLngLat = (lon: number, lat: number) =>
  Number.isFinite(lon) && Number.isFinite(lat) &&
  lon >= -180 && lon <= 180 &&
  lat >= -90 && lat <= 90;

export function useShips(): ShipsResult {
  const queries = useQueries({
    queries: [
      {
        queryKey: ["vessels", "galapagos"],
        queryFn: () => api.vessels("galapagos"),
        staleTime: 60_000,
      },
      {
        queryKey: ["vessel-tracks", "global"],
        queryFn: () => api.globalVesselTracks(),
        staleTime: 60_000,
      },
      {
        queryKey: ["csv", "sample_ship_detections"],
        queryFn: () => fetchCSV("/data/sample_ship_detections.csv"),
        staleTime: Infinity,
      },
      {
        queryKey: ["csv", "gold_vessel_detections_enriched"],
        queryFn: () => fetchCSV("/data/gold_vessel_detections_enriched.csv"),
        staleTime: Infinity,
      },
    ],
  });

  const [vesselsQ, globalTracksQ, sarRawQ, sarEnrichedQ] = queries;

  return useMemo<ShipsResult>(() => {
    const merged = new Map<string, Ship>();
    const tracksFeatures: Feature<LineString, { mmsi: string; risk: Risk }>[] = [];
    const errors: string[] = [];
    const bySource: Record<ShipSource, number> = {
      "backend-galapagos": 0,
      "backend-global": 0,
      "sar-detections": 0,
      "sar-enriched": 0,
    };

    const insert = (ship: Ship) => {
      if (!validLngLat(ship.lon, ship.lat)) return;
      bySource[ship.source]++;
      const existing = merged.get(ship.mmsi);
      if (!existing || SOURCE_PRIORITY[ship.source] > SOURCE_PRIORITY[existing.source]) {
        merged.set(ship.mmsi, ship);
      }
    };

    if (vesselsQ.data) {
      for (const v of vesselsQ.data) {
        const pos = v.last_position;
        if (!pos) continue;
        insert({
          mmsi: v.mmsi,
          name: v.name ?? undefined,
          flag: v.flag ?? undefined,
          lon: pos.lon,
          lat: pos.lat,
          source: "backend-galapagos",
          vesselType: v.gear_type ?? undefined,
          timestamp: v.last_seen ?? undefined,
        });
      }
    }
    if (vesselsQ.error) errors.push(`vessels: ${(vesselsQ.error as Error).message}`);

    if (globalTracksQ.data) {
      for (const t of globalTracksQ.data as GlobalVesselTrack[]) {
        if (!t.points || t.points.length === 0) continue;
        const last = t.points[t.points.length - 1];
        const [lat, lon] = last;
        insert({
          mmsi: t.mmsi,
          name: t.name,
          flag: t.flag,
          lon,
          lat,
          source: "backend-global",
          risk: t.risk,
        });
        const lineCoords = t.points
          .map(([la, lo]) => [lo, la] as [number, number])
          .filter(([lo, la]) => validLngLat(lo, la));
        if (lineCoords.length >= 2) {
          tracksFeatures.push({
            type: "Feature",
            geometry: { type: "LineString", coordinates: lineCoords },
            properties: { mmsi: t.mmsi, risk: t.risk },
          });
        }
      }
    }
    if (globalTracksQ.error) errors.push(`global-tracks: ${(globalTracksQ.error as Error).message}`);

    if (sarRawQ.data) {
      for (const r of sarRawQ.data) {
        const lon = num(r.lon);
        const lat = num(r.lat);
        if (lon === undefined || lat === undefined) continue;
        insert({
          mmsi: r.vessel_mmsi || r.mmsi || "",
          lon,
          lat,
          source: "sar-detections",
          confidence: num(r.detection_confidence),
          timestamp: r.image_timestamp,
        });
      }
    }
    if (sarRawQ.error) errors.push(`sar-detections: ${(sarRawQ.error as Error).message}`);

    if (sarEnrichedQ.data) {
      for (const r of sarEnrichedQ.data) {
        const lon = num(r.detection_lon);
        const lat = num(r.detection_lat);
        if (lon === undefined || lat === undefined) continue;
        const high = bool(r.is_high_risk);
        insert({
          mmsi: r.mmsi || "",
          name: r.vessel_name || undefined,
          flag: r.vessel_flag || undefined,
          lon,
          lat,
          source: "sar-enriched",
          vesselType: r.vessel_type || undefined,
          confidence: num(r.detection_confidence),
          timestamp: r.image_timestamp,
          isHighRisk: high,
          durationHours: num(r.event_duration_hours),
          risk: high ? "high_risk" : "suspect",
        });
      }
    }
    if (sarEnrichedQ.error) errors.push(`sar-enriched: ${(sarEnrichedQ.error as Error).message}`);

    const ships = [...merged.values()].filter((s) => s.mmsi);

    return {
      ships,
      tracks: { type: "FeatureCollection", features: tracksFeatures },
      isLoading: queries.some((q) => q.isLoading),
      isFetching: queries.some((q) => q.isFetching),
      errors,
      bySource,
    };
  }, [vesselsQ.data, vesselsQ.error, globalTracksQ.data, globalTracksQ.error, sarRawQ.data, sarRawQ.error, sarEnrichedQ.data, sarEnrichedQ.error, queries]);
}

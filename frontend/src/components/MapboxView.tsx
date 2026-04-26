import type { FeatureCollection, GeoJsonProperties, Geometry, LineString } from "geojson";
import { forwardRef, useImperativeHandle, useRef } from "react";
import Map, {
  Layer,
  Marker,
  NavigationControl,
  Source,
  type MapRef,
} from "react-map-gl/mapbox";

import type { Risk } from "@/lib/api";
import { SOURCE_COLOR, type Ship } from "@/types/ship";

import "mapbox-gl/dist/mapbox-gl.css";

const TOKEN = (import.meta.env as Record<string, string | undefined>).MAP_BOX_TOKEN ?? "";

const RISK_COLOR: Record<Risk, string> = {
  safe: "#00d4ff",
  suspect: "#ffaa00",
  high_risk: "#ff3b3b",
  confirmed_iuu: "#ff3b3b",
};

export interface MapboxHandle {
  flyTo: (lon: number, lat: number, zoom?: number) => void;
}

interface Props {
  ships: Ship[];
  tracks: FeatureCollection<LineString, { mmsi: string; risk: Risk }>;
  selected: Ship | null;
  onSelect: (ship: Ship | null) => void;
  speciesOverlay?: FeatureCollection<Geometry, GeoJsonProperties> | null;
}

export const MapboxView = forwardRef<MapboxHandle, Props>(function MapboxView(
  { ships, tracks, selected, onSelect, speciesOverlay },
  ref,
) {
  const mapRef = useRef<MapRef | null>(null);

  useImperativeHandle(ref, () => ({
    flyTo: (lon, lat, zoom = 6) => {
      mapRef.current?.flyTo({ center: [lon, lat], zoom, duration: 1200 });
    },
  }));

  if (!TOKEN) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-ink-950 px-6 text-center">
        <p className="max-w-md text-sm text-slate2-300">
          Mapbox needs a token. Set <code className="text-accent-safe">MAP_BOX_TOKEN</code> in the
          repo root <code className="text-slate2-400">.env</code> (Vite{" "}
          <code className="text-slate2-400">envDir</code> is the repo root) or in{" "}
          <code className="text-slate2-400">frontend/.env</code>, then restart{" "}
          <code className="text-slate2-400">npm run dev</code>.
        </p>
      </div>
    );
  }

  const hasSpeciesFeatures =
    speciesOverlay &&
    Array.isArray(speciesOverlay.features) &&
    speciesOverlay.features.length > 0;

  return (
    <Map
      ref={mapRef}
      mapboxAccessToken={TOKEN}
      mapStyle="mapbox://styles/mapbox/dark-v11"
      initialViewState={{ longitude: -90, latitude: 0, zoom: 1.8 }}
      projection={{ name: "globe" }}
      style={{ width: "100%", height: "100%" }}
      reuseMaps
    >
      <NavigationControl position="top-right" visualizePitch={false} />

      <Source id="tracks" type="geojson" data={tracks}>
        <Layer
          id="tracks-line"
          type="line"
          paint={{
            "line-color": [
              "match",
              ["get", "risk"],
              "confirmed_iuu",
              RISK_COLOR.confirmed_iuu,
              "high_risk",
              RISK_COLOR.high_risk,
              "suspect",
              RISK_COLOR.suspect,
              "safe",
              RISK_COLOR.safe,
              "#7a8398",
            ],
            "line-width": 1,
            "line-opacity": 0.45,
          }}
        />
      </Source>

      {hasSpeciesFeatures && (
        <Source id="species-exposure" type="geojson" data={speciesOverlay}>
          <Layer
            id="species-fill"
            type="fill"
            paint={{
              "fill-color": "#00d4ff",
              "fill-opacity": 0.12,
            }}
          />
          <Layer
            id="species-outline"
            type="line"
            paint={{
              "line-color": "#00d4ff",
              "line-width": 1,
              "line-opacity": 0.55,
            }}
          />
        </Source>
      )}

      {ships.map((s) => {
        const modelColor =
          s.modelRisk === "spoof_suspect"
            ? "#ff3b3b"
            : s.modelRisk === "uncertain"
              ? "#ffaa00"
              : null;
        const color = modelColor ?? (s.risk ? RISK_COLOR[s.risk] : SOURCE_COLOR[s.source]);
        const isSelected = selected?.mmsi === s.mmsi;
        const haloRing =
          s.modelRisk === "spoof_suspect"
            ? "model-halo-spoof"
            : s.modelRisk === "uncertain"
              ? "model-halo-uncertain"
              : "";
        const tooltip = s.modelNarration ?? s.name ?? s.mmsi;
        return (
          <Marker
            key={`${s.source}:${s.mmsi}`}
            longitude={s.lon}
            latitude={s.lat}
            anchor="center"
            onClick={(e) => {
              e.originalEvent.stopPropagation();
              onSelect(s);
            }}
          >
            <div className={`relative ${haloRing}`} title={tooltip} style={{ cursor: "pointer" }}>
              {s.modelRisk === "spoof_suspect" && (
                <span
                  aria-hidden
                  className="absolute inset-0 -m-2 rounded-full border-2 border-dashed animate-pulse"
                  style={{ borderColor: modelColor!, opacity: 0.7 }}
                />
              )}
              {s.modelRisk === "uncertain" && (
                <span
                  aria-hidden
                  className="absolute inset-0 -m-1.5 rounded-full border"
                  style={{ borderColor: modelColor!, opacity: 0.55 }}
                />
              )}
              <div
                className={`rounded-full ring-1 transition-transform ${
                  isSelected ? "scale-150 ring-white" : "ring-white/40 hover:scale-125"
                }`}
                style={{
                  width: isSelected ? 12 : 8,
                  height: isSelected ? 12 : 8,
                  background: color,
                  boxShadow: `0 0 8px ${color}`,
                }}
              />
            </div>
          </Marker>
        );
      })}
    </Map>
  );
});

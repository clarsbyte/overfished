import type { FeatureCollection, GeoJsonProperties, Geometry, LineString } from "geojson";
import { forwardRef, useImperativeHandle, useRef } from "react";

import { GlobeView, type GlobeHandle } from "@/components/GlobeView";
import { MapboxView, type MapboxHandle } from "@/components/MapboxView";
import type { Risk } from "@/lib/api";
import type { Ship } from "@/types/ship";

export interface MapHandle {
  flyTo: (lon: number, lat: number, zoom?: number) => void;
}

export type MapRenderer = "globe" | "mapbox";

interface Props {
  renderer: MapRenderer;
  ships: Ship[];
  tracks: FeatureCollection<LineString, { mmsi: string; risk: Risk }>;
  selected: Ship | null;
  onSelect: (ship: Ship | null) => void;
  speciesOverlay?: FeatureCollection<Geometry, GeoJsonProperties> | null;
  showPlastic?: boolean;
}

export const MapView = forwardRef<MapHandle, Props>(function MapView(
  { renderer, ships, tracks, selected, onSelect, speciesOverlay, showPlastic },
  ref,
) {
  const mapboxRef = useRef<MapboxHandle | null>(null);
  const globeRef = useRef<GlobeHandle | null>(null);

  useImperativeHandle(ref, () => ({
    flyTo: (lon, lat, zoom) => {
      if (renderer === "globe") {
        globeRef.current?.flyTo(lon, lat, zoom);
      } else {
        mapboxRef.current?.flyTo(lon, lat, zoom);
      }
    },
  }));

  if (renderer === "globe") {
    return (
      <GlobeView ref={globeRef} ships={ships} selected={selected} onSelect={onSelect} />
    );
  }

  return (
    <MapboxView
      ref={mapboxRef}
      ships={ships}
      tracks={tracks}
      selected={selected}
      onSelect={onSelect}
      speciesOverlay={speciesOverlay}
      showPlastic={showPlastic}
    />
  );
});

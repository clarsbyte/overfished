import type { FeatureCollection, GeoJsonProperties, Geometry, LineString } from "geojson";
import { forwardRef, useImperativeHandle, useRef } from "react";
import type { GlobeMethods } from "react-globe.gl";

import { MapboxView, type MapboxHandle } from "@/components/MapboxView";
import {
  type FisheryRegion,
  OverfishGlobe,
  type PortCall,
} from "@/components/OverfishGlobe";
import { useDrawController } from "@/components/useDrawController";
import type { Risk } from "@/lib/api";
import type { Vessel } from "@/types/schemas";
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
  cameraLocked?: boolean;
  onRegionSelected?: (region: FisheryRegion) => void;
  portCalls?: PortCall[];
}

function vesselToShip(v: Vessel): Ship {
  return {
    mmsi: v.mmsi,
    name: v.name ?? undefined,
    flag: v.flag ?? undefined,
    lat: v.last_position?.lat ?? 0,
    lon: v.last_position?.lon ?? 0,
    source: "backend-global",
  };
}

export const MapView = forwardRef<MapHandle, Props>(function MapView(
  {
    renderer,
    ships,
    tracks,
    selected,
    onSelect,
    speciesOverlay,
    cameraLocked,
    onRegionSelected,
    portCalls,
  },
  ref,
) {
  const mapboxRef = useRef<MapboxHandle | null>(null);
  const drawGlobeRef = useRef<GlobeMethods | undefined>(undefined);
  const draw = useDrawController({ globeRef: drawGlobeRef, onCommit: () => {} });

  useImperativeHandle(ref, () => ({
    flyTo: (lon, lat, zoom) => {
      if (renderer === "mapbox") {
        mapboxRef.current?.flyTo(lon, lat, zoom);
      }
      // Globe branch: programmatic flyTo not exposed on OverfishGlobe; the
      // region-click cinematic owns camera moves on the globe path.
    },
  }));

  if (renderer === "globe") {
    return (
      <OverfishGlobe
        draw={draw}
        portCalls={portCalls}
        cameraLocked={cameraLocked}
        onRegionSelected={onRegionSelected}
        onVesselSelected={(v) => onSelect(vesselToShip(v))}
      />
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
    />
  );
});

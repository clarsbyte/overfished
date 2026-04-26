import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react";

import type { Risk } from "@/lib/api";
import { SOURCE_COLOR, type Ship } from "@/types/ship";

interface GlobePoint {
  mmsi: string;
  name?: string;
  lat: number;
  lng: number;
  color: string;
  selected: boolean;
  ship: Ship;
}

interface GlobeInstance {
  globeImageUrl: (url: string) => GlobeInstance;
  backgroundImageUrl: (url: string) => GlobeInstance;
  backgroundColor: (value: string) => GlobeInstance;
  atmosphereColor: (value: string) => GlobeInstance;
  atmosphereAltitude: (value: number) => GlobeInstance;
  pointsData: (value: GlobePoint[]) => GlobeInstance;
  pointLat: (value: keyof GlobePoint) => GlobeInstance;
  pointLng: (value: keyof GlobePoint) => GlobeInstance;
  pointColor: (value: ((point: GlobePoint) => string) | keyof GlobePoint) => GlobeInstance;
  pointAltitude: (value: ((point: GlobePoint) => number) | number) => GlobeInstance;
  pointRadius: (value: ((point: GlobePoint) => number) | number) => GlobeInstance;
  pointResolution: (value: number) => GlobeInstance;
  pointsMerge: (value: boolean) => GlobeInstance;
  pointsTransitionDuration: (value: number) => GlobeInstance;
  pointLabel: (value: ((point: GlobePoint) => string) | keyof GlobePoint) => GlobeInstance;
  onPointClick: (callback: (point: GlobePoint) => void) => GlobeInstance;
  pointOfView: (view: { lat: number; lng: number; altitude?: number }, durationMs?: number) => GlobeInstance;
  controls: () => { autoRotate: boolean; autoRotateSpeed: number };
  width: (value: number) => GlobeInstance;
  height: (value: number) => GlobeInstance;
  _destructor?: () => void;
}

const RISK_COLOR: Record<Risk, string> = {
  safe: "#00d4ff",
  suspect: "#ffaa00",
  high_risk: "#ff3b3b",
  confirmed_iuu: "#ff3b3b",
};
const DEFAULT_VIEW = { lat: 0, lng: 0, altitude: 2.0 };
const FOCUS_VIEW_ALTITUDE = 1.4;

export interface GlobeHandle {
  flyTo: (lon: number, lat: number, zoom?: number) => void;
}

interface Props {
  ships: Ship[];
  selected: Ship | null;
  onSelect: (ship: Ship | null) => void;
}

export const GlobeView = forwardRef<GlobeHandle, Props>(function GlobeView(
  { ships, selected, onSelect },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const globeRef = useRef<GlobeInstance | null>(null);
  const onSelectRef = useRef(onSelect);
  const viewRef = useRef(DEFAULT_VIEW);

  onSelectRef.current = onSelect;

  const points = useMemo<GlobePoint[]>(() => {
    return ships.map((ship) => ({
      mmsi: ship.mmsi,
      name: ship.name,
      lat: ship.lat,
      lng: ship.lon,
      color: ship.risk ? RISK_COLOR[ship.risk] : SOURCE_COLOR[ship.source],
      selected: selected?.mmsi === ship.mmsi,
      ship,
    }));
  }, [ships, selected]);

  useImperativeHandle(ref, () => ({
    flyTo: (lon, lat) => {
      const nextView = { lat, lng: lon, altitude: FOCUS_VIEW_ALTITUDE };
      viewRef.current = nextView;
      globeRef.current?.pointOfView(nextView, 1200);
    },
  }));

  useEffect(() => {
    let isMounted = true;
    async function initGlobe() {
      if (!containerRef.current || globeRef.current) return;
      const mod = await import("globe.gl");
      if (!isMounted || !containerRef.current) return;
      const globe = new mod.default(containerRef.current) as unknown as GlobeInstance;
      globe
        .globeImageUrl("//unpkg.com/three-globe/example/img/earth-blue-marble.jpg")
        .backgroundImageUrl("//unpkg.com/three-globe/example/img/night-sky.png")
        .atmosphereColor("#00b3ff")
        .atmosphereAltitude(0.22)
        .pointLat("lat")
        .pointLng("lng")
        .pointColor((point: GlobePoint) => point.color)
        .pointAltitude(0)
        .pointRadius((point: GlobePoint) => (point.selected ? 0.8 : 0.45))
        .pointResolution(32)
        .pointsMerge(false)
        .pointsTransitionDuration(250)
        .pointLabel((point: GlobePoint) => `${point.name ?? point.mmsi} (${point.mmsi})`)
        .onPointClick((point: GlobePoint) => onSelectRef.current(point.ship))
        .width(window.innerWidth)
        .height(window.innerHeight)
        .pointOfView(DEFAULT_VIEW, 0);

      const controls = globe.controls();
      controls.autoRotate = true;
      controls.autoRotateSpeed = 0.16;

      globeRef.current = globe;
    }

    void initGlobe();

    return () => {
      isMounted = false;
      globeRef.current?._destructor?.();
      globeRef.current = null;
    };
  }, []);

  useEffect(() => {
    globeRef.current?.pointsData(points);
  }, [points]);

  useEffect(() => {
    const handleResize = () => {
      if (!globeRef.current) return;
      globeRef.current.width(window.innerWidth);
      globeRef.current.height(window.innerHeight);
      globeRef.current.pointOfView(viewRef.current, 0);
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return <div ref={containerRef} className="globe-canvas fixed inset-0 -z-10" />;
});

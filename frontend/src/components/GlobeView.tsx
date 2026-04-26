import { useQuery } from "@tanstack/react-query";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react";
import * as THREE from "three";

import type { Risk } from "@/lib/api";
import { isLand, whenLandMaskReady } from "@/lib/landMask";
import { SOURCE_COLOR, type Ship } from "@/types/ship";

interface SharkPoint { lat: number; lng: number; weight: number; }

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
  onGlobeClick: (callback: (coords: { lat: number; lng: number }) => void) => GlobeInstance;
  pointOfView: (view: { lat: number; lng: number; altitude?: number }, durationMs?: number) => GlobeInstance;
  controls: () => { autoRotate: boolean; autoRotateSpeed: number };
  scene: () => THREE.Scene;
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
  onGlobeClick?: (lat: number, lng: number) => void;
  pinCoord?: { lat: number; lng: number } | null;
  isPicking?: boolean;
  showSharkHeatmap?: boolean;
}

export const GlobeView = forwardRef<GlobeHandle, Props>(function GlobeView(
  { ships, selected, onSelect, onGlobeClick, pinCoord, isPicking, showSharkHeatmap },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const globeRef = useRef<GlobeInstance | null>(null);
  const onSelectRef = useRef(onSelect);
  const onGlobeClickRef = useRef(onGlobeClick);
  const viewRef = useRef(DEFAULT_VIEW);

  onSelectRef.current = onSelect;
  onGlobeClickRef.current = onGlobeClick;

  const points = useMemo<GlobePoint[]>(() => {
    const pts: GlobePoint[] = ships.map((ship) => ({
      mmsi: ship.mmsi,
      name: ship.name,
      lat: ship.lat,
      lng: ship.lon,
      color: ship.risk ? RISK_COLOR[ship.risk] : SOURCE_COLOR[ship.source],
      selected: selected?.mmsi === ship.mmsi,
      ship,
    }));
    if (pinCoord) {
      pts.push({
        mmsi: "__agent_pin__",
        name: `Agent pin (${pinCoord.lat.toFixed(3)}, ${pinCoord.lng.toFixed(3)})`,
        lat: pinCoord.lat,
        lng: pinCoord.lng,
        color: "#22c55e",
        selected: false,
        ship: null as unknown as Ship,
      });
    }
    return pts;
  }, [ships, selected, pinCoord]);

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
        .pointRadius((point: GlobePoint) =>
          point.mmsi === "__agent_pin__" ? 0.7 : point.selected ? 0.5 : 0.35,
        )
        .pointResolution(3)
        .pointsMerge(false)
        .pointsTransitionDuration(250)
        .pointLabel((point: GlobePoint) => `${point.name ?? point.mmsi} (${point.mmsi})`)
        .onPointClick((point: GlobePoint) => {
          if (point.mmsi !== "__agent_pin__") onSelectRef.current(point.ship);
        })
        .onGlobeClick(({ lat, lng }) => onGlobeClickRef.current?.(lat, lng))
        .width(window.innerWidth)
        .height(window.innerHeight)
        .pointOfView(DEFAULT_VIEW, 0);

      const controls = globe.controls();
      controls.autoRotate = false;

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

  // ── Shark heatmap overlay ─────────────────────────────────────────────
  const sharkQ = useQuery({
    queryKey: ["sharkHeatmap"],
    queryFn: async () => {
      const res = await fetch("/shark-heatmap.json");
      if (!res.ok) throw new Error("Failed to load shark data");
      return res.json() as Promise<SharkPoint[]>;
    },
    enabled: !!showSharkHeatmap,
  });

  useEffect(() => {
    if (!globeRef.current) return;
    const scene = globeRef.current.scene();

    const removeExisting = () => {
      const old = scene.getObjectByName("shark-heatmap-overlay");
      if (old) {
        scene.remove(old);
        (old as THREE.Mesh).geometry.dispose();
        ((old as THREE.Mesh).material as THREE.MeshBasicMaterial).map?.dispose();
        ((old as THREE.Mesh).material as THREE.MeshBasicMaterial).dispose();
      }
    };

    removeExisting();

    if (!showSharkHeatmap || !sharkQ.data?.length) return;

    let cancelled = false;

    void whenLandMaskReady().then(() => {
      if (cancelled) return;

      // Skip near-zero points (~half the dataset) — they add noise but no signal.
      const oceanPts = sharkQ.data!.filter((p) => p.weight > 0.05 && !isLand(p.lat, p.lng));

      const W = 4096;
      const H = 2048;
      const canvas = document.createElement("canvas");
      canvas.width = W;
      canvas.height = H;
      const ctx = canvas.getContext("2d")!;
      ctx.globalCompositeOperation = "lighter";

      // Gaussian falloff stops (e^(-(t·2)²/2) normalised so center=1).
      const GAUSS_STOPS: [number, number][] = [
        [0.00, 1.000],
        [0.15, 0.895],
        [0.30, 0.638],
        [0.45, 0.367],
        [0.60, 0.165],
        [0.75, 0.058],
        [0.90, 0.016],
        [1.00, 0.000],
      ];

      for (const pt of oceanPts) {
        const px = ((pt.lng + 180) / 360) * W;
        const py = ((90 - pt.lat) / 180) * H;
        // Moderate radius; weight scales it slightly so hot zones spread.
        const r = 35 + pt.weight * 35;
        // Peak alpha is dominated by weight so weak points don't pile up.
        const peak = 0.10 + pt.weight * 0.32;
        const grad = ctx.createRadialGradient(px, py, 0, px, py, r);
        for (const [t, k] of GAUSS_STOPS) {
          grad.addColorStop(t, `rgba(110, 245, 150, ${(peak * k).toFixed(3)})`);
        }
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fill();
      }

      const texture = new THREE.CanvasTexture(canvas);
      texture.minFilter = THREE.LinearFilter;
      texture.magFilter = THREE.LinearFilter;
      texture.generateMipmaps = false;
      texture.anisotropy = 8;
      texture.needsUpdate = true;

      const GLOBE_R = 100;
      const geom = new THREE.SphereGeometry(GLOBE_R * 1.003, 128, 64);
      const mat = new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        depthTest: true,
        side: THREE.FrontSide,
        polygonOffset: true,
        polygonOffsetFactor: -1,
        polygonOffsetUnits: -1,
      });

      const mesh = new THREE.Mesh(geom, mat);
      mesh.name = "shark-heatmap-overlay";
      mesh.renderOrder = 1;
      scene.add(mesh);
    });

    return () => {
      cancelled = true;
      removeExisting();
    };
  }, [showSharkHeatmap, sharkQ.data]);

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

  return (
    <div
      ref={containerRef}
      className="globe-canvas fixed inset-0 -z-10"
      style={isPicking ? { cursor: "crosshair" } : undefined}
    />
  );
});

/**
 * The 3D globe — react-globe.gl mount with the full layer stack.
 *
 * Layers:
 *   Globe          — Blue Marble (NASA daytime) base + cyan atmosphere. Visible
 *                    landmasses, lighter ocean (vs the previous earth-night
 *                    image which was too dark to see continents).
 *   Heatmap        — global fishing-effort thermal density (replaces the hex
 *                    polygon overlay; risk regions are still visible as
 *                    density hotspots, just smoother).
 *   Polygons       — Galápagos MPA boundary, user-drawn region, and
 *                    INVISIBLE click-target polygons over each named fishery
 *                    region (kept so click-to-select still works without
 *                    showing colored hex tiles).
 *   3D Objects     — animated vessel ship-meshes interpolating along tracks.
 *   Rings          — pulsing red on confirmed-IUU vessels.
 *   Paths          — demo vessel trajectory + in-progress drawing polyline.
 *   Arcs           — port-call beat (when /notify-port fires).
 *   Labels         — region names (color-coded by risk) + port names.
 *
 * Interaction model:
 *   - Click a region label/area to select it. Camera flies in, auto-rotate
 *     stops so the user can inspect vessel detail in that region.
 *   - Click DEFINE REGION button → drawing mode → click globe to place vertices.
 *   - In drawing mode, every other layer's clicks are suppressed.
 */

import { api } from "@/lib/api";
import { isLand, whenLandMaskReady } from "@/lib/landMask";
import { generateRoutes } from "@/lib/proceduralRoutes";
import type { Vessel } from "@/types/schemas";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Globe, { type GlobeMethods } from "react-globe.gl";
import * as THREE from "three";
import {
  useFlightPathLayer,
  type Route as FlightRoute,
} from "@/flightPath/useFlightPathLayer";
import { useGlobeControls } from "./GlobeControls";
import {
  type AnimatedVessel,
  type FleetVessel,
  useAnimatedFleet,
} from "./useAnimatedFleet";
import { useDrawController } from "./useDrawController";
import { makeLightweightVesselMesh } from "./vesselMesh";
import { useGlobeControlsContext } from "./GlobeControlsContext";

export interface PortCall {
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
}

/** Internal arc kinds — only the demo trajectory + port-call beat use
 * react-globe.gl's Arcs layer now. The dense ambient flight-path traffic
 * lives in a separate Three.js InstancedMesh layer (see ./flightPath/).
 */
type AnyArc =
  | {
    kind: "demo_track";
    startLat: number;
    startLng: number;
    endLat: number;
    endLng: number;
  }
  | {
    kind: "port_call";
    startLat: number;
    startLng: number;
    endLat: number;
    endLng: number;
  };

export interface FisheryRegion {
  region_id: string;
  name: string;
  risk: "confirmed_iuu" | "high_risk" | "suspect" | "safe";
  geometry: GeoJSON.Polygon;
}

export interface LayerOverrides {
  showVessels?: boolean;
  showHeatmap?: boolean;
  showPaths?: boolean;
  flightCount?: number;
  showSharkHeatmap?: boolean;
}

interface SharkPoint {
  lat: number;
  lng: number;
  weight: number;
}

interface Props {
  draw: ReturnType<typeof useDrawController>;
  onVesselSelected: (vessel: Vessel) => void;
  onRegionSelected?: (region: FisheryRegion) => void;
  portCalls?: PortCall[];
  /** When provided, these override the leva debug-panel values. */
  layerOverrides?: LayerOverrides;
  /** When true, disable user pan/zoom/rotate and stop auto-rotate. */
  cameraLocked?: boolean;
}

// Blue Marble (NASA): bright daytime imagery, visible continents and oceans.
// Same source as globe.gl's day-night-cycle and clouds examples.
const GLOBE_IMG = "//unpkg.com/three-globe/example/img/earth-blue-marble.jpg";
const BUMP_IMG = "//unpkg.com/three-globe/example/img/earth-topology.png";
const BG_IMG = "//unpkg.com/three-globe/example/img/night-sky.png";

const DEMO_MMSI = "412345678";

// Saturated, high-contrast colors to pop against Blue Marble's warm-blue ocean.
const RISK_COLOR: Record<"confirmed_iuu" | "high_risk" | "suspect" | "safe", string> = {
  confirmed_iuu: "#ff1f4d", // hot red
  high_risk: "#ff8a00", // pure orange (was "#ff7849", too brown against blue water)
  suspect: "#ffd400", // bright amber-yellow
  safe: "#00ffe0", // electric cyan
};

export function OverfishGlobe({
  draw,
  onVesselSelected,
  onRegionSelected,
  portCalls = [],
  layerOverrides,
  cameraLocked = false,
}: Props) {
  const globeRef = useRef<GlobeMethods>();

  // Live-tunable controls (leva panel mounted in main.tsx).
  const controls = useGlobeControls();
  const { isUpdatingLayers } = useGlobeControlsContext();
  const showVessels = layerOverrides?.showVessels ?? controls.showVessels;
  const showHeatmap = layerOverrides?.showHeatmap ?? controls.showHeatmap;
  const showPaths = layerOverrides?.showPaths ?? controls.showPaths;
  const flightCount = layerOverrides?.flightCount ?? controls.flightCount;
  const showSharkHeatmap = layerOverrides?.showSharkHeatmap ?? controls.showSharkHeatmap;

  useEffect(() => {
    if (!globeRef.current) return;
    const orbit = globeRef.current.controls();
    if (orbit) {
      orbit.autoRotate = true;
      orbit.autoRotateSpeed = 0.4;
    }
    globeRef.current.pointOfView({ lat: -0.5, lng: -90.5, altitude: 2.4 }, 0);

    // Add a hemisphere light so PBR materials (procedural and GLTF) are
    // visible from any angle. Default scene has only ambient + directional.
    const scene = globeRef.current.scene();
    const hemi = new THREE.HemisphereLight(0xffffff, 0x223355, 1.1);
    scene.add(hemi);
    const fill = new THREE.DirectionalLight(0xffffff, 0.6);
    fill.position.set(-150, 100, 50);
    scene.add(fill);

    return () => {
      scene.remove(hemi);
      scene.remove(fill);
    };
  }, []);

  // Pause auto-rotate while drawing OR while a region is selected, so the
  // user can zoom in and inspect vessels without the camera spinning away.
  // Region-select clears auto-rotate inside handleRegionClick (below); this
  // hook only handles the drawing-mode case.
  useEffect(() => {
    const controls = globeRef.current?.controls();
    if (!controls) return;
    if (draw.mode !== "idle") {
      controls.autoRotate = false;
    }
  }, [draw.mode]);

  // Camera lock: when true, freeze pan/zoom/rotate and stop auto-rotate.
  // Used by the click-a-region cinematic so the camera holds steady on the
  // selected region. We do this in two phases:
  //   1. Immediately disable user-driven controls + auto-rotate (so the
  //      pointOfView fly-in is the only allowed motion).
  //   2. After the ~2.2s pointOfView animation settles, snapshot the camera
  //      pose and pin it on every controls "change" event — anything that
  //      tries to nudge the camera (residual inertia, accidental input,
  //      damping tail) gets snapped back to the snapshot.
  // Restoring on unlock re-enables interaction + auto-rotate.
  useEffect(() => {
    const orbit = globeRef.current?.controls() as
      | {
          autoRotate: boolean;
          enableZoom: boolean;
          enablePan: boolean;
          enableRotate: boolean;
          enableDamping: boolean;
          object: THREE.Camera;
          target: THREE.Vector3;
          update: () => void;
          addEventListener: (event: string, cb: () => void) => void;
          removeEventListener: (event: string, cb: () => void) => void;
        }
      | undefined;
    if (!orbit) return;

    if (!cameraLocked) {
      orbit.enableZoom = true;
      orbit.enablePan = true;
      orbit.enableRotate = true;
      orbit.enableDamping = true;
      orbit.autoRotate = true;
      return;
    }

    // Phase 1: hard-disable user input immediately.
    orbit.autoRotate = false;
    orbit.enableZoom = false;
    orbit.enablePan = false;
    orbit.enableRotate = false;
    orbit.enableDamping = false; // kill any inertia tail

    let pinning = false;
    let pinPos: THREE.Vector3 | null = null;
    let pinTarget: THREE.Vector3 | null = null;
    let onChange: (() => void) | null = null;

    // Phase 2: after the fly-in finishes, snapshot pose and start enforcing.
    const settleMs = 2400;
    const settleId = window.setTimeout(() => {
      pinPos = orbit.object.position.clone();
      pinTarget = orbit.target.clone();
      pinning = true;
      onChange = () => {
        if (!pinning || !pinPos || !pinTarget) return;
        // Snap back if anything moved.
        if (
          !orbit.object.position.equals(pinPos) ||
          !orbit.target.equals(pinTarget)
        ) {
          orbit.object.position.copy(pinPos);
          orbit.target.copy(pinTarget);
        }
      };
      orbit.addEventListener("change", onChange);
    }, settleMs);

    return () => {
      window.clearTimeout(settleId);
      pinning = false;
      if (onChange) orbit.removeEventListener("change", onChange);
    };
  }, [cameraLocked]);

  // ── Data ─────────────────────────────────────────────────────────────
  const vesselsQ = useQuery({ queryKey: ["vessels"], queryFn: () => api.vessels() });
  const heatmapQ = useQuery({ queryKey: ["heatmap"], queryFn: () => api.heatmap() });
  const trackQ = useQuery({
    queryKey: ["track", DEMO_MMSI],
    queryFn: () => api.vesselTrack(DEMO_MMSI),
  });
  const regionQ = useQuery({
    queryKey: ["region"],
    queryFn: () => api.defineRegion({ type: "Polygon", coordinates: [] }),
  });
  const fisheryRegionsQ = useQuery({
    queryKey: ["fisheryRegions"],
    queryFn: () => api.fisheryRegions(),
  });
  const globalTracksQ = useQuery({
    queryKey: ["globalTracks"],
    queryFn: () => api.globalVesselTracks(),
  });
  const pointsQ = useQuery({
    queryKey: ["fishingDots"],
    queryFn: async () => {
      const res = await fetch("/fishing-dots.json");
      if (!res.ok) throw new Error("Failed to load dots");
      return res.json() as Promise<{ lat: number; lng: number; flag: string | null; hours: number }[]>;
    },
  });

  // ── Shark heatmap data ───────────────────────────────────────────────
  const sharkQ = useQuery({
    queryKey: ["sharkHeatmap"],
    queryFn: async () => {
      const res = await fetch("/shark-heatmap.json");
      if (!res.ok) throw new Error("Failed to load shark data");
      return res.json() as Promise<SharkPoint[]>;
    },
  });

  // Render shark distribution as a Gaussian heatmap texture wrapped on a
  // sphere slightly above the globe surface. Paints an equirectangular
  // canvas (ocean-only, land-masked) and drapes it onto a Three.js sphere
  // added directly to the scene.
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

      // Filter out any points that sit on land
      const oceanPts = sharkQ.data!.filter((p) => !isLand(p.lat, p.lng));

      const W = 4096;
      const H = 2048;
      const canvas = document.createElement("canvas");
      canvas.width = W;
      canvas.height = H;
      const ctx = canvas.getContext("2d")!;
      ctx.globalCompositeOperation = "lighter";

      for (const pt of oceanPts) {
        const px = ((pt.lng + 180) / 360) * W;
        const py = ((90 - pt.lat) / 180) * H;
        const r = 25 + pt.weight * 30;
        const grad = ctx.createRadialGradient(px, py, 0, px, py, r);
        const a0 = 0.10 + pt.weight * 0.14;
        const a1 = 0.04 + pt.weight * 0.06;
        grad.addColorStop(0.0, `rgba(100, 240, 140, ${a0.toFixed(3)})`);
        grad.addColorStop(0.4, `rgba(40, 180, 80, ${a1.toFixed(3)})`);
        grad.addColorStop(0.75, `rgba(15, 120, 50, ${(a1 * 0.3).toFixed(3)})`);
        grad.addColorStop(1.0, "rgba(0, 80, 30, 0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fill();
      }


      const texture = new THREE.CanvasTexture(canvas);
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

  const isDrawing = draw.mode === "drawing";

  // ── Fleet ────────────────────────────────────────────────────────────
  // Combine ambient global tracks + the demo vessel itself so the demo vessel
  // also appears as a 3D ship at its (static) last_position.
  const ambientFleet: FleetVessel[] = useMemo(() => {
    const fleet: FleetVessel[] = [...(globalTracksQ.data ?? [])];
    // Add Galápagos vessels as static (single-point) tracks so they get 3D meshes too.
    for (const v of vesselsQ.data ?? []) {
      if (!v.last_position) continue;
      fleet.push({
        mmsi: v.mmsi,
        name: v.name ?? v.mmsi,
        flag: v.flag ?? "",
        risk: v.mmsi === DEMO_MMSI ? "confirmed_iuu" : "safe",
        // Static: same point twice so interpolation is a no-op.
        points: [
          [v.last_position.lat, v.last_position.lon],
          [v.last_position.lat, v.last_position.lon],
        ],
      });
    }
    return fleet;
  }, [globalTracksQ.data, vesselsQ.data]);

  const animatedVessels = useAnimatedFleet(ambientFleet);

  // ── Vessel mesh cache: one persistent Three.js Group per vessel ──────
  // Critical: getVesselMesh must always return the SAME object reference for
  // the same vessel. globe.gl re-uses the existing mesh when the reference
  // matches; if we returned a new clone each call, the layer would tear down
  // and rebuild scene graph entries every frame (catastrophic perf).
  const meshCacheRef = useRef<Map<string, THREE.Group>>(new Map());
  useEffect(() => () => meshCacheRef.current.clear(), []);

  const getVesselMesh = useCallback((d: object): THREE.Object3D => {
    const v = d as AnimatedVessel;
    let mesh = meshCacheRef.current.get(v.mmsi);
    if (!mesh) {
      mesh = makeLightweightVesselMesh(RISK_COLOR[v.risk]);
      const scale = v.mmsi === DEMO_MMSI ? 1.6 : 1.2;
      mesh.scale.set(scale, scale, scale);
      meshCacheRef.current.set(v.mmsi, mesh);
    }
    mesh.rotation.set(0, 0, ((-v.heading + 90) * Math.PI) / 180);
    return mesh;
  }, []);

  // ── Galápagos demo flagged vessel (for the rings layer) ──────────────
  // Use a ref-equality-stable filter so the rings layer doesn't re-init
  // every animation tick.
  const flagged = useMemo(() => {
    const m = animatedVessels.find((v) => v.mmsi === DEMO_MMSI);
    return m ? [m] : [];
  }, [animatedVessels]);

  // ── Flight-path layer: dense procedural routes with InstancedMesh ────
  // The visible-everywhere ambient traffic. Generated deterministically
  // (seeded) so hot-reload doesn't reshuffle the route set on every render.
  // Color hints map RouteRisk → curve gradient + vessel tint.
  //
  // Async because route generation depends on the land/ocean mask being
  // loaded. While the mask is in flight, `flightRoutes` is empty and the
  // layer renders nothing — typical first-paint delay is ~50ms.
  const [flightRoutes, setFlightRoutes] = useState<FlightRoute[]>([]);
  useEffect(() => {
    let cancelled = false;
    if (flightCount <= 0) {
      setFlightRoutes([]);
      return;
    }
    void whenLandMaskReady().then(() => {
      if (cancelled) return;
      const routes: FlightRoute[] = generateRoutes(flightCount, 42).map((r) => {
        const c = RISK_COLOR[r.risk];
        return {
          waypoints: r.waypoints,
          curveColorStart: new THREE.Color(c).multiplyScalar(0.25),
          curveColorEnd: new THREE.Color(c),
          vesselColor: c,
        };
      });
      setFlightRoutes(routes);
    });
    return () => {
      cancelled = true;
    };
  }, [flightCount]);

  useFlightPathLayer(globeRef, {
    routes: flightRoutes,
    showVessels,
    showPaths,
    vesselSize: controls.vesselSize,
    animationSpeed: controls.animationSpeed,
    tiltMode: controls.tiltMode,
    dashSize: controls.dashSize,
    gapSize: controls.gapSize,
    vesselElevation: controls.vesselElevation,
    arcMinAltitude: controls.arcMinAltitude,
    arcMaxAltitude: controls.arcMaxAltitude,
  });

  // ── Arcs: demo vessel parabolic trajectory + port-call surface line ──
  // The dense ambient flight-path traffic is a separate Three.js
  // InstancedMesh layer (see ./flightPath/useFlightPathLayer.ts), so the
  // Arcs layer only handles the two narrative beats.
  const arcsData: AnyArc[] = useMemo(() => {
    const out: AnyArc[] = [];
    const track = trackQ.data;
    if (track && track.length >= 2) {
      const [startLat, startLng] = track[0];
      const [endLat, endLng] = track[track.length - 1];
      out.push({ kind: "demo_track", startLat, startLng, endLat, endLng });
    }
    for (const c of portCalls) {
      out.push({
        kind: "port_call",
        startLat: c.startLat,
        startLng: c.startLng,
        endLat: c.endLat,
        endLng: c.endLng,
      });
    }
    return out;
  }, [trackQ.data, portCalls]);

  // Pulsing rings at every active port-call destination (the "notification
  // landed" beat). The rings layer already pulses the flagged vessel; we
  // append destination points to a separate ringsData below.
  const portPulseRings = useMemo(() => {
    return portCalls.map((c) => ({ lat: c.endLat, lng: c.endLng }));
  }, [portCalls]);

  const allRingsData = useMemo(
    () => [
      ...flagged.map((v) => ({ lat: v.lat, lng: v.lng, kind: "flagged" as const })),
      ...portPulseRings.map((p) => ({ lat: p.lat, lng: p.lng, kind: "port" as const })),
    ],
    [flagged, portPulseRings],
  );

  // ── Paths: drawing polyline only ─────────────────────────────────────
  // Ambient wakes were removed for perf; the demo vessel trajectory still
  // renders via the Arcs layer (parabolic) below.
  type AnyPath = { kind: "draft"; pts: { lat: number; lng: number }[] };

  const pathsData: AnyPath[] = useMemo(() => {
    const out: AnyPath[] = [];
    for (const p of draw.drawingPathsData) {
      out.push({ kind: "draft", pts: p.pts });
    }
    return out;
  }, [draw.drawingPathsData]);

  // ── Polygons (MPA + drawn region + invisible region click targets) ───
  // The "click target" entries are invisible (cap+side+stroke all transparent)
  // — they exist purely to receive onPolygonClick events for region selection,
  // since we removed the visible hex-polygons layer.
  type AnyPoly =
    | { kind: "mpa"; geometry: GeoJSON.Polygon; name?: string }
    | { kind: "committed"; geometry: GeoJSON.Polygon }
    | { kind: "region_click_target"; geometry: GeoJSON.Polygon; region: FisheryRegion };

  const polygonsData: AnyPoly[] = useMemo(() => {
    if (isDrawing) return [];
    const out: AnyPoly[] = [];
    if (regionQ.data?.polygon_geojson) {
      out.push({
        kind: "mpa",
        geometry: regionQ.data.polygon_geojson as unknown as GeoJSON.Polygon,
        name: regionQ.data.name,
      });
    }
    for (const c of draw.committedPolygonsData) {
      out.push({ kind: "committed", geometry: c.geometry });
    }
    for (const r of fisheryRegionsQ.data ?? []) {
      out.push({ kind: "region_click_target", geometry: r.geometry, region: r });
    }
    return out;
  }, [isDrawing, regionQ.data, draw.committedPolygonsData, fisheryRegionsQ.data]);

  // ── Heatmap ──────────────────────────────────────────────────────────
  const heatmapsData = useMemo(
    () => (showHeatmap && heatmapQ.data ? [heatmapQ.data] : []),
    [heatmapQ.data, showHeatmap],
  );

  // ── Labels ───────────────────────────────────────────────────────────
  const labelsData = useMemo(() => {
    const regionLabels = (fisheryRegionsQ.data ?? []).map((r) => {
      const ring = r.geometry.coordinates[0] as GeoJSON.Position[];
      const lng = ring.reduce((s, p) => s + p[0], 0) / ring.length;
      const lat = ring.reduce((s, p) => s + p[1], 0) / ring.length;
      return {
        lat,
        lng,
        text: r.name.toUpperCase(),
        risk: r.risk,
        kind: "region" as const,
        regionId: r.region_id,
      };
    });
    return [
      ...regionLabels,
      { lat: -12.0464, lng: -77.1428, text: "CALLAO", risk: "safe" as const, kind: "port" as const, regionId: undefined },
      { lat: -0.9485, lng: -80.7256, text: "MANTA", risk: "safe" as const, kind: "port" as const, regionId: undefined },
    ];
  }, [fisheryRegionsQ.data]);

  // ── Region click handler ─────────────────────────────────────────────
  // Triggered by clicking either the invisible region polygon or the region
  // label dot. Stops auto-rotate, flies camera in, surfaces the region to App.
  const selectRegion = (region: FisheryRegion) => {
    const ring = region.geometry.coordinates[0] as GeoJSON.Position[];
    const lng = ring.reduce((s, p) => s + p[0], 0) / ring.length;
    const lat = ring.reduce((s, p) => s + p[1], 0) / ring.length;
    const controls = globeRef.current?.controls();
    if (controls) controls.autoRotate = false;
    globeRef.current?.pointOfView({ lat, lng, altitude: 0.55 }, 2200);
    onRegionSelected?.(region);
  };

  const handlePolygonClick = (d: object) => {
    const poly = d as AnyPoly;
    if (poly.kind === "region_click_target") {
      selectRegion(poly.region);
    }
  };

  const handleLabelClick = (d: object) => {
    const label = d as { regionId?: string; kind: string };
    if (label.kind !== "region" || !label.regionId) return;
    const region = (fisheryRegionsQ.data ?? []).find((r) => r.region_id === label.regionId);
    if (region) selectRegion(region);
  };

  // ── Pointer-events filter: in drawing mode, suppress non-globe clicks ─
  const pointerEventsFilter = useCallback(
    (_obj: object) => !isDrawing, // false (block) while drawing; true otherwise
    [isDrawing],
  );

  // ── Stable path accessors (drawing polyline only) ────────────────────
  const pathPoints = useCallback(
    (d: object) => (d as AnyPath).pts.map((v) => [v.lat, v.lng]),
    [],
  );
  const pathColor = useCallback((): string[] => ["#00ffe0", "#00ffe0"], []);
  const pathStroke = useCallback(() => 0.4, []);
  const pathDashLength = useCallback(() => 0.3, []);
  const pathDashAnimateTime = useCallback(() => 1500, []);

  // Stable accessors for the 3D objects layer (vessels)
  const objectLat = useCallback((d: object) => (d as AnimatedVessel).lat, []);
  const objectLng = useCallback((d: object) => (d as AnimatedVessel).lng, []);

  // ── Arc accessors — only demo_track + port_call now, since the dense
  // ambient traffic moved to the InstancedMesh flight-path layer.
  const arcColor = useCallback((d: object): string[] => {
    const a = d as AnyArc;
    if (a.kind === "demo_track") {
      return ["rgba(255, 31, 77, 0.15)", "rgba(255, 31, 77, 1)"];
    }
    return ["rgba(255, 140, 60, 0.6)", "rgba(255, 140, 60, 1)"];
  }, []);

  const arcStroke = useCallback((d: object) => {
    const a = d as AnyArc;
    return a.kind === "demo_track" ? 0.7 : 0.45;
  }, []);

  const arcAltitude = useCallback((d: object) => {
    const a = d as AnyArc;
    return a.kind === "port_call" ? 0.001 : null;
  }, []);

  const arcDashLength = useCallback((d: object) => {
    const a = d as AnyArc;
    return a.kind === "demo_track" ? 0.35 : 0.25;
  }, []);

  const arcDashGap = useCallback((d: object) => {
    const a = d as AnyArc;
    return a.kind === "demo_track" ? 0.15 : 0.2;
  }, []);

  const arcDashInitialGap = useCallback((d: object) => {
    const a = d as AnyArc;
    return a.kind === "demo_track" ? 1 : 0;
  }, []);

  const arcDashAnimateTime = useCallback((d: object) => {
    const a = d as AnyArc;
    return a.kind === "demo_track" ? 3500 : 2000;
  }, []);

  return (
    <div className="globe-host relative">
      {/* Heavy 3D Calculation Loading Overlay */}
      {isUpdatingLayers && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm pointer-events-none transition-opacity">
          <div className="flex flex-col items-center gap-4">
            <div className="w-12 h-12 border-4 border-cyan-500/20 border-t-cyan-400 rounded-full animate-spin shadow-[0_0_15px_rgba(34,211,238,0.5)]" />
            <div className="text-cyan-400/80 font-mono text-sm tracking-widest uppercase animate-pulse">Rendering Data...</div>
          </div>
        </div>
      )}

      <Globe
        ref={globeRef}
        globeImageUrl={GLOBE_IMG}
        bumpImageUrl={BUMP_IMG}
        backgroundImageUrl={BG_IMG}
        atmosphereColor="#00d4ff"
        atmosphereAltitude={0.18}
        showGraticules={false}
        pointerEventsFilter={pointerEventsFilter}
        /* Globe click (drawing) */
        onGlobeClick={({ lat, lng }) => draw.onGlobeClick({ lat, lng })}
        /* ── Heatmap (smoother gradient — perf budget) ───────── */
        /* Wider bandwidth + lower top altitude → coarser KDE grid + fewer
         * triangles. Trades off the dramatic 3D peaks for smoother frames
         * during drag/zoom; risk regions still read as warm density blobs. */
        heatmapsData={heatmapsData}
        heatmapPoints={(set) => set as { lat: number; lon: number; hours: number }[]}
        heatmapPointLat="lat"
        heatmapPointLng="lon"
        heatmapPointWeight="hours"
        heatmapBandwidth={1.5}
        heatmapColorSaturation={2.6}
        heatmapBaseAltitude={0.01}
        heatmapTopAltitude={0.04}
        heatmapsTransitionDuration={2000}

        /* ── Points (Raw AIS positions) ───────── */
        pointsData={controls.showPoints ? pointsQ.data ?? [] : []}
        pointLat="lat"
        pointLng="lng"
        pointColor={(d: object) => {
          const flag = (d as { flag: string | null }).flag ?? "";
          if (["CHN", "TWN", "VUT", "COM", "TGO", "GNE"].includes(flag)) return "rgba(255,80,20,0.85)";
          if (["KOR", "RUS", "ESP", "IDN", "IRN"].includes(flag)) return "rgba(255,160,0,0.80)";
          return "rgba(255,210,50,0.72)";
        }}
        pointAltitude={0.01}
        pointRadius={0.35}
        pointResolution={3}
        pointsMerge={true}
        pointsTransitionDuration={0}

        /* ── Polygons: MPA boundary + user draw + invisible region click targets ── */
        polygonsData={polygonsData}
        polygonGeoJsonGeometry={(d: object) =>
          (d as AnyPoly).geometry as unknown as { type: string; coordinates: number[] }
        }
        polygonAltitude={(d: object) => {
          const p = d as AnyPoly;
          if (p.kind === "region_click_target") {
            // Lift risky regions slightly so the tint reads against the globe.
            const r = p.region.risk;
            if (r === "confirmed_iuu" || r === "high_risk") return 0.006;
            if (r === "suspect") return 0.003;
            return 0.001; // safe — keep invisible
          }
          return 0.012;
        }}
        polygonCapColor={(d: object) => {
          const p = d as AnyPoly;
          if (p.kind === "region_click_target") {
            const r = p.region.risk;
            if (r === "confirmed_iuu") return "rgba(255, 31, 77, 0.22)";
            if (r === "high_risk") return "rgba(255, 138, 0, 0.18)";
            if (r === "suspect") return "rgba(255, 212, 0, 0.10)";
            return "rgba(0, 0, 0, 0)"; // safe — invisible
          }
          if (p.kind === "mpa") return "rgba(0, 255, 224, 0.10)";
          return "rgba(0, 255, 224, 0.22)"; // committed user-drawn region
        }}
        polygonSideColor={(d: object) => {
          const p = d as AnyPoly;
          if (p.kind === "region_click_target") {
            const r = p.region.risk;
            if (r === "confirmed_iuu") return "rgba(255, 31, 77, 0.10)";
            if (r === "high_risk") return "rgba(255, 138, 0, 0.08)";
            return "rgba(0, 0, 0, 0)";
          }
          return "rgba(0, 255, 224, 0.06)";
        }}
        polygonStrokeColor={(d: object) => {
          const p = d as AnyPoly;
          if (p.kind === "region_click_target") {
            const r = p.region.risk;
            if (r === "confirmed_iuu") return "#ff1f4d";
            if (r === "high_risk") return "#ff8a00";
            if (r === "suspect") return "rgba(255, 212, 0, 0.7)";
            return "rgba(0, 0, 0, 0)";
          }
          return "#00ffe0";
        }}
        polygonLabel={(d: object) => {
          const p = d as AnyPoly;
          if (p.kind !== "region_click_target") return "";
          const r = p.region;
          return `<div class="font-mono text-xs leading-tight bg-black/85 text-cyan-100 border border-cyan-500/30 rounded px-2 py-1.5 shadow-lg">
            <div class="font-medium text-sm">${r.name}</div>
            <div class="text-[10px] uppercase tracking-wider mt-0.5" style="color: ${RISK_COLOR[r.risk]}">${r.risk.replace("_", " ")}</div>
            <div class="text-[10px] text-cyan-300/70 mt-1">click to inspect region</div>
          </div>`;
        }}
        onPolygonClick={handlePolygonClick}
        polygonsTransitionDuration={1200}
        /* ── Vessel meshes (3D Objects) ────────────────── */
        objectsData={showVessels ? animatedVessels : []}
        objectLat={objectLat}
        objectLng={objectLng}
        objectAltitude={0.012}
        objectFacesSurfaces={true}
        objectThreeObject={getVesselMesh}
        objectLabel={(d: object) => {
          const v = d as AnimatedVessel;
          return `<div class="font-mono text-xs leading-tight bg-black/85 text-cyan-100 border border-cyan-500/30 rounded px-2 py-1">
            <div class="font-medium">${v.name}</div>
            <div class="text-cyan-300/60">MMSI ${v.mmsi}${v.flag ? ` · ${v.flag}` : ""}</div>
            <div class="text-[10px] uppercase tracking-wider mt-0.5" style="color: ${RISK_COLOR[v.risk]}">${v.risk.replace("_", " ")}</div>
          </div>`;
        }}
        onObjectClick={(d: object) => {
          const v = d as AnimatedVessel;
          onVesselSelected({
            mmsi: v.mmsi,
            name: v.name,
            flag: v.flag,
            authorizations: [],
            last_position: { lat: v.lat, lon: v.lng },
          } as Vessel);
          globeRef.current?.pointOfView({ lat: v.lat, lng: v.lng, altitude: 0.4 }, 2500);
        }}
        /* ── Pulsing rings (flagged vessel + port-call destinations) ───── */
        ringsData={allRingsData}
        ringLat={(d) => (d as { lat: number }).lat}
        ringLng={(d) => (d as { lng: number }).lng}
        ringColor={((d: object) => {
          const r = d as { kind: "flagged" | "port" };
          return r.kind === "flagged"
            ? (t: number) => `rgba(255, 59, 59, ${1 - t})`
            : (t: number) => `rgba(255, 140, 60, ${0.85 * (1 - t)})`;
        }) as (d: object) => (t: number) => string}
        ringMaxRadius={(d) => ((d as { kind: string }).kind === "port" ? 2.4 : 4)}
        ringPropagationSpeed={(d) =>
          (d as { kind: string }).kind === "port" ? 1.4 : 2
        }
        ringRepeatPeriod={(d) =>
          (d as { kind: string }).kind === "port" ? 900 : 700
        }
        /* ── Paths (ambient wakes + drawing polyline) ────── */
        pathsData={pathsData}
        pathPoints={pathPoints}
        pathPointLat={(p: unknown) => (p as [number, number])[0]}
        pathPointLng={(p: unknown) => (p as [number, number])[1]}
        pathColor={pathColor}
        pathStroke={pathStroke}
        pathDashLength={pathDashLength}
        pathDashGap={0.16}
        pathDashAnimateTime={pathDashAnimateTime}
        pathResolution={4}
        /* ── Arcs (demo vessel parabolic trajectory + port-call surface line) ─ */
        /* Demo trajectory lifts off the sphere as a bold parabolic arc with
         * marching dashes — the AIS-gap "vessel went dark and reappeared
         * here" beat. Port-call hugs the surface as a low dashed line so the
         * two read as different actions, not the same kind of event. */
        arcsData={arcsData}
        arcStartLat={(d) => (d as AnyArc).startLat}
        arcStartLng={(d) => (d as AnyArc).startLng}
        arcEndLat={(d) => (d as AnyArc).endLat}
        arcEndLng={(d) => (d as AnyArc).endLng}
        arcColor={arcColor as unknown as (d: object) => string}
        arcStroke={arcStroke}
        arcAltitude={arcAltitude}
        arcAltitudeAutoScale={0.5}
        arcDashLength={arcDashLength}
        arcDashGap={arcDashGap}
        arcDashInitialGap={arcDashInitialGap}
        arcDashAnimateTime={arcDashAnimateTime}
        /* ── Labels (big + region-colored, clickable for region selection) ─ */
        labelsData={labelsData}
        labelLat={(d) => (d as { lat: number }).lat}
        labelLng={(d) => (d as { lng: number }).lng}
        labelText={(d) => (d as { text: string }).text}
        labelSize={(d) => ((d as { kind: string }).kind === "port" ? 0.55 : 0.95)}
        labelColor={(d) => {
          const l = d as { kind: string; risk: keyof typeof RISK_COLOR };
          if (l.kind === "port") return "#ffce5e";
          // Strong opaque colors so labels read against bright Blue Marble.
          return RISK_COLOR[l.risk];
        }}
        labelResolution={3}
        labelDotRadius={0.18}
        labelDotOrientation={() => "bottom"}
        labelAltitude={0.018}
        onLabelClick={handleLabelClick}
      />
    </div>
  );
}


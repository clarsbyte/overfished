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
import type { Vessel } from "@/types/schemas";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Globe, { type GlobeMethods } from "react-globe.gl";
import * as THREE from "three";
import {
  type AnimatedVessel,
  type FleetVessel,
  useAnimatedFleet,
} from "./useAnimatedFleet";
import { useDrawController } from "./useDrawController";
import { makeVesselMesh, preloadVesselModel } from "./vesselMesh";

interface PortCallArc {
  startLat: number;
  startLng: number;
  endLat: number;
  endLng: number;
}

export interface FisheryRegion {
  region_id: string;
  name: string;
  risk: "confirmed_iuu" | "high_risk" | "suspect" | "safe";
  geometry: GeoJSON.Polygon;
}

interface Props {
  draw: ReturnType<typeof useDrawController>;
  onVesselSelected: (vessel: Vessel) => void;
  onRegionSelected?: (region: FisheryRegion) => void;
  portCallArcs?: PortCallArc[];
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
  portCallArcs = [],
}: Props) {
  const globeRef = useRef<GlobeMethods>();

  // Track when the GLTF model is ready so vessel meshes can re-render to
  // pick it up. We bump a cache-busting key on load — the meshCacheRef gets
  // cleared and getVesselMesh rebuilds from cachedGltf the next time.
  const [modelReady, setModelReady] = useState(false);

  // Initial camera + auto-rotate + GLTF preload + extra lighting (the PBR
  // procedural ship and any GLTF need MeshStandardMaterial-friendly light).
  useEffect(() => {
    if (!globeRef.current) return;
    const controls = globeRef.current.controls();
    if (controls) {
      controls.autoRotate = true;
      controls.autoRotateSpeed = 0.4;
    }
    globeRef.current.pointOfView({ lat: -0.5, lng: -90.5, altitude: 1.8 }, 0);

    // Add a hemisphere light so PBR materials (procedural and GLTF) are
    // visible from any angle. Default scene has only ambient + directional.
    const scene = globeRef.current.scene();
    const hemi = new THREE.HemisphereLight(0xffffff, 0x223355, 1.1);
    scene.add(hemi);
    const fill = new THREE.DirectionalLight(0xffffff, 0.6);
    fill.position.set(-150, 100, 50);
    scene.add(fill);

    // Kick off GLTF load (no-op if no model file is present; falls back to
    // the procedural ship until or unless a real GLTF resolves).
    void preloadVesselModel().then((loaded) => {
      if (loaded) setModelReady(true);
    });

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
  //
  // Cleared when the GLTF resolves so cached procedural meshes get upgraded.
  const meshCacheRef = useRef<Map<string, THREE.Group>>(new Map());
  useEffect(() => {
    meshCacheRef.current.clear();
  }, [modelReady]);
  useEffect(() => () => meshCacheRef.current.clear(), []);

  const getVesselMesh = useCallback((d: object): THREE.Object3D => {
    const v = d as AnimatedVessel;
    let mesh = meshCacheRef.current.get(v.mmsi);
    if (!mesh) {
      const isFlagged = v.mmsi === DEMO_MMSI;
      mesh = makeVesselMesh(RISK_COLOR[v.risk], isFlagged);
      const scale = isFlagged ? 1.6 : 1.2;
      mesh.scale.set(scale, scale, scale);
      meshCacheRef.current.set(v.mmsi, mesh);
    }
    // Update rotation in place — heading changes per frame as vessel moves.
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

  // ── Paths: demo vessel trajectory + ambient wakes + drawing polyline ──
  // Wake trails: every ambient vessel's full track is rendered as a faint
  // animated dashed path. Reads as 80 simultaneous AIS history lines moving
  // alongside their ships.
  type AnyPath =
    | { kind: "track"; points: [number, number][]; mmsi: string }
    | { kind: "wake"; points: [number, number][]; risk: keyof typeof RISK_COLOR }
    | { kind: "draft"; pts: { lat: number; lng: number }[] };

  // Sample every Nth vessel for wakes. With ~80 vessels in fleet, N=3 gives
  // ~27 wake trails — enough to read as a busy ocean, light enough to keep
  // the Paths layer cheap.
  const WAKE_SAMPLE_RATE = 3;

  const pathsData: AnyPath[] = useMemo(() => {
    const out: AnyPath[] = [];
    // Demo vessel's prominent red trajectory (Galápagos AIS gap).
    if (trackQ.data) out.push({ kind: "track", points: trackQ.data, mmsi: DEMO_MMSI });
    // Ambient fleet wakes — every Nth vessel, color by risk class.
    const tracks = globalTracksQ.data ?? [];
    for (let i = 0; i < tracks.length; i += WAKE_SAMPLE_RATE) {
      const v = tracks[i];
      if (v.points.length < 2) continue;
      out.push({ kind: "wake", points: v.points, risk: v.risk });
    }
    // In-progress drawing polyline.
    for (const p of draw.drawingPathsData) {
      out.push({ kind: "draft", pts: p.pts });
    }
    return out;
  }, [trackQ.data, globalTracksQ.data, draw.drawingPathsData]);

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
  const heatmapsData = useMemo(() => (heatmapQ.data ? [heatmapQ.data] : []), [heatmapQ.data]);

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

  // ── Stable path accessors — hot path, ~30 Hz invocations ─────────────
  const pathPoints = useCallback((d: object) => {
    const p = d as AnyPath;
    if (p.kind === "draft") return p.pts.map((v) => [v.lat, v.lng]);
    return p.points;
  }, []);

  const pathColor = useCallback((d: object): string[] => {
    const p = d as AnyPath;
    if (p.kind === "draft") return ["#00ffe0", "#00ffe0"];
    if (p.kind === "track") return ["rgba(255, 31, 77, 0)", "rgba(255, 31, 77, 0.98)"];
    const c = RISK_COLOR[p.risk];
    return [hexToRgba(c, 0), hexToRgba(c, 0.65)];
  }, []);

  const pathStroke = useCallback((d: object) => {
    const p = d as AnyPath;
    if (p.kind === "draft") return 0.4;
    if (p.kind === "track") return 0.7;
    return 0.28;
  }, []);

  const pathDashLength = useCallback((d: object) => {
    const p = d as AnyPath;
    if (p.kind === "draft") return 0.3;
    if (p.kind === "track") return 0.4;
    return 0.32;
  }, []);

  const pathDashAnimateTime = useCallback((d: object) => {
    const p = d as AnyPath;
    if (p.kind === "draft") return 1500;
    if (p.kind === "track") return 4000;
    return 9000;
  }, []);

  // Stable accessors for the 3D objects layer (vessels)
  const objectLat = useCallback((d: object) => (d as AnimatedVessel).lat, []);
  const objectLng = useCallback((d: object) => (d as AnimatedVessel).lng, []);

  return (
    <div className="globe-host">
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
        /* ── Heatmap (dramatic 3D peaks for IUU hotspots) ─────── */
        /* Tightened bandwidth so density concentrates rather than smearing
         * across the ocean; topAltitude bumped substantially so high-risk
         * regions rise as visible 3D mounds (matches the docs example). */
        heatmapsData={heatmapsData}
        heatmapPoints={(set) => set as { lat: number; lon: number; hours: number }[]}
        heatmapPointLat="lat"
        heatmapPointLng="lon"
        heatmapPointWeight="hours"
        heatmapBandwidth={0.85}
        heatmapColorSaturation={2.6}
        heatmapBaseAltitude={0.01}
        heatmapTopAltitude={0.08}
        heatmapsTransitionDuration={2000}
        /* ── Polygons: MPA boundary + user draw + invisible region click targets ── */
        polygonsData={polygonsData}
        polygonGeoJsonGeometry={(d: object) =>
          (d as AnyPoly).geometry as unknown as { type: string; coordinates: number[] }
        }
        polygonAltitude={(d: object) => {
          const p = d as AnyPoly;
          if (p.kind === "region_click_target") return 0.001; // flat to avoid visual lift
          return 0.012;
        }}
        polygonCapColor={(d: object) => {
          const p = d as AnyPoly;
          if (p.kind === "region_click_target") return "rgba(0, 0, 0, 0)"; // INVISIBLE click target
          if (p.kind === "mpa") return "rgba(0, 255, 224, 0.10)";
          return "rgba(0, 255, 224, 0.22)"; // committed user-drawn region
        }}
        polygonSideColor={(d: object) =>
          (d as AnyPoly).kind === "region_click_target"
            ? "rgba(0, 0, 0, 0)"
            : "rgba(0, 255, 224, 0.06)"
        }
        polygonStrokeColor={(d: object) =>
          (d as AnyPoly).kind === "region_click_target" ? "rgba(0, 0, 0, 0)" : "#00ffe0"
        }
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
        objectsData={animatedVessels}
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
        /* ── Pulsing rings (flagged vessel only) ───────── */
        ringsData={flagged}
        ringLat={objectLat}
        ringLng={objectLng}
        ringColor={() => (t: number) => `rgba(255, 59, 59, ${1 - t})`}
        ringMaxRadius={4}
        ringPropagationSpeed={2}
        ringRepeatPeriod={700}
        /* ── Paths (demo vessel + ambient wakes + drawing) ─ */
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
        /* ── Arcs (port-call beat) ─────────────────────── */
        arcsData={portCallArcs}
        arcStartLat={(d) => (d as PortCallArc).startLat}
        arcStartLng={(d) => (d as PortCallArc).startLng}
        arcEndLat={(d) => (d as PortCallArc).endLat}
        arcEndLng={(d) => (d as PortCallArc).endLng}
        arcColor={() => "#ff3b3b"}
        arcStroke={0.5}
        arcDashLength={0.3}
        arcDashGap={0.2}
        arcDashAnimateTime={2500}
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

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

import { useQuery } from "@tanstack/react-query";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react";
import * as THREE from "three";

import type { Risk } from "@/lib/api";
import { isLand, whenLandMaskReady } from "@/lib/landMask";
import { SOURCE_COLOR, type Ship } from "@/types/ship";

interface SharkPoint { lat: number; lng: number; weight: number; }

export interface Seamount {
  id: string;
  name: string;
  region: string;
  lat: number;
  lng: number;
  summit_depth_m: number;
  base_depth_m: number;
  radius_km: number;
  fishing_pressure: number;
  coral_age_years: number;
  note: string;
}

export interface Port {
  id: string;
  name: string;
  country: string;
  lat: number;
  lng: number;
  type: "fishing" | "commercial" | "transshipment";
  tier: 1 | 2 | 3;
  note: string;
}

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
  controls: () => { autoRotate: boolean; autoRotateSpeed: number; object: THREE.Camera };
  scene: () => THREE.Scene;
  camera: () => THREE.Camera;
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
  showTunaHeatmap?: boolean;
  showSeamounts?: boolean;
  onSeamountHover?: (seamount: Seamount | null) => void;
  showPorts?: boolean;
}

export const GlobeView = forwardRef<GlobeHandle, Props>(function GlobeView(
  { ships, selected, onSelect, onGlobeClick, pinCoord, isPicking, showSharkHeatmap, showTunaHeatmap, showSeamounts, onSeamountHover, showPorts },
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
        // U = (lng + 90)/360 (mod 1) aligns canvas-on-default-sphere with the
        // earth texture, which three-globe rotates -π/2 around Y (see
        // node_modules/three-globe/dist/three-globe.js:8149).
        const px = (((pt.lng + 90) + 360) % 360) / 360 * W;
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

  // ── Atlantic Bluefin Tuna heatmap (real ABFT presence data) ─────────
  const tunaQ = useQuery({
    queryKey: ["tunaHeatmap"],
    queryFn: async () => {
      const res = await fetch("/tuna-heatmap.json");
      if (!res.ok) throw new Error("Failed to load tuna data");
      return res.json() as Promise<SharkPoint[]>;
    },
    enabled: !!showTunaHeatmap,
  });

  useEffect(() => {
    if (!globeRef.current) return;
    const scene = globeRef.current.scene();

    const removeExisting = () => {
      const old = scene.getObjectByName("tuna-heatmap-overlay");
      if (old) {
        scene.remove(old);
        (old as THREE.Mesh).geometry.dispose();
        ((old as THREE.Mesh).material as THREE.MeshBasicMaterial).map?.dispose();
        ((old as THREE.Mesh).material as THREE.MeshBasicMaterial).dispose();
      }
    };

    removeExisting();
    if (!showTunaHeatmap || !tunaQ.data?.length) return;

    let cancelled = false;

    void whenLandMaskReady().then(() => {
      if (cancelled) return;

      // Drop low-confidence cells and any presence point that snapped onto land.
      const oceanPts = tunaQ.data!.filter((p) => p.weight > 0.04 && !isLand(p.lat, p.lng));

      const W = 4096;
      const H = 2048;
      const canvas = document.createElement("canvas");
      canvas.width = W;
      canvas.height = H;
      const ctx = canvas.getContext("2d")!;
      ctx.globalCompositeOperation = "lighter";

      // U = (lng + 90)/360 (mod 1) aligns canvas-on-default-sphere with the
      // earth texture, which three-globe rotates -π/2 around Y.
      const toU = (lng: number) => (((lng + 90) + 360) % 360) / 360;

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
        const px = toU(pt.lng) * W;
        const py = ((90 - pt.lat) / 180) * H;
        const r = 26 + pt.weight * 38;
        const peak = 0.10 + pt.weight * 0.42;
        const grad = ctx.createRadialGradient(px, py, 0, px, py, r);
        for (const [t, k] of GAUSS_STOPS) {
          // Cyan-blue palette to match the bluefin tuna theme.
          grad.addColorStop(t, `rgba(80, 195, 255, ${(peak * k).toFixed(3)})`);
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
      const geom = new THREE.SphereGeometry(GLOBE_R * 1.004, 128, 64);
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
      mesh.name = "tuna-heatmap-overlay";
      mesh.renderOrder = 2;
      scene.add(mesh);
    });

    return () => {
      cancelled = true;
      removeExisting();
    };
  }, [showTunaHeatmap, tunaQ.data]);

  // ── Seamount 3D bathymetry overlay ──────────────────────────────────
  const seamountsQ = useQuery({
    queryKey: ["seamounts"],
    queryFn: async () => {
      const res = await fetch("/seamounts.json");
      if (!res.ok) throw new Error("Failed to load seamount data");
      return res.json() as Promise<Seamount[]>;
    },
    enabled: !!showSeamounts,
  });

  const onSeamountHoverRef = useRef(onSeamountHover);
  onSeamountHoverRef.current = onSeamountHover;

  useEffect(() => {
    if (!globeRef.current) return;
    const scene = globeRef.current.scene();
    const groupName = "seamounts-overlay";

    const removeExisting = () => {
      const old = scene.getObjectByName(groupName);
      if (!old) return;
      scene.remove(old);
      old.traverse((obj: THREE.Object3D) => {
        if (obj instanceof THREE.Mesh) {
          (obj.geometry as THREE.BufferGeometry).dispose();
          const m = obj.material as THREE.Material | THREE.Material[];
          if (Array.isArray(m)) m.forEach((mm) => mm.dispose());
          else m.dispose();
        }
      });
    };

    removeExisting();
    if (!showSeamounts || !seamountsQ.data?.length) return;

    const GLOBE_R = 100;
    const Y_UP = new THREE.Vector3(0, 1, 0);

    // Match three-globe's convention so seamounts align with the rotated
    // earth texture. (three-globe.js: polar2Cartesian uses theta = 90 - lng,
    // x = r·sin(phi)·cos(theta) — note the +x sign, not -x.)
    const polar2Cartesian = (lat: number, lng: number, alt = 0) => {
      const phi = ((90 - lat) * Math.PI) / 180;
      const theta = ((90 - lng) * Math.PI) / 180;
      const r = GLOBE_R * (1 + alt);
      const sinPhi = Math.sin(phi);
      return new THREE.Vector3(
        r * sinPhi * Math.cos(theta),
        r * Math.cos(phi),
        r * sinPhi * Math.sin(theta),
      );
    };

    const group = new THREE.Group();
    group.name = groupName;

    for (const sm of seamountsQ.data) {
      const basePos = polar2Cartesian(sm.lat, sm.lng, 0);
      const normal = basePos.clone().normalize();

      // Real prominence in km, exaggerated for visibility (1 unit ≈ 64 km).
      const prominenceKm = (sm.base_depth_m - sm.summit_depth_m) / 1000;
      const heightScene = 2.4 + Math.min(5, prominenceKm) * 0.95;
      const radiusScene = Math.max(0.55, Math.min(2.4, sm.radius_km / 35));

      // ── Mountain body: cone with vertex-color gradient ───────────
      const coneGeom = new THREE.ConeGeometry(radiusScene, heightScene, 28, 6, false);
      const baseColor = new THREE.Color(0x0a2540);
      const midColor = new THREE.Color(0x2b6f8a);
      const peakColor = new THREE.Color().setHSL(
        0.045 - sm.fishing_pressure * 0.045,
        0.92,
        0.42 + sm.fishing_pressure * 0.18,
      );

      const colors: number[] = [];
      const pos = coneGeom.attributes.position;
      for (let i = 0; i < pos.count; i++) {
        const py = pos.getY(i);
        const t = (py + heightScene / 2) / heightScene;
        const c =
          t < 0.55
            ? baseColor.clone().lerp(midColor, t / 0.55)
            : midColor.clone().lerp(peakColor, (t - 0.55) / 0.45);
        colors.push(c.r, c.g, c.b);
      }
      coneGeom.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));

      const coneMat = new THREE.MeshBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.93,
        depthWrite: true,
        polygonOffset: true,
        polygonOffsetFactor: -1,
        polygonOffsetUnits: -1,
      });
      const cone = new THREE.Mesh(coneGeom, coneMat);
      cone.quaternion.copy(new THREE.Quaternion().setFromUnitVectors(Y_UP, normal));
      cone.position.copy(basePos.clone().add(normal.clone().multiplyScalar(heightScene / 2)));
      cone.userData.seamount = sm;
      cone.name = `seamount-cone-${sm.id}`;
      group.add(cone);

      const peakPos = basePos.clone().add(normal.clone().multiplyScalar(heightScene + 0.05));

      // ── Trawl-pressure halo ring at peak (pulses) ────────────────
      const haloOuter = radiusScene * (1.55 + sm.fishing_pressure * 1.4);
      const haloGeom = new THREE.RingGeometry(radiusScene * 0.12, haloOuter, 64);
      const haloMat = new THREE.MeshBasicMaterial({
        color: peakColor,
        transparent: true,
        opacity: 0.32 + sm.fishing_pressure * 0.45,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const halo = new THREE.Mesh(haloGeom, haloMat);
      halo.position.copy(peakPos);
      halo.lookAt(0, 0, 0);
      halo.userData.basePulseOpacity = haloMat.opacity;
      halo.userData.fishingPressure = sm.fishing_pressure;
      halo.name = `seamount-halo-${sm.id}`;
      group.add(halo);

      // ── Solid peak disc (fishing concentration) ──────────────────
      const discGeom = new THREE.CircleGeometry(radiusScene * 0.62, 36);
      const discMat = new THREE.MeshBasicMaterial({
        color: peakColor,
        transparent: true,
        opacity: 0.55 + sm.fishing_pressure * 0.32,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const disc = new THREE.Mesh(discGeom, discMat);
      disc.position.copy(peakPos);
      disc.lookAt(0, 0, 0);
      group.add(disc);
    }

    scene.add(group);

    // Pulse animation — speed scales with fishing pressure.
    let raf = 0;
    let cancelled = false;
    const start = performance.now();
    const tick = () => {
      if (cancelled) return;
      const t = (performance.now() - start) / 1000;
      group.traverse((obj: THREE.Object3D) => {
        if (obj instanceof THREE.Mesh && obj.name.startsWith("seamount-halo-")) {
          const mat = obj.material as THREE.MeshBasicMaterial;
          const base = (obj.userData.basePulseOpacity as number) ?? 0.5;
          const pressure = (obj.userData.fishingPressure as number) ?? 0.5;
          const speed = 1.1 + pressure * 1.6;
          const pulse = 0.5 + 0.5 * Math.sin(t * speed);
          mat.opacity = base * (0.55 + pulse * 0.55);
        }
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      removeExisting();
    };
  }, [showSeamounts, seamountsQ.data]);

  // Hover detection — raycast against seamount cones for activist tooltip.
  useEffect(() => {
    if (!showSeamounts || !containerRef.current || !globeRef.current) return;
    const el = containerRef.current;
    const globe = globeRef.current;
    const scene = globe.scene();
    const raycaster = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    let lastId: string | null = null;

    const getCamera = (): THREE.Camera | null => {
      try {
        if (typeof globe.camera === "function") return globe.camera();
      } catch {/* ignore */}
      try {
        const c = globe.controls();
        if (c && (c as { object?: THREE.Camera }).object) return (c as { object: THREE.Camera }).object;
      } catch {/* ignore */}
      return null;
    };

    const onMove = (ev: MouseEvent) => {
      const rect = el.getBoundingClientRect();
      ndc.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      ndc.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;

      const cam = getCamera();
      if (!cam) return;
      const group = scene.getObjectByName("seamounts-overlay");
      if (!group) return;
      const cones: THREE.Object3D[] = [];
      group.traverse((o: THREE.Object3D) => {
        if (o instanceof THREE.Mesh && o.name.startsWith("seamount-cone-")) cones.push(o);
      });
      raycaster.setFromCamera(ndc, cam);
      const hit = raycaster.intersectObjects(cones, false)[0]?.object as THREE.Mesh | undefined;
      const sm = (hit?.userData?.seamount as Seamount | undefined) ?? null;
      const id = sm?.id ?? null;
      if (id !== lastId) {
        lastId = id;
        onSeamountHoverRef.current?.(sm);
      }
    };

    el.addEventListener("mousemove", onMove);
    return () => {
      el.removeEventListener("mousemove", onMove);
      onSeamountHoverRef.current?.(null);
    };
  }, [showSeamounts]);

  // ── Major fishing & commercial ports ────────────────────────────────
  const portsQ = useQuery({
    queryKey: ["ports"],
    queryFn: async () => {
      const res = await fetch("/ports.json");
      if (!res.ok) throw new Error("Failed to load ports data");
      return res.json() as Promise<Port[]>;
    },
    enabled: !!showPorts,
  });

  useEffect(() => {
    if (!globeRef.current) return;
    const scene = globeRef.current.scene();
    const groupName = "ports-overlay";

    const removeExisting = () => {
      const old = scene.getObjectByName(groupName);
      if (!old) return;
      scene.remove(old);
      old.traverse((obj: THREE.Object3D) => {
        if (obj instanceof THREE.Mesh) {
          (obj.geometry as THREE.BufferGeometry).dispose();
          const m = obj.material as THREE.Material | THREE.Material[];
          if (Array.isArray(m)) m.forEach((mm) => mm.dispose());
          else m.dispose();
        }
      });
    };

    removeExisting();
    if (!showPorts || !portsQ.data?.length) return;

    const GLOBE_R = 100;

    // Same convention as the seamount layer; matches three-globe's polar2Cartesian
    // so port markers sit on the visible coastline of the rotated earth texture.
    const polar2Cartesian = (lat: number, lng: number, alt = 0) => {
      const phi = ((90 - lat) * Math.PI) / 180;
      const theta = ((90 - lng) * Math.PI) / 180;
      const r = GLOBE_R * (1 + alt);
      const sinPhi = Math.sin(phi);
      return new THREE.Vector3(
        r * sinPhi * Math.cos(theta),
        r * Math.cos(phi),
        r * sinPhi * Math.sin(theta),
      );
    };

    const TYPE_COLOR: Record<Port["type"], number> = {
      fishing: 0xfbbf24,        // amber
      commercial: 0x38bdf8,     // sky-blue
      transshipment: 0xf472b6,  // pink — stands out for the IUU/transshipment story
    };

    const group = new THREE.Group();
    group.name = groupName;

    for (const p of portsQ.data) {
      // Lift slightly off the surface so dots aren't hidden by atmosphere/heatmap meshes.
      const pos = polar2Cartesian(p.lat, p.lng, 0.012);
      const normal = pos.clone().normalize();
      const color = new THREE.Color(TYPE_COLOR[p.type] ?? 0xfbbf24);

      // Tier scales the marker radius (1→0.45, 2→0.65, 3→0.95 scene units).
      const tier = Math.max(1, Math.min(3, p.tier ?? 1));
      const dotR = 0.30 + tier * 0.18;

      // Solid dot
      const dotGeom = new THREE.SphereGeometry(dotR, 12, 10);
      const dotMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.95,
      });
      const dot = new THREE.Mesh(dotGeom, dotMat);
      dot.position.copy(pos);
      dot.userData.port = p;
      dot.name = `port-dot-${p.id}`;
      group.add(dot);

      // Glow halo (additive ring facing the camera direction along surface normal)
      const haloGeom = new THREE.RingGeometry(dotR * 1.3, dotR * 2.6, 32);
      const haloMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.18 + tier * 0.07,
        side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const halo = new THREE.Mesh(haloGeom, haloMat);
      halo.position.copy(pos.clone().add(normal.clone().multiplyScalar(0.05)));
      halo.lookAt(0, 0, 0);
      group.add(halo);
    }

    scene.add(group);

    return () => {
      removeExisting();
    };
  }, [showPorts, portsQ.data]);

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

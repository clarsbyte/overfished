/**
 * useFlightPathLayer — mounts Curves + PlanesShader onto a react-globe.gl
 * globe and drives them with a RAF loop.
 *
 * Pattern: react-globe.gl exposes its internal Three.js scene via
 * `globeRef.current.scene()`. We add our merged-LineSegments curves mesh
 * and our InstancedMesh of vessel sprites as children of that scene, so
 * they render on the same canvas as the globe and respect the globe's
 * camera + transforms.
 *
 * Animation: the PlanesShader runs all per-vessel position/rotation math
 * in the GPU vertex shader. The CPU only increments one `time` uniform
 * per frame. Curves are STATIC after `setCurve`, so we don't touch them
 * during the RAF loop.
 *
 * Caller passes a list of `Route` records (lat/lng pairs + style hints).
 * We convert each to a parabolic 4-point control set via
 * `generateParabolicControlPoints` + `normalizeControlPoints`, then push
 * the same control points into both `Curves` (for the path line) and
 * `PlanesShader` (for the vessel quad).
 */

import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { GlobeMethods } from "react-globe.gl";
import { Curves } from "./Curves";
import {
  generateMultiLegParabolicControlPoints,
  normalizeControlPoints,
  type LatLng,
} from "./geometry";
import { loadVesselTexture } from "./loadVesselTexture";
import { PlanesShader, type TiltMode } from "./PlanesShader";

export interface Route {
  /** Full ordered sequence of waypoints (start, intermediates, end). */
  waypoints: LatLng[];
  /** Curve gradient endpoint colors. */
  curveColorStart: THREE.ColorRepresentation;
  curveColorEnd: THREE.ColorRepresentation;
  /** Vessel sprite tint. */
  vesselColor: THREE.ColorRepresentation;
}

export interface FlightPathLayerOptions {
  routes: Route[];
  /** Show the vessel quads (instanced billboards). */
  showVessels: boolean;
  /** Show the parabolic path lines. */
  showPaths: boolean;
  /** Per-vessel sprite size (in three-globe world units). */
  vesselSize: number;
  /** Per-vessel travel speed multiplier. Higher = faster cycle. */
  animationSpeed: number;
  /** Tilt mode: Perpendicular (vessel facing forward) or Tangent (lying flat). */
  tiltMode: TiltMode;
  /** Dash length on path lines (0 = solid). */
  dashSize: number;
  /** Gap between dashes on path lines. */
  gapSize: number;
  /** Lift the vessel quad above the curve by this much (world units). */
  vesselElevation: number;
  /** Apex altitude of the parabolic arc for short hops (world units). */
  arcMinAltitude: number;
  /** Apex altitude of the parabolic arc for long-distance routes. */
  arcMaxAltitude: number;
}

const MAX_ROUTES = 500; // hard cap; pre-allocates buffers in PlanesShader/Curves

interface LayerHandle {
  curves: Curves;
  planes: PlanesShader;
}

/**
 * Mount the layer onto the react-globe.gl globe. Returns nothing — the
 * caller controls everything via `options` props that re-trigger the hook.
 */
export function useFlightPathLayer(
  globeRef: React.MutableRefObject<GlobeMethods | undefined>,
  options: FlightPathLayerOptions,
): void {
  const handleRef = useRef<LayerHandle | null>(null);
  const lastFrameRef = useRef<number>(performance.now());
  const rafRef = useRef<number>(0);

  // ── One-time mount: create Curves + PlanesShader on the globe's scene.
  useEffect(() => {
    const globe = globeRef.current;
    if (!globe) return;
    const scene = globe.scene();

    const curves = new Curves(scene, {
      maxCurves: MAX_ROUTES,
      segmentsPerCurve: 80,
      dashSize: options.dashSize,
      gapSize: options.gapSize,
    });

    const planes = new PlanesShader(scene, {
      maxPanes: MAX_ROUTES,
      baseSize: 1,
      baseElevation: options.vesselElevation,
    });

    handleRef.current = { curves, planes };

    // Kick off the texture load — vessel quads are invisible (white tint
    // multiplied with texture) until this resolves.
    void loadVesselTexture()
      .then((tex) => {
        const mat = (planes as any).material as THREE.ShaderMaterial | null;
        if (!mat?.uniforms) return;
        mat.uniforms.paneMap.value = tex;
        mat.uniforms.useTexture.value = 1.0;
        mat.needsUpdate = true;
      })
      .catch((err) => {
        console.warn("vessel texture load failed; falling back to flat color", err);
      });

    // RAF loop: only the PlanesShader needs per-frame work (uTime increment).
    const tick = () => {
      const now = performance.now();
      const dt = (now - lastFrameRef.current) / 1000;
      lastFrameRef.current = now;
      planes.update(dt);
      curves.applyUpdates();
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafRef.current);
      curves.remove();
      planes.remove();
      handleRef.current = null;
    };
    // Deliberately mount once. Subsequent prop changes are handled by the
    // other effects below — re-creating the InstancedMesh on every prop
    // change would kill the perf benefit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [globeRef]);

  // ── Routes: rebuild curves + control points whenever the route list
  //    changes. This is the expensive operation, but it only runs when
  //    the input identity actually changes (caller is responsible for
  //    memoizing).
  useEffect(() => {
    const h = handleRef.current;
    if (!h) return;

    // Hide every slot first so old routes vanish.
    for (let i = 0; i < MAX_ROUTES; i++) {
      h.curves.hideCurve(i);
      h.planes.hidePane(i);
    }

    options.routes.slice(0, MAX_ROUTES).forEach((route, i) => {
      const raw = generateMultiLegParabolicControlPoints(route.waypoints, {
        minCruiseAltitude: options.arcMinAltitude,
        maxCruiseAltitude: options.arcMaxAltitude,
      });
      const normalized = normalizeControlPoints(raw);
      if (normalized.length < 4) return;

      h.curves.setCurve(i, normalized, {
        start: new THREE.Color(route.curveColorStart),
        end: new THREE.Color(route.curveColorEnd),
      });

      h.planes.setCurveControlPoints(i, normalized);
      h.planes.setPaneColor(i, route.vesselColor);
      h.planes.setPaneSize(i, options.vesselSize);
      h.planes.setElevationOffset(i, options.vesselElevation);
      h.planes.setAnimationSpeed(i, options.animationSpeed);
      h.planes.setTiltMode(i, options.tiltMode);
    });

    h.curves.applyUpdates();
    // intentionally not depending on options.vesselSize/animationSpeed/etc;
    // those have their own effects below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.routes, options.arcMinAltitude, options.arcMaxAltitude]);

  // ── Cheap prop changes: tweak attributes in place, no rebuild.
  useEffect(() => {
    const h = handleRef.current;
    if (!h) return;
    for (let i = 0; i < options.routes.length && i < MAX_ROUTES; i++) {
      h.planes.setPaneSize(i, options.vesselSize);
      h.planes.setElevationOffset(i, options.vesselElevation);
      h.planes.setAnimationSpeed(i, options.animationSpeed);
      h.planes.setTiltMode(i, options.tiltMode);
    }
  }, [
    options.vesselSize,
    options.vesselElevation,
    options.animationSpeed,
    options.tiltMode,
    options.routes,
  ]);

  useEffect(() => {
    const h = handleRef.current;
    if (!h) return;
    h.planes.setPlanesVisible(options.showVessels);
  }, [options.showVessels]);

  useEffect(() => {
    const h = handleRef.current;
    if (!h) return;
    h.curves.setVisible(options.showPaths);
  }, [options.showPaths]);

  useEffect(() => {
    const h = handleRef.current;
    if (!h) return;
    h.curves.setDashPattern(options.dashSize, options.gapSize);
  }, [options.dashSize, options.gapSize]);
}

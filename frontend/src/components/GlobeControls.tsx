/**
 * Leva-backed live controls for the globe.
 *
 * Mirrors the dat.GUI panel from jeantimex/flight-path's "Interactive
 * Controls" section: flight count, dash length/gap/speed, show toggles,
 * vessel scale, arc opacity. Returns a single typed object consumed by
 * <OverfishGlobe/>; the leva panel itself is mounted globally in
 * frontend/src/main.tsx via <Leva collapsed={false} />.
 */

import { useControls } from "leva";

/**
 * Live-tunable controls for the globe — mirrors flight-path's dat.GUI panel.
 *
 * Three groups:
 *   - Flight paths: count, path dash pattern, path visibility.
 *   - Vessels: count is the same (one vessel per path), size, animation
 *     speed, elevation, tilt mode, visibility.
 *   - Globe overlays: legacy controls retained for the heatmap/arc layers
 *     we still render alongside the flight-path layer.
 */
export interface GlobeControlsState {
  // ─ Flight-path controls (the new InstancedMesh layer)
  flightCount: number;
  dashSize: number;
  gapSize: number;
  arcMinAltitude: number;
  arcMaxAltitude: number;
  showPaths: boolean;
  showVessels: boolean;
  vesselSize: number;
  animationSpeed: number;
  vesselElevation: number;
  tiltMode: "Perpendicular" | "Tangent";
  // ─ Legacy globe overlays (still in OverfishGlobe.tsx)
  showHeatmap: boolean;
}

export function useGlobeControls(): GlobeControlsState {
  // Mirror flight-path's "Flight Controls" group, renamed for vessels.
  // The state key stays `flightCount` (no other call sites need updating);
  // only the user-facing label changes.
  const flightControls = useControls(
    "Vessel traffic",
    {
      flightCount: { value: 250, min: 0, max: 500, step: 5, label: "Vessel count" },
    },
    { collapsed: false },
  );

  // Mirror flight-path's "Flight Path" group (dash + arc altitude). Altitudes
  // are in three-globe world units; globe radius is 100, so altitude=10 means
  // the arc apex sits 10% of the radius above the surface. Ships fly lower
  // than planes, so defaults are well under flight-path's own (which were 28).
  const pathControls = useControls(
    "Flight path",
    {
      dashSize: { value: 1.0, min: 0, max: 4, step: 0.05, label: "Dash size" },
      gapSize: { value: 0.4, min: 0, max: 4, step: 0.05, label: "Dash gap" },
      arcMinAltitude: {
        // Min 2.0 matches the geometry's hard `minCurveAltitude` floor —
        // values below that get clamped up internally anyway, so the
        // slider would lie. 2.5 default for a gentle visible arc.
        value: 2.5,
        min: 2,
        max: 20,
        step: 0.1,
        label: "Arc min alt",
      },
      arcMaxAltitude: {
        value: 9,
        min: 3,
        max: 30,
        step: 0.5,
        label: "Arc max alt",
      },
      showPaths: { value: true, label: "Show paths" },
    },
    { collapsed: false },
  );

  // Mirror flight-path's "Plane Controls" group, renamed for vessels.
  const vesselControls = useControls(
    "Vessel controls",
    {
      vesselSize: {
        value: 1.6,
        min: 0.5,
        max: 6,
        step: 0.05,
        label: "Vessel size",
      },
      animationSpeed: {
        value: 0.05,
        min: 0.005,
        max: 0.3,
        step: 0.005,
        label: "Fly speed",
      },
      vesselElevation: {
        // Min 0.5 so vessels stay above the surface even on the
        // lowest-altitude curves. Default 0.8 lifts them just slightly
        // off the path so they read as "on the water" not "embedded in it".
        value: 0.8,
        min: 0.5,
        max: 6,
        step: 0.05,
        label: "Elevation",
      },
      tiltMode: {
        value: "Perpendicular" as "Perpendicular" | "Tangent",
        options: ["Perpendicular", "Tangent"] as const,
        label: "Tilt mode",
      },
      showVessels: { value: true, label: "Show vessels" },
    },
    { collapsed: false },
  );

  const overlayControls = useControls(
    "Globe overlays",
    {
      showHeatmap: { value: true, label: "Show heatmap" },
    },
    { collapsed: true },
  );

  return {
    ...flightControls,
    ...pathControls,
    ...vesselControls,
    ...overlayControls,
  } as GlobeControlsState;
}

/**
 * Geometry helpers — lat/lng → world space + parabolic curve generation.
 *
 * The lat/lng convention is the one three-globe (and react-globe.gl) uses
 * internally:
 *   phi   = (90 - lat) * π/180
 *   theta = (90 - lng) * π/180
 *   r     = GLOBE_RADIUS * (1 + altitude)
 *
 * The flight-path repo's `latLngToVector3` used a different rotation; we
 * substitute three-globe's so the InstancedMesh we add as a child of
 * `globeRef.current.scene()` lines up with the rendered globe.
 *
 * `generateParabolicControlPoints` is a near-verbatim port of
 * `flight-path-study/src/flights/FlightUtils.ts:154-289` — it lifts the
 * great-circle path off the sphere into a parabolic arc, then samples 9
 * control points along it. We then call `normalizeControlPoints` to reduce
 * to the 4 evenly-spaced points the GPU shader expects.
 */

import * as THREE from "three";

/** Matches three-globe's internal GLOBE_RADIUS constant. */
export const GLOBE_RADIUS = 100;

export interface LatLng {
  lat: number;
  lng: number;
}

/**
 * Convert lat/lng to a 3D position in three-globe's coordinate space.
 * Use this for any point we want to align with the rendered globe.
 */
export function latLngToVector3(
  lat: number,
  lng: number,
  altitudeRel: number = 0,
): THREE.Vector3 {
  const phi = ((90 - lat) * Math.PI) / 180;
  const theta = ((90 - lng) * Math.PI) / 180;
  const r = GLOBE_RADIUS * (1 + altitudeRel);
  const phiSin = Math.sin(phi);
  return new THREE.Vector3(
    r * phiSin * Math.cos(theta),
    r * Math.cos(phi),
    r * phiSin * Math.sin(theta),
  );
}

/** Snap any control point that's dipped under the surface back above it. */
function ensureMinAltitude(
  points: THREE.Vector3[],
  radius: number,
  minAltitude: number,
): THREE.Vector3[] {
  const safe = radius + minAltitude;
  return points.map((p) => {
    const len = p.length();
    if (len > 0 && len < safe) {
      return p.clone().normalize().multiplyScalar(safe);
    }
    return p.clone();
  });
}

/**
 * Generate 9 parabolic control points lifting the path off the sphere.
 * Port of `FlightUtils.generateParabolicControlPoints`.
 */
export function generateParabolicControlPoints(
  departure: LatLng,
  arrival: LatLng,
  options: {
    radius?: number;
    takeoffOffset?: number;
    minCurveAltitude?: number;
    minCruiseAltitude?: number;
    maxCruiseAltitude?: number;
  } = {},
): THREE.Vector3[] {
  const radius = options.radius ?? GLOBE_RADIUS;
  // Bumped from 0.5 / 1.0 — earlier defaults were too close to the surface
  // and CatmullRom interpolation between adjacent control points could dip
  // below the sphere. The 2.0 floor keeps every control point clearly
  // above water.
  const takeoffOffset = options.takeoffOffset ?? 1.5;
  const minCurveAltitude = options.minCurveAltitude ?? 2;
  const minCruiseAltitude = options.minCruiseAltitude ?? 6;
  const maxCruiseAltitude = options.maxCruiseAltitude ?? 28;

  const surfaceOffset = Math.max(takeoffOffset, minCurveAltitude);
  const cruiseMin = Math.max(minCruiseAltitude, surfaceOffset + 0.5);

  const origin = latLngToVector3(departure.lat, departure.lng).normalize();
  const dest = latLngToVector3(arrival.lat, arrival.lng).normalize();

  const startSurface = origin.clone().multiplyScalar(radius + surfaceOffset);
  const endSurface = dest.clone().multiplyScalar(radius + surfaceOffset);

  const distance = startSurface.distanceTo(endSurface);
  const maxDistance = radius * Math.PI;
  const distanceRatio = Math.min(distance / (maxDistance * 0.3), 1);
  const cruiseAltitude =
    cruiseMin + (maxCruiseAltitude - cruiseMin) * Math.pow(distanceRatio, 0.7);

  const liftAt = (t: number, fraction: number): THREE.Vector3 =>
    startSurface
      .clone()
      .lerp(endSurface, t)
      .normalize()
      .multiplyScalar(radius + cruiseAltitude * fraction);

  const climbPoint1 = liftAt(0.2, 0.4);
  const climbPoint2 = liftAt(0.35, 0.75);
  const cruisePeak = liftAt(0.5, 0.85);
  const descentPoint1 = liftAt(0.65, 0.75);
  const descentPoint2 = liftAt(0.8, 0.4);

  // Tangent points keep the start/end smooth (avoid kinks at the surface).
  const startNormal = startSurface.clone().normalize();
  let pathDirStart = endSurface.clone().sub(startSurface);
  if (pathDirStart.lengthSq() < 1e-6) pathDirStart = new THREE.Vector3().randomDirection();
  let tangentStart = pathDirStart
    .clone()
    .sub(startNormal.clone().multiplyScalar(pathDirStart.dot(startNormal)));
  if (tangentStart.lengthSq() < 1e-6) {
    tangentStart = new THREE.Vector3().crossVectors(startNormal, new THREE.Vector3(0, 1, 0));
    if (tangentStart.lengthSq() < 1e-6) tangentStart = new THREE.Vector3(1, 0, 0);
  }
  tangentStart.normalize();
  const tangentDistance = radius * 0.08;
  const surfaceLength = startSurface.length();
  const startTangentPoint = startSurface
    .clone()
    .add(tangentStart.clone().multiplyScalar(tangentDistance))
    .normalize()
    .multiplyScalar(surfaceLength);

  const endNormal = endSurface.clone().normalize();
  let pathDirEnd = startSurface.clone().sub(endSurface);
  if (pathDirEnd.lengthSq() < 1e-6) pathDirEnd = new THREE.Vector3().randomDirection();
  let tangentEnd = pathDirEnd
    .clone()
    .sub(endNormal.clone().multiplyScalar(pathDirEnd.dot(endNormal)));
  if (tangentEnd.lengthSq() < 1e-6) {
    tangentEnd = new THREE.Vector3().crossVectors(endNormal, new THREE.Vector3(0, 1, 0));
    if (tangentEnd.lengthSq() < 1e-6) tangentEnd = new THREE.Vector3(1, 0, 0);
  }
  tangentEnd.normalize();
  const endSurfaceLength = endSurface.length();
  const endTangentPoint = endSurface
    .clone()
    .add(tangentEnd.clone().multiplyScalar(tangentDistance))
    .normalize()
    .multiplyScalar(endSurfaceLength);

  const controlPoints = [
    startSurface,
    startTangentPoint,
    climbPoint1,
    climbPoint2,
    cruisePeak,
    descentPoint1,
    descentPoint2,
    endTangentPoint,
    endSurface,
  ];
  return ensureMinAltitude(controlPoints, radius, minCurveAltitude);
}

/**
 * Multi-leg variant of `generateParabolicControlPoints`. Takes a list of
 * waypoints (start, intermediates, end) and produces a single smooth
 * parabolic arc passing through every waypoint.
 *
 * Strategy: lift each waypoint to a per-point altitude that ramps up to
 * the cruise apex at the path midpoint and back down. The resulting
 * sequence is fed to CatmullRom (in `Curves.setCurve` and the GPU
 * shader's `evaluateCatmullRom`) which smoothly interpolates between
 * them. One continuous arc, no per-leg "lift off / land" pumps.
 *
 * The cruise altitude scales with the total along-path great-circle
 * distance, matching the single-leg behavior, so a 5-waypoint route
 * through Cape Horn isn't visually flatter than a 0-waypoint trans-Atlantic.
 */
export function generateMultiLegParabolicControlPoints(
  waypoints: LatLng[],
  options: {
    radius?: number;
    takeoffOffset?: number;
    minCurveAltitude?: number;
    minCruiseAltitude?: number;
    maxCruiseAltitude?: number;
  } = {},
): THREE.Vector3[] {
  if (waypoints.length < 2) return [];
  if (waypoints.length === 2) {
    // Defer to the proven single-leg path.
    return generateParabolicControlPoints(waypoints[0], waypoints[1], options);
  }

  const radius = options.radius ?? GLOBE_RADIUS;
  // Same higher floors as the single-leg variant — see the matching block
  // in `generateParabolicControlPoints` for rationale.
  const takeoffOffset = options.takeoffOffset ?? 1.5;
  const minCurveAltitude = options.minCurveAltitude ?? 2;
  const minCruiseAltitude = options.minCruiseAltitude ?? 6;
  const maxCruiseAltitude = options.maxCruiseAltitude ?? 28;

  const surfaceOffset = Math.max(takeoffOffset, minCurveAltitude);
  const cruiseMin = Math.max(minCruiseAltitude, surfaceOffset + 0.5);

  // Compute total along-path distance (sum of leg distances at the
  // surface-offset radius) so apex altitude scales with path length.
  const surfacePoints = waypoints.map((wp) =>
    latLngToVector3(wp.lat, wp.lng).normalize().multiplyScalar(radius + surfaceOffset),
  );
  let totalDistance = 0;
  for (let i = 0; i < surfacePoints.length - 1; i++) {
    totalDistance += surfacePoints[i].distanceTo(surfacePoints[i + 1]);
  }
  const maxDistance = radius * Math.PI;
  const distanceRatio = Math.min(totalDistance / (maxDistance * 0.3), 1);
  const cruiseAltitude =
    cruiseMin + (maxCruiseAltitude - cruiseMin) * Math.pow(distanceRatio, 0.7);

  // Per-point altitude profile: low at endpoints, peak at middle.
  // The base parabolic envelope `1 - (2t-1)^2` evaluates to 0 at endpoints,
  // which would put endpoints right at `surfaceOffset`. CatmullRom can then
  // overshoot below the surface between an endpoint and an intermediate
  // waypoint. Adding a small constant floor (`ENDPOINT_FLOOR_FRACTION` of
  // the cruise altitude) keeps endpoints visibly above water and gives
  // the spline headroom on either side.
  const ENDPOINT_FLOOR_FRACTION = 0.18;
  const out: THREE.Vector3[] = [];
  const lastIdx = waypoints.length - 1;
  for (let i = 0; i <= lastIdx; i++) {
    const t = i / lastIdx;
    const baseEnvelope = 1 - Math.pow(2 * t - 1, 2); // 0..1..0
    const envelope = ENDPOINT_FLOOR_FRACTION + (1 - ENDPOINT_FLOOR_FRACTION) * baseEnvelope;
    const alt = surfaceOffset + (cruiseAltitude - surfaceOffset) * envelope;
    const wp = waypoints[i];
    const dir = latLngToVector3(wp.lat, wp.lng).normalize();
    out.push(dir.multiplyScalar(radius + alt));
  }

  return ensureMinAltitude(out, radius, minCurveAltitude);
}

/**
 * Reduce N control points down to 4 evenly-spaced samples along the
 * curve. The shader expects exactly 4. Port of
 * `FlightUtils.normalizeControlPoints`.
 */
export function normalizeControlPoints(
  points: THREE.Vector3[],
  radius: number = GLOBE_RADIUS,
  minAltitude: number = 1,
): THREE.Vector3[] {
  if (!points || !points.length) return [];
  if (points.length === 4) return ensureMinAltitude(points, radius, minAltitude);

  const curve = new THREE.CatmullRomCurve3(points);
  const sampled = [
    curve.getPoint(0.0),
    curve.getPoint(0.333),
    curve.getPoint(0.666),
    curve.getPoint(1.0),
  ];
  return ensureMinAltitude(sampled, radius, minAltitude);
}

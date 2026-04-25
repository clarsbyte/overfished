/**
 * Procedural maritime route generator.
 *
 * Inspired by jeantimex/flight-path's `src/Data.js`. Picks random
 * (start, end) pairs from a hand-curated list of port-like coordinates,
 * weighted toward IUU-relevant hotspots so the visual density carries
 * narrative meaning ("the ocean is busy, especially in flagged regions").
 *
 * The generator is deterministic given a fixed seed — important so hot-reload
 * doesn't re-shuffle the route set on every render.
 *
 * Routes whose great-circle path crosses land are rejected via the
 * `landMask` lookup. Caller must `whenLandMaskReady()` before invoking
 * `generateRoutes` — otherwise every check returns "ocean" and we get
 * the old behavior of routes cutting through continents.
 */

import { isLand } from "./landMask";

export type RouteRisk = "confirmed_iuu" | "high_risk" | "suspect" | "safe";

export interface LatLng {
  lat: number;
  lng: number;
}

export interface ProceduralRoute {
  /** First waypoint. Equivalent to the old `startLat`/`startLng`. */
  startLat: number;
  startLng: number;
  /** Last waypoint. Equivalent to the old `endLat`/`endLng`. */
  endLat: number;
  endLng: number;
  /**
   * Full ordered sequence of waypoints, INCLUDING start and end. May
   * have 2+ entries — anything beyond [start, end] is a mid-ocean
   * detour the route bends through. Real shipping lanes don't follow
   * great-circles; multi-waypoint routes give the visual nuance.
   */
  waypoints: LatLng[];
  risk: RouteRisk;
}

interface Hotspot {
  lat: number;
  lng: number;
  name: string;
  risk: RouteRisk;
  /** Sampling weight — IUU regions get extra mass. */
  weight: number;
}

// ~30 maritime hotspots: major commercial ports + IUU-relevant fishery
// hubs. Coordinates are approximate. Risk class informs the rendered
// arc color in the Arcs layer.
const MARITIME_HOTSPOTS: Hotspot[] = [
  // ── IUU hotspots (heavy weight) ─────────────────────────────────────
  { name: "Galápagos Marine Reserve", lat: -0.7533, lng: -90.3689, risk: "confirmed_iuu", weight: 4 },
  { name: "Yellow Sea (East)", lat: 35.5, lng: 123.0, risk: "confirmed_iuu", weight: 4 },
  { name: "Gulf of Guinea", lat: 2.0, lng: 5.0, risk: "high_risk", weight: 3 },
  { name: "Patagonian Shelf", lat: -45.0, lng: -60.0, risk: "high_risk", weight: 3 },
  { name: "Humboldt Current", lat: -15.0, lng: -78.0, risk: "high_risk", weight: 3 },
  { name: "Banda Sea", lat: -5.0, lng: 127.0, risk: "high_risk", weight: 3 },
  { name: "South China Sea", lat: 12.0, lng: 115.0, risk: "high_risk", weight: 3 },
  { name: "Bering Sea", lat: 58.0, lng: -178.0, risk: "suspect", weight: 2 },
  { name: "North Atlantic Cod", lat: 49.0, lng: -50.0, risk: "suspect", weight: 2 },

  // ── Major commercial ports (baseline traffic) ───────────────────────
  { name: "Shanghai", lat: 31.2304, lng: 121.4737, risk: "safe", weight: 2 },
  { name: "Singapore", lat: 1.2655, lng: 103.8186, risk: "safe", weight: 2 },
  { name: "Rotterdam", lat: 51.9244, lng: 4.4777, risk: "safe", weight: 2 },
  { name: "Los Angeles", lat: 33.7406, lng: -118.2706, risk: "safe", weight: 2 },
  { name: "Dubai", lat: 25.0657, lng: 55.1713, risk: "safe", weight: 2 },
  { name: "Hong Kong", lat: 22.3193, lng: 114.1694, risk: "safe", weight: 2 },
  { name: "Busan", lat: 35.1796, lng: 129.0756, risk: "safe", weight: 2 },
  { name: "Tokyo Bay", lat: 35.6, lng: 139.8, risk: "safe", weight: 2 },
  { name: "New York", lat: 40.7, lng: -74.0, risk: "safe", weight: 2 },
  { name: "Hamburg", lat: 53.5511, lng: 9.9937, risk: "safe", weight: 1 },
  { name: "Antwerp", lat: 51.2194, lng: 4.4025, risk: "safe", weight: 1 },
  { name: "Mumbai", lat: 18.95, lng: 72.83, risk: "safe", weight: 2 },
  { name: "Cape Town", lat: -33.9, lng: 18.4, risk: "safe", weight: 1 },
  { name: "Sydney", lat: -33.87, lng: 151.21, risk: "safe", weight: 1 },
  { name: "Vancouver", lat: 49.29, lng: -123.11, risk: "safe", weight: 1 },
  { name: "Manta", lat: -0.95, lng: -80.73, risk: "safe", weight: 1 },
  { name: "Callao", lat: -12.05, lng: -77.14, risk: "safe", weight: 1 },
  { name: "Reykjavik", lat: 64.13, lng: -21.94, risk: "safe", weight: 1 },
  { name: "Murmansk", lat: 68.97, lng: 33.08, risk: "suspect", weight: 1 },
  { name: "Lagos", lat: 6.45, lng: 3.4, risk: "suspect", weight: 1 },
  { name: "Buenos Aires", lat: -34.6, lng: -58.4, risk: "safe", weight: 1 },
];

const RISK_PRIORITY: Record<RouteRisk, number> = {
  confirmed_iuu: 4,
  high_risk: 3,
  suspect: 2,
  safe: 1,
};

// Mid-ocean waypoints: hand-curated lat/lng nodes in deep open water.
// Routes bend through 0-5 of these to get a more nuanced shipping-lane
// look (instead of a perfectly straight great-circle). Picked so that
// all sit reliably in ocean cells of the 110m land mask, including
// near-cape passages and known shipping-lane bottlenecks.
const MID_OCEAN_WAYPOINTS: LatLng[] = [
  // ── Deep-water mid-basin pivots ─────────────────────────────────────
  { lat: 0, lng: -25 },     // mid-Atlantic equatorial
  { lat: 30, lng: -40 },    // North Atlantic mid
  { lat: -30, lng: -25 },   // South Atlantic mid
  { lat: 0, lng: -150 },    // mid-Pacific equatorial
  { lat: 30, lng: -150 },   // North Pacific mid
  { lat: -30, lng: -130 },  // South Pacific mid
  { lat: 0, lng: 75 },      // central Indian Ocean
  { lat: -30, lng: 75 },    // South Indian Ocean
  // ── Shipping-lane chokepoint approaches ────────────────────────────
  { lat: -36, lng: 20 },    // Cape of Good Hope passage
  { lat: -56, lng: -65 },   // Cape Horn / Drake Passage approach
  { lat: 36, lng: -10 },    // Strait of Gibraltar approach (Atlantic side)
  { lat: 13, lng: 55 },     // Gulf of Aden / Bab-el-Mandeb approach
  { lat: 5, lng: 100 },     // Strait of Malacca approach
  { lat: 50, lng: -170 },   // Bering / North Pacific great-circle pivot
];

/**
 * Tiny deterministic PRNG (Mulberry32). Good enough for shuffle work,
 * keeps the route set stable across hot reloads when the seed is fixed.
 */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Build a weighted-sampling table once at module load. */
const WEIGHTED_HOTSPOTS: Hotspot[] = (() => {
  const out: Hotspot[] = [];
  for (const h of MARITIME_HOTSPOTS) {
    for (let i = 0; i < h.weight; i++) out.push(h);
  }
  return out;
})();

/**
 * Walk the great-circle path between two lat/lng points and return true
 * if any sample lands on a continent. Uses spherical-linear interpolation
 * (slerp) on the unit sphere so points stay on the actual great-circle,
 * not on the lat/lng-grid lerp that would distort near the poles.
 */
function crossesLand(
  aLat: number,
  aLng: number,
  bLat: number,
  bLng: number,
  samples = 32,
): boolean {
  // Convert lat/lng to unit-vector positions.
  const toRad = (d: number) => (d * Math.PI) / 180;
  const toLat = (v: { x: number; y: number; z: number }) =>
    (Math.asin(v.z) * 180) / Math.PI;
  const toLng = (v: { x: number; y: number; z: number }) =>
    (Math.atan2(v.y, v.x) * 180) / Math.PI;

  const aPhi = toRad(aLat);
  const aLam = toRad(aLng);
  const bPhi = toRad(bLat);
  const bLam = toRad(bLng);

  const ax = Math.cos(aPhi) * Math.cos(aLam);
  const ay = Math.cos(aPhi) * Math.sin(aLam);
  const az = Math.sin(aPhi);
  const bx = Math.cos(bPhi) * Math.cos(bLam);
  const by = Math.cos(bPhi) * Math.sin(bLam);
  const bz = Math.sin(bPhi);

  const dot = Math.max(-1, Math.min(1, ax * bx + ay * by + az * bz));
  const omega = Math.acos(dot);
  if (omega < 1e-6) return false; // identical / antipodal-ish: nothing to check
  const sinOm = Math.sin(omega);

  // Skip the endpoints themselves — we trust the hand-picked port list.
  for (let i = 1; i < samples; i++) {
    const t = i / samples;
    const wA = Math.sin((1 - t) * omega) / sinOm;
    const wB = Math.sin(t * omega) / sinOm;
    const x = wA * ax + wB * bx;
    const y = wA * ay + wB * by;
    const z = wA * az + wB * bz;
    const lat = toLat({ x, y, z });
    const lng = toLng({ x, y, z });
    if (isLand(lat, lng)) return true;
  }
  return false;
}

/**
 * For a candidate waypoint W and an endpoint pair (A, B), return how
 * much W "deviates" from the great-circle A→B. A waypoint that lies
 * roughly on the line gets a low score; one off to the side gets a
 * higher score. Used to prefer waypoints that are at least somewhat on
 * the way, so detours don't look chaotic.
 *
 * Implementation: cross-track distance via spherical trig. Returns
 * radians of angular deviation.
 */
function offTrackDistance(
  a: LatLng,
  b: LatLng,
  w: LatLng,
): { offTrack: number; alongTrack: number } {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const φ1 = toRad(a.lat);
  const φ2 = toRad(b.lat);
  const φ3 = toRad(w.lat);
  const λ1 = toRad(a.lng);
  const λ2 = toRad(b.lng);
  const λ3 = toRad(w.lng);

  // Distance from A to W (radians).
  const dAW = Math.acos(
    Math.max(
      -1,
      Math.min(
        1,
        Math.sin(φ1) * Math.sin(φ3) +
          Math.cos(φ1) * Math.cos(φ3) * Math.cos(λ3 - λ1),
      ),
    ),
  );
  // Bearing A→W and A→B.
  const bearingAW = Math.atan2(
    Math.sin(λ3 - λ1) * Math.cos(φ3),
    Math.cos(φ1) * Math.sin(φ3) - Math.sin(φ1) * Math.cos(φ3) * Math.cos(λ3 - λ1),
  );
  const bearingAB = Math.atan2(
    Math.sin(λ2 - λ1) * Math.cos(φ2),
    Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(λ2 - λ1),
  );

  const offTrack = Math.asin(Math.sin(dAW) * Math.sin(bearingAW - bearingAB));
  const alongTrack = Math.acos(
    Math.max(-1, Math.min(1, Math.cos(dAW) / Math.cos(offTrack))),
  );
  return { offTrack: Math.abs(offTrack), alongTrack };
}

/**
 * Pick 0-5 mid-ocean waypoints that are roughly on the way between A
 * and B, sorted by progress along the great-circle. Each picked
 * waypoint must keep the resulting per-leg path off-land.
 */
function pickWaypoints(
  a: LatLng,
  b: LatLng,
  rand: () => number,
): LatLng[] | null {
  const targetCount = Math.floor(rand() * 6); // 0..5
  if (targetCount === 0) {
    return crossesLand(a.lat, a.lng, b.lat, b.lng) ? null : [];
  }

  // Score every waypoint by how close it is to the A→B great-circle and
  // how far along it sits. Reject any that's wildly off-track or beyond
  // the endpoints (alongTrack must be in [0, dAB]).
  const dAB = (() => {
    const toRad = (d: number) => (d * Math.PI) / 180;
    const φ1 = toRad(a.lat);
    const φ2 = toRad(b.lat);
    const dλ = toRad(b.lng - a.lng);
    return Math.acos(
      Math.max(
        -1,
        Math.min(1, Math.sin(φ1) * Math.sin(φ2) + Math.cos(φ1) * Math.cos(φ2) * Math.cos(dλ)),
      ),
    );
  })();

  const MAX_OFFTRACK = Math.PI / 4; // 45° cap — anything farther isn't "on the way"
  const candidates: { wp: LatLng; alongTrack: number; offTrack: number }[] = [];
  for (const wp of MID_OCEAN_WAYPOINTS) {
    const { offTrack, alongTrack } = offTrackDistance(a, b, wp);
    if (alongTrack < 0 || alongTrack > dAB) continue;
    if (offTrack > MAX_OFFTRACK) continue;
    candidates.push({ wp, alongTrack, offTrack });
  }
  if (candidates.length === 0) {
    // No on-the-way waypoints exist — fall back to a direct route if
    // possible, else reject the whole route.
    return crossesLand(a.lat, a.lng, b.lat, b.lng) ? null : [];
  }

  // Sort by off-track distance (closest to the great-circle first), then
  // pick the top targetCount and re-sort those by alongTrack progress.
  candidates.sort((x, y) => x.offTrack - y.offTrack);
  const chosen = candidates.slice(0, Math.min(targetCount, candidates.length));
  chosen.sort((x, y) => x.alongTrack - y.alongTrack);
  const waypoints = chosen.map((c) => c.wp);

  // Validate each leg against land. If any leg crosses land, reject.
  const fullPath: LatLng[] = [a, ...waypoints, b];
  for (let i = 0; i < fullPath.length - 1; i++) {
    const p = fullPath[i];
    const q = fullPath[i + 1];
    if (crossesLand(p.lat, p.lng, q.lat, q.lng)) {
      return null;
    }
  }
  return waypoints;
}

/**
 * Generate ``count`` great-circle routes between random hotspot pairs.
 * The route's risk class is the higher-priority of the two endpoints —
 * one IUU endpoint marks the whole route as IUU.
 *
 * Each route gets 0-5 mid-ocean waypoints chosen from the
 * MID_OCEAN_WAYPOINTS table, picked to lie roughly on the great-circle
 * path. Every per-leg segment is validated against the land mask.
 *
 * Caller must ``await whenLandMaskReady()`` first or routes won't be
 * filtered against land — they'll all be accepted.
 */
export function generateRoutes(count: number, seed = 42): ProceduralRoute[] {
  const rand = mulberry32(seed);
  const out: ProceduralRoute[] = [];
  let attempts = 0;
  // Higher attempt budget — multi-leg validation rejects more pairs.
  const maxAttempts = count * 18;
  while (out.length < count && attempts < maxAttempts) {
    attempts++;
    const a = WEIGHTED_HOTSPOTS[Math.floor(rand() * WEIGHTED_HOTSPOTS.length)];
    const b = WEIGHTED_HOTSPOTS[Math.floor(rand() * WEIGHTED_HOTSPOTS.length)];
    if (a === b) continue;
    // Reject extremely short hops — they look like nothing on the globe.
    const dlat = a.lat - b.lat;
    const dlng = a.lng - b.lng;
    if (dlat * dlat + dlng * dlng < 25) continue;

    const waypoints = pickWaypoints(
      { lat: a.lat, lng: a.lng },
      { lat: b.lat, lng: b.lng },
      rand,
    );
    if (waypoints === null) continue;

    const risk: RouteRisk =
      RISK_PRIORITY[a.risk] >= RISK_PRIORITY[b.risk] ? a.risk : b.risk;
    out.push({
      startLat: a.lat,
      startLng: a.lng,
      endLat: b.lat,
      endLng: b.lng,
      waypoints: [{ lat: a.lat, lng: a.lng }, ...waypoints, { lat: b.lat, lng: b.lng }],
      risk,
    });
  }
  return out;
}

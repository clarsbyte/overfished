/**
 * Build a 1-bit-per-pixel land/ocean mask from Natural Earth's
 * `ne_110m_land` polygon set.
 *
 * Output: `frontend/public/sprites/land-mask.bin` — a packed bitmap.
 *   - 1024 × 512 grid (lng × lat, 0.35° per cell at the equator).
 *   - 1 bit per pixel: 1 = land, 0 = ocean.
 *   - Row-major, top-down (row 0 = north pole, row 511 = south pole).
 *   - 64 KB total (1024 * 512 / 8 bytes).
 *
 * One-shot script. Run via:
 *   node scripts/build_land_mask.mjs
 *
 * The output PNG isn't checked into git out of habit (binary asset
 * regeneratable from this script), but we do ship the .bin so the demo
 * boots without an external fetch.
 *
 * Implementation: classic point-in-polygon (ray-casting). Naive O(W*H*N)
 * but runs in under 30 seconds for the 110m dataset (~150 polygons,
 * 1024*512 pixels). Acceptable for a one-shot.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_PATH = `${__dirname}/../frontend/public/sprites/land-mask.bin`;
const GEOJSON_URL =
  "https://raw.githubusercontent.com/martynafford/natural-earth-geojson/master/110m/physical/ne_110m_land.json";

const GRID_W = 1024;
const GRID_H = 512;

console.log(`Fetching ${GEOJSON_URL}…`);
const res = await fetch(GEOJSON_URL);
if (!res.ok) {
  console.error(`Failed: HTTP ${res.status}`);
  process.exit(1);
}
const geojson = await res.json();
const features = geojson.features ?? [];
console.log(`  → ${features.length} features`);

// Flatten all polygon rings into a single array of [lng, lat] arrays.
// Multi-polygons unfold into one ring per polygon-piece. We treat every
// outer ring as land; we ignore holes (small lakes) — fine at 110m res.
const rings = [];
for (const f of features) {
  const geom = f.geometry;
  if (!geom) continue;
  if (geom.type === "Polygon") {
    if (geom.coordinates[0]) rings.push(geom.coordinates[0]);
  } else if (geom.type === "MultiPolygon") {
    for (const poly of geom.coordinates) {
      if (poly[0]) rings.push(poly[0]);
    }
  }
}
console.log(`  → ${rings.length} land polygons`);

// Compute bounding boxes once per ring so we can early-reject a pixel
// against a polygon whose bbox doesn't contain it.
const bboxes = rings.map((ring) => {
  let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
  for (const [lng, lat] of ring) {
    if (lng < minLng) minLng = lng;
    if (lat < minLat) minLat = lat;
    if (lng > maxLng) maxLng = lng;
    if (lat > maxLat) maxLat = lat;
  }
  return { minLng, minLat, maxLng, maxLat };
});

/** Standard ray-casting point-in-polygon (Sunday). */
function inRing(lng, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersect =
      yi > lat !== yj > lat &&
      lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

const totalBits = GRID_W * GRID_H;
const packed = new Uint8Array(totalBits / 8);

console.log(`Rasterizing ${GRID_W}×${GRID_H}…`);
const startTime = Date.now();

let landCount = 0;
for (let row = 0; row < GRID_H; row++) {
  // row 0 = north pole (lat = +90), row H-1 = south pole (lat = -90).
  const lat = 90 - ((row + 0.5) / GRID_H) * 180;
  for (let col = 0; col < GRID_W; col++) {
    // col 0 = -180°, col W-1 = +180°.
    const lng = -180 + ((col + 0.5) / GRID_W) * 360;
    let isLand = false;
    for (let r = 0; r < rings.length; r++) {
      const bb = bboxes[r];
      if (lng < bb.minLng || lng > bb.maxLng || lat < bb.minLat || lat > bb.maxLat) {
        continue;
      }
      if (inRing(lng, lat, rings[r])) {
        isLand = true;
        break;
      }
    }
    if (isLand) {
      const bitIdx = row * GRID_W + col;
      packed[bitIdx >> 3] |= 1 << (bitIdx & 7);
      landCount++;
    }
  }
  if (row % 32 === 0) {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    process.stdout.write(`\r  row ${row}/${GRID_H} (${elapsed}s)…`);
  }
}
const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
process.stdout.write("\r" + " ".repeat(60) + "\r");
console.log(`  done in ${elapsed}s`);
console.log(`  land coverage: ${((landCount / totalBits) * 100).toFixed(2)}% (Earth's actual: ~29%)`);

mkdirSync(dirname(OUT_PATH), { recursive: true });
writeFileSync(OUT_PATH, packed);
console.log(`\n✅ Wrote ${OUT_PATH} (${packed.length} bytes)`);

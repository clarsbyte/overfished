/**
 * Converts ABFT_dataset.csv → public/tuna-heatmap.json
 * Format: [{lat, lng, weight}] — identical to shark-heatmap.json
 *
 * Only rows with Presence=1 are used (confirmed tuna locations).
 * Points are binned into 0.5° grid cells and weights are normalised 0-1.
 */
import { createReadStream } from "fs";
import { createInterface } from "readline";
import { writeFileSync } from "fs";
import { fileURLToPath } from "url";
import path from "path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CSV_PATH = path.join(__dirname, "../public/ABFT_dataset.csv");
const OUT_PATH = path.join(__dirname, "../public/tuna-heatmap.json");

const BIN = 0.5; // degree resolution
const counts = new Map();

const rl = createInterface({ input: createReadStream(CSV_PATH), crlfDelay: Infinity });

let header = null;
let latIdx = -1, lonIdx = -1, presIdx = -1;
let total = 0, kept = 0;

for await (const line of rl) {
  if (!header) {
    header = line.replace(/"/g, "").split(",");
    latIdx  = header.indexOf("Latitude");
    lonIdx  = header.indexOf("Longitude");
    presIdx = header.indexOf("Presence");
    if (latIdx < 0 || lonIdx < 0 || presIdx < 0) {
      throw new Error(`Missing columns. Found: ${header.join(", ")}`);
    }
    continue;
  }

  total++;
  const cols = line.split(",");
  const presence = cols[presIdx]?.trim();
  if (presence !== "1") continue;

  const lat = parseFloat(cols[latIdx]);
  const lon = parseFloat(cols[lonIdx]);
  if (!isFinite(lat) || !isFinite(lon)) continue;

  // Snap to grid
  const bLat = Math.round(lat / BIN) * BIN;
  const bLon = Math.round(lon / BIN) * BIN;
  const key = `${bLat},${bLon}`;
  counts.set(key, (counts.get(key) ?? 0) + 1);
  kept++;
}

console.log(`Processed ${total} rows, kept ${kept} presence=1 points → ${counts.size} grid cells`);

const max = Math.max(...counts.values());
const points = [];
for (const [key, count] of counts) {
  const [lat, lng] = key.split(",").map(Number);
  points.push({ lat, lng, weight: Math.round((count / max) * 1e4) / 1e4 });
}

writeFileSync(OUT_PATH, JSON.stringify(points));
console.log(`Written to ${OUT_PATH} (${points.length} points)`);

/**
 * Converts public/mmsi-daily-csvs-10-v3-2024-06-01.csv → public/fishing-dots.json
 * Run automatically via the "prebuild" / "predev" chain in package.json.
 * Output is a flat JSON array of { lat, lng, flag, hours } objects, fishing rows only.
 */

import { readFileSync, writeFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");

const CSV   = join(root, "public", "mmsi-daily-csvs-10-v3-2024-06-01.csv");
const OUT   = join(root, "public", "fishing-dots.json");

// ITU MID → ISO 3166-1 alpha-3 flag
const MID_FLAG = {
  412:"CHN",413:"CHN",416:"TWN",431:"JPN",432:"JPN",433:"JPN",
  440:"KOR",441:"KOR",477:"HKG",514:"KHM",518:"COK",519:"COK",
  525:"IDN",529:"IDN",533:"MYS",548:"PHL",566:"SGP",574:"VNM",576:"VNM",
  419:"IND",463:"PAK",470:"ARE",273:"RUS",
  224:"ESP",225:"ESP",228:"FRA",229:"MLT",248:"MLT",
  232:"GBR",233:"GBR",234:"GBR",235:"GBR",
  247:"ITA",257:"NOR",265:"SWE",230:"FIN",219:"DNK",271:"TUR",
  319:"CYM",351:"PAN",352:"PAN",353:"PAN",354:"PAN",
  355:"PAN",356:"PAN",357:"PAN",370:"PAN",371:"PAN",372:"PAN",373:"PAN",374:"PAN",
  636:"LBR",601:"ZAF",613:"SEN",616:"GHA",624:"NGA",632:"GNQ",654:"SYC",659:"COM",
  338:"USA",503:"AUS",701:"ARG",710:"BRA",725:"CHL",735:"ECU",770:"PER",775:"URY",
};

if (!existsSync(CSV)) {
  console.error(`CSV not found: ${CSV}`);
  process.exit(1);
}

console.log("Preprocessing GFW fleet CSV…");
const lines = readFileSync(CSV, "utf-8").split("\n");
const dots = [];

for (let i = 1; i < lines.length; i++) {
  const line = lines[i];
  if (!line) continue;

  const c1 = line.indexOf(",");
  const c2 = line.indexOf(",", c1 + 1);
  const c3 = line.indexOf(",", c2 + 1);
  const c4 = line.indexOf(",", c3 + 1);
  const c5 = line.indexOf(",", c4 + 1);

  const fh = parseFloat(line.slice(c5 + 1));
  if (!(fh > 0)) continue;

  const lat = parseFloat(line.slice(c1 + 1, c2));
  const lng = parseFloat(line.slice(c2 + 1, c3));
  if (isNaN(lat) || isNaN(lng)) continue;

  const mmsi = parseInt(line.slice(c3 + 1, c4), 10);
  const mid  = Math.floor(mmsi / 1_000_000);
  const flag = MID_FLAG[mid] ?? null;

  dots.push({ lat, lng, flag, hours: fh });
}

writeFileSync(OUT, JSON.stringify(dots));
console.log(`✓ Wrote ${dots.length} fishing positions → public/fishing-dots.json`);

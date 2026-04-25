/**
 * GET /api/fishing-events
 *
 * Parses the GFW fleet-daily CSV for 2024-06-01 (hardcoded, no API key needed).
 * Filters to rows with fishing_hours > 0, derives flag from MMSI MID prefix,
 * returns the top 10 000 most active fishing positions as GfwDot[].
 *
 * Source file: public/mmsi-daily-csvs-10-v3-2024-06-01.csv
 * Columns:     date, cell_ll_lat, cell_ll_lon, mmsi, hours, fishing_hours
 */

import fs from "fs";
import path from "path";
import { NextResponse } from "next/server";

export interface GfwDot {
  lat: number;
  lng: number;
  flag: string | null;
  name: string | null;
  hours: number;
}

// ITU Maritime Identification Digits → ISO 3166-1 alpha-3 flag state
// Covers the top fishing nations by vessel count / IUU risk.
const MID_FLAG: Record<number, string> = {
  // East Asia
  412: "CHN", 413: "CHN",
  416: "TWN",
  431: "JPN", 432: "JPN", 433: "JPN",
  440: "KOR", 441: "KOR",
  477: "HKG",
  // SE Asia / Pacific
  514: "KHM",
  518: "COK", 519: "COK",
  525: "IDN", 529: "IDN",
  533: "MYS",
  548: "PHL",
  566: "SGP",
  574: "VNM", 576: "VNM",
  // South Asia
  419: "IND",
  463: "PAK",
  // Middle East
  470: "ARE",
  // Russia
  273: "RUS",
  // Europe
  224: "ESP", 225: "ESP",
  228: "FRA",
  229: "MLT", 248: "MLT",
  232: "GBR", 233: "GBR", 234: "GBR", 235: "GBR",
  247: "ITA",
  257: "NOR",
  265: "SWE",
  230: "FIN",
  219: "DNK",
  271: "TUR",
  // Flag of convenience / open registries
  319: "CYM",
  351: "PAN", 352: "PAN", 353: "PAN", 354: "PAN",
  355: "PAN", 356: "PAN", 357: "PAN",
  370: "PAN", 371: "PAN", 372: "PAN", 373: "PAN", 374: "PAN",
  636: "LBR",
  // Africa
  601: "ZAF",
  613: "SEN",
  616: "GHA",
  624: "NGA",
  632: "GNQ",
  654: "SYC",
  659: "COM",
  // Americas
  338: "USA",
  503: "AUS",
  701: "ARG",
  710: "BRA",
  725: "CHL",
  735: "ECU",
  770: "PER",
  775: "URY",
};

function midToFlag(mmsi: number): string | null {
  const mid = Math.floor(mmsi / 1_000_000);
  return MID_FLAG[mid] ?? null;
}

function loadFleetDots(): GfwDot[] {
  const csvPath = path.join(
    process.cwd(),
    "public",
    "mmsi-daily-csvs-10-v3-2024-06-01.csv",
  );

  const text = fs.readFileSync(csvPath, "utf-8");
  const lines = text.split("\n");

  const dots: GfwDot[] = [];

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line) continue;

    const comma1 = line.indexOf(",");
    const comma2 = line.indexOf(",", comma1 + 1);
    const comma3 = line.indexOf(",", comma2 + 1);
    const comma4 = line.indexOf(",", comma3 + 1);
    const comma5 = line.indexOf(",", comma4 + 1);

    const fishingHours = parseFloat(line.slice(comma5 + 1));
    if (!(fishingHours > 0)) continue;

    const lat = parseFloat(line.slice(comma1 + 1, comma2));
    const lng = parseFloat(line.slice(comma2 + 1, comma3));
    const mmsi = parseInt(line.slice(comma3 + 1, comma4), 10);

    if (isNaN(lat) || isNaN(lng)) continue;

    dots.push({ lat, lng, flag: midToFlag(mmsi), name: null, hours: fishingHours });
  }

  return dots;
}

export async function GET() {
  const dots = loadFleetDots();
  return NextResponse.json(dots, {
    headers: { "Cache-Control": "s-maxage=86400, stale-while-revalidate=604800" },
  });
}

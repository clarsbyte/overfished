"use client";

import type { GfwDot } from "@/app/api/fishing-events/route";
import { useCallback, useEffect, useRef, useState } from "react";
import Globe, { type GlobeMethods } from "react-globe.gl";

const GLOBE_IMG = "//unpkg.com/three-globe/example/img/earth-blue-marble.jpg";
const BUMP_IMG = "//unpkg.com/three-globe/example/img/earth-topology.png";
const BG_IMG = "//unpkg.com/three-globe/example/img/night-sky.png";

// ─────────────────────────────────────────────────────────────────────────
export default function GlobeClient() {
  const globeRef = useRef<GlobeMethods | undefined>(undefined);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [gfwDots, setGfwDots] = useState<GfwDot[]>([]);

  useEffect(() => {
    const measure = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  // Fetch real GFW fishing-event positions → vessel dots
  useEffect(() => {
    fetch("/api/fishing-events")
      .then(r => r.json())
      .then(data => { if (Array.isArray(data)) setGfwDots(data); })
      .catch(() => { /* no token / network error — sim paths still show */ });
  }, []);

  // Use onGlobeReady (fires after WebGL context is fully up) instead of a
  // size-based effect — avoids the race where globeRef isn't set yet.
  const handleGlobeReady = useCallback(() => {
    if (!globeRef.current) return;
    const ctrl = globeRef.current as unknown as { controls: () => { autoRotate: boolean; autoRotateSpeed: number } };
    const c = ctrl.controls();
    c.autoRotate = true;
    c.autoRotateSpeed = 0.45;
    globeRef.current.pointOfView({ lat: 10, lng: -20, altitude: 2.0 }, 0);
  }, []);

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#000" }}>
      {size.w > 0 && (
        <Globe
          ref={globeRef}
          width={size.w}
          height={size.h}
          onGlobeReady={handleGlobeReady}
          globeImageUrl={GLOBE_IMG}
          bumpImageUrl={BUMP_IMG}
          backgroundImageUrl={BG_IMG}
          atmosphereColor="#00b3ff"
          atmosphereAltitude={0.28}
          showGraticules={false}

          /* ── GFW fleet-daily dots — 2024-06-01 snapshot ────────
           * Top 10 000 fishing positions by fishing_hours from the
           * GFW mmsi-daily-csvs dataset. Flag derived from MMSI MID.
           * Red = high-IUU flags; amber = elevated risk; gold = other. */
          pointsData={gfwDots}
          pointLat={(d) => (d as GfwDot).lat}
          pointLng={(d) => (d as GfwDot).lng}
          pointAltitude={0}
          pointColor={(d: object) => {
            const flag = (d as GfwDot).flag ?? "";
            // Flag states with highest IUU incidence per GFW and INTERPOL data
            if (["CHN", "TWN", "VUT", "COM", "TGO", "GNE"].includes(flag)) return "rgba(255,80,20,0.85)";
            if (["KOR", "RUS", "ESP", "IDN", "IRN"].includes(flag)) return "rgba(255,160,0,0.80)";
            return "rgba(255,210,50,0.72)";  // all others — GFW gold
          }}
          pointRadius={0.12}
          pointResolution={3}
          pointsMerge={true}
        />
      )}
    </div>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import Globe, { type GlobeMethods } from "react-globe.gl";

interface GfwDot { lat: number; lng: number; flag: string | null; hours: number; }

const GLOBE_IMG = "//unpkg.com/three-globe/example/img/earth-blue-marble.jpg";
const BUMP_IMG  = "//unpkg.com/three-globe/example/img/earth-topology.png";
const BG_IMG    = "//unpkg.com/three-globe/example/img/night-sky.png";

const HIGH_RISK = new Set(["CHN", "TWN", "VUT", "COM", "TGO", "GNE"]);
const MED_RISK  = new Set(["KOR", "RUS", "ESP", "IDN", "IRN"]);

// Stable module-level accessors — never recreated on re-render so Globe
// doesn't think its data changed and rebuild the 61K-point mesh.
const pointLat   = (d: object) => (d as GfwDot).lat;
const pointLng   = (d: object) => (d as GfwDot).lng;
const EMPTY: GfwDot[] = [];

function dotColor(d: object) {
  const flag = (d as GfwDot).flag ?? "";
  if (HIGH_RISK.has(flag)) return "rgba(255,80,20,0.85)";
  if (MED_RISK.has(flag))  return "rgba(255,160,0,0.80)";
  return "rgba(255,210,50,0.72)";
}

function Spinner({ size = 32 }: { size?: number }) {
  return (
    <div style={{
      width: size, height: size, flexShrink: 0,
      border: "1.5px solid rgba(0,210,255,0.1)",
      borderTop: "1.5px solid rgba(0,210,255,0.8)",
      borderRadius: "50%",
      animation: "spin 0.9s linear infinite",
    }} />
  );
}

function LayerRow({ label, count, checked, loading, onChange }: {
  label: string; count?: number; checked: boolean;
  loading: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div
      onClick={e => { e.stopPropagation(); onChange(!checked); }}
      style={{ display: "flex", alignItems: "center", gap: 12,
               cursor: "pointer", userSelect: "none", padding: "5px 0" }}
    >
      <div style={{
        width: 14, height: 14, flexShrink: 0,
        border: `1.5px solid rgba(0,210,255,${checked ? 0.7 : 0.22})`,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: checked ? "rgba(0,210,255,0.15)" : "transparent",
        transition: "all 0.15s",
      }}>
        {checked && !loading && (
          <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
            <path d="M1 3.5L3.5 6L8 1" stroke="rgba(0,210,255,0.95)"
                  strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
        {loading && <Spinner size={10} />}
      </div>
      <span style={{
        fontFamily: "'JetBrains Mono', monospace", fontSize: 12,
        color: `rgba(0,210,255,${checked ? 0.85 : 0.35})`,
        letterSpacing: "0.03em", flex: 1, transition: "color 0.15s",
      }}>
        {label}
      </span>
      {!loading && checked && count !== undefined && (
        <span style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
          color: "rgba(0,210,255,0.3)", letterSpacing: "0.04em",
        }}>
          {count.toLocaleString()}
        </span>
      )}
    </div>
  );
}

// ── Collapsible panel ───────────────────────────────────────────────────────
function Panel({ children, open }: { children: React.ReactNode; open: boolean }) {
  return (
    <div style={{
      overflow: "hidden",
      maxHeight: open ? 400 : 0,
      opacity: open ? 1 : 0,
      transition: "max-height 0.28s ease, opacity 0.2s ease",
    }}>
      {/* Divider */}
      <div style={{ borderTop: "1px solid rgba(0,210,255,0.1)", margin: "10px 0 12px" }} />
      {children}
    </div>
  );
}

// ── Main ────────────────────────────────────────────────────────────────────
export default function GlobeClient() {
  const globeRef                        = useRef<GlobeMethods | undefined>(undefined);
  const [size, setSize]                 = useState({ w: window.innerWidth, h: window.innerHeight });
  const [dots, setDots]                 = useState<GfwDot[]>([]);
  const [ready, setReady]               = useState(false);
  const [showDots, setShowDots]         = useState(true);
  const [layerLoading, setLayerLoading] = useState(false);
  const [panelOpen, setPanelOpen]       = useState(false);
  const [pinned, setPinned]             = useState(false);

  useEffect(() => {
    const measure = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    fetch("/fishing-dots.json", { signal: ctrl.signal })
      .then(r => r.json())
      .then(data => { if (Array.isArray(data)) setDots(data); })
      .catch(() => {});
    return () => ctrl.abort();
  }, []);

  const handleGlobeReady = useCallback(() => {
    if (!globeRef.current) return;
    const c = (globeRef.current as unknown as {
      controls: () => { autoRotate: boolean; autoRotateSpeed: number };
    }).controls();
    c.autoRotate = true;
    c.autoRotateSpeed = 0.45;
    globeRef.current.pointOfView({ lat: 10, lng: -20, altitude: 2.0 }, 0);
    setReady(true);
  }, []);

  const toggleDots = (v: boolean) => {
    setLayerLoading(true);
    setShowDots(v);
    setTimeout(() => setLayerLoading(false), 600);
  };

  const handleHeaderClick = () => {
    const next = !pinned;
    setPinned(next);
    setPanelOpen(next);
  };

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#000", position: "relative" }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

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
        pointsData={showDots ? dots : EMPTY}
        pointLat={pointLat}
        pointLng={pointLng}
        pointAltitude={0}
        pointColor={dotColor}
        pointRadius={0.12}
        pointResolution={3}
        pointsMerge={true}
      />

      {/* Spinner on the globe */}
      {(!ready || layerLoading) && (
        <div style={{
          position: "absolute", inset: 0, zIndex: 20, pointerEvents: "none",
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", gap: 14,
        }}>
          <Spinner size={48} />
          <span style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
            letterSpacing: "0.25em", textTransform: "uppercase",
            color: "rgba(0,210,255,0.5)",
          }}>
            {ready ? "Rendering" : "Initialising"}
          </span>
        </div>
      )}

      {/* Initial black cover */}
      <div style={{
        position: "absolute", inset: 0, background: "#000", zIndex: 19,
        opacity: ready ? 0 : 1, transition: "opacity 1s ease", pointerEvents: "none",
      }} />

      {/* ── Panel ────────────────────────────────────────────────────────── */}
      <div
        style={{
          position: "absolute", bottom: 32, left: 32, zIndex: 10,
          width: 240,
          background: "rgba(2,10,20,0.88)",
          backdropFilter: "blur(14px)",
          border: "1px solid rgba(0,210,255,0.14)",
          borderTop: `1px solid rgba(0,210,255,${panelOpen ? 0.5 : 0.25})`,
          backgroundImage: [
            "linear-gradient(112deg, transparent 38%, rgba(0,210,255,0.022) 39%, rgba(0,210,255,0.022) 40%, transparent 41%)",
            "linear-gradient(154deg, transparent 55%, rgba(0,210,255,0.015) 56%, rgba(0,210,255,0.015) 57%, transparent 58%)",
            "linear-gradient(rgba(2,10,20,0.88), rgba(2,10,20,0.88))",
          ].join(", "),
          padding: "12px 18px",
          cursor: "pointer",
          transition: "border-top-color 0.2s",
        }}
        onMouseEnter={() => !pinned && setPanelOpen(true)}
        onMouseLeave={() => !pinned && setPanelOpen(false)}
        onClick={handleHeaderClick}
      >
        {/* Header — always visible */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
            letterSpacing: "0.22em", textTransform: "uppercase",
            color: `rgba(0,210,255,${panelOpen ? 0.7 : 0.4})`,
            transition: "color 0.2s",
          }}>
            Layers
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {/* Pin indicator */}
            {pinned && (
              <span style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 9,
                color: "rgba(0,210,255,0.4)", letterSpacing: "0.1em",
              }}>
                PINNED
              </span>
            )}
            {/* Chevron */}
            <svg width="10" height="6" viewBox="0 0 10 6" fill="none"
              style={{ transform: panelOpen ? "rotate(180deg)" : "rotate(0deg)",
                       transition: "transform 0.25s ease" }}>
              <path d="M1 1L5 5L9 1" stroke="rgba(0,210,255,0.4)"
                    strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </div>

        {/* Collapsible content */}
        <Panel open={panelOpen}>
          <LayerRow
            label="Fishing vessels"
            count={dots.length}
            checked={showDots}
            loading={layerLoading}
            onChange={toggleDots}
          />
          {/* More rows go here */}
        </Panel>
      </div>
    </div>
  );
}

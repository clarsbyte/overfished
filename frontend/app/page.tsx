import GlobeWrapper from "@/src/components/GlobeWrapper";

const RISK_LEGEND = [
  { label: "Confirmed IUU", color: "#ff1f4d" },
  { label: "High Risk",     color: "#ff8a00" },
  { label: "Suspect",       color: "#ffd400" },
  { label: "Safe",          color: "#00ffe0" },
] as const;

export default function Home() {
  return (
    <main className="relative w-screen h-screen overflow-hidden bg-black">
      {/* Full-screen globe */}
      <GlobeWrapper />

      {/* Top-left wordmark */}
      <header className="fixed top-0 left-0 z-10 px-6 py-5 pointer-events-none">
        <p style={{ fontFamily: "monospace", fontSize: 10, letterSpacing: "0.3em",
                    textTransform: "uppercase", color: "rgba(0,212,255,0.6)", margin: 0 }}>
          Overfish AI · Maritime Surveillance Console
        </p>
        <p style={{ fontFamily: "monospace", fontSize: 11, color: "rgba(255,255,255,0.3)",
                    marginTop: 4 }}>
          Global IUU fishing tracker · live AIS · {new Date().getFullYear()}
        </p>
      </header>

      {/* Bottom-left legend */}
      <aside className="fixed bottom-6 left-6 z-10 pointer-events-none"
             style={{ fontFamily: "monospace" }}>
        <p style={{ fontSize: 9, letterSpacing: "0.2em", textTransform: "uppercase",
                    color: "rgba(255,255,255,0.3)", marginBottom: 8 }}>
          Risk level
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {RISK_LEGEND.map(({ label, color }) => (
            <div key={label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: color,
                            boxShadow: `0 0 6px ${color}` }} />
              <span style={{ fontSize: 11, color: "rgba(255,255,255,0.55)" }}>{label}</span>
            </div>
          ))}
        </div>
      </aside>
    </main>
  );
}

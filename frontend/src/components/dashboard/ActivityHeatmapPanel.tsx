import { Layers3, MapPin, Thermometer } from "lucide-react";
import { Card } from "./Card";

const HEAT_BLOBS = [
  { left: 18, top: 48, size: 18, intensity: 0.95 },
  { left: 28, top: 55, size: 12, intensity: 0.65 },
  { left: 42, top: 62, size: 14, intensity: 0.5 },
  { left: 58, top: 35, size: 22, intensity: 0.85 },
  { left: 72, top: 60, size: 16, intensity: 0.75 },
  { left: 80, top: 50, size: 14, intensity: 0.6 },
  { left: 50, top: 25, size: 10, intensity: 0.45 },
];

export function ActivityHeatmapPanel() {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-[10px] font-mono tracking-[0.22em] text-cyan-300/70 uppercase">
            Activity Heatmap
          </div>
          <div className="text-[10px] font-mono tracking-[0.18em] text-slate-500 mt-0.5">
            30 day view
          </div>
        </div>
      </div>

      <div className="flex gap-3">
        <div className="flex flex-col gap-1.5">
          <button className="w-7 h-7 rounded-md bg-white/[0.04] border border-white/[0.07] hover:border-cyan-400/40 flex items-center justify-center transition-colors">
            <Layers3 className="w-3.5 h-3.5 text-slate-400" />
          </button>
          <button className="w-7 h-7 rounded-md bg-white/[0.04] border border-white/[0.07] hover:border-cyan-400/40 flex items-center justify-center transition-colors">
            <MapPin className="w-3.5 h-3.5 text-slate-400" />
          </button>
          <button className="w-7 h-7 rounded-md bg-white/[0.04] border border-white/[0.07] hover:border-cyan-400/40 flex items-center justify-center transition-colors">
            <Thermometer className="w-3.5 h-3.5 text-slate-400" />
          </button>
        </div>

        <div className="flex-1 min-w-0">
          <div className="relative w-full h-[80px] rounded-md overflow-hidden bg-[#050913] border border-white/[0.05]">
            <WorldOutline />
            {HEAT_BLOBS.map((b, i) => (
              <div
                key={i}
                className="absolute rounded-full pointer-events-none"
                style={{
                  left: `${b.left}%`,
                  top: `${b.top}%`,
                  width: `${b.size}px`,
                  height: `${b.size}px`,
                  background: `radial-gradient(circle, rgba(255,80,40,${b.intensity}) 0%, rgba(255,140,30,${b.intensity * 0.5}) 40%, transparent 75%)`,
                  filter: "blur(1.5px)",
                  transform: "translate(-50%,-50%)",
                }}
              />
            ))}
          </div>

          <div className="mt-2 flex items-center gap-2">
            <span className="text-[9px] font-mono tracking-wider text-slate-500">LOW</span>
            <div className="flex-1 h-1 rounded-full bg-gradient-to-r from-cyan-500/40 via-amber-400 to-red-500" />
            <span className="text-[9px] font-mono tracking-wider text-slate-500">HIGH</span>
          </div>
        </div>
      </div>
    </Card>
  );
}

/** Tiny faint world coastline for the mini heatmap background. */
function WorldOutline() {
  return (
    <svg viewBox="0 0 200 80" className="absolute inset-0 w-full h-full opacity-25">
      <g fill="none" stroke="#3b82f6" strokeWidth="0.5" opacity="0.7">
        {/* Americas */}
        <path d="M18,18 Q22,22 24,30 L26,42 Q24,50 28,58 L34,68 Q40,72 38,76" />
        <path d="M44,40 Q48,50 50,60 L52,72" />
        {/* Europe + Africa */}
        <path d="M92,18 Q96,22 102,24 L110,22 Q116,28 114,36 L112,52 Q116,62 112,72" />
        <path d="M84,28 Q90,32 92,38" />
        {/* Asia + Oceania */}
        <path d="M120,14 Q140,16 156,22 L168,28 Q176,32 178,40" />
        <path d="M148,40 Q156,46 158,54" />
        <path d="M158,58 Q166,62 172,60" />
      </g>
    </svg>
  );
}

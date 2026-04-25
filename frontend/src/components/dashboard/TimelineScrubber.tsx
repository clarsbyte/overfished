import { Camera, Pause, Play, Settings2 } from "lucide-react";
import { useState } from "react";
import { Card } from "./Card";

const RANGES = ["30 DAYS", "7D", "30D", "90D", "1Y"] as const;
type Range = (typeof RANGES)[number];

const DATE_LABELS = ["APR 15", "APR 22", "APR 29", "MAY 6"];

export function TimelineScrubber() {
  const [range, setRange] = useState<Range>("30D");
  const [playing, setPlaying] = useState(false);

  return (
    <Card className="px-4 py-3 w-[560px] bg-[linear-gradient(165deg,rgba(18,29,52,0.62)_0%,rgba(8,14,27,0.48)_100%)] border-white/[0.18]">
      {/* Range tabs */}
      <div className="flex items-center justify-center gap-1 mb-2">
        {RANGES.map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={[
              "px-3 py-1 rounded-md text-[10.5px] font-mono tracking-[0.12em] transition-colors",
              range === r
                ? "bg-cyan-300/14 text-cyan-200 border border-cyan-300/28 shadow-[0_0_12px_rgba(34,211,238,0.2)]"
                : "text-slate-400 hover:text-slate-200 border border-transparent hover:bg-white/[0.06]",
            ].join(" ")}
          >
            {r}
          </button>
        ))}
      </div>

      {/* Scrubber track */}
      <div className="relative h-[36px] mb-1">
        {/* Tick row */}
        <div className="absolute inset-x-0 top-1.5 h-3 flex items-end justify-between">
          {Array.from({ length: 30 }).map((_, i) => (
            <span
              key={i}
              className={`w-px ${i % 7 === 0 ? "h-3 bg-cyan-400/50" : "h-1.5 bg-slate-600/60"}`}
            />
          ))}
        </div>

        {/* Baseline */}
        <div className="absolute inset-x-0 top-[18px] h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />

        {/* Date labels */}
        <div className="absolute inset-x-0 bottom-0 flex justify-between text-[9px] font-mono tracking-wider text-slate-500">
          {DATE_LABELS.map((d) => (
            <span key={d}>{d}</span>
          ))}
          <span className="text-red-400 font-medium">NOW MAY 13</span>
        </div>

        {/* NOW indicator */}
        <div className="absolute right-[6%] top-0 bottom-3 w-px bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.7)]">
          <div className="absolute -top-0.5 -left-[3px] w-[7px] h-[7px] rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]" />
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center justify-center gap-2 pt-1">
        <button
          onClick={() => setPlaying((p) => !p)}
          className="w-8 h-8 rounded-full bg-cyan-300/16 border border-cyan-300/32 backdrop-blur-xl flex items-center justify-center text-cyan-200 hover:bg-cyan-300/26 transition-colors shadow-[0_0_10px_rgba(34,211,238,0.2)]"
          aria-label={playing ? "Pause" : "Play"}
        >
          {playing ? (
            <Pause className="w-3.5 h-3.5" fill="currentColor" />
          ) : (
            <Play className="w-3.5 h-3.5" fill="currentColor" />
          )}
        </button>

        <button className="px-2 h-7 rounded-md text-[10.5px] font-mono text-slate-300 bg-white/[0.08] border border-white/[0.15] backdrop-blur-xl hover:border-cyan-400/30 transition-colors flex items-center gap-1">
          1x
          <span className="text-slate-600">▾</span>
        </button>

        <div className="ml-2 flex items-center gap-1.5">
          <button
            aria-label="Snapshot"
            className="w-7 h-7 rounded-md bg-white/[0.08] border border-white/[0.15] backdrop-blur-xl hover:border-cyan-400/30 flex items-center justify-center transition-colors"
          >
            <Camera className="w-3.5 h-3.5 text-slate-400" />
          </button>
          <button
            aria-label="Timeline settings"
            className="w-7 h-7 rounded-md bg-white/[0.08] border border-white/[0.15] backdrop-blur-xl hover:border-cyan-400/30 flex items-center justify-center transition-colors"
          >
            <Settings2 className="w-3.5 h-3.5 text-slate-400" />
          </button>
        </div>
      </div>
    </Card>
  );
}

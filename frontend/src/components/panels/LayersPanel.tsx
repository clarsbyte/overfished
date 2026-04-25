import { Layers } from "lucide-react";
import { useState } from "react";

export interface LayerState {
  showVessels: boolean;
  showHeatmap: boolean;
  showPaths: boolean;
  flightCount: number;
}

interface Props {
  value: LayerState;
  onChange: (next: LayerState) => void;
}

const TOGGLES: { key: keyof LayerState; label: string }[] = [
  { key: "showVessels", label: "Vessel traffic" },
  { key: "showHeatmap", label: "Fishing heatmap" },
  { key: "showPaths", label: "Flight paths" },
];

export function LayersPanel({ value, onChange }: Props) {
  const [open, setOpen] = useState(true);

  return (
    <div className="w-72 pointer-events-auto bg-ink-900/85 backdrop-blur border border-cyan-500/20 rounded shadow-lg">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 border-b border-cyan-500/15 hover:bg-cyan-500/5"
      >
        <div className="flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-cyan-300" />
          <span className="text-[10px] font-mono tracking-[0.2em] text-cyan-300/80 uppercase">
            Layers
          </span>
        </div>
        <span className="text-[10px] font-mono text-slate-500">{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="px-3 py-2.5 space-y-2.5">
          {TOGGLES.map(({ key, label }) => {
            const checked = value[key] as boolean;
            return (
              <label
                key={key}
                className="flex items-center justify-between cursor-pointer text-xs text-slate-200 hover:text-cyan-100"
              >
                <span>{label}</span>
                <span
                  onClick={() => onChange({ ...value, [key]: !checked })}
                  className={`relative inline-flex h-4 w-7 items-center rounded-full transition-colors ${
                    checked ? "bg-cyan-500/70" : "bg-slate-700"
                  }`}
                >
                  <span
                    className={`inline-block h-3 w-3 rounded-full bg-white transition-transform ${
                      checked ? "translate-x-3.5" : "translate-x-0.5"
                    }`}
                  />
                </span>
              </label>
            );
          })}

          <div className="pt-2 border-t border-cyan-500/10">
            <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 mb-1">
              <span className="uppercase tracking-wider">Vessel count</span>
              <span className="text-cyan-300">{value.flightCount}</span>
            </div>
            <input
              type="range"
              min={0}
              max={300}
              step={10}
              value={value.flightCount}
              onChange={(e) =>
                onChange({ ...value, flightCount: Number(e.target.value) })
              }
              className="w-full accent-cyan-400"
            />
          </div>
        </div>
      )}
    </div>
  );
}

import { Palette } from "lucide-react";

export type GlassTheme =
  | "arctic"
  | "aurora"
  | "sunset"
  | "obsidian"
  | "prism"
  | "deepsea"
  | "neon"
  | "frostfire";

interface ThemeOption {
  id: GlassTheme;
  label: string;
  swatch: string;
}

const OPTIONS: ThemeOption[] = [
  { id: "arctic", label: "Arctic", swatch: "from-cyan-300 to-blue-500" },
  { id: "aurora", label: "Aurora", swatch: "from-cyan-300 to-fuchsia-500" },
  { id: "sunset", label: "Sunset", swatch: "from-amber-300 to-rose-500" },
  { id: "obsidian", label: "Graphite", swatch: "from-zinc-200 to-slate-500" },
  { id: "prism", label: "Prism", swatch: "from-violet-300 to-cyan-300" },
  { id: "deepsea", label: "Deep Sea", swatch: "from-blue-300 to-emerald-300" },
  { id: "neon", label: "Neon", swatch: "from-fuchsia-400 to-cyan-300" },
  { id: "frostfire", label: "Frostfire", swatch: "from-sky-300 to-orange-300" },
];

interface Props {
  value: GlassTheme;
  onChange: (theme: GlassTheme) => void;
}

export function GlassThemeSwitcher({ value, onChange }: Props) {
  return (
    <div className="liquid-glass-surface rounded-xl p-3 w-[280px]">
      <div className="flex items-center gap-2 mb-2.5">
        <Palette className="w-3.5 h-3.5 text-cyan-300" />
        <span className="text-[10px] font-mono tracking-[0.2em] text-cyan-300/80 uppercase">
          Glass Preset
        </span>
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {OPTIONS.map((option) => {
          const active = option.id === value;
          return (
            <button
              key={option.id}
              onClick={() => onChange(option.id)}
              className={[
                "relative px-2 py-1.5 rounded-md text-[10.5px] font-medium transition-colors text-left whitespace-nowrap",
                "liquid-glass-pill",
                active
                  ? "text-cyan-100 border-cyan-300/55 shadow-[0_0_10px_rgba(34,211,238,0.25)]"
                  : "text-slate-300 hover:text-slate-100 border-white/20",
              ].join(" ")}
            >
              <span
                className={`inline-block w-2 h-2 rounded-full bg-gradient-to-r ${option.swatch} mr-1.5 align-middle`}
              />
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

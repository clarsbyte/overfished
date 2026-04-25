import {
  Anchor,
  AlertTriangle,
  Cloud,
  Fish,
  Plus,
  Mountain,
  Navigation,
  Shield,
  Ship,
  Waves,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { Card } from "./Card";
import { Logo } from "./Logo";
import { Toggle } from "./Toggle";

interface Layer {
  id: string;
  label: string;
  icon: LucideIcon;
  defaultOn: boolean;
}

const LAYERS: Layer[] = [
  { id: "vessel_traffic", label: "Vessel Traffic", icon: Ship, defaultOn: true },
  { id: "illegal_activity", label: "Illegal Activity", icon: AlertTriangle, defaultOn: true },
  { id: "fishing_zones", label: "Fishing Zones", icon: Fish, defaultOn: true },
  { id: "mpas", label: "MPAs", icon: Shield, defaultOn: true },
  { id: "eez", label: "EEZ Boundaries", icon: Navigation, defaultOn: true },
  { id: "weather", label: "Weather", icon: Cloud, defaultOn: false },
  { id: "currents", label: "Ocean Currents", icon: Waves, defaultOn: false },
  { id: "bathymetry", label: "Bathymetry", icon: Mountain, defaultOn: false },
  { id: "ports", label: "Ports", icon: Anchor, defaultOn: false },
];

export function LayersPanel() {
  const [state, setState] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(LAYERS.map((l) => [l.id, l.defaultOn])),
  );

  return (
    <Card className="p-4">
      <div className="mb-4">
        <Logo />
      </div>

      <div className="text-[10px] font-mono tracking-[0.22em] text-cyan-300/70 uppercase mb-2.5">
        Layers
      </div>

      <div className="space-y-1">
        {LAYERS.map((layer) => {
          const Icon = layer.icon;
          const on = state[layer.id];
          return (
            <button
              key={layer.id}
              onClick={() => setState((s) => ({ ...s, [layer.id]: !s[layer.id] }))}
              className="group w-full flex items-center justify-between gap-3 px-2 py-1.5 rounded-md hover:bg-white/[0.04] transition-colors"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <Icon
                  className={`w-3.5 h-3.5 flex-shrink-0 transition-colors ${
                    on ? "text-cyan-300" : "text-slate-500"
                  }`}
                  strokeWidth={1.75}
                />
                <span
                  className={`text-[12px] truncate ${
                    on ? "text-slate-200" : "text-slate-400"
                  }`}
                >
                  {layer.label}
                </span>
              </div>
              <Toggle
                on={on}
                onChange={(v) => setState((s) => ({ ...s, [layer.id]: v }))}
                ariaLabel={`${layer.label} layer`}
              />
            </button>
          );
        })}
      </div>

      <button
        type="button"
        className="mt-3 w-full flex items-center justify-center gap-1.5 py-2 rounded-md border border-dashed border-white/10 text-[11px] font-medium text-slate-400 hover:text-cyan-300 hover:border-cyan-400/30 hover:bg-cyan-400/[0.04] transition-colors"
      >
        <Plus className="w-3.5 h-3.5" />
        Add Layer
      </button>
    </Card>
  );
}

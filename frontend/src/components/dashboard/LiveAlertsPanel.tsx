import { AlertTriangle, EyeOff, MapPinned, Radar } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card } from "./Card";

type Severity = "critical" | "high" | "warn" | "info";

interface Alert {
  id: string;
  title: string;
  location: string;
  ago: string;
  severity: Severity;
  icon: LucideIcon;
}

const ALERTS: Alert[] = [
  {
    id: "1",
    title: "Suspicious Activity",
    location: "North Pacific",
    ago: "2m ago",
    severity: "critical",
    icon: AlertTriangle,
  },
  {
    id: "2",
    title: "AIS Dark Event",
    location: "West Africa Coast",
    ago: "15m ago",
    severity: "high",
    icon: EyeOff,
  },
  {
    id: "3",
    title: "Vessel in MPA",
    location: "Galapagos Marine Reserve",
    ago: "28m ago",
    severity: "warn",
    icon: MapPinned,
  },
  {
    id: "4",
    title: "Anomaly Detected",
    location: "Indian Ocean",
    ago: "45m ago",
    severity: "info",
    icon: Radar,
  },
];

const SEVERITY_STYLES: Record<Severity, { dot: string; tile: string; icon: string }> = {
  critical: {
    dot: "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.7)]",
    tile: "bg-red-500/10 border-red-500/30",
    icon: "text-red-400",
  },
  high: {
    dot: "bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.6)]",
    tile: "bg-red-400/10 border-red-400/25",
    icon: "text-red-300",
  },
  warn: {
    dot: "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)]",
    tile: "bg-amber-400/10 border-amber-400/25",
    icon: "text-amber-300",
  },
  info: {
    dot: "bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.6)]",
    tile: "bg-cyan-400/10 border-cyan-400/25",
    icon: "text-cyan-300",
  },
};

export function LiveAlertsPanel() {
  return (
    <Card className="p-4 w-[300px]">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="text-[10px] font-mono tracking-[0.22em] text-cyan-300/70 uppercase">
            Live Alerts
          </div>
          <span className="px-1.5 h-[16px] min-w-[20px] rounded-full bg-red-500 text-[9px] font-bold text-white flex items-center justify-center shadow-[0_0_8px_rgba(239,68,68,0.5)]">
            23
          </span>
        </div>
        <button className="text-[10px] font-medium text-cyan-300/80 hover:text-cyan-200 transition-colors">
          View all
        </button>
      </div>

      <div className="space-y-1.5">
        {ALERTS.map((a) => {
          const styles = SEVERITY_STYLES[a.severity];
          const Icon = a.icon;
          return (
            <button
              key={a.id}
              className="group w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md bg-white/[0.02] border border-white/[0.05] hover:bg-white/[0.05] hover:border-white/[0.1] transition-colors text-left"
            >
              <div
                className={`w-7 h-7 rounded-md border flex items-center justify-center flex-shrink-0 ${styles.tile}`}
              >
                <Icon className={`w-3.5 h-3.5 ${styles.icon}`} strokeWidth={2} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[12px] text-slate-200 font-medium truncate">{a.title}</div>
                <div className="text-[10px] text-slate-500 truncate">{a.location}</div>
              </div>
              <div className="text-[10px] font-mono text-slate-500 flex-shrink-0">{a.ago}</div>
            </button>
          );
        })}
      </div>
    </Card>
  );
}

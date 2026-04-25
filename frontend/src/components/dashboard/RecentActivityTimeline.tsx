import { ChevronDown } from "lucide-react";
import { Card } from "./Card";

type Severity = "critical" | "warn" | "info";

interface Event {
  time: string;
  title: string;
  detail: string;
  severity: Severity;
}

const EVENTS: Event[] = [
  {
    time: "14:30",
    title: "AIS signal lost",
    detail: "South Pacific Ocean",
    severity: "critical",
  },
  {
    time: "12:45",
    title: "Entered High Risk Zone",
    detail: "Near Galapagos MPA",
    severity: "warn",
  },
  {
    time: "09:20",
    title: "Rendezvous Detected",
    detail: "With vessel LU RONG YU 998",
    severity: "warn",
  },
  {
    time: "03:15",
    title: "AIS signal regained",
    detail: "South Pacific Ocean",
    severity: "info",
  },
  {
    time: "01:05",
    title: "Port departure",
    detail: "Papeete, French Polynesia",
    severity: "info",
  },
];

const DOT_COLORS: Record<Severity, string> = {
  critical: "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.65)] ring-red-500/30",
  warn: "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)] ring-amber-400/30",
  info: "bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.6)] ring-cyan-400/30",
};

export function RecentActivityTimeline() {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] font-mono tracking-[0.22em] text-cyan-300/70 uppercase">
          Recent Activity Timeline
        </div>
        <button className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-200 transition-colors px-2 py-1 rounded bg-white/[0.03] border border-white/[0.06]">
          Last 48 Hours
          <ChevronDown className="w-3 h-3" />
        </button>
      </div>

      <ul className="relative">
        {/* Vertical track */}
        <div className="absolute left-[5px] top-1.5 bottom-1.5 w-px bg-gradient-to-b from-white/[0.12] via-white/[0.06] to-transparent" />

        {EVENTS.map((e, i) => (
          <li key={i} className="relative flex gap-3 pb-3 last:pb-0">
            <span
              className={`relative z-10 flex-shrink-0 mt-1 w-[11px] h-[11px] rounded-full ring-2 ring-offset-0 ${DOT_COLORS[e.severity]}`}
            />
            <div className="flex-1 min-w-0 -mt-0.5">
              <div className="flex items-baseline gap-2">
                <span className="text-[11px] font-mono text-slate-500 tabular">{e.time}</span>
                <span className="text-[12px] text-slate-200 font-medium truncate">
                  {e.title}
                </span>
              </div>
              <div className="text-[10.5px] text-slate-500 truncate">{e.detail}</div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

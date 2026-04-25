import { Ship, X } from "lucide-react";
import { Card } from "./Card";

interface Props {
  onClose?: () => void;
}

const ROWS: { label: string; value: string; valueClass?: string }[] = [
  { label: "Flag", value: "China" },
  { label: "IMO", value: "412345678", valueClass: "tabular font-mono" },
  { label: "MMSI", value: "412345678", valueClass: "tabular font-mono" },
  { label: "Type", value: "Trawler" },
  { label: "Length", value: "45.2 m" },
  { label: "Last Seen", value: "2m ago" },
];

export function VesselProfilePanel({ onClose }: Props) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] font-mono tracking-[0.22em] text-cyan-300/70 uppercase">
          Vessel Profile
        </div>
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-slate-300 transition-colors"
          aria-label="Close vessel profile"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex items-center gap-3 mb-3 pb-3 border-b border-white/[0.06]">
        <div className="w-10 h-10 rounded-md bg-red-500/15 border border-red-500/30 flex items-center justify-center flex-shrink-0">
          <Ship className="w-5 h-5 text-red-300" strokeWidth={1.75} />
        </div>
        <div className="min-w-0">
          <div className="text-[14px] font-semibold text-white truncate">FU YUAN YU 612</div>
          <div className="text-[10px] text-slate-400">Fishing Vessel</div>
        </div>
      </div>

      {/* Risk score block */}
      <div className="mb-3 p-3 rounded-lg bg-gradient-to-br from-red-500/10 to-red-900/5 border border-red-500/20">
        <div className="flex items-end justify-between">
          <div>
            <div className="text-[10px] font-mono tracking-[0.18em] uppercase text-slate-400">
              Risk Score
            </div>
            <div className="mt-1 text-[10px] text-red-300 font-medium">Very High</div>
          </div>
          <div className="text-right leading-none">
            <span className="text-[40px] font-bold tabular text-white tracking-tight">87</span>
          </div>
        </div>
        <div className="mt-2 relative h-1 rounded-full bg-white/[0.06] overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-amber-400 to-red-500"
            style={{ width: "87%" }}
          />
        </div>
      </div>

      <div className="space-y-2 text-[12px]">
        {ROWS.map((r) => (
          <Row key={r.label} label={r.label} value={r.value} valueClass={r.valueClass} />
        ))}

        <div className="pt-1.5">
          <div className="text-[10px] font-mono tracking-[0.18em] uppercase text-slate-500 mb-0.5">
            Location
          </div>
          <div className="text-[12px] text-slate-200">South Pacific Ocean</div>
          <div className="text-[10px] font-mono text-slate-500 tabular">-15.2345, 165.5678</div>
        </div>

        <Row label="Speed" value="8.2 kn" valueClass="tabular" />
        <Row label="Course" value="245°" valueClass="tabular" />
        <Row
          label="Status"
          value="Under Investigation"
          valueClass="text-red-300 font-medium"
        />
      </div>

      <button className="mt-4 w-full py-2 rounded-md text-[12px] font-medium text-cyan-200 bg-cyan-400/10 border border-cyan-400/30 hover:bg-cyan-400/20 hover:border-cyan-400/50 transition-colors">
        View Full Profile
      </button>
    </Card>
  );
}

function Row({
  label,
  value,
  valueClass = "",
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[10px] font-mono tracking-[0.18em] uppercase text-slate-500">
        {label}
      </span>
      <span className={`text-[12px] text-slate-200 ${valueClass}`}>{value}</span>
    </div>
  );
}

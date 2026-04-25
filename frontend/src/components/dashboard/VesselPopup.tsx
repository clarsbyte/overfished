import { Ship } from "lucide-react";
import { Card } from "./Card";

interface Props {
  onViewProfile?: () => void;
}

export function VesselPopup({ onViewProfile }: Props) {
  return (
    <Card className="w-[300px] p-3.5">
      {/* Optional connector line indicator (purely decorative) */}
      <div className="absolute -left-3 top-1/2 -translate-y-1/2 w-3 h-px bg-cyan-400/40" />

      <div className="flex items-center gap-3 mb-3">
        <div className="w-9 h-9 rounded-md bg-red-500/15 border border-red-500/30 flex items-center justify-center flex-shrink-0">
          <Ship className="w-4 h-4 text-red-300" strokeWidth={1.75} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-semibold text-white truncate">FU YUAN YU 612</div>
          <div className="text-[10px] text-slate-400">Fishing Vessel</div>
        </div>
        <span className="px-2 py-0.5 rounded text-[9px] font-mono tracking-wider uppercase bg-red-500/15 text-red-300 border border-red-500/30">
          High Risk
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 mb-3">
        <Stat label="Speed" value="8.2 kn" />
        <Stat label="Course" value="245°" />
        <Stat label="Updated" value="2m ago" />
      </div>

      <button
        onClick={onViewProfile}
        className="w-full py-2 rounded-md text-[11px] font-medium text-cyan-300 bg-cyan-400/10 border border-cyan-400/30 hover:bg-cyan-400/20 hover:border-cyan-400/50 transition-colors"
      >
        View Profile
      </button>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white/[0.03] border border-white/[0.05] rounded px-2 py-1.5">
      <div className="text-[9px] font-mono tracking-wider text-slate-500 uppercase mb-0.5">
        {label}
      </div>
      <div className="text-[11px] font-medium text-slate-100 tabular">{value}</div>
    </div>
  );
}

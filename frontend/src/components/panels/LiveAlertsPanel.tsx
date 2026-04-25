import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

type RegionRisk = "confirmed_iuu" | "high_risk" | "suspect" | "safe";

const RISK_DOT: Record<RegionRisk, string> = {
  confirmed_iuu: "bg-red-500",
  high_risk: "bg-orange-400",
  suspect: "bg-amber-300",
  safe: "bg-emerald-400",
};

const RISK_LABEL: Record<RegionRisk, string> = {
  confirmed_iuu: "IUU CONFIRMED",
  high_risk: "HIGH RISK",
  suspect: "SUSPECT",
  safe: "SAFE",
};

interface Props {
  onRegionSelect?: (regionId: string) => void;
}

export function LiveAlertsPanel({ onRegionSelect }: Props) {
  const regionsQ = useQuery({
    queryKey: ["fisheryRegions"],
    queryFn: () => api.fisheryRegions(),
  });

  const alerts = (regionsQ.data ?? [])
    .filter((r) => r.risk !== "safe")
    .sort((a, b) => severityRank(b.risk) - severityRank(a.risk))
    .slice(0, 5);

  return (
    <div className="w-80 pointer-events-auto bg-ink-900/85 backdrop-blur border border-cyan-500/20 rounded shadow-lg">
      <div className="flex items-center justify-between px-3 py-2 border-b border-cyan-500/15">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
          <span className="text-[10px] font-mono tracking-[0.2em] text-cyan-300/80 uppercase">
            Live alerts
          </span>
        </div>
        <span className="text-[10px] font-mono text-slate-500">{alerts.length} active</span>
      </div>

      <ul className="divide-y divide-cyan-500/10">
        {alerts.length === 0 && (
          <li className="px-3 py-3 text-xs font-mono text-slate-500">No active alerts</li>
        )}
        {alerts.map((r) => (
          <li
            key={r.region_id}
            onClick={() => onRegionSelect?.(r.region_id)}
            className="px-3 py-2.5 flex items-start gap-2.5 cursor-pointer hover:bg-cyan-500/5 transition-colors"
          >
            <span
              className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${RISK_DOT[r.risk]} animate-pulse`}
            />
            <div className="flex-1 min-w-0">
              <div className="text-xs text-slate-200 truncate">{r.name}</div>
              <div className="text-[10px] font-mono text-slate-500 mt-0.5">
                {RISK_LABEL[r.risk]}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function severityRank(r: RegionRisk): number {
  return r === "confirmed_iuu" ? 3 : r === "high_risk" ? 2 : r === "suspect" ? 1 : 0;
}

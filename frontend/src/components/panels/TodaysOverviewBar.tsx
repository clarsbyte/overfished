import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";

export function TodaysOverviewBar() {
  const vesselsQ = useQuery({ queryKey: ["vessels"], queryFn: () => api.vessels() });
  const regionsQ = useQuery({
    queryKey: ["fisheryRegions"],
    queryFn: () => api.fisheryRegions(),
  });

  const activeVessels = vesselsQ.data?.length ?? 0;
  const regions = regionsQ.data ?? [];
  const alertsToday = regions.filter((r) => r.risk !== "safe").length;
  const highRiskZones = regions.filter(
    (r) => r.risk === "confirmed_iuu" || r.risk === "high_risk",
  ).length;

  return (
    <div className="pointer-events-auto bg-ink-900/85 backdrop-blur border border-cyan-500/20 rounded shadow-lg flex divide-x divide-cyan-500/15">
      <Tile label="Active vessels" value={activeVessels} accent="text-cyan-300" />
      <Tile label="Alerts today" value={alertsToday} accent="text-amber-300" />
      <Tile label="High-risk zones" value={highRiskZones} accent="text-red-400" />
    </div>
  );
}

function Tile({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  return (
    <div className="px-5 py-2.5 min-w-[110px] text-center">
      <div className={`text-2xl font-mono leading-tight ${accent}`}>{value}</div>
      <div className="text-[9px] font-mono uppercase tracking-[0.2em] text-slate-500 mt-0.5">
        {label}
      </div>
    </div>
  );
}

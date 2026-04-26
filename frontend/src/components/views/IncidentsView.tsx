import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2, MapPin } from "lucide-react";
import { LiquidGlass } from "../LiquidGlass";

type RegionRisk = "confirmed_iuu" | "high_risk" | "suspect" | "safe";

const RISK_RANK: Record<RegionRisk, number> = {
    confirmed_iuu: 3,
    high_risk: 2,
    suspect: 1,
    safe: 0,
};

const RISK_TILE: Record<RegionRisk, { dot: string; tile: string; label: string; text: string }> = {
    confirmed_iuu: {
        dot: "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.65)]",
        tile: "bg-red-500/10 border-red-500/30",
        text: "text-red-300",
        label: "IUU CONFIRMED",
    },
    high_risk: {
        dot: "bg-orange-400 shadow-[0_0_8px_rgba(251,146,60,0.55)]",
        tile: "bg-orange-400/10 border-orange-400/30",
        text: "text-orange-300",
        label: "HIGH RISK",
    },
    suspect: {
        dot: "bg-yellow-400 shadow-[0_0_8px_rgba(250,204,21,0.5)]",
        tile: "bg-yellow-400/10 border-yellow-400/25",
        text: "text-yellow-300",
        label: "SUSPECT",
    },
    safe: {
        dot: "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]",
        tile: "bg-emerald-400/10 border-emerald-400/25",
        text: "text-emerald-300",
        label: "SAFE",
    },
};

interface Props {
    onSelectRegion: (regionId: string) => void;
}

/**
 * Incidents view — every named fishery region from /fishery-regions, sorted
 * by severity. Clicking flies the globe camera to the region centroid.
 */
export function IncidentsView({ onSelectRegion }: Props) {
    const regionsQ = useQuery({
        queryKey: ["fisheryRegions"],
        queryFn: () => api.fisheryRegions(),
    });

    const sorted = (regionsQ.data ?? [])
        .slice()
        .sort((a, b) => RISK_RANK[b.risk] - RISK_RANK[a.risk]);

    const counts = {
        confirmed_iuu: sorted.filter((r) => r.risk === "confirmed_iuu").length,
        high_risk: sorted.filter((r) => r.risk === "high_risk").length,
        suspect: sorted.filter((r) => r.risk === "suspect").length,
        safe: sorted.filter((r) => r.risk === "safe").length,
    };

    return (
        <aside className="w-80 h-full flex flex-col gap-4 p-4 pointer-events-auto overflow-y-auto">
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">
                            Incident Severity
                        </h2>
                        <AlertTriangle className="w-4 h-4 text-red-400" />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <SeverityTile risk="confirmed_iuu" count={counts.confirmed_iuu} />
                        <SeverityTile risk="high_risk" count={counts.high_risk} />
                        <SeverityTile risk="suspect" count={counts.suspect} />
                        <SeverityTile risk="safe" count={counts.safe} />
                    </div>
                </div>
            </LiquidGlass>

            <LiquidGlass className="rounded-[30px] flex-1 min-h-0" chromaticAberration={2} depth={8}>
                <div className="p-5 flex flex-col h-full min-h-0">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">All Incidents</h2>
                        <span className="text-[10px] font-mono text-slate-500">{sorted.length}</span>
                    </div>

                    <div className="flex-1 overflow-y-auto -mx-2 px-2 space-y-2">
                        {regionsQ.isLoading && (
                            <div className="flex items-center gap-2 text-xs text-slate-500 py-3">
                                <Loader2 className="w-3 h-3 animate-spin" /> loading…
                            </div>
                        )}
                        {sorted.map((r) => {
                            const meta = RISK_TILE[r.risk];
                            return (
                                <button
                                    key={r.region_id}
                                    onClick={() => onSelectRegion(r.region_id)}
                                    className="w-full flex items-center gap-3 px-2.5 py-2 rounded-xl hover:bg-white/5 transition-colors text-left group"
                                >
                                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${meta.dot}`} />
                                    <div className="flex-1 min-w-0">
                                        <div className="text-[12.5px] text-slate-100 font-medium truncate">{r.name}</div>
                                        <div className={`text-[10px] font-mono uppercase tracking-widest ${meta.text}`}>
                                            {meta.label}
                                        </div>
                                    </div>
                                    <MapPin className="w-3.5 h-3.5 text-slate-500 group-hover:text-cyan-300 transition-colors" />
                                </button>
                            );
                        })}
                    </div>
                </div>
            </LiquidGlass>
        </aside>
    );
}

function SeverityTile({ risk, count }: { risk: RegionRisk; count: number }) {
    const meta = RISK_TILE[risk];
    return (
        <div className={`rounded-xl border p-3 ${meta.tile}`}>
            <div className="text-2xl font-bold text-slate-100 tabular-nums">{count}</div>
            <div className={`text-[9px] font-bold uppercase tracking-wider mt-0.5 ${meta.text}`}>
                {meta.label}
            </div>
        </div>
    );
}

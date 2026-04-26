import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { LiquidGlass } from "../LiquidGlass";

const DEMO_CASE_ID = "demo";

type RegionRisk = "confirmed_iuu" | "high_risk" | "suspect" | "safe";

const RISK_COLOR: Record<RegionRisk, string> = {
    confirmed_iuu: "bg-red-500",
    high_risk: "bg-orange-400",
    suspect: "bg-yellow-400",
    safe: "bg-emerald-400",
};

const RISK_LABEL: Record<RegionRisk, string> = {
    confirmed_iuu: "IUU CONFIRMED",
    high_risk: "HIGH RISK",
    suspect: "SUSPECT",
    safe: "SAFE",
};

/**
 * Analytics view — pulls live metrics from /vessels, /fishery-regions, and
 * /case/:id/fine. Renders headline KPIs + a horizontal stack of risk-share
 * bars so operators can see the global risk distribution at a glance.
 */
export function AnalyticsView() {
    const vesselsQ = useQuery({ queryKey: ["vessels"], queryFn: () => api.vessels() });
    const regionsQ = useQuery({
        queryKey: ["fisheryRegions"],
        queryFn: () => api.fisheryRegions(),
    });
    const heatmapQ = useQuery({ queryKey: ["heatmap"], queryFn: () => api.heatmap() });
    const fineQ = useQuery({
        queryKey: ["fine", DEMO_CASE_ID],
        queryFn: () => api.caseFine(DEMO_CASE_ID),
    });

    const regions = regionsQ.data ?? [];
    const totalRegions = regions.length || 1;
    const counts: Record<RegionRisk, number> = {
        confirmed_iuu: regions.filter((r) => r.risk === "confirmed_iuu").length,
        high_risk: regions.filter((r) => r.risk === "high_risk").length,
        suspect: regions.filter((r) => r.risk === "suspect").length,
        safe: regions.filter((r) => r.risk === "safe").length,
    };
    const totalHours = (heatmapQ.data ?? []).reduce((s, p) => s + p.hours, 0);
    const fine = fineQ.data?.total_fine_usd ?? 0;

    return (
        <aside className="w-80 h-full flex flex-col gap-4 p-4 pointer-events-auto overflow-y-auto">
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Network Health</h2>
                    <div className="grid grid-cols-2 gap-3">
                        <Kpi value={vesselsQ.data?.length ?? 0} label="Active Vessels" tone="text-cyan-300" />
                        <Kpi value={regions.length} label="Tracked Regions" tone="text-slate-100" />
                        <Kpi
                            value={Math.round(totalHours)}
                            label="Fishing Hours"
                            tone="text-amber-300"
                            suffix="h"
                        />
                        <Kpi
                            value={fine}
                            label="Pending Fine"
                            tone="text-red-300"
                            isCurrency
                        />
                    </div>
                </div>
            </LiquidGlass>

            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Risk Distribution</h2>
                    {/* Stacked horizontal bar */}
                    <div className="flex h-3 rounded-full overflow-hidden bg-white/[0.04]">
                        {(Object.keys(counts) as RegionRisk[]).map((k) => {
                            const w = (counts[k] / totalRegions) * 100;
                            if (w === 0) return null;
                            return (
                                <div
                                    key={k}
                                    style={{ width: `${w}%` }}
                                    className={`${RISK_COLOR[k]}`}
                                    title={`${RISK_LABEL[k]} · ${counts[k]}`}
                                />
                            );
                        })}
                    </div>
                    <div className="space-y-1.5">
                        {(Object.keys(counts) as RegionRisk[]).map((k) => (
                            <div key={k} className="flex items-center gap-2 text-[11px]">
                                <span className={`w-2 h-2 rounded-full ${RISK_COLOR[k]}`} />
                                <span className="text-slate-300 flex-1">{RISK_LABEL[k]}</span>
                                <span className="font-mono tabular-nums text-slate-400">{counts[k]}</span>
                                <span className="font-mono tabular-nums text-slate-500 w-10 text-right">
                                    {((counts[k] / totalRegions) * 100).toFixed(0)}%
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </LiquidGlass>
        </aside>
    );
}

function Kpi({
    value,
    label,
    tone,
    suffix,
    isCurrency,
}: {
    value: number;
    label: string;
    tone: string;
    suffix?: string;
    isCurrency?: boolean;
}) {
    const display = isCurrency
        ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
        : `${value.toLocaleString()}${suffix ?? ""}`;
    return (
        <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-3">
            <div className={`text-xl font-bold tabular-nums ${tone}`}>{display}</div>
            <div className="text-[9px] font-bold text-slate-500 uppercase tracking-wider mt-0.5">
                {label}
            </div>
        </div>
    );
}

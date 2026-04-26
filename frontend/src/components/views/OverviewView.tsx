import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, BookOpen, ChevronRight, Loader2, Scale } from "lucide-react";
import { LiquidGlass } from "../LiquidGlass";

type RegionRisk = "confirmed_iuu" | "high_risk" | "suspect" | "safe";

const RISK_RANK: Record<RegionRisk, number> = {
    confirmed_iuu: 3,
    high_risk: 2,
    suspect: 1,
    safe: 0,
};

const RISK_LABEL: Record<RegionRisk, string> = {
    confirmed_iuu: "IUU CONFIRMED",
    high_risk: "HIGH RISK",
    suspect: "SUSPECT",
    safe: "SAFE",
};

interface Props {
    onSelectRegion: (regionId: string) => void;
    onSeeAll?: () => void;
    selectedRegionId?: string | null;
}

/**
 * Overview view — first tab. Replaces the old hardcoded right panel with
 * three live data cards: alerts (fishery regions), risk heatmap (heatmap
 * density bars), and today's overview (vessel + alert counts).
 */
export function OverviewView({ onSelectRegion, onSeeAll, selectedRegionId }: Props) {
    const regionsQ = useQuery({
        queryKey: ["fisheryRegions"],
        queryFn: () => api.fisheryRegions(),
    });
    const heatmapQ = useQuery({ queryKey: ["heatmap"], queryFn: () => api.heatmap() });
    const vesselsQ = useQuery({ queryKey: ["vessels"], queryFn: () => api.vessels() });
    const regulationsQ = useQuery({
        queryKey: ["regulations", selectedRegionId],
        queryFn: () => api.regulations(selectedRegionId!),
        enabled: Boolean(selectedRegionId),
    });
    const citationsQ = useQuery({
        queryKey: ["citations", selectedRegionId],
        queryFn: () => api.citations(selectedRegionId!),
        enabled: Boolean(selectedRegionId),
    });

    const regions = regionsQ.data ?? [];
    const alerts = regions
        .filter((r) => r.risk !== "safe")
        .sort((a, b) => RISK_RANK[b.risk] - RISK_RANK[a.risk])
        .slice(0, 5);

    const activeVessels = vesselsQ.data?.length ?? 0;
    const alertsToday = regions.filter((r) => r.risk !== "safe").length;
    const highRiskZones = regions.filter(
        (r) => r.risk === "confirmed_iuu" || r.risk === "high_risk",
    ).length;

    return (
        <aside className="w-80 h-full flex flex-col gap-4 p-4 pointer-events-auto overflow-y-auto">
            {/* Live Alerts (sourced from /fishery-regions) */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Live Alerts</h2>
                        <button
                            onClick={onSeeAll}
                            className="text-[10px] text-cyan-400 hover:text-cyan-300 font-bold uppercase tracking-widest transition-colors flex items-center gap-1 group"
                        >
                            View all
                            <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                        </button>
                    </div>
                    <div className="space-y-3">
                        {regionsQ.isLoading && (
                            <div className="flex items-center gap-2 text-xs text-slate-500">
                                <Loader2 className="w-3 h-3 animate-spin" /> loading…
                            </div>
                        )}
                        {!regionsQ.isLoading && alerts.length === 0 && (
                            <div className="text-xs text-slate-500">No active alerts.</div>
                        )}
                        {alerts.map((r) => (
                            <AlertItem
                                key={r.region_id}
                                risk={r.risk}
                                title={r.name}
                                loc={RISK_LABEL[r.risk]}
                                onClick={() => onSelectRegion(r.region_id)}
                            />
                        ))}
                    </div>
                </div>
            </LiquidGlass>

            {/* Risk Heatmap — backed by /heatmap latitude-density bars */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Risk Heatmap</h2>
                        <span className="text-[10px] font-mono text-slate-500">
                            {heatmapQ.data?.length ?? 0} pts
                        </span>
                    </div>
                    <HeatmapBars data={heatmapQ.data ?? []} />
                </div>
            </LiquidGlass>

            {/* Today's Overview */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Today's Overview</h2>
                    <div className="grid grid-cols-3 gap-2">
                        <OverviewStat value={activeVessels} label="Active Vessels" />
                        <OverviewStat value={alertsToday} label="Alerts Today" />
                        <OverviewStat value={highRiskZones} label="High Risk Zones" />
                    </div>
                </div>
            </LiquidGlass>

            {/* Regulations — shown when a region is selected */}
            {selectedRegionId && (
                <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                    <div className="p-5 space-y-3">
                        <div className="flex items-center gap-2">
                            <Scale className="w-3.5 h-3.5 text-cyan-400" />
                            <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">
                                Regulations
                            </h2>
                            {regulationsQ.isLoading && <Loader2 className="w-3 h-3 animate-spin text-slate-500" />}
                        </div>
                        {!regulationsQ.isLoading && (regulationsQ.data ?? []).length === 0 && (
                            <p className="text-[11px] text-slate-500">No regulations found for this region.</p>
                        )}
                        <ul className="space-y-2">
                            {(regulationsQ.data ?? []).slice(0, 4).map((r) => (
                                <li key={r.rule_id} className="space-y-0.5">
                                    <div className="text-[11px] font-medium text-slate-100">{r.category.replace(/_/g, " ")}</div>
                                    <div className="text-[10px] text-slate-500 leading-snug line-clamp-2">{r.description}</div>
                                    {r.penalty_text && (
                                        <div className="text-[10px] font-mono text-red-400/80">{r.penalty_text}</div>
                                    )}
                                </li>
                            ))}
                        </ul>
                    </div>
                </LiquidGlass>
            )}

            {/* Legal Citations — shown when a region is selected */}
            {selectedRegionId && (
                <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                    <div className="p-5 space-y-3">
                        <div className="flex items-center gap-2">
                            <BookOpen className="w-3.5 h-3.5 text-cyan-400" />
                            <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">
                                Legal Citations
                            </h2>
                            {citationsQ.isLoading && <Loader2 className="w-3 h-3 animate-spin text-slate-500" />}
                        </div>
                        {!citationsQ.isLoading && (citationsQ.data ?? []).length === 0 && (
                            <p className="text-[11px] text-slate-500">No citations found for this region.</p>
                        )}
                        <ul className="space-y-2.5">
                            {(citationsQ.data ?? []).slice(0, 4).map((c, i) => (
                                <li key={i} className="space-y-0.5">
                                    <div className="flex items-start gap-2">
                                        <span className="text-[9px] font-bold uppercase tracking-wider text-cyan-500/70 bg-cyan-500/10 border border-cyan-500/20 rounded px-1.5 py-0.5 flex-shrink-0 mt-0.5">
                                            {c.layer}
                                        </span>
                                        <div className="text-[11px] font-medium text-slate-100 leading-snug">{c.instrument}</div>
                                    </div>
                                    {c.excerpt && (
                                        <div className="text-[10px] text-slate-500 leading-snug line-clamp-2 pl-1">{c.excerpt}</div>
                                    )}
                                </li>
                            ))}
                        </ul>
                    </div>
                </LiquidGlass>
            )}
        </aside>
    );
}

const RISK_ICON: Record<RegionRisk, { color: string; Icon: typeof AlertTriangle }> = {
    confirmed_iuu: { color: "text-red-500", Icon: AlertTriangle },
    high_risk: { color: "text-orange-400", Icon: AlertTriangle },
    suspect: { color: "text-yellow-400", Icon: AlertCircle },
    safe: { color: "text-cyan-400", Icon: AlertCircle },
};

function AlertItem({
    risk,
    title,
    loc,
    onClick,
}: {
    risk: RegionRisk;
    title: string;
    loc: string;
    onClick?: () => void;
}) {
    const { color, Icon } = RISK_ICON[risk];
    return (
        <button
            onClick={onClick}
            className="w-full flex gap-3 group cursor-pointer hover:bg-white/5 p-2 -mx-2 rounded-xl transition-colors text-left"
        >
            <div className="mt-0.5">
                <Icon className={`w-4 h-4 ${color}`} />
            </div>
            <div className="flex-1 min-w-0">
                <div className="flex justify-between items-start gap-2">
                    <h4 className="text-[13px] font-semibold text-slate-100 truncate">{title}</h4>
                </div>
                <p className="text-[11px] text-slate-500 truncate">{loc}</p>
            </div>
        </button>
    );
}

function OverviewStat({ value, label }: { value: number; label: string }) {
    return (
        <div className="flex flex-col gap-1">
            <span className="text-xl font-bold text-slate-100 tracking-tight tabular-nums">{value}</span>
            <span className="text-[9px] font-bold text-slate-500 uppercase tracking-tighter leading-tight">
                {label}
            </span>
        </div>
    );
}

const BANDS = 14;

function HeatmapBars({ data }: { data: { lat: number; lon: number; hours: number }[] }) {
    if (data.length === 0) {
        return (
            <div className="flex items-end gap-0.5 h-16">
                {Array.from({ length: BANDS }).map((_, i) => (
                    <div key={i} className="flex-1 bg-slate-800/60 rounded-sm" style={{ height: "8%" }} />
                ))}
            </div>
        );
    }
    const minLat = Math.min(...data.map((p) => p.lat));
    const maxLat = Math.max(...data.map((p) => p.lat));
    const span = maxLat - minLat || 1;
    const buckets = new Array(BANDS).fill(0);
    for (const p of data) {
        const idx = Math.min(BANDS - 1, Math.floor(((p.lat - minLat) / span) * BANDS));
        buckets[idx] += p.hours;
    }
    const max = Math.max(...buckets, 1);
    return (
        <div>
            <div className="flex items-end gap-0.5 h-16">
                {buckets.map((v, i) => {
                    const intensity = v / max;
                    return (
                        <div
                            key={i}
                            className="flex-1 rounded-sm"
                            style={{
                                height: `${Math.max(intensity * 100, 6)}%`,
                                background: `rgba(255, ${Math.round(180 - intensity * 140)}, ${Math.round(60 - intensity * 40)}, ${0.4 + intensity * 0.55})`,
                            }}
                        />
                    );
                })}
            </div>
            <div className="flex justify-between text-[9px] font-mono text-slate-500 mt-1.5">
                <span>SOUTH</span>
                <span className="text-slate-600">latitude</span>
                <span>NORTH</span>
            </div>
        </div>
    );
}

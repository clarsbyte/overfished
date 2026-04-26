import { api } from "@/lib/api";
import type { Vessel } from "@/types/schemas";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Search, Ship } from "lucide-react";
import { useMemo, useState } from "react";
import { LiquidGlass } from "../LiquidGlass";

interface Props {
    selectedMmsi?: string | null;
    onSelectVessel: (vessel: Vessel) => void;
}

/**
 * Vessels view — lists every vessel returned by /vessels for the active
 * region. Clicking a row notifies App so it can sync the globe camera and
 * surface the floating VesselDetailsCard.
 */
export function VesselsView({ selectedMmsi, onSelectVessel }: Props) {
    const vesselsQ = useQuery({ queryKey: ["vessels"], queryFn: () => api.vessels() });
    const [query, setQuery] = useState("");

    const filtered = useMemo(() => {
        const all = vesselsQ.data ?? [];
        const q = query.trim().toLowerCase();
        if (!q) return all;
        return all.filter(
            (v) =>
                (v.name ?? "").toLowerCase().includes(q) ||
                v.mmsi.includes(q) ||
                (v.flag ?? "").toLowerCase().includes(q),
        );
    }, [vesselsQ.data, query]);

    return (
        <aside className="w-80 h-full flex flex-col gap-4 p-4 pointer-events-auto overflow-y-auto">
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Tracked Vessels</h2>
                        <span className="text-[10px] font-mono text-slate-500">
                            {vesselsQ.data?.length ?? 0}
                        </span>
                    </div>
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
                        <input
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Filter by name, flag, MMSI…"
                            className="w-full bg-white/5 border border-white/10 rounded-xl pl-9 pr-3 py-2 text-[12px] text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500/30"
                        />
                    </div>
                </div>
            </LiquidGlass>

            <LiquidGlass className="rounded-[30px] flex-1 min-h-0" chromaticAberration={2} depth={8}>
                <div className="p-5 flex flex-col h-full min-h-0">
                    <div className="flex items-center justify-between mb-3">
                        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Fleet</h2>
                        <span className="text-[10px] font-mono text-slate-500">{filtered.length}</span>
                    </div>
                    <div className="flex-1 overflow-y-auto -mx-2 px-2 space-y-1.5">
                        {vesselsQ.isLoading && (
                            <div className="flex items-center gap-2 text-xs text-slate-500 py-3">
                                <Loader2 className="w-3 h-3 animate-spin" /> loading…
                            </div>
                        )}
                        {!vesselsQ.isLoading && filtered.length === 0 && (
                            <div className="text-xs text-slate-500 py-2">No vessels match your filter.</div>
                        )}
                        {filtered.map((v) => {
                            const active = v.mmsi === selectedMmsi;
                            return (
                                <button
                                    key={v.mmsi}
                                    onClick={() => onSelectVessel(v)}
                                    className={[
                                        "w-full flex items-center gap-3 px-2.5 py-2 rounded-xl text-left transition-colors",
                                        active
                                            ? "bg-cyan-500/15 border border-cyan-500/35"
                                            : "hover:bg-white/5 border border-transparent",
                                    ].join(" ")}
                                >
                                    <div
                                        className={[
                                            "w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0",
                                            active
                                                ? "bg-cyan-400/15 border border-cyan-400/40"
                                                : "bg-white/[0.05] border border-white/[0.08]",
                                        ].join(" ")}
                                    >
                                        <Ship className={`w-4 h-4 ${active ? "text-cyan-300" : "text-slate-300"}`} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-[13px] font-semibold text-slate-100 truncate">
                                            {v.name ?? "Unknown vessel"}
                                        </div>
                                        <div className="text-[10px] font-mono text-slate-500 tabular-nums truncate">
                                            MMSI {v.mmsi}
                                            {v.flag ? ` · ${v.flag}` : ""}
                                            {v.gear_type ? ` · ${v.gear_type}` : ""}
                                        </div>
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                </div>
            </LiquidGlass>
        </aside>
    );
}

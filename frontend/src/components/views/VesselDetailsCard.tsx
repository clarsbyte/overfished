import { api } from "@/lib/api";
import type { Vessel } from "@/types/schemas";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertTriangle, Loader2, Phone, PlayCircle, Radio, Ship, X } from "lucide-react";
import { LiquidGlass } from "../LiquidGlass";

const DEMO_CASE_ID = "demo";

interface Props {
    vessel: Vessel;
    onClose: () => void;
    onRunDemo: () => void;
    onNotifyPort: () => void;
    runDemoPending?: boolean;
    notifyPortPending?: boolean;
}

const RISK_TONE: Record<string, { tile: string; text: string; label: string }> = {
    confirmed_iuu: { tile: "bg-red-500/15 border-red-500/35", text: "text-red-300", label: "IUU CONFIRMED" },
    high_risk: { tile: "bg-orange-500/15 border-orange-500/35", text: "text-orange-300", label: "HIGH RISK" },
    suspect: { tile: "bg-amber-400/15 border-amber-400/30", text: "text-amber-200", label: "SUSPECT" },
    safe: { tile: "bg-emerald-500/15 border-emerald-500/35", text: "text-emerald-300", label: "SAFE" },
};

/**
 * VesselDetailsCard — floating LiquidGlass card that appears whenever a
 * vessel is selected (either via globe click or the Vessels view list).
 * Pulls real vessel info, risk score, and recent events from the backend
 * and exposes the demo-flow + notify-port mutations as one-click actions.
 */
export function VesselDetailsCard({
    vessel,
    onClose,
    onRunDemo,
    onNotifyPort,
    runDemoPending,
    notifyPortPending,
}: Props) {
    const riskQ = useQuery({
        queryKey: ["risk", vessel.mmsi],
        queryFn: () => api.vesselRisk(vessel.mmsi),
        retry: 0,
    });
    const eventsQ = useQuery({
        queryKey: ["events", vessel.mmsi],
        queryFn: () => api.vesselEvents(vessel.mmsi),
        retry: 0,
    });
    const hailM = useMutation({
        mutationFn: () => api.hailVessel(DEMO_CASE_ID),
        onSuccess: (data) => {
            if (data.audio_url) {
                new Audio(data.audio_url).play().catch(() => {});
            }
        },
    });

    const riskScore = riskQ.data?.risk_score ?? 0;
    const riskLevel = riskQ.data?.classification ?? "safe";
    const tone = RISK_TONE[riskLevel] ?? RISK_TONE.safe;
    const events = (eventsQ.data ?? []).slice(0, 3);

    return (
        <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.96 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="w-[340px]"
        >
            <LiquidGlass className="rounded-[28px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    {/* Header */}
                    <div className="flex items-start gap-3">
                        <div className={`w-11 h-11 rounded-xl border flex items-center justify-center flex-shrink-0 ${tone.tile}`}>
                            <Ship className={`w-5 h-5 ${tone.text}`} strokeWidth={1.75} />
                        </div>
                        <div className="flex-1 min-w-0">
                            <div className="text-[10px] font-mono tracking-[0.22em] text-slate-400 uppercase">
                                Vessel
                            </div>
                            <div className="text-[15px] font-semibold text-white truncate leading-tight">
                                {vessel.name ?? "Unknown vessel"}
                            </div>
                            <div className="text-[10px] font-mono text-slate-500 mt-0.5 tabular-nums">
                                MMSI {vessel.mmsi}
                                {vessel.flag ? ` · ${vessel.flag}` : ""}
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            aria-label="Close vessel details"
                            className="p-1.5 -m-1.5 text-slate-500 hover:text-cyan-300 transition-colors"
                        >
                            <X className="w-4 h-4" />
                        </button>
                    </div>

                    {/* Risk band */}
                    <div className={`rounded-2xl border p-3 ${tone.tile}`}>
                        <div className="flex items-end justify-between">
                            <div>
                                <div className="text-[10px] font-mono tracking-[0.18em] uppercase text-slate-400">
                                    Risk Score
                                </div>
                                <div className={`mt-1 text-[10px] font-bold tracking-widest ${tone.text}`}>
                                    {tone.label}
                                </div>
                            </div>
                            <div className="text-right leading-none">
                                <span className="text-[36px] font-bold tabular-nums text-white tracking-tight">
                                    {Math.round(riskScore)}
                                </span>
                            </div>
                        </div>
                        <div className="mt-2 relative h-1 rounded-full bg-white/[0.08] overflow-hidden">
                            <div
                                className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-amber-300 via-orange-400 to-red-500 transition-all"
                                style={{ width: `${Math.min(Math.max(riskScore, 0), 100)}%` }}
                            />
                        </div>
                    </div>

                    {/* Stats grid */}
                    <div className="grid grid-cols-3 gap-2">
                        <Stat label="IMO" value={vessel.imo ?? "—"} mono />
                        <Stat label="Gear" value={vessel.gear_type ?? "—"} />
                        <Stat
                            label="Length"
                            value={vessel.length_m ? `${vessel.length_m.toFixed(0)} m` : "—"}
                        />
                    </div>

                    {vessel.last_position && (
                        <Stat
                            label="Position"
                            value={`${vessel.last_position.lat.toFixed(2)}, ${vessel.last_position.lon.toFixed(2)}`}
                            mono
                            full
                        />
                    )}

                    {/* Events */}
                    {events.length > 0 && (
                        <div className="pt-3 border-t border-white/[0.06] space-y-2">
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                                Recent events
                            </div>
                            <ul className="space-y-1.5">
                                {events.map((e) => (
                                    <li key={e.event_id} className="flex items-start gap-2 text-[11px]">
                                        <AlertTriangle className="w-3 h-3 text-amber-300 mt-0.5 flex-shrink-0" />
                                        <span className="flex-1 text-slate-300 leading-snug">
                                            <span className="text-slate-100 font-medium">
                                                {e.type.replace(/_/g, " ").toLowerCase()}
                                            </span>
                                            {e.duration_hours ? (
                                                <span className="text-slate-500">
                                                    {" "}
                                                    — {e.duration_hours.toFixed(1)}h
                                                </span>
                                            ) : null}
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {/* Actions */}
                    <div className="grid grid-cols-2 gap-2 pt-2">
                        <button
                            onClick={onRunDemo}
                            disabled={runDemoPending}
                            className="flex items-center justify-center gap-1.5 py-2 rounded-xl bg-red-500/10 border border-red-500/40 text-red-200 hover:bg-red-500/20 hover:border-red-500/70 transition-colors text-[11px] font-mono tracking-[0.16em] uppercase disabled:opacity-50"
                        >
                            <PlayCircle className="w-3.5 h-3.5" />
                            {runDemoPending ? "…" : "Run flow"}
                        </button>
                        <button
                            onClick={onNotifyPort}
                            disabled={notifyPortPending}
                            className="flex items-center justify-center gap-1.5 py-2 rounded-xl bg-amber-500/10 border border-amber-500/40 text-amber-200 hover:bg-amber-500/20 hover:border-amber-500/70 transition-colors text-[11px] font-mono tracking-[0.16em] uppercase disabled:opacity-50"
                        >
                            <Phone className="w-3.5 h-3.5" />
                            {notifyPortPending ? "…" : "Notify port"}
                        </button>
                    </div>
                    <button
                        onClick={() => hailM.mutate()}
                        disabled={hailM.isPending}
                        className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-200 hover:bg-cyan-500/20 hover:border-cyan-500/60 transition-colors text-[11px] font-mono tracking-[0.16em] uppercase disabled:opacity-50"
                    >
                        {hailM.isPending ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                            <Radio className="w-3.5 h-3.5" />
                        )}
                        {hailM.isPending ? "Hailing…" : hailM.isSuccess ? "Hailed ✓" : "Hail vessel"}
                    </button>
                </div>
            </LiquidGlass>
        </motion.div>
    );
}

function Stat({
    label,
    value,
    mono,
    full,
}: {
    label: string;
    value: string;
    mono?: boolean;
    full?: boolean;
}) {
    return (
        <div className={`bg-white/[0.03] border border-white/[0.06] rounded-xl px-2.5 py-1.5 ${full ? "col-span-3" : ""}`}>
            <div className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">{label}</div>
            <div className={`text-[12px] text-slate-100 truncate ${mono ? "font-mono tabular-nums" : ""}`}>
                {value}
            </div>
        </div>
    );
}

import { AlertTriangle, AlertCircle, ChevronRight } from "lucide-react";
import { LiquidGlass } from "./LiquidGlass";

export function DashboardRightPanel() {
    return (
        <aside className="w-80 h-full flex flex-col gap-4 p-4 pointer-events-auto overflow-y-auto">
            {/* Live Alerts */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Live Alerts</h2>
                        <button className="text-[10px] text-cyan-400 hover:text-cyan-300 font-bold uppercase tracking-widest transition-colors flex items-center gap-1 group">
                            View all
                            <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                        </button>
                    </div>
                    <div className="space-y-3">
                        <AlertItem type="danger" title="Suspicious Activity" loc="North Pacific" time="2m ago" />
                        <AlertItem type="warning" title="Dark Vessel Detected" loc="West Africa Coast" time="15m ago" />
                        <AlertItem type="info" title="AIS Anomaly" loc="South China Sea" time="28m ago" />
                        <AlertItem type="warning" title="Zone Violation" loc="Galapagos Marine Reserve" time="45m ago" />
                    </div>
                </div>
            </LiquidGlass>

            {/* Risk Heatmap */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Risk Heatmap</h2>
                    <div className="relative aspect-video bg-slate-900/40 rounded-xl overflow-hidden border border-white/5">
                        <img
                            src="https://upload.wikimedia.org/wikipedia/commons/e/ec/World_map_blank_without_borders.svg"
                            alt="World Map Heatmap"
                            className="w-full h-full object-cover opacity-20 invert"
                        />
                        <div className="absolute top-1/4 left-1/3 w-2 h-2 bg-red-500 rounded-full animate-pulse shadow-[0_0_8px_rgba(239,68,68,0.8)]" />
                        <div className="absolute top-1/2 left-2/3 w-1.5 h-1.5 bg-orange-400 rounded-full animate-pulse shadow-[0_0_6px_rgba(251,146,60,0.8)]" />
                        <div className="absolute bottom-1/3 left-1/2 w-1 h-1 bg-yellow-400 rounded-full animate-pulse shadow-[0_0_4px_rgba(250,204,21,0.8)]" />
                        <div className="absolute bottom-2 left-2 flex flex-col gap-1">
                            <Legend color="bg-red-500" label="High" />
                            <Legend color="bg-orange-400" label="Med" />
                            <Legend color="bg-yellow-400" label="Low" />
                        </div>
                    </div>
                </div>
            </LiquidGlass>

            {/* Today's Overview */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Today's Overview</h2>
                    <div className="grid grid-cols-3 gap-2">
                        <OverviewStat value="23" label="Total Alerts" />
                        <OverviewStat value="12" label="Investigations" />
                        <OverviewStat value="7" label="Confirmed" />
                    </div>
                </div>
            </LiquidGlass>
        </aside>
    );
}

function AlertItem({ type, title, loc, time }: { type: 'danger' | 'warning' | 'info', title: string, loc: string, time: string }) {
    const icons = {
        danger: <AlertTriangle className="w-4 h-4 text-red-500" />,
        warning: <AlertTriangle className="w-4 h-4 text-orange-400" />,
        info: <AlertCircle className="w-4 h-4 text-cyan-400" />
    };

    return (
        <div className="flex gap-3 group cursor-pointer hover:bg-white/5 p-2 -mx-2 rounded-xl transition-colors">
            <div className="mt-0.5">{icons[type]}</div>
            <div className="flex-1 min-w-0">
                <div className="flex justify-between items-start gap-2">
                    <h4 className="text-[13px] font-semibold text-slate-100 truncate">{title}</h4>
                    <span className="text-[10px] text-slate-500 font-medium whitespace-nowrap">{time}</span>
                </div>
                <p className="text-[11px] text-slate-500 truncate">{loc}</p>
            </div>
        </div>
    );
}

function Legend({ color, label }: { color: string, label: string }) {
    return (
        <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${color}`} />
            <span className="text-[8px] text-slate-400 uppercase font-bold tracking-tighter">{label}</span>
        </div>
    );
}

function OverviewStat({ value, label }: { value: string, label: string }) {
    return (
        <div className="flex flex-col gap-1">
            <span className="text-xl font-bold text-slate-100 tracking-tight">{value}</span>
            <span className="text-[9px] font-bold text-slate-500 uppercase tracking-tighter leading-tight">{label}</span>
        </div>
    );
}

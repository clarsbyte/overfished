import {
    LayoutDashboard,
    AlertTriangle,
    Ship,
    Bell,
    BarChart3,
    FileText,
    Settings,
    Waves,
    Crosshair,
} from "lucide-react";
import { LiquidGlass } from "./LiquidGlass";

type NavView = "ops" | "overview" | "incidents" | "vessels" | "analytics" | "reports" | "settings";

interface SidebarProps {
    activeView: NavView;
    onNavigate: (v: NavView) => void;
    totalVessels?: number;
    isOnline?: boolean;
}

export function OverfishedSidebar({ activeView, onNavigate, totalVessels, isOnline = true }: SidebarProps) {
    return (
        <LiquidGlass
            className="rounded-[40px] h-full"
            chromaticAberration={2}
            depth={10}
        >
            <div className="w-72 h-full flex flex-col p-6 gap-8 select-none">
                {/* Brand */}
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-cyan-600/20 rounded-xl flex items-center justify-center border border-cyan-500/30">
                        <Waves className="w-6 h-6 text-cyan-400" />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold tracking-tight text-white">Overfished</h1>
                        <p className="text-[10px] text-cyan-500/80 font-bold uppercase tracking-widest">Illegal Fishing Intelligence</p>
                    </div>
                </div>

                {/* Navigation */}
                <nav className="flex-1 space-y-1">
                    <NavItem icon={Crosshair} label="Ops" active={activeView === "ops"} onClick={() => onNavigate("ops")} />
                    <NavItem icon={LayoutDashboard} label="Overview" active={activeView === "overview"} onClick={() => onNavigate("overview")} />
                    <NavItem icon={AlertTriangle} label="Incidents" active={activeView === "incidents"} onClick={() => onNavigate("incidents")} />
                    <NavItem icon={Ship} label="Vessels" active={activeView === "vessels"} onClick={() => onNavigate("vessels")} />
                    <NavItem icon={Bell} label="Alerts" active={false} onClick={() => onNavigate("incidents")} />
                    <NavItem icon={BarChart3} label="Analytics" active={activeView === "analytics"} onClick={() => onNavigate("analytics")} />
                    <NavItem icon={FileText} label="Reports" active={activeView === "reports"} onClick={() => onNavigate("reports")} />
                    <NavItem icon={Settings} label="Settings" active={activeView === "settings"} onClick={() => onNavigate("settings")} />
                </nav>

                {/* Live Status Widget */}
                <div className="space-y-4 pt-6 border-t border-white/10">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">Live Status</h3>

                    <div className="space-y-3">
                        <StatusRow label="Active Vessels" value={totalVessels != null ? totalVessels.toLocaleString() : "—"} />
                        <StatusRow label="Alerts Today" value="—" />
                        <StatusRow label="High Risk Zones" value="—" />
                    </div>

                    <div className="pt-4 flex items-center gap-3">
                        <div className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">System Status</div>
                        <div className="flex items-center gap-1.5">
                            <div className={`w-2 h-2 rounded-full ${isOnline
                                ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]"
                                : "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.6)]"
                                }`} />
                            <span className={`text-[10px] font-bold uppercase tracking-widest ${isOnline ? "text-emerald-500" : "text-red-500"}`}>
                                {isOnline ? "Online" : "Offline"}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </LiquidGlass>
    );
}

function NavItem({ icon: Icon, label, active = false, onClick }: {
    icon: React.ElementType;
    label: string;
    active?: boolean;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all cursor-pointer group text-left ${active ? "bg-cyan-500/15 border border-cyan-500/25" : "hover:bg-white/5 border border-transparent"
                }`}
        >
            <Icon className={`w-5 h-5 ${active ? "text-cyan-400" : "text-slate-400 group-hover:text-slate-200"} transition-colors`} />
            <span className={`text-sm font-medium ${active ? "text-white" : "text-slate-400 group-hover:text-slate-200"} transition-colors`}>
                {label}
            </span>
            {active && <div className="ml-auto w-1 h-1 bg-cyan-400 rounded-full shadow-[0_0_8px_rgba(34,211,238,1)]" />}
        </button>
    );
}

function StatusRow({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex items-baseline justify-between">
            <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wide">{label}</span>
            <span className="text-sm font-bold text-slate-200">{value}</span>
        </div>
    );
}

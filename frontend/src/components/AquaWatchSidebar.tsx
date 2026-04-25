import {
    LayoutDashboard,
    AlertTriangle,
    Ship,
    Bell,
    BarChart3,
    FileText,
    Settings,
    Waves
} from "lucide-react";
import { LiquidGlass } from "./LiquidGlass";

export function AquaWatchSidebar() {
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
                        <h1 className="text-xl font-bold tracking-tight text-white">AquaWatch</h1>
                        <p className="text-[10px] text-cyan-500/80 font-bold uppercase tracking-widest">Illegal Fishing Intelligence</p>
                    </div>
                </div>

                {/* Navigation */}
                <nav className="flex-1 space-y-1">
                    <NavItem icon={LayoutDashboard} label="Overview" active />
                    <NavItem icon={AlertTriangle} label="Incidents" />
                    <NavItem icon={Ship} label="Vessels" />
                    <NavItem icon={Bell} label="Alerts" />
                    <NavItem icon={BarChart3} label="Analytics" />
                    <NavItem icon={FileText} label="Reports" />
                    <NavItem icon={Settings} label="Settings" />
                </nav>

                {/* Live Status Widget */}
                <div className="space-y-4 pt-6 border-t border-white/10">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">Live Status</h3>

                    <div className="space-y-3">
                        <StatusRow label="Active Vessels" value="1,247" delta="+23" deltaColor="text-emerald-400" />
                        <StatusRow label="Alerts Today" value="23" delta="+5" deltaColor="text-emerald-400" />
                        <StatusRow label="High Risk Zones" value="8" delta="+2" deltaColor="text-emerald-400" />
                    </div>

                    <div className="pt-4 flex items-center gap-3">
                        <div className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">System Status</div>
                        <div className="flex items-center gap-1.5">
                            <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]" />
                            <span className="text-[10px] font-bold text-emerald-500 uppercase tracking-widest">Online</span>
                        </div>
                    </div>
                </div>
            </div>
        </LiquidGlass>
    );
}

function NavItem({ icon: Icon, label, active = false }: { icon: any, label: string, active?: boolean }) {
    return (
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all cursor-pointer group ${active ? 'bg-cyan-500/15 border border-cyan-500/25' : 'hover:bg-white/5'
            }`}>
            <Icon className={`w-5 h-5 ${active ? 'text-cyan-400' : 'text-slate-400 group-hover:text-slate-200'} transition-colors`} />
            <span className={`text-sm font-medium ${active ? 'text-white' : 'text-slate-400 group-hover:text-slate-200'} transition-colors`}>{label}</span>
            {active && <div className="ml-auto w-1 h-1 bg-cyan-400 rounded-full shadow-[0_0_8px_rgba(34,211,238,1)]" />}
        </div>
    );
}

function StatusRow({ label, value, delta, deltaColor }: { label: string, value: string, delta: string, deltaColor: string }) {
    return (
        <div className="flex items-baseline justify-between">
            <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wide">{label}</span>
            <div className="flex items-baseline gap-2">
                <span className="text-sm font-bold text-slate-200">{value}</span>
                <span className={`text-[10px] font-bold ${deltaColor}`}>{delta}</span>
            </div>
        </div>
    );
}

import { Search, Bell, User } from "lucide-react";
import { useEffect, useState } from "react";
import { LiquidGlass } from "./LiquidGlass";

export function DashboardTopBar() {
    const [time, setTime] = useState(new Date());

    useEffect(() => {
        const timer = setInterval(() => setTime(new Date()), 1000);
        return () => clearInterval(timer);
    }, []);

    const timeStr = time.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
        timeZone: 'UTC'
    });

    const dateStr = time.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    });

    return (
        <LiquidGlass className="rounded-[30px] mx-4 mt-2" chromaticAberration={2} depth={8}>
            <div className="flex items-center justify-between px-8 py-4 pointer-events-auto">
                {/* Search */}
                <div className="flex-1 max-w-xl relative group">
                    <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none">
                        <Search className="w-4 h-4 text-slate-400 group-focus-within:text-cyan-400 transition-colors" />
                    </div>
                    <input
                        type="text"
                        placeholder="Search vessels, incidents, zones..."
                        className="w-full bg-white/5 border border-white/10 rounded-2xl pl-12 pr-4 py-2.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500/30 focus:bg-white/10 transition-all"
                    />
                </div>

                {/* Right Actions */}
                <div className="flex items-center gap-6">
                    <div className="flex flex-col items-end border-r border-white/10 pr-6">
                        <span className="text-xs font-bold text-slate-200 tracking-wide">{dateStr}</span>
                        <span className="text-[10px] font-mono text-cyan-500/80 uppercase tracking-widest">{timeStr} UTC</span>
                    </div>

                    <div className="flex items-center gap-4">
                        <button className="relative p-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 transition-all group">
                            <Bell className="w-4 h-4 text-slate-400 group-hover:text-slate-100" />
                            <span className="absolute top-2 right-2 w-2 h-2 bg-red-500 rounded-full border-2 border-[#030708] shadow-[0_0_8px_rgba(239,68,68,0.5)]" />
                        </button>
                        <button className="p-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 transition-all group">
                            <User className="w-4 h-4 text-slate-400 group-hover:text-slate-100" />
                        </button>
                    </div>
                </div>
            </div>
        </LiquidGlass>
    );
}

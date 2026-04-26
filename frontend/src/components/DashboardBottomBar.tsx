import {
    Ship,
    Info,
    Radar,
    Cloud,
    Layers,
    Plus,
    Check,
    Waves,
} from "lucide-react";
import { useState } from "react";
import { LiquidGlass } from "./LiquidGlass";
import { useGlobeControlsContext } from "./GlobeControlsContext";

export function DashboardBottomBar() {
    const [menuOpen, setMenuOpen] = useState(false);
    const { controls, toggleLayer } = useGlobeControlsContext();

    return (
        <div className="relative pointer-events-auto">
            {/* Layers Menu Popover (Positioned outside so overflow-hidden doesn't clip it) */}
            {menuOpen && (
                <div className="absolute bottom-full right-0 mb-4 animate-in slide-in-from-bottom-2 fade-in duration-200 z-50">
                    <LiquidGlass className="rounded-[24px]" chromaticAberration={2} depth={6}>
                        <div className="p-4 w-56 flex flex-col gap-1">
                            <div className="px-2 pb-2 mb-2 border-b border-white/5">
                                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Map Layers</span>
                            </div>

                            <ToggleItem
                                label="Show Vessels"
                                checked={controls.showVessels}
                                onChange={() => toggleLayer("showVessels")}
                            />
                            <ToggleItem
                                label="Show Paths"
                                checked={controls.showPaths}
                                onChange={() => toggleLayer("showPaths")}
                            />
                            <ToggleItem
                                label="Show Heatmap"
                                checked={controls.showHeatmap}
                                onChange={() => toggleLayer("showHeatmap")}
                            />
                            <ToggleItem
                                label="Show Points"
                                checked={controls.showPoints}
                                onChange={() => toggleLayer("showPoints")}
                            />

                            <div className="px-2 pt-3 pb-2 mt-1 border-t border-white/5">
                                <span className="text-[10px] font-bold text-blue-400/70 uppercase tracking-widest flex items-center gap-1.5">
                                    <Waves className="w-3 h-3" />
                                    Marine Life
                                </span>
                            </div>
                            <ToggleItem
                                label="Shark Distribution"
                                checked={controls.showSharkHeatmap}
                                onChange={() => toggleLayer("showSharkHeatmap")}
                                accent="blue"
                            />
                        </div>
                    </LiquidGlass>
                </div>
            )}

            {/* Main Bottom Bar */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <nav className="flex items-center gap-1 p-1.5 relative">
                    <CategoryItem icon={Ship} label="Vessels" active />
                    <CategoryItem icon={Info} label="Incidents" />
                    <CategoryItem icon={Radar} label="Zones" />
                    <CategoryItem icon={Cloud} label="Weather" />
                    <CategoryItem icon={Layers} label="Layers" />

                    <div className="w-[1px] h-6 bg-white/10 mx-2" />

                    <button
                        onClick={() => setMenuOpen(!menuOpen)}
                        className={`p-3 rounded-xl transition-all group relative ${menuOpen ? 'bg-cyan-500/20 text-cyan-400' : 'hover:bg-white/10 text-slate-400 hover:text-white'}`}
                    >
                        <Plus className={`w-5 h-5 transition-transform duration-300 ${menuOpen ? 'rotate-45' : 'group-hover:scale-110'}`} />
                    </button>
                </nav>
            </LiquidGlass>
        </div>
    );
}

function CategoryItem({ icon: Icon, label, active = false }: { icon: any, label: string, active?: boolean }) {
    return (
        <button className={`flex items-center gap-2.5 px-6 py-2.5 rounded-xl transition-all group relative ${active ? 'bg-cyan-500/15 text-white' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
            }`}>
            <Icon className={`w-4 h-4 ${active ? 'text-cyan-400' : 'group-hover:text-slate-200'} transition-colors`} />
            <span className="text-xs font-bold uppercase tracking-widest">{label}</span>
        </button>
    );
}

function ToggleItem({ label, checked, onChange, accent = "cyan" }: { label: string, checked: boolean, onChange: () => void, accent?: "cyan" | "blue" }) {
    const activeBox = accent === "blue"
        ? "bg-blue-500 border-blue-400"
        : "bg-cyan-500 border-cyan-400";
    return (
        <button
            onClick={onChange}
            className="flex items-center justify-between px-3 py-2.5 hover:bg-white/5 rounded-xl transition-colors group w-full text-left cursor-pointer"
        >
            <span className={`text-sm font-medium transition-colors ${checked ? 'text-slate-200' : 'text-slate-400 group-hover:text-slate-300'}`}>
                {label}
            </span>
            <div className={`w-4 h-4 rounded-[4px] border flex items-center justify-center transition-all ${checked ? activeBox : 'border-slate-500 group-hover:border-slate-400'}`}>
                <Check className={`w-3 h-3 text-[10px] text-white transition-opacity ${checked ? 'opacity-100' : 'opacity-0'}`} strokeWidth={3} />
            </div>
        </button>
    );
}

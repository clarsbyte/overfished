import { Check, Layers as LayersIcon, Pencil, RotateCcw } from "lucide-react";
import { useGlobeControlsContext } from "../GlobeControlsContext";
import { LiquidGlass } from "../LiquidGlass";

interface Props {
    drawMode: "idle" | "drawing" | "committed";
    onStartDrawing: () => void;
    onResetDrawing: () => void;
    vertexCount: number;
}

const TOGGLES: { key: "showVessels" | "showPaths" | "showHeatmap" | "showPoints"; label: string; hint: string }[] = [
    { key: "showVessels", label: "Vessels", hint: "Animated 3D ship meshes" },
    { key: "showPaths", label: "Flight paths", hint: "Procedural ambient routes" },
    { key: "showHeatmap", label: "Fishing heatmap", hint: "Globally aggregated effort density" },
    { key: "showPoints", label: "Raw AIS points", hint: "Static dot dataset" },
];

/**
 * Settings view — exposes globe layer toggles (driven by GlobeControlsContext)
 * and the polygon-drawing controls. The drawing controller lives in App.tsx;
 * we accept its imperative handles as props so this view stays declarative.
 */
export function SettingsView({ drawMode, onStartDrawing, onResetDrawing, vertexCount }: Props) {
    const { controls, toggleLayer } = useGlobeControlsContext();

    return (
        <aside className="w-80 h-full flex flex-col gap-4 p-4 pointer-events-auto overflow-y-auto">
            {/* Layers */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Map Layers</h2>
                        <LayersIcon className="w-4 h-4 text-cyan-300" />
                    </div>
                    <div className="space-y-1">
                        {TOGGLES.map(({ key, label, hint }) => {
                            const checked = controls[key];
                            return (
                                <button
                                    key={key}
                                    onClick={() => toggleLayer(key)}
                                    className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-white/5 rounded-xl transition-colors group text-left"
                                >
                                    <div className="min-w-0">
                                        <div className="text-[12.5px] font-medium text-slate-200">{label}</div>
                                        <div className="text-[10px] text-slate-500">{hint}</div>
                                    </div>
                                    <div
                                        className={`w-4 h-4 rounded-[4px] border flex items-center justify-center transition-all flex-shrink-0 ${checked ? "bg-cyan-500 border-cyan-400" : "border-slate-500 group-hover:border-slate-400"
                                            }`}
                                    >
                                        <Check
                                            className={`w-3 h-3 text-white transition-opacity ${checked ? "opacity-100" : "opacity-0"
                                                }`}
                                            strokeWidth={3}
                                        />
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                </div>
            </LiquidGlass>

            {/* Region drawing */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Define Region</h2>
                        <Pencil className="w-4 h-4 text-cyan-300" />
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                        Draw a polygon directly on the globe. POSTs your shape to{" "}
                        <code className="text-cyan-300 font-mono">/region</code> and resolves overlapping MPAs and
                        EEZs server-side.
                    </p>

                    {drawMode === "drawing" ? (
                        <>
                            <div className="rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-3 py-2.5">
                                <div className="text-[10px] font-bold text-cyan-200 uppercase tracking-widest mb-1">
                                    Drawing · {vertexCount} vertex{vertexCount === 1 ? "" : "es"}
                                </div>
                                <ul className="text-[11px] text-slate-200 space-y-0.5 list-disc list-inside">
                                    <li>Click the globe to add vertices</li>
                                    <li>Double-click or press Enter to commit</li>
                                    <li>Press Esc to cancel</li>
                                </ul>
                            </div>
                            <button
                                onClick={onResetDrawing}
                                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-slate-500/40 text-slate-200 hover:bg-white/5 text-[12px] font-mono uppercase tracking-[0.18em]"
                            >
                                <RotateCcw className="w-4 h-4" />
                                Cancel
                            </button>
                        </>
                    ) : (
                        <button
                            onClick={onStartDrawing}
                            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-cyan-400/40 bg-cyan-400/10 text-cyan-200 hover:bg-cyan-400/20 hover:border-cyan-400/60 text-[12px] font-mono uppercase tracking-[0.18em] transition-colors"
                        >
                            <Pencil className="w-4 h-4" />
                            Start Drawing
                        </button>
                    )}
                </div>
            </LiquidGlass>

            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-2">
                    <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">About</h2>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                        AquaWatch · Maritime Surveillance Console. Backed by Global Fishing Watch
                        AIS, ProtectedSeas MPAs, and the Overfish AI agent network.
                    </p>
                </div>
            </LiquidGlass>
        </aside>
    );
}

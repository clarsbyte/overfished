import type { FeatureCollection } from "geojson";
import {
  Bell,
  Fish,
  Layers3,
  Mountain,
  Search,
  Ship as ShipIcon,
  User,
  X as XIcon,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  AgentPipelineMinimizedChip,
  AgentPipelineModal,
} from "@/components/AgentPipelineModal";
import { AquaWatchSidebar } from "@/components/AquaWatchSidebar";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { LiquidGlass } from "@/components/LiquidGlass";
import { MapView, type MapHandle, type Seamount } from "@/components/MapView";
import { VesselDetailPanel } from "@/components/VesselDetailPanel";
import { AgentPipelineProvider } from "@/state/agentPipeline";
import { AnalyticsView } from "@/components/views/AnalyticsView";
import { IncidentsView } from "@/components/views/IncidentsView";
import { OpsView } from "@/components/views/OpsView";
import { ReportsView } from "@/components/views/ReportsView";
import { SettingsView } from "@/components/views/SettingsView";
import { VesselsView } from "@/components/views/VesselsView";
import { useShips } from "@/hooks/useShips";
import type { DocumentArtifact, Vessel } from "@/types/schemas";
import type { Ship } from "@/types/ship";

const MAP_RENDERER_KEY = "ui:map-renderer";
type BottomDockTab = "vessels" | "layers" | "animals";
export type NavView = "ops" | "overview" | "incidents" | "vessels" | "analytics" | "reports" | "settings";


export default function App() {
  const { ships, tracks, isLoading, errors, bySource } = useShips();

  const [selected, setSelected] = useState<Ship | null>(null);
  const [selectedVessel, setSelectedVessel] = useState<Vessel | null>(null);
  const [speciesOverlay, setSpeciesOverlay] = useState<FeatureCollection | null>(null);
  const [activeView, setActiveView] = useState<NavView>("ops");
  const [activeDockTab, setActiveDockTab] = useState<BottomDockTab>("vessels");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeRegionName, setActiveRegionName] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentArtifact[]>([]);
  const [portCall, setPortCall] = useState<{ endLat: number; endLng: number } | null>(null);
  const [demoError] = useState<string | null>(null);

  const [agentPin, setAgentPin] = useState<{ lat: number; lng: number } | null>(null);
  const agentPickCbRef = useRef<((lat: number, lng: number) => void) | null>(null);
  const [isPicking, setIsPicking] = useState(false);
  const [showSharkHeatmap, setShowSharkHeatmap] = useState(false);
  const [showTunaHeatmap, setShowTunaHeatmap] = useState(false);
  const [showSeamounts, setShowSeamounts] = useState(false);
  const [hoveredSeamount, setHoveredSeamount] = useState<Seamount | null>(null);

  const handleRequestGlobePick = useCallback((cb: (lat: number, lng: number) => void) => {
    agentPickCbRef.current = cb;
    setIsPicking(true);
  }, []);

  const handleGlobeClick = useCallback((lat: number, lng: number) => {
    if (!agentPickCbRef.current) return;
    agentPickCbRef.current(lat, lng);
    agentPickCbRef.current = null;
    setAgentPin({ lat, lng });
    setIsPicking(false);
  }, []);

  const [renderer, setRenderer] = useState<"globe" | "mapbox">(() => {
    if (typeof window === "undefined") return "globe";
    const stored = window.localStorage.getItem(MAP_RENDERER_KEY);
    return stored === "mapbox" ? "mapbox" : "globe";
  });

  useEffect(() => {
    if (typeof window !== "undefined") window.localStorage.setItem(MAP_RENDERER_KEY, renderer);
  }, [renderer]);

  const mapRef = useRef<MapHandle | null>(null);

  const handleSelect = (ship: Ship | null) => {
    setSelected(ship);
    if (ship) mapRef.current?.flyTo(ship.lon, ship.lat, 5);
  };

  const handleSelectVessel = useCallback((vessel: Vessel) => {
    setSelectedVessel(vessel);
    // Always sync the Ship selection so the globe highlights and detail panel appear
    const ship = ships.find(s => s.mmsi === vessel.mmsi);
    if (vessel.last_position) {
      mapRef.current?.flyTo(vessel.last_position.lon, vessel.last_position.lat, 5);
      if (ship) setSelected(ship);
    } else if (ship) {
      setSelected(ship);
      mapRef.current?.flyTo(ship.lon, ship.lat, 5);
    }
  }, [ships]);

  const handleSpeciesHighlightChange = useCallback((geojson: FeatureCollection | null) => {
    setSpeciesOverlay(geojson);
  }, []);

  // Live clock
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const dateStr = now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const timeStr =
    now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) + " UTC";

  const isOnline = true;
  void errors;

  // Right panel content by nav view
  const rightPanel = () => {
    switch (activeView) {
      case "incidents":
        return <IncidentsView onSelectRegion={setActiveRegionName} />;
      case "vessels":
        return (
          <VesselsView
            selectedMmsi={selectedVessel?.mmsi ?? null}
            onSelectVessel={handleSelectVessel}
          />
        );
      case "analytics":
        return <AnalyticsView />;
      case "reports":
        return (
          <ReportsView
            documents={documents}
            onPreview={() => {}}
            onSetDocuments={setDocuments}
            onPortCallReady={(call) => setPortCall({ endLat: call.endLat, endLng: call.endLng })}
            selectedVessel={selectedVessel}
          />
        );
      case "settings":
        return (
          <SettingsView
            drawMode="idle"
            onStartDrawing={() => {}}
            onResetDrawing={() => {}}
            vertexCount={0}
          />
        );
      default: // "ops" | "overview"
        return (
          <OpsView
            selectedVessel={selectedVessel}
            documents={documents}
            activeRegionName={activeRegionName}
            onSelectVessel={handleSelectVessel}
            onSelectRegion={setActiveRegionName}
            onRunDemo={() => {}}
            onNotifyPort={() => {}}
            onPreview={() => {}}
            runDemoPending={false}
            notifyPortPending={false}
            demoRunning={false}
            demoError={demoError}
            lastPortCall={portCall}
            bySource={bySource}
            selectedShip={selected}
            onSpeciesHighlightChange={handleSpeciesHighlightChange}
            onRequestGlobePick={handleRequestGlobePick}
          />
        );
    }
  };

  return (
    <AgentPipelineProvider>
    <div className="space-canvas flex h-screen w-screen overflow-hidden text-slate2-200">

      {/* LEFT: Navigation sidebar */}
      <div className="z-20 m-3 mr-0 flex-shrink-0 h-[calc(100vh-1.5rem)] flex items-center">
        <AquaWatchSidebar
          activeView={activeView}
          onNavigate={setActiveView}
          totalVessels={ships.length}
          isOnline={isOnline}
        />
      </div>

      {/* CENTER: Globe + overlays */}
      <main className="relative isolate z-10 flex-1 min-w-0 overflow-hidden">

        <div className="absolute inset-0 z-0">
          <MapView
            ref={mapRef}
            renderer={renderer}
            ships={ships}
            tracks={tracks}
            selected={selected}
            onSelect={handleSelect}
            speciesOverlay={speciesOverlay}
            onGlobeClick={handleGlobeClick}
            pinCoord={agentPin}
            isPicking={isPicking}
            showSharkHeatmap={showSharkHeatmap}
            showTunaHeatmap={showTunaHeatmap}
            showSeamounts={showSeamounts}
            onSeamountHover={setHoveredSeamount}
          />
        </div>

        {isPicking && (
          <div className="pointer-events-none absolute inset-x-0 top-20 z-40 flex justify-center">
            <div className="glass-surface glass-shell flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-yellow-300 ring-1 ring-yellow-400/40">
              <span className="animate-pulse">⊕</span>
              Click the globe to place your agent pin
            </div>
          </div>
        )}

        <div className="starfield-static z-10 opacity-45 pointer-events-none" aria-hidden />

        {/* Top bar: search + date/time + user */}
        <div className="pointer-events-none absolute top-3 inset-x-3 z-30 flex items-center gap-2">
          <div className="flex-1 pointer-events-auto">
            <LiquidGlass className="rounded-full" chromaticAberration={2} depth={8}>
              <div className="flex items-center gap-2.5 px-4 py-2.5">
                <Search size={14} className="text-slate2-400 flex-shrink-0" />
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search vessels, incidents, zones..."
                  className="bg-transparent text-sm text-slate2-200 placeholder:text-slate2-400 outline-none flex-1 min-w-0"
                />
              </div>
            </LiquidGlass>
          </div>
          <div className="pointer-events-auto flex-shrink-0">
            <LiquidGlass className="rounded-full" chromaticAberration={2} depth={8}>
              <div className="flex items-center gap-3 px-4 py-2.5">
                <div className="text-right">
                  <div className="text-[10px] font-mono text-slate2-400 leading-none">{dateStr}</div>
                  <div className="text-[11px] font-mono font-semibold text-slate2-200 leading-none mt-0.5">{timeStr}</div>
                </div>
                <div className="w-px h-4 bg-white/10" />
                <button type="button" className="text-slate2-400 hover:text-slate2-200 transition-colors">
                  <Bell size={14} />
                </button>
                <button type="button" className="w-6 h-6 rounded-full bg-accent-safe/20 border border-accent-safe/30 flex items-center justify-center">
                  <User size={11} className="text-accent-safe" />
                </button>
              </div>
            </LiquidGlass>
          </div>
        </div>

        {/* Vessel detail floating card — bottom-left, above dock */}
        {selected && (
          <div className="pointer-events-none absolute bottom-20 left-3 z-20 w-[320px]">
            <div className="pointer-events-auto">
              <ErrorBoundary label="Vessel detail">
                <VesselDetailPanel ship={selected} onClose={() => setSelected(null)} />
              </ErrorBoundary>
            </div>
          </div>
        )}

        {/* Seamount activist card — top-left, below search */}
        {showSeamounts && (
          <div className="pointer-events-none absolute left-3 top-20 z-20 w-[340px]">
            <div className="pointer-events-auto">
              <LiquidGlass className="rounded-2xl" chromaticAberration={2} depth={10}>
                <div className="space-y-3 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Mountain size={14} className="text-orange-300" />
                      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-orange-300">
                        GEBCO × GFW Overlay
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setShowSeamounts(false)}
                      className="text-slate2-400 transition-colors hover:text-slate2-200"
                      aria-label="Close seamounts overlay"
                    >
                      <XIcon size={14} />
                    </button>
                  </div>

                  {hoveredSeamount ? (
                    <>
                      <div>
                        <div className="text-base font-semibold leading-tight text-slate2-100">
                          {hoveredSeamount.name}
                        </div>
                        <div className="mt-0.5 text-[11px] text-slate2-400">{hoveredSeamount.region}</div>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-[11px]">
                        <div>
                          <div className="font-mono uppercase tracking-wide text-slate2-500">Summit</div>
                          <div className="font-semibold text-slate2-100">
                            {hoveredSeamount.summit_depth_m.toLocaleString()} m
                          </div>
                        </div>
                        <div>
                          <div className="font-mono uppercase tracking-wide text-slate2-500">Base</div>
                          <div className="font-semibold text-slate2-100">
                            {hoveredSeamount.base_depth_m.toLocaleString()} m
                          </div>
                        </div>
                        <div>
                          <div className="font-mono uppercase tracking-wide text-slate2-500">Coral age</div>
                          <div className="font-semibold text-orange-300">
                            {hoveredSeamount.coral_age_years.toLocaleString()} yr
                          </div>
                        </div>
                      </div>
                      <div>
                        <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wide text-slate2-400">
                          <span>Bottom-trawl pressure</span>
                          <span className="font-mono text-slate2-200">
                            {Math.round(hoveredSeamount.fishing_pressure * 100)}%
                          </span>
                        </div>
                        <div className="relative h-1.5 overflow-hidden rounded-full bg-white/5">
                          <div
                            className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-amber-400 to-rose-500"
                            style={{ width: `${hoveredSeamount.fishing_pressure * 100}%` }}
                          />
                        </div>
                      </div>
                      <p className="text-[11.5px] leading-relaxed text-slate2-300">{hoveredSeamount.note}</p>
                    </>
                  ) : (
                    <>
                      <h3 className="text-[15px] font-semibold leading-snug text-slate2-100">
                        Fishing concentrated on the peaks
                      </h3>
                      <p className="text-[11.5px] leading-relaxed text-slate2-300">
                        Seamounts push deep-sea currents upward, fertilising biodiversity hotspots that schooling
                        fish and cold-water coral forests depend on. The same peaks are easiest for bottom-trawlers
                        to anchor — a single pass strips reefs that took up to{" "}
                        <span className="font-semibold text-orange-300">11,000 years</span> to grow.
                      </p>
                      <div className="grid grid-cols-2 gap-2 text-[11px]">
                        <div className="rounded-lg bg-white/[0.03] p-2 ring-1 ring-white/5">
                          <div className="font-mono text-[10px] uppercase tracking-wide text-slate2-400">
                            Seamounts shown
                          </div>
                          <div className="text-base font-semibold text-slate2-100">15</div>
                        </div>
                        <div className="rounded-lg bg-white/[0.03] p-2 ring-1 ring-white/5">
                          <div className="font-mono text-[10px] uppercase tracking-wide text-slate2-400">
                            Avg trawl pressure
                          </div>
                          <div className="text-base font-semibold text-orange-300">71%</div>
                        </div>
                      </div>
                      <div className="text-[10px] italic text-slate2-500">
                        Hover a peak for detail · GEBCO bathymetry × GFW fishing effort
                      </div>
                    </>
                  )}
                </div>
              </LiquidGlass>
            </div>
          </div>
        )}

        {/* Bottom dock */}
        <div className="pointer-events-none absolute bottom-3 left-1/2 z-30 -translate-x-1/2">
          <div className="pointer-events-auto">
            <LiquidGlass className="rounded-full" chromaticAberration={2} depth={8}>
              <div className="flex items-center gap-1 p-2.5">
                {(
                  [
                    { id: "vessels",   label: "Vessels",   icon: ShipIcon     },
                    { id: "animals",   label: "Animals",   icon: Fish         },
                    { id: "layers",    label: "Layers",    icon: Layers3      },
                  ] as const
                ).map(({ id, label, icon: Icon }) => {
                  const active = activeDockTab === id;
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setActiveDockTab(id)}
                      className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold uppercase tracking-[0.02em] transition ${
                        active ? "glass-chip text-accent-safe" : "text-slate2-300 hover:glass-chip hover:text-slate2-100"
                      }`}
                    >
                      <Icon size={16} />
                      {label}
                    </button>
                  );
                })}
              </div>
            </LiquidGlass>
          </div>
          {activeDockTab === "layers" && (
            <div className="pointer-events-auto absolute -top-14 left-1/2 -translate-x-1/2">
              <LiquidGlass className="rounded-full" chromaticAberration={2} depth={6}>
                <div className="flex items-center gap-1 p-1.5 text-[11px] uppercase tracking-wide text-slate2-200">
                  <button
                    type="button"
                    onClick={() => setRenderer("globe")}
                    className={`rounded px-2 py-1 transition ${renderer === "globe" ? "glass-chip text-accent-safe" : "text-slate2-300 hover:glass-chip"}`}
                  >
                    Globe
                  </button>
                  <button
                    type="button"
                    onClick={() => setRenderer("mapbox")}
                    className={`rounded px-2 py-1 transition ${renderer === "mapbox" ? "glass-chip text-accent-safe" : "text-slate2-300 hover:glass-chip"}`}
                  >
                    Mapbox
                  </button>
                </div>
              </LiquidGlass>
            </div>
          )}
          {activeDockTab === "animals" && (
            <div className="pointer-events-auto absolute -top-14 left-1/2 -translate-x-1/2">
              <LiquidGlass className="rounded-full" chromaticAberration={2} depth={6}>
                <div className="flex items-center gap-1 p-1.5 text-[11px] uppercase tracking-wide text-slate2-200">
                  <button
                    type="button"
                    onClick={() => setShowSharkHeatmap(v => !v)}
                    className={`flex items-center gap-1.5 rounded px-2 py-1 transition ${showSharkHeatmap ? "glass-chip text-accent-safe" : "text-slate2-300 hover:glass-chip"}`}
                  >
                    <Fish size={12} />
                    Shark
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowTunaHeatmap(v => !v)}
                    className={`flex items-center gap-1.5 rounded px-2 py-1 transition ${showTunaHeatmap ? "glass-chip text-cyan-400" : "text-slate2-300 hover:glass-chip"}`}
                  >
                    <Fish size={12} />
                    Bluefin Tuna
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowSeamounts(v => !v)}
                    className={`flex items-center gap-1.5 rounded px-2 py-1 transition ${showSeamounts ? "glass-chip text-orange-300" : "text-slate2-300 hover:glass-chip"}`}
                    title="GEBCO bathymetry × GFW fishing effort"
                  >
                    <Mountain size={12} />
                    Seamounts
                  </button>
                </div>
              </LiquidGlass>
            </div>
          )}
        </div>
      </main>

      {/* RIGHT: Active view panel */}
      <div className="z-20 m-3 ml-0 flex-shrink-0 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]">
        <ErrorBoundary label="Right panel">
          {rightPanel()}
        </ErrorBoundary>
      </div>

      <AgentPipelineModal />
      <AgentPipelineMinimizedChip />
    </div>
    </AgentPipelineProvider>
  );
}

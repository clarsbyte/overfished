import type { FeatureCollection } from "geojson";
import {
  AlertTriangle,
  Bell,
  Layers3,
  MapPinned,
  Pencil,
  PlayCircle,
  Search,
  Ship as ShipIcon,
  User,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { AquaWatchSidebar } from "@/components/AquaWatchSidebar";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { MapView, type MapHandle } from "@/components/MapView";
import { VesselDetailPanel } from "@/components/VesselDetailPanel";
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
type BottomDockTab = "vessels" | "incidents" | "zones" | "layers";
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

  const isOnline = errors.length === 0;

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
          />
        );
    }
  };

  return (
    <div className="space-canvas flex h-screen w-screen overflow-hidden text-slate2-200">

      {/* LEFT: Navigation sidebar */}
      <div className="z-20 m-3 mr-0 flex-shrink-0">
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
          />
        </div>

        <div className="starfield-static z-10 opacity-45 pointer-events-none" aria-hidden />

        {/* Top bar: search + date/time + user */}
        <div className="pointer-events-none absolute top-3 inset-x-3 z-30 flex items-center gap-2">
          <div className="flex-1 pointer-events-auto">
            <div className="glass-surface glass-shell flex items-center gap-2.5 px-4 py-2.5">
              <Search size={14} className="text-slate2-400 flex-shrink-0" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search vessels, incidents, zones..."
                className="bg-transparent text-sm text-slate2-200 placeholder:text-slate2-400 outline-none flex-1 min-w-0"
              />
            </div>
          </div>
          <div className="glass-surface glass-shell pointer-events-auto flex items-center gap-3 px-4 py-2.5 flex-shrink-0">
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
        </div>

        {/* Action buttons: Define Region + Run Demo Flow */}
        <div className="pointer-events-none absolute top-16 right-3 z-30 flex items-center gap-2">
          <button
            type="button"
            className="glass-surface glass-shell pointer-events-auto flex items-center gap-2 px-4 py-2 text-[11px] font-bold uppercase tracking-wider text-slate2-300 hover:text-slate2-100 transition-colors"
          >
            <Pencil size={12} />
            Define Region
          </button>
          <button
            type="button"
            onClick={() => setActiveView("reports")}
            className="glass-surface glass-shell pointer-events-auto flex items-center gap-2 px-4 py-2 text-[11px] font-bold uppercase tracking-wider text-red-300 border-red-500/25 bg-red-500/10 hover:bg-red-500/20 transition-colors"
          >
            <PlayCircle size={12} />
            Run Demo Flow
          </button>
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

        {/* Bottom dock */}
        <div className="pointer-events-none absolute bottom-3 left-1/2 z-30 -translate-x-1/2">
          <div className="glass-surface glass-shell pointer-events-auto relative flex items-center gap-1 p-2.5">
            {(
              [
                { id: "vessels",   label: "Vessels",   icon: ShipIcon     },
                { id: "incidents", label: "Incidents", icon: AlertTriangle },
                { id: "zones",     label: "Zones",     icon: MapPinned    },
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
          {activeDockTab === "layers" && (
            <div className="glass-surface glass-panel pointer-events-auto absolute -top-14 left-1/2 flex -translate-x-1/2 items-center gap-1 p-1.5 text-[11px] uppercase tracking-wide text-slate2-200">
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
          )}
        </div>
      </main>

      {/* RIGHT: Active view panel */}
      <div className="z-20 m-3 ml-0 flex-shrink-0 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]">
        <ErrorBoundary label="Right panel">
          {rightPanel()}
        </ErrorBoundary>
      </div>
    </div>
  );
}

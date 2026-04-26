import type { FeatureCollection } from "geojson";
import {
  AlertTriangle,
  Anchor,
  ChevronLeft,
  ChevronRight,
  Layers3,
  MapPinned,
  Ship as ShipIcon,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { AnalysisStack } from "@/components/AnalysisStack";
import { MapView, type MapHandle } from "@/components/MapView";
import { Sidebar } from "@/components/Sidebar";
import { useShips } from "@/hooks/useShips";
import type { Ship } from "@/types/ship";

const SIDEBAR_OPEN_KEY = "ui:sidebar-expanded";
const MAP_RENDERER_KEY = "ui:map-renderer";
type BottomDockTab = "vessels" | "incidents" | "zones" | "layers";

export default function App() {
  const { ships, tracks, isLoading, errors, bySource } = useShips();
  const [selected, setSelected] = useState<Ship | null>(null);
  const [speciesOverlay, setSpeciesOverlay] = useState<FeatureCollection | null>(null);
  const [renderer, setRenderer] = useState<"globe" | "mapbox">(() => {
    if (typeof window === "undefined") return "globe";
    const stored = window.localStorage.getItem(MAP_RENDERER_KEY);
    return stored === "mapbox" ? "mapbox" : "globe";
  });
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    if (typeof window === "undefined") return true;
    const raw = window.localStorage.getItem(SIDEBAR_OPEN_KEY);
    if (raw === "0") return false;
    if (raw === "1") return true;
    return true;
  });
  const [activeDockTab, setActiveDockTab] = useState<BottomDockTab>("vessels");
  const mapRef = useRef<MapHandle | null>(null);

  const handleSpeciesHighlightChange = useCallback((geojson: FeatureCollection | null) => {
    setSpeciesOverlay(geojson);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SIDEBAR_OPEN_KEY, sidebarOpen ? "1" : "0");
  }, [sidebarOpen]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(MAP_RENDERER_KEY, renderer);
  }, [renderer]);

  const handleSelect = (ship: Ship | null) => {
    setSelected(ship);
    if (ship) mapRef.current?.flyTo(ship.lon, ship.lat, 5);
  };

  return (
    <div className="space-canvas flex h-screen w-screen text-slate2-200">
      <aside
        className={`glass-surface glass-panel z-20 m-3 mr-0 flex shrink-0 flex-col transition-[width] duration-200 ease-out ${
          sidebarOpen ? "w-80" : "w-11"
        }`}
      >
        {!sidebarOpen ? (
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="flex h-full w-full flex-col items-center gap-3 py-4 text-slate2-400 transition hover:bg-ink-900 hover:text-slate2-200"
            title="Show vessel list"
            aria-label="Expand sidebar"
          >
            <ChevronRight size={18} className="shrink-0" />
            <ShipIcon size={16} className="shrink-0 text-accent-safe" />
            <span className="max-h-[40vh] select-none text-[10px] font-medium uppercase tracking-widest text-slate2-500 [writing-mode:vertical-rl]">
              Vessels
            </span>
            <span className="rounded-full bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-slate2-300">
              {ships.length}
            </span>
          </button>
        ) : (
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div className="flex h-9 shrink-0 items-center justify-between border-b border-ink-800 px-2">
              <span className="flex items-center gap-1.5 pl-1 text-[11px] font-medium uppercase tracking-wider text-slate2-500">
                <Anchor size={12} className="text-accent-safe" />
                Panel
              </span>
              <button
                type="button"
                onClick={() => setSidebarOpen(false)}
                className="rounded p-1.5 text-slate2-400 transition hover:bg-ink-800 hover:text-slate2-200"
                title="Hide vessel list"
                aria-label="Collapse sidebar"
              >
                <ChevronLeft size={18} />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-hidden">
              <Sidebar
                ships={ships}
                bySource={bySource}
                selected={selected}
                isLoading={isLoading}
                errors={errors}
                renderer={renderer}
                onSelect={handleSelect}
              />
            </div>
          </div>
        )}
      </aside>
      <main className="relative isolate z-10 min-w-0 flex-1 overflow-hidden">
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
        <div className="starfield-static z-10 opacity-45" aria-hidden />
        <AnalysisStack
          selectedShip={selected}
          onSelectShip={setSelected}
          onSpeciesHighlightChange={handleSpeciesHighlightChange}
        />
        <div className="pointer-events-none absolute bottom-5 left-1/2 z-30 -translate-x-1/2">
          <div className="glass-surface glass-shell pointer-events-auto relative flex items-center gap-1 p-2.5">
            {(
              [
                { id: "vessels", label: "Vessels", icon: ShipIcon },
                { id: "incidents", label: "Incidents", icon: AlertTriangle },
                { id: "zones", label: "Zones", icon: MapPinned },
                { id: "layers", label: "Layers", icon: Layers3 },
              ] as const
            ).map(({ id, label, icon: Icon }) => {
              const active = activeDockTab === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setActiveDockTab(id)}
                  className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold uppercase tracking-[0.02em] transition ${
                    active
                      ? "glass-chip text-accent-safe"
                      : "text-slate2-300 hover:glass-chip hover:text-slate2-100"
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
                className={`rounded px-2 py-1 transition ${
                  renderer === "globe"
                    ? "glass-chip text-accent-safe"
                    : "text-slate2-300 hover:glass-chip"
                }`}
              >
                Globe
              </button>
              <button
                type="button"
                onClick={() => setRenderer("mapbox")}
                className={`rounded px-2 py-1 transition ${
                  renderer === "mapbox"
                    ? "glass-chip text-accent-safe"
                    : "text-slate2-300 hover:glass-chip"
                }`}
              >
                Mapbox
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

import type { FeatureCollection } from "geojson";
import { Anchor, ChevronLeft, ChevronRight, Ship as ShipIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { AnalysisStack } from "@/components/AnalysisStack";
import { MapView, type MapHandle } from "@/components/MapView";
import { Sidebar } from "@/components/Sidebar";
import { useShips } from "@/hooks/useShips";
import type { Ship } from "@/types/ship";

const SIDEBAR_OPEN_KEY = "ui:sidebar-expanded";

export default function App() {
  const { ships, tracks, isLoading, errors, bySource } = useShips();
  const [selected, setSelected] = useState<Ship | null>(null);
  const [speciesOverlay, setSpeciesOverlay] = useState<FeatureCollection | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    if (typeof window === "undefined") return true;
    const raw = window.localStorage.getItem(SIDEBAR_OPEN_KEY);
    if (raw === "0") return false;
    if (raw === "1") return true;
    return true;
  });
  const mapRef = useRef<MapHandle | null>(null);

  const handleSpeciesHighlightChange = useCallback((geojson: FeatureCollection | null) => {
    setSpeciesOverlay(geojson);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SIDEBAR_OPEN_KEY, sidebarOpen ? "1" : "0");
  }, [sidebarOpen]);

  const handleSelect = (ship: Ship | null) => {
    setSelected(ship);
    if (ship) mapRef.current?.flyTo(ship.lon, ship.lat, 5);
  };

  return (
    <div className="flex h-screen w-screen bg-ink-950 text-slate2-200">
      <aside
        className={`flex shrink-0 flex-col border-r border-ink-800 bg-ink-950 transition-[width] duration-200 ease-out ${
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
                onSelect={handleSelect}
              />
            </div>
          </div>
        )}
      </aside>
      <main className="relative flex-1">
        <MapView
          ref={mapRef}
          ships={ships}
          tracks={tracks}
          selected={selected}
          onSelect={setSelected}
          speciesOverlay={speciesOverlay}
        />
        <AnalysisStack
          selectedShip={selected}
          onSelectShip={setSelected}
          onSpeciesHighlightChange={handleSpeciesHighlightChange}
        />
      </main>
    </div>
  );
}

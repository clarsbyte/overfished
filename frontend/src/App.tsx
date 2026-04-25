import { api } from "@/lib/api";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, PlayCircle } from "lucide-react";
import { Suspense, lazy, useRef, useState } from "react";
import type { GlobeMethods } from "react-globe.gl";
import { DocumentDownloadsPanel } from "./components/DocumentDownloadsPanel";
import type { FisheryRegion, LayerOverrides } from "./components/OverfishGlobe";
import { LayersPanel, type LayerState } from "./components/panels/LayersPanel";
import { LiveAlertsPanel } from "./components/panels/LiveAlertsPanel";
import { RiskHeatmapMini } from "./components/panels/RiskHeatmapMini";
import { TodaysOverviewBar } from "./components/panels/TodaysOverviewBar";
import { VesselDetailsPanel } from "./components/panels/VesselDetailsPanel";
import { useDrawController } from "./components/useDrawController";
import type { DocumentArtifact, Vessel } from "./types/schemas";

const OverfishGlobe = lazy(() =>
  import("./components/OverfishGlobe").then((m) => ({ default: m.OverfishGlobe })),
);
const IntroSequence = lazy(() =>
  import("./components/IntroSequence").then((m) => ({ default: m.IntroSequence })),
);
const DocumentPreviewModal = lazy(() =>
  import("./components/DocumentPreviewModal").then((m) => ({
    default: m.DocumentPreviewModal,
  })),
);

const DEMO_CASE_ID = "demo";

const DEFAULT_LAYERS: LayerState = {
  showVessels: true,
  showHeatmap: true,
  showPaths: true,
  flightCount: 60,
};

export default function App() {
  const [introDone, setIntroDone] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<DocumentArtifact | null>(null);
  const [selectedVessel, setSelectedVessel] = useState<Vessel | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<FisheryRegion | null>(null);
  const [layers, setLayers] = useState<LayerState>(DEFAULT_LAYERS);

  const globeRef = useRef<GlobeMethods>();
  const draw = useDrawController({
    globeRef,
    onCommit: async (polygon) => {
      try {
        await api.defineRegion(polygon);
      } catch (e) {
        console.warn("defineRegion failed:", e);
      }
    },
  });

  const queryClient = useQueryClient();

  const fineQ = useQuery({
    queryKey: ["fine", DEMO_CASE_ID],
    queryFn: () => api.caseFine(DEMO_CASE_ID),
  });

  const fisheryRegionsQ = useQuery({
    queryKey: ["fisheryRegions"],
    queryFn: () => api.fisheryRegions(),
  });

  const renderDocsM = useMutation({
    mutationFn: () => api.renderDocumentFamily(DEMO_CASE_ID),
  });

  const notifyPortM = useMutation({
    mutationFn: () => api.notifyPort(DEMO_CASE_ID),
  });

  const onRunDemo = async () => {
    if (renderDocsM.isPending) return;
    await renderDocsM.mutateAsync();
    queryClient.invalidateQueries({ queryKey: ["fine"] });
  };

  const portCalls = (() => {
    const r = notifyPortM.data;
    if (!r) return [];
    return [
      {
        startLat: -0.7533,
        startLng: -90.3689,
        endLat: r.port.lat,
        endLng: r.port.lon,
      },
    ];
  })();

  const layerOverrides: LayerOverrides = {
    showVessels: layers.showVessels,
    showHeatmap: layers.showHeatmap,
    showPaths: layers.showPaths,
    flightCount: layers.flightCount,
  };

  const handleAlertSelect = (regionId: string) => {
    const region = (fisheryRegionsQ.data ?? []).find((r) => r.region_id === regionId);
    if (region) setSelectedRegion(region);
  };

  return (
    <>
      {!introDone && (
        <Suspense fallback={null}>
          <IntroSequence onComplete={() => setIntroDone(true)} />
        </Suspense>
      )}

      <div
        className={`${introDone ? "opacity-100" : "opacity-0"} transition-opacity duration-700 min-h-screen`}
      >
        <Suspense fallback={null}>
          <OverfishGlobe
            draw={draw}
            onVesselSelected={setSelectedVessel}
            onRegionSelected={setSelectedRegion}
            portCalls={portCalls}
            layerOverrides={layerOverrides}
          />
        </Suspense>

        {/* Top-bar HUD */}
        <header className="fixed top-0 left-0 right-0 z-10 px-6 py-4 flex items-center justify-between pointer-events-none">
          <div className="pointer-events-auto">
            <div className="text-[10px] font-mono tracking-[0.3em] text-cyan-400/60 uppercase">
              Overfish AI · Maritime Surveillance Console
            </div>
            <div className="text-xs font-mono text-slate-500 mt-0.5">
              Region: {selectedRegion?.name ?? "Galápagos Marine Reserve"} · Mode: {draw.mode}
            </div>
          </div>

          <div className="flex gap-2 pointer-events-auto">
            <button
              onClick={() => (draw.mode === "drawing" ? draw.reset() : draw.startDrawing())}
              className="px-3 py-2 bg-ink-900/80 backdrop-blur border border-cyan-500/30 rounded text-xs font-mono tracking-[0.15em] text-cyan-300 hover:bg-cyan-500/10 hover:border-cyan-500/60 transition-colors flex items-center gap-2"
            >
              <Pencil className="w-3.5 h-3.5" />
              {draw.mode === "drawing" ? "CANCEL DRAW (Esc)" : "DEFINE REGION"}
            </button>

            <button
              onClick={onRunDemo}
              disabled={renderDocsM.isPending}
              className="px-3 py-2 bg-red-500/10 backdrop-blur border border-red-500/40 rounded text-xs font-mono tracking-[0.15em] text-red-300 hover:bg-red-500/20 hover:border-red-500/70 transition-colors flex items-center gap-2 disabled:opacity-50"
            >
              <PlayCircle className="w-3.5 h-3.5" />
              {renderDocsM.isPending ? "RENDERING…" : "RUN DEMO FLOW"}
            </button>
          </div>
        </header>

        {/* Drawing instructions */}
        {draw.mode === "drawing" && (
          <div className="fixed top-20 left-6 z-10 bg-ink-900/90 backdrop-blur border border-cyan-500/30 rounded p-4 max-w-xs pointer-events-auto">
            <div className="text-[10px] font-mono tracking-[0.2em] text-cyan-400/60 uppercase mb-2">
              Region drawing
            </div>
            <ul className="text-xs text-slate-300 space-y-1 list-disc list-inside">
              <li>Click on the globe to place vertices</li>
              <li>Double-click or press Enter to commit (≥3 vertices)</li>
              <li>Press Esc to cancel</li>
            </ul>
            <div className="text-[10px] font-mono text-slate-500 mt-2">
              Vertices: {draw.vertices.length}
            </div>
          </div>
        )}

        {/* Right column: alerts + layers + (conditional) vessel details */}
        <div className="fixed top-20 right-6 z-10 flex flex-col gap-3 pointer-events-none">
          <LiveAlertsPanel onRegionSelect={handleAlertSelect} />
          <LayersPanel value={layers} onChange={setLayers} />
          <VesselDetailsPanel
            vessel={selectedVessel}
            onClose={() => setSelectedVessel(null)}
            onRunDemo={onRunDemo}
            onNotifyPort={() => notifyPortM.mutate()}
            runDemoPending={renderDocsM.isPending}
            notifyPortPending={notifyPortM.isPending}
          />
        </div>

        {/* Bottom-center metric tiles */}
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
          <TodaysOverviewBar />
        </div>

        {/* Bottom-left mini heatmap */}
        <div className="fixed bottom-6 left-6 z-10 pointer-events-none">
          <RiskHeatmapMini />
        </div>

        {/* Bottom-right document panel (shown after demo flow) */}
        <div className="fixed bottom-6 right-6 z-10 w-[640px] max-w-[calc(100vw-3rem)]">
          <DocumentDownloadsPanel
            documents={renderDocsM.data ?? []}
            totalFineUsd={fineQ.data?.total_fine_usd ?? 0}
            visible={Boolean(renderDocsM.data)}
            onPreview={setPreviewDoc}
          />
        </div>

        <Suspense fallback={null}>
          <DocumentPreviewModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />
        </Suspense>
      </div>
    </>
  );
}

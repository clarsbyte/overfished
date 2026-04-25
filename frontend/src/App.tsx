import { useRef, useState } from "react";
import type { GlobeMethods } from "react-globe.gl";
import { OverfishGlobe } from "./components/OverfishGlobe";
import { useDrawController } from "./components/useDrawController";
import { IntroSequence } from "./components/IntroSequence";
import type { Vessel } from "./types/schemas";

// New Dashboard Components
import { AquaWatchSidebar } from "./components/AquaWatchSidebar";
import { DashboardTopBar } from "./components/DashboardTopBar";
import { DashboardRightPanel } from "./components/DashboardRightPanel";
import { DashboardBottomBar } from "./components/DashboardBottomBar";
import { GlobeControlsProvider } from "./components/GlobeControlsContext";

const DEFAULT_LAYERS: LayerState = {
  showVessels: true,
  showHeatmap: true,
  showPaths: true,
  flightCount: 60,
};

export default function App() {
  const [introDone, setIntroDone] = useState(false);
  const [selectedVessel, setSelectedVessel] = useState<Vessel | null>(null);

  const globeRef = useRef<GlobeMethods>();
  const draw = useDrawController({
    globeRef,
    onCommit: () => { }
  });

  return (
    <GlobeControlsProvider>
      <div className="relative w-screen h-screen bg-[#030708] overflow-hidden">
        {!introDone && <IntroSequence onComplete={() => setIntroDone(true)} />}

        <div className={`transition-opacity duration-1000 ${introDone ? "opacity-100" : "opacity-0"}`}>
          {/* Background Globe */}
          <div className="absolute inset-x-0 inset-y-0 z-0">
            <OverfishGlobe
              draw={draw}
              onVesselSelected={setSelectedVessel}
            />
          </div>

          {/* UI Overlay Layer */}
          <div className="absolute inset-0 z-10 p-8 flex pointer-events-none">
            {/* Left Sidebar */}
            <div className="h-full pr-4 flex-shrink-0 pointer-events-auto">
              <AquaWatchSidebar />
            </div>

            {/* Main Content Area */}
            <div className="flex-1 flex flex-col min-w-0">
              {/* Top Bar */}
              <div className="w-full">
                <DashboardTopBar />
              </div>

              <div className="flex-1 flex justify-between items-stretch overflow-hidden">
                {/* Center Spacer to show Globe */}
                <div className="flex-1" />

                {/* Right Panel */}
                <div className="h-full pl-4 flex-shrink-0 pointer-events-auto">
                  <DashboardRightPanel />
                </div>
              </div>

              {/* Spacer for Bottom Bar height */}
              <div className="h-16" />
            </div>

            {/* Centered Bottom Bar */}
            <div className="absolute bottom-10 left-1/2 -translate-x-1/2 pointer-events-auto">
              <DashboardBottomBar />
            </div>
          </div>
        </div>
      </div>
    </GlobeControlsProvider>
  );
}

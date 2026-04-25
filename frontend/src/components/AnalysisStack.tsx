import type { FeatureCollection } from "geojson";

import { ErrorBoundary } from "./ErrorBoundary";
import { VesselDetailPanel } from "./VesselDetailPanel";
import { AgentsPanel } from "./panels/AgentsPanel";
import { SequenceModelsPanel } from "./panels/SequenceModelsPanel";
import { SpeciesExposurePanel } from "./panels/SpeciesExposurePanel";
import type { Ship } from "@/types/ship";

interface Props {
  selectedShip: Ship | null;
  onSelectShip?: (ship: Ship | null) => void;
  onSpeciesHighlightChange?: (geojson: FeatureCollection | null) => void;
}

export function AnalysisStack({
  selectedShip,
  onSelectShip,
  onSpeciesHighlightChange,
}: Props) {
  return (
    <div className="pointer-events-none absolute right-4 top-4 z-10 flex max-h-[calc(100vh-2rem)] w-[380px] max-w-[calc(100%-2rem)] flex-col items-end gap-3 overflow-y-auto pr-1">
      <ErrorBoundary label="Vessel detail">
        <VesselDetailPanel
          ship={selectedShip}
          onClose={() => onSelectShip?.(null)}
        />
      </ErrorBoundary>
      <ErrorBoundary label="Agents">
        <AgentsPanel selectedShip={selectedShip} />
      </ErrorBoundary>
      <ErrorBoundary label="Sequence models">
        <SequenceModelsPanel />
      </ErrorBoundary>
      {onSpeciesHighlightChange && (
        <ErrorBoundary label="Species exposure">
          <SpeciesExposurePanel onHighlightChange={onSpeciesHighlightChange} />
        </ErrorBoundary>
      )}
    </div>
  );
}

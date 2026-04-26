import { useQuery } from "@tanstack/react-query";
import type { FeatureCollection } from "geojson";
import { Fish } from "lucide-react";
import { useEffect, useState } from "react";

import { CollapsiblePanel, type PanelStatus } from "@/components/CollapsiblePanel";
import { api, type DemoSpecies, type Risk } from "@/lib/api";

const SPECIES_OPTIONS: { id: DemoSpecies; label: string }[] = [
  { id: "cod", label: "Cod" },
  { id: "salmon", label: "Salmon" },
  { id: "trout", label: "Trout" },
];

const RISK_BADGE: Record<Risk, string> = {
  confirmed_iuu: "bg-accent-iuu/25 text-accent-iuu ring-accent-iuu/50",
  high_risk: "bg-accent-iuu/15 text-red-300 ring-red-400/40",
  suspect: "bg-accent-suspect/20 text-accent-suspect ring-accent-suspect/40",
  safe: "bg-accent-safe/15 text-accent-safe ring-accent-safe/35",
};

interface Props {
  onHighlightChange: (geojson: FeatureCollection | null) => void;
}

export function SpeciesExposurePanel({ onHighlightChange }: Props) {
  const [species, setSpecies] = useState<DemoSpecies>("cod");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["species-fishing-exposure", species],
    queryFn: () => api.speciesFishingExposure(species),
  });

  useEffect(() => {
    onHighlightChange(data?.geojson ?? null);
    return () => onHighlightChange(null);
  }, [data?.geojson, onHighlightChange]);

  const status: PanelStatus = isLoading ? "running" : isError ? "error" : data ? "ok" : "idle";

  return (
    <CollapsiblePanel
      id="species-exposure"
      title="Species & IUU exposure"
      titleShort="Species"
      icon={<Fish size={14} />}
      status={status}
      defaultOpen
    >
      <div className="pointer-events-auto space-y-3">
        <p className="text-[10px] leading-snug text-slate2-500">{data?.disclaimer}</p>

        <div className="flex flex-wrap gap-1">
          {SPECIES_OPTIONS.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => setSpecies(o.id)}
              className={`rounded px-2 py-1 text-[11px] font-medium transition ${
                species === o.id
                  ? "bg-accent-safe/20 text-accent-safe ring-1 ring-accent-safe/40"
                  : "bg-ink-900 text-slate2-400 hover:bg-ink-800"
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>

        {isError && (
          <pre className="whitespace-pre-wrap break-words rounded border border-accent-iuu/40 bg-accent-iuu/10 p-2 text-[11px] text-accent-iuu">
            {(error as Error).message}
          </pre>
        )}

        {isLoading && <p className="text-[11px] text-slate2-400">Loading regions…</p>}

        {data && (
          <ol className="max-h-64 space-y-2 overflow-y-auto pr-0.5">
            {data.regions.map((r, i) => (
              <li
                key={r.region_id}
                className="rounded border border-ink-800 bg-ink-900/80 p-2 text-[11px] leading-snug text-slate2-200"
              >
                <div className="mb-1 flex items-start justify-between gap-2">
                  <span className="font-medium text-slate2-100">
                    {i + 1}. {r.name}
                  </span>
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] uppercase tracking-wide ring-1 ${RISK_BADGE[r.risk]}`}
                  >
                    {r.risk.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="text-[10px] text-slate2-400">{r.species_note}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </CollapsiblePanel>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef } from "react";

import {
  agentApi,
  type ModelContext,
  type PerMmsiSummary,
  type SequenceLatest,
} from "@/lib/agentApi";

interface Result {
  ready: boolean;
  byMmsi: Map<string, PerMmsiSummary>;
  reportNarration: string | null;
  generatedAt: string | null;
  source: "demo" | "canonical" | null;
  isFetching: boolean;
  isTraining: boolean;
  trainError: Error | null;
  retrain: () => void;
}

export function useSequenceLatest(): Result {
  const qc = useQueryClient();

  const latest = useQuery<SequenceLatest>({
    queryKey: ["sequence", "latest"],
    queryFn: agentApi.sequenceLatest,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const train = useMutation({
    mutationFn: () => agentApi.sequenceRunCanonical(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sequence", "latest"] }),
  });

  // Auto-kick a canonical training run on first load if the cache is empty.
  // Guarded by a ref so we don't loop on transient errors.
  const autoKicked = useRef(false);
  useEffect(() => {
    if (autoKicked.current) return;
    if (latest.isLoading || latest.isFetching) return;
    if (latest.data?.ready) return;
    autoKicked.current = true;
    train.mutate();
  }, [latest.data?.ready, latest.isLoading, latest.isFetching, train]);

  return useMemo<Result>(() => {
    const data = latest.data;
    const perMmsi = data?.report?.per_mmsi_summary ?? null;
    const byMmsi = new Map<string, PerMmsiSummary>();
    if (perMmsi) {
      for (const [k, v] of Object.entries(perMmsi)) {
        byMmsi.set(String(k), v);
      }
    }
    return {
      ready: !!data?.ready,
      byMmsi,
      reportNarration: data?.report?.narration ?? null,
      generatedAt: data?.generated_at ?? null,
      source: data?.source ?? null,
      isFetching: latest.isFetching,
      isTraining: train.isPending,
      trainError: (train.error as Error | null) ?? null,
      retrain: () => train.mutate(),
    };
  }, [latest.data, latest.isFetching, train]);
}

export function buildModelContext(
  selectedMmsi: string | null | undefined,
  byMmsi: Map<string, PerMmsiSummary>,
  reportNarration: string | null,
  generatedAt: string | null,
  source: "demo" | "canonical" | null,
  nearbyMmsis: string[] = [],
): ModelContext | null {
  if (byMmsi.size === 0) return null;
  const selected = selectedMmsi ? byMmsi.get(String(selectedMmsi)) ?? null : null;
  const nearby: PerMmsiSummary[] = [];
  const seen = new Set<string>(selected ? [selected.mmsi] : []);
  for (const m of nearbyMmsis) {
    const v = byMmsi.get(String(m));
    if (v && !seen.has(v.mmsi)) {
      nearby.push(v);
      seen.add(v.mmsi);
      if (nearby.length >= 5) break;
    }
  }
  if (!selected && nearby.length === 0 && !reportNarration) return null;
  return {
    selected,
    nearby,
    report_narration: reportNarration,
    generated_at: generatedAt,
    source,
  };
}

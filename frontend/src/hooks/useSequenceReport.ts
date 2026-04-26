import { useSyncExternalStore } from "react";

import {
  agentApi,
  type SequenceReport,
  type SequenceReportRequest,
} from "@/lib/agentApi";

interface State {
  data: SequenceReport | null;
  error: Error | null;
  isPending: boolean;
  lastParams: SequenceReportRequest | null;
}

let state: State = {
  data: null,
  error: null,
  isPending: false,
  lastParams: null,
};

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return state;
}

function setState(patch: Partial<State>) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}

async function run(params?: SequenceReportRequest) {
  setState({ isPending: true, error: null, lastParams: params ?? state.lastParams });
  try {
    const data =
      params && (params.training || params.csv_path || params.use_sample === false)
        ? await agentApi.sequenceReport({
            use_sample: params.use_sample ?? true,
            include_narration: params.include_narration ?? true,
            csv_path: params.csv_path ?? null,
            training: params.training,
          })
        : await agentApi.sequenceDemo();
    setState({ data, isPending: false, error: null });
  } catch (error) {
    setState({ error: error as Error, isPending: false });
  }
}

async function runCanonical() {
  setState({ isPending: true, error: null, lastParams: state.lastParams });
  try {
    const data = await agentApi.sequenceRunCanonical();
    setState({ data, isPending: false, error: null });
  } catch (error) {
    setState({ error: error as Error, isPending: false });
  }
}

export interface UseSequenceReport {
  data: SequenceReport | null;
  error: Error | null;
  isPending: boolean;
  lastParams: SequenceReportRequest | null;
  run: (params?: SequenceReportRequest) => Promise<void>;
  runCanonical: () => Promise<void>;
}

export function useSequenceReport(): UseSequenceReport {
  const snap = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return {
    data: snap.data,
    error: snap.error,
    isPending: snap.isPending,
    lastParams: snap.lastParams,
    run,
    runCanonical,
  };
}

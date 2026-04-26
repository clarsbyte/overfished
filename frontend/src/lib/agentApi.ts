import { buildAuthFetchOptions } from "@/lib/authToken";

function resolveAgentApiBase(): string {
  const raw = import.meta.env.VITE_AGENT_API_URL;
  if (raw == null || String(raw).trim() === "") return "/agentapi";
  return String(raw).replace(/\/$/, "");
}

const BASE = resolveAgentApiBase();

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(
    `${BASE}${path}`,
    await buildAuthFetchOptions({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : "{}",
    }),
  );
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} (${path})${text ? ` - ${text}` : ""}`);
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, await buildAuthFetchOptions());
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} (${path})${text ? ` - ${text}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export type AgentTextBlock = {
  text?: string;
  type?: string;
  [k: string]: unknown;
};

export interface AgentRunResponse {
  status?: string;
  message?: string | AgentTextBlock[];
  detail?: Record<string, unknown> | null;
  // Legacy fields some callers still read.
  agent?: string;
  output?: string | AgentTextBlock[];
  [k: string]: unknown;
}

export interface SequenceTopKPrediction {
  mmsi: string;
  class_id: number;
  probability: number;
}
export interface SequenceValRow {
  row_index: number;
  true_mmsi: string;
  true_class_id: number;
  topk_predictions: SequenceTopKPrediction[];
}
export interface SequenceModelBlock {
  model_type: "rnn" | "bilstm";
  metrics: Record<string, number>;
  n_val_rows: number;
  n_classes: number;
  val_rows_sample: SequenceValRow[];
}
export interface SequenceEnsembleBlock {
  metrics: Record<string, number> | null;
  n_val_rows: number;
  val_rows_sample: SequenceValRow[] | null;
}
export interface SuspectWindow {
  true_mmsi: string;
  model_top_mmsi: string;
  confidence: number;
  note: string;
}

export type ModelRisk = "safe" | "uncertain" | "spoof_suspect";

export interface PerMmsiSummary {
  mmsi: string;
  n_windows: number;
  top1_match_rate: number;
  mean_confidence: number;
  alias_mmsi: string | null;
  alias_share: number;
  model_risk: ModelRisk;
  narration: string;
}

export interface ModelContext {
  selected: PerMmsiSummary | null;
  nearby: PerMmsiSummary[];
  report_narration: string | null;
  generated_at: string | null;
  source: "demo" | "canonical" | null;
}

export interface SequenceReport {
  class_to_mmsi: Record<string, string>;
  feature_columns: string[];
  selected_model_type: "rnn" | "bilstm";
  ensemble_val_metrics: Record<string, number> | null;
  rnn: SequenceModelBlock;
  bilstm: SequenceModelBlock;
  ensemble: SequenceEnsembleBlock | null;
  suspect_readout: { suspect_windows: SuspectWindow[]; count: number };
  per_mmsi_summary?: Record<string, PerMmsiSummary>;
  narration?: string;
}

export interface SequenceLatest {
  ready: boolean;
  report: SequenceReport | null;
  generated_at: string | null;
  source: "demo" | "canonical" | null;
}

export interface SequenceReportRequest {
  use_sample?: boolean;
  csv_path?: string | null;
  include_narration?: boolean;
  training?: {
    epochs?: number;
    seq_len?: number;
    hidden_dim?: number;
    batch_size?: number;
    val_fraction?: number;
    top_k?: number;
    max_val_rows?: number;
  };
}

export type AgentAction = "gfw" | "vessel" | "law" | "complete";

export interface AgentRunPayload {
  latitude?: number;
  longitude?: number;
  radius_miles?: number;
  mmsi?: string;
  query?: string;
  days_back?: number;
}

function buildAgentRunBody(
  action: AgentAction,
  payload: AgentRunPayload,
  modelContext?: ModelContext | null,
) {
  // /agent/run expects { query, context }. Context is the LangChain
  // "static runtime context" slot — see plugins/fetch_plugin/.../factory.py
  // and backend/pipeline_agent.py:_format_model_context_block.
  const query =
    payload.query ??
    (action === "gfw"
      ? payload.mmsi ?? action
      : `agent action: ${action}`);
  return {
    query,
    context: {
      action,
      ...payload,
      model_context: modelContext ?? null,
    },
  };
}

function agentRun(
  action: AgentAction,
  payload: AgentRunPayload,
  modelContext?: ModelContext | null,
) {
  return post<AgentRunResponse>(
    "/agent/run",
    buildAgentRunBody(action, payload, modelContext),
  );
}

export const agentApi = {
  run: agentRun,

  gfw: (query: string, daysBack = 365, modelContext?: ModelContext | null) =>
    agentRun("gfw", { query, mmsi: query, days_back: daysBack }, modelContext),

  vessel: (
    latitude: number,
    longitude: number,
    radius_miles = 50,
    modelContext?: ModelContext | null,
  ) =>
    agentRun("vessel", { latitude, longitude, radius_miles }, modelContext),

  law: (
    latitude: number,
    longitude: number,
    modelContext?: ModelContext | null,
  ) => agentRun("law", { latitude, longitude }, modelContext),

  complete: (
    latitude: number,
    longitude: number,
    mmsi?: string,
    radius_miles = 50,
    modelContext?: ModelContext | null,
  ) =>
    agentRun(
      "complete",
      { latitude, longitude, radius_miles, mmsi },
      modelContext,
    ),

  sequenceDemo: () => get<SequenceReport>("/ml/sequence/demo"),
  sequenceReport: (body: SequenceReportRequest) =>
    post<SequenceReport>("/ml/sequence/report", body),
  sequenceLatest: () => get<SequenceLatest>("/ml/sequence/latest"),
  sequenceRunCanonical: () =>
    post<SequenceReport>("/ml/sequence/run-canonical"),
};

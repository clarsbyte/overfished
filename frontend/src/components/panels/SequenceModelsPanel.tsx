import { Brain, Network, Play } from "lucide-react";
import { useMemo, useState } from "react";

import { CollapsiblePanel, type PanelStatus } from "@/components/CollapsiblePanel";
import { useSequenceReport } from "@/hooks/useSequenceReport";
import { SequencePredictionsList } from "./SequencePredictionsList";

type ModelTab = "rnn" | "bilstm";

export function SequenceModelsPanel({ className }: { className?: string }) {
  const { data, error, isPending, run } = useSequenceReport();
  const [epochs, setEpochs] = useState(1);
  const [seqLen, setSeqLen] = useState(3);
  const [hiddenDim, setHiddenDim] = useState(8);
  const [tab, setTab] = useState<ModelTab>("rnn");

  const status: PanelStatus = isPending
    ? "running"
    : error
      ? "error"
      : data
        ? "ok"
        : "idle";

  const agreement = useMemo(() => {
    if (!data) return null;
    const rnnRows = data.rnn.val_rows_sample;
    const lstmRows = data.bilstm.val_rows_sample;
    if (!rnnRows.length || !lstmRows.length) return null;
    let agreed = 0;
    let total = 0;
    for (let i = 0; i < Math.min(rnnRows.length, lstmRows.length); i++) {
      const r = rnnRows[i].topk_predictions[0];
      const l = lstmRows[i].topk_predictions[0];
      if (r && l) {
        total++;
        if (r.mmsi === l.mmsi) agreed++;
      }
    }
    return { agreed, total };
  }, [data]);

  const activeBlock = tab === "rnn" ? data?.rnn : data?.bilstm;
  const acc = activeBlock?.metrics?.top1_accuracy;
  const loss = activeBlock?.metrics?.loss;

  return (
    <CollapsiblePanel
      id="sequence-models"
      title="RNN + Bi-LSTM"
      className={className}
      titleShort="Models"
      icon={
        <span className="flex items-center gap-0.5">
          <Brain size={12} />
          <Network size={12} />
        </span>
      }
      status={status}
      minimizableToChip
      chipStorageKey="sequence-models"
      badge={
        activeBlock && (
          <span className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-slate2-400">
            {tab.toUpperCase()} n={activeBlock.n_val_rows}/{activeBlock.n_classes}
          </span>
        )
      }
    >
      <div className="pointer-events-auto space-y-3">
        <div className="grid grid-cols-3 gap-2">
          <Slider label="epochs" value={epochs} min={1} max={5} onChange={setEpochs} />
          <Slider label="seq_len" value={seqLen} min={2} max={8} onChange={setSeqLen} />
          <Slider label="hidden" value={hiddenDim} min={8} max={64} step={8} onChange={setHiddenDim} />
        </div>
        <button
          type="button"
          onClick={() =>
            run({
              use_sample: true,
              include_narration: true,
              training: { epochs, seq_len: seqLen, hidden_dim: hiddenDim, top_k: 3, max_val_rows: 12 },
            })
          }
          disabled={isPending}
          className="flex w-full items-center justify-center gap-1.5 rounded bg-accent-safe/10 px-2 py-1.5 text-xs font-medium text-accent-safe ring-1 ring-accent-safe/40 transition hover:bg-accent-safe/20 disabled:opacity-50"
        >
          <Play size={12} />
          {isPending ? "Training... (~10-30 s)" : "Run RNN + Bi-LSTM"}
        </button>

        {error && (
          <pre className="whitespace-pre-wrap break-words rounded border border-accent-iuu/40 bg-accent-iuu/10 p-2 text-[11px] text-accent-iuu">
            {error.message}
          </pre>
        )}

        <div className="flex flex-wrap gap-1">
          <button
            type="button"
            onClick={() => setTab("rnn")}
            className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] transition ${
              tab === "rnn"
                ? "bg-accent-safe/20 text-accent-safe ring-1 ring-accent-safe/40"
                : "bg-ink-900 text-slate2-400 hover:bg-ink-800"
            }`}
          >
            <Brain size={12} />
            RNN
          </button>
          <button
            type="button"
            onClick={() => setTab("bilstm")}
            className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] transition ${
              tab === "bilstm"
                ? "bg-accent-safe/20 text-accent-safe ring-1 ring-accent-safe/40"
                : "bg-ink-900 text-slate2-400 hover:bg-ink-800"
            }`}
          >
            <Network size={12} />
            Bi-LSTM
          </button>
        </div>

        {!data && !error && !isPending && (
          <p className="rounded border border-dashed border-ink-800 px-2 py-2 text-center text-[11px] text-slate2-400">
            Run training to compare both heads on the same validation slice.
          </p>
        )}

        {tab === "bilstm" && data && agreement && (
          <div className="rounded border border-ink-800 bg-ink-900/60 px-2 py-1.5 text-[11px]">
            <span className="text-slate2-400">RNN / Bi-LSTM agreement: </span>
            <span className="font-mono text-slate2-200">
              {agreement.agreed}/{agreement.total}
            </span>
            <span className="ml-1 text-slate2-400">
              ({agreement.total ? ((agreement.agreed / agreement.total) * 100).toFixed(0) : 0}%)
            </span>
          </div>
        )}

        {data?.selected_model_type === "bilstm" && tab === "bilstm" && (
          <div className="rounded border border-accent-safe/40 bg-accent-safe/5 px-2 py-1 text-[10px] text-accent-safe">
            Selected by training comparison.
          </div>
        )}

        {activeBlock && (
          <>
            <div className="grid grid-cols-2 gap-2 text-[10px]">
              <Metric label="top-1 acc" value={acc !== undefined ? `${(acc * 100).toFixed(1)}%` : "-"} />
              <Metric label="loss" value={loss !== undefined ? loss.toFixed(3) : "-"} />
            </div>
            <SequencePredictionsList rows={activeBlock.val_rows_sample} />
          </>
        )}
      </div>
    </CollapsiblePanel>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between text-[10px] text-slate2-400">
        <span>{label}</span>
        <span className="font-mono text-slate2-200">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-accent-safe"
      />
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded bg-ink-900/60 px-2 py-1">
      <div className="text-[10px] uppercase tracking-wider text-slate2-400">{label}</div>
      <div className="font-mono text-xs text-slate2-200">{value}</div>
    </div>
  );
}

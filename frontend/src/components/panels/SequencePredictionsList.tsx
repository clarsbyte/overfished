import type { SequenceValRow } from "@/lib/agentApi";

interface Props {
  rows: SequenceValRow[];
  highlightMmsi?: string;
}

const BAR_COLORS = ["#00d4ff", "#7a8398", "#ffaa00", "#ff3b3b", "#a78bfa"];

export function SequencePredictionsList({ rows, highlightMmsi }: Props) {
  if (!rows.length) {
    return (
      <p className="rounded border border-dashed border-ink-800 px-2 py-3 text-center text-[11px] text-slate2-400">
        No validation rows yet. Run the demo above.
      </p>
    );
  }
  return (
    <ol className="space-y-2">
      {rows.map((row) => {
        const top = row.topk_predictions[0];
        const correct = top && top.mmsi === row.true_mmsi;
        const isHighlighted = highlightMmsi && row.true_mmsi === highlightMmsi;
        return (
          <li
            key={row.row_index}
            className={`rounded border px-2 py-1.5 text-[11px] transition ${
              isHighlighted
                ? "border-accent-safe/60 bg-accent-safe/5"
                : "border-ink-800 bg-ink-900/60"
            }`}
          >
            <div className="mb-1 flex items-center justify-between font-mono text-[10px]">
              <span className="text-slate2-200">true: {row.true_mmsi}</span>
              <span className={correct ? "text-accent-safe" : "text-accent-suspect"}>
                {correct ? "match" : "miss"}
              </span>
            </div>
            <div className="space-y-1">
              {row.topk_predictions.map((p, i) => {
                const pct = Math.max(0, Math.min(1, p.probability)) * 100;
                return (
                  <div key={p.class_id} className="flex items-center gap-2">
                    <span className="w-20 shrink-0 truncate font-mono text-[10px] text-slate2-400">
                      {p.mmsi}
                    </span>
                    <div className="relative h-1.5 flex-1 overflow-hidden rounded bg-ink-800">
                      <div
                        className="absolute inset-y-0 left-0 rounded"
                        style={{ width: `${pct}%`, background: BAR_COLORS[i % BAR_COLORS.length] }}
                      />
                    </div>
                    <span className="w-10 shrink-0 text-right font-mono text-[10px] text-slate2-200">
                      {pct.toFixed(0)}%
                    </span>
                  </div>
                );
              })}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

const BANDS = 12;

export function RiskHeatmapMini() {
  const heatmapQ = useQuery({ queryKey: ["heatmap"], queryFn: () => api.heatmap() });

  const bars = useMemo(() => {
    const points = heatmapQ.data ?? [];
    if (points.length === 0) return [] as number[];
    const minLat = Math.min(...points.map((p) => p.lat));
    const maxLat = Math.max(...points.map((p) => p.lat));
    const span = maxLat - minLat || 1;
    const buckets = new Array(BANDS).fill(0);
    for (const p of points) {
      const idx = Math.min(BANDS - 1, Math.floor(((p.lat - minLat) / span) * BANDS));
      buckets[idx] += p.hours;
    }
    const max = Math.max(...buckets, 1);
    return buckets.map((v) => v / max);
  }, [heatmapQ.data]);

  return (
    <div className="w-56 pointer-events-auto bg-ink-900/85 backdrop-blur border border-cyan-500/20 rounded shadow-lg px-3 py-2.5">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] font-mono tracking-[0.2em] text-cyan-300/80 uppercase">
          Risk heatmap
        </span>
        <span className="text-[10px] font-mono text-slate-500">
          {heatmapQ.data?.length ?? 0} pts
        </span>
      </div>
      <div className="flex items-end gap-0.5 h-12">
        {bars.length === 0 &&
          Array.from({ length: BANDS }).map((_, i) => (
            <div key={i} className="flex-1 bg-slate-800/60 rounded-sm" style={{ height: "10%" }} />
          ))}
        {bars.map((v, i) => {
          const intensity = Math.round(v * 100);
          return (
            <div
              key={i}
              className="flex-1 rounded-sm"
              style={{
                height: `${Math.max(intensity, 4)}%`,
                background: `rgba(${255}, ${Math.round(180 - v * 140)}, ${Math.round(60 - v * 40)}, ${0.35 + v * 0.55})`,
              }}
              title={`band ${i}: ${intensity}%`}
            />
          );
        })}
      </div>
      <div className="flex justify-between text-[9px] font-mono text-slate-600 mt-1">
        <span>SOUTH</span>
        <span>NORTH</span>
      </div>
    </div>
  );
}

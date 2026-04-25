import type { Vessel } from "@/types/schemas";
import { Phone, PlayCircle, X } from "lucide-react";

interface Props {
  vessel: Vessel | null;
  onClose: () => void;
  onRunDemo: () => void;
  onNotifyPort: () => void;
  runDemoPending?: boolean;
  notifyPortPending?: boolean;
}

export function VesselDetailsPanel({
  vessel,
  onClose,
  onRunDemo,
  onNotifyPort,
  runDemoPending,
  notifyPortPending,
}: Props) {
  if (!vessel) return null;

  return (
    <div className="w-80 pointer-events-auto bg-ink-900/90 backdrop-blur border border-cyan-500/25 rounded shadow-xl animate-in slide-in-from-right duration-200">
      <div className="flex items-start justify-between px-3 py-2.5 border-b border-cyan-500/15">
        <div className="min-w-0">
          <div className="text-[10px] font-mono tracking-[0.2em] text-cyan-300/60 uppercase">
            Vessel
          </div>
          <div className="text-sm text-slate-100 font-medium truncate">
            {vessel.name ?? "Unknown vessel"}
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-cyan-300 p-1 -m-1"
          aria-label="Close"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <dl className="px-3 py-2.5 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
        <Field label="MMSI" value={vessel.mmsi} mono />
        <Field label="IMO" value={vessel.imo ?? "—"} mono />
        <Field label="Flag" value={vessel.flag ?? "—"} />
        <Field label="Gear" value={vessel.gear_type ?? "—"} />
        <Field
          label="Length"
          value={vessel.length_m ? `${vessel.length_m.toFixed(0)} m` : "—"}
        />
        <Field
          label="Position"
          value={
            vessel.last_position
              ? `${vessel.last_position.lat.toFixed(2)}, ${vessel.last_position.lon.toFixed(2)}`
              : "—"
          }
          mono
        />
        <div className="col-span-2">
          <Field label="Owner" value={vessel.owner ?? "—"} />
        </div>
      </dl>

      <div className="px-3 py-2.5 border-t border-cyan-500/15 flex flex-col gap-1.5">
        <button
          onClick={onRunDemo}
          disabled={runDemoPending}
          className="px-2.5 py-1.5 bg-red-500/10 border border-red-500/40 rounded text-[11px] font-mono tracking-[0.15em] text-red-300 hover:bg-red-500/20 hover:border-red-500/70 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
        >
          <PlayCircle className="w-3.5 h-3.5" />
          {runDemoPending ? "RENDERING…" : "RUN DEMO FLOW"}
        </button>
        <button
          onClick={onNotifyPort}
          disabled={notifyPortPending}
          className="px-2.5 py-1.5 bg-ink-900/80 border border-amber-500/30 rounded text-[11px] font-mono tracking-[0.15em] text-amber-300 hover:bg-amber-500/10 hover:border-amber-500/60 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
        >
          <Phone className="w-3.5 h-3.5" />
          {notifyPortPending ? "DIALING…" : "NOTIFY PORT"}
        </button>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
        {label}
      </dt>
      <dd
        className={`text-slate-200 truncate ${mono ? "font-mono text-[11px]" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}

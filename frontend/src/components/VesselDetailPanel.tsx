import { useMutation } from "@tanstack/react-query";
import { ImageOff, Info, Phone, Ship as ShipIcon, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { CollapsiblePanel, type PanelStatus } from "@/components/CollapsiblePanel";
import { useVesselCard, useVesselCards } from "@/hooks/useVesselCards";
import { api, type NotifyPortResponse, type Risk } from "@/lib/api";
import { SOURCE_LABEL, type Ship } from "@/types/ship";

const DEMO_CASE_ID = "galapagos_demo";

interface Props {
  ship: Ship | null;
  onClose: () => void;
  onRequestAgent?: () => void;
}

const RISK_BADGE: Record<Risk, string> = {
  safe: "bg-accent-safe/15 text-accent-safe ring-accent-safe/40",
  suspect: "bg-accent-suspect/15 text-accent-suspect ring-accent-suspect/40",
  high_risk: "bg-accent-iuu/15 text-accent-iuu ring-accent-iuu/40",
  confirmed_iuu: "bg-accent-iuu/20 text-accent-iuu ring-accent-iuu/60",
};

function RiskBadge({ risk }: { risk?: Risk }) {
  if (!risk) return null;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ring-1 ${RISK_BADGE[risk]}`}
    >
      {risk.replace("_", " ")}
    </span>
  );
}

interface ImgState {
  src: string | null;
  stage: "local" | "remote" | "placeholder" | "missing";
}

/** Deterministic stock photo per MMSI (not the vessel). Requires network during demo. */
function picsumPlaceholderUrl(mmsi: string): string {
  const seed = encodeURIComponent(`vessel-${mmsi}`);
  return `https://picsum.photos/seed/${seed}/800/480`;
}

function resolveImageState(
  local: string | undefined,
  remote: string | undefined,
  mmsi: string | undefined,
): ImgState {
  if (local) return { src: local, stage: "local" };
  if (remote) return { src: remote, stage: "remote" };
  if (mmsi) return { src: picsumPlaceholderUrl(mmsi), stage: "placeholder" };
  return { src: null, stage: "missing" };
}

export function VesselDetailPanel({ ship, onClose, onRequestAgent }: Props) {
  const { isError: vesselCardsFailed, error: vesselCardsError } = useVesselCards();
  const card = useVesselCard(ship?.mmsi);
  const localUrl = card?.image_path;
  const remoteUrl = card?.image_source_url;

  const [img, setImg] = useState<ImgState>(() =>
    resolveImageState(localUrl, remoteUrl, ship?.mmsi),
  );
  const lastKeyRef = useRef<string>("");

  useEffect(() => {
    if (!ship) return;
    const key = `${ship.mmsi}|${localUrl ?? ""}|${remoteUrl ?? ""}`;
    if (key === lastKeyRef.current) return;
    lastKeyRef.current = key;
    setImg(resolveImageState(localUrl, remoteUrl, ship.mmsi));
  }, [ship, localUrl, remoteUrl]);

  const notify = useMutation<NotifyPortResponse, Error, void>({
    mutationFn: () => api.notifyPort(DEMO_CASE_ID),
  });

  useEffect(() => {
    notify.reset();
  }, [ship?.mmsi]); // eslint-disable-line react-hooks/exhaustive-deps

  const status: PanelStatus = useMemo(() => {
    if (notify.isPending) return "running";
    if (notify.isError) return "error";
    if (notify.data) return "ok";
    return "idle";
  }, [notify.isPending, notify.isError, notify.data]);

  if (!ship) return null;

  const name = card?.name ?? ship.name ?? "Unknown vessel";
  const flag = card?.flag ?? ship.flag;
  const vesselType = card?.vessel_type ?? ship.vesselType;
  const risk = (card?.risk ?? ship.risk) as Risk | undefined;
  const duration = card?.duration_hours ?? ship.durationHours;

  const handleImgError = () => {
    setImg((prev) => {
      if (prev.stage === "local" && remoteUrl) {
        return { src: remoteUrl, stage: "remote" };
      }
      if (prev.stage === "local" && !remoteUrl && ship.mmsi) {
        return { src: picsumPlaceholderUrl(ship.mmsi), stage: "placeholder" };
      }
      if (prev.stage === "remote" && ship.mmsi) {
        return { src: picsumPlaceholderUrl(ship.mmsi), stage: "placeholder" };
      }
      return { src: null, stage: "missing" };
    });
  };

  return (
    <CollapsiblePanel
      id="vessel-detail"
      title={name}
      titleShort={ship.mmsi}
      icon={<ShipIcon size={14} />}
      status={status}
      badge={
        <span className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] text-slate2-400">
          {ship.mmsi}
        </span>
      }
    >
      <div className="space-y-3">
        {vesselCardsFailed && (
          <p className="rounded border border-accent-suspect/40 bg-accent-suspect/10 px-2 py-1.5 text-[11px] text-accent-suspect">
            Could not load vessel cards: {(vesselCardsError as Error).message}
          </p>
        )}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="font-display text-sm font-semibold leading-tight text-slate2-100">
              {name}
            </div>
            <div className="font-mono text-[11px] text-slate2-400">MMSI {ship.mmsi}</div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <RiskBadge risk={risk} />
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1 text-slate2-400 transition hover:bg-ink-800 hover:text-slate2-200"
              title="Close"
              aria-label="Close vessel detail"
            >
              <X size={12} />
            </button>
          </div>
        </div>

        <div className="overflow-hidden rounded border border-ink-800 bg-ink-900">
          {img.src ? (
            <>
              <img
                key={img.src}
                src={img.src}
                alt={`${name} (MMSI ${ship.mmsi})`}
                onError={handleImgError}
                loading="lazy"
                className="block h-44 w-full object-cover"
              />
              {img.stage === "placeholder" && (
                <p className="border-t border-ink-800 bg-ink-950 px-2 py-1 text-center text-[10px] text-slate2-500">
                  Placeholder image (not this vessel)
                </p>
              )}
            </>
          ) : (
            <div className="flex h-44 w-full flex-col items-center justify-center gap-1 bg-ink-900 text-slate2-500">
              <ImageOff size={24} />
              <span className="text-[11px]">No image available</span>
            </div>
          )}
        </div>

        {card?.summary && (
          <p className="rounded border border-ink-800 bg-ink-900 p-2 text-[11px] leading-snug text-slate2-200">
            {card.summary}
          </p>
        )}

        <dl className="grid grid-cols-2 gap-x-2 gap-y-1 text-[11px]">
          {flag && (
            <>
              <dt className="text-slate2-400">Flag</dt>
              <dd>{flag}</dd>
            </>
          )}
          {vesselType && (
            <>
              <dt className="text-slate2-400">Type</dt>
              <dd className="capitalize">{vesselType}</dd>
            </>
          )}
          {typeof ship.confidence === "number" && (
            <>
              <dt className="text-slate2-400">Confidence</dt>
              <dd>{(ship.confidence * 100).toFixed(0)}%</dd>
            </>
          )}
          {typeof duration === "number" && (
            <>
              <dt className="text-slate2-400">Duration</dt>
              <dd>{duration.toFixed(1)} h</dd>
            </>
          )}
          <dt className="text-slate2-400">Source</dt>
          <dd>{SOURCE_LABEL[ship.source]}</dd>
          <dt className="text-slate2-400">Position</dt>
          <dd className="font-mono">
            {ship.lat.toFixed(3)}, {ship.lon.toFixed(3)}
          </dd>
        </dl>

        <div className="flex items-center gap-2">
          <button
            onClick={() => notify.mutate()}
            disabled={notify.isPending}
            className="flex flex-1 items-center justify-center gap-1.5 rounded bg-accent-safe/10 px-2 py-1.5 text-xs font-medium text-accent-safe ring-1 ring-accent-safe/40 transition hover:bg-accent-safe/20 disabled:opacity-50"
          >
            <Phone size={12} />
            {notify.isPending ? "Notifying..." : "Notify Port"}
          </button>
          {onRequestAgent && (
            <button
              onClick={onRequestAgent}
              className="flex items-center justify-center gap-1.5 rounded bg-ink-900 px-2 py-1.5 text-xs font-medium text-slate2-300 ring-1 ring-ink-800 transition hover:bg-ink-800"
              title="Run agents on this vessel"
            >
              <Info size={12} />
              More info
            </button>
          )}
        </div>

        {notify.isError && (
          <div className="rounded border border-accent-iuu/40 bg-accent-iuu/10 p-2 text-[11px] text-accent-iuu">
            {(notify.error as Error).message}
          </div>
        )}
        {notify.data && (
          <div className="rounded border border-ink-800 bg-ink-950 p-2 text-[11px] leading-tight">
            <div>
              <span className="text-slate2-400">Port:</span>{" "}
              <span>{notify.data.port.name}</span>{" "}
              <span className="font-mono text-slate2-400">{notify.data.port.un_locode}</span>
            </div>
            <div>
              <span className="text-slate2-400">Call:</span>{" "}
              <span className="font-mono">{notify.data.call.call_id}</span>{" "}
              <span className="text-accent-safe">{notify.data.call.status}</span>
            </div>
          </div>
        )}
      </div>
    </CollapsiblePanel>
  );
}

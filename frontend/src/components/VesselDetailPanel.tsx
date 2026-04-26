import { useMutation, useQuery } from "@tanstack/react-query";
import { ImageOff, Phone, Ship as ShipIcon, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { CollapsiblePanel, type PanelStatus } from "@/components/CollapsiblePanel";
import { useVesselCard, useVesselCards } from "@/hooks/useVesselCards";
import { api, type NotifyPortResponse, type Risk } from "@/lib/api";
import type { RiskAssessment, Vessel, VesselEvent } from "@/types/schemas";
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

const RISK_BAR: Record<Risk, string> = {
  safe: "bg-accent-safe",
  suspect: "bg-accent-suspect",
  high_risk: "bg-accent-iuu",
  confirmed_iuu: "bg-accent-iuu",
};

const RISK_TEXT: Record<Risk, string> = {
  safe: "text-accent-safe",
  suspect: "text-accent-suspect",
  high_risk: "text-accent-iuu",
  confirmed_iuu: "text-accent-iuu",
};

const EVENT_META: Record<VesselEvent["type"], { label: string; color: string; dot: string }> = {
  FISHING:    { label: "Fishing",    color: "text-red-400",    dot: "bg-red-500" },
  GAP:        { label: "AIS Gap",    color: "text-amber-400",  dot: "bg-amber-500" },
  ENCOUNTER:  { label: "Encounter",  color: "text-violet-400", dot: "bg-violet-500" },
  LOITERING:  { label: "Loitering",  color: "text-yellow-400", dot: "bg-yellow-500" },
  PORT_VISIT: { label: "Port Visit", color: "text-cyan-400",   dot: "bg-cyan-500" },
};

function fmtDate(dt: string) {
  return new Date(dt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function fmtDateTime(dt: string) {
  return new Date(dt).toLocaleDateString("en-US", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

function RiskBadge({ risk }: { risk?: Risk }) {
  if (!risk) return null;
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ring-1 ${RISK_BADGE[risk]}`}>
      {risk.replace(/_/g, " ")}
    </span>
  );
}

interface ImgState { src: string | null; stage: "local" | "remote" | "missing"; }
function resolveImage(local?: string, remote?: string): ImgState {
  if (local) return { src: local, stage: "local" };
  if (remote) return { src: remote, stage: "remote" };
  return { src: null, stage: "missing" };
}

type Tab = "overview" | "events" | "risk";

// ── helpers ──────────────────────────────────────────────────────────

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="truncate text-slate2-400">{label}</dt>
      <dd className="truncate text-slate2-200">{children}</dd>
    </>
  );
}

function Placeholder({ text, dashed }: { text: string; dashed?: boolean }) {
  return (
    <div className={`py-4 text-center text-[11px] text-slate2-400 ${dashed ? "rounded border border-dashed border-ink-800" : ""}`}>
      {text}
    </div>
  );
}

function ErrBox({ error }: { error: unknown }) {
  return (
    <div className="rounded border border-accent-iuu/40 bg-accent-iuu/10 p-2 text-[11px] text-accent-iuu">
      {(error as Error).message}
    </div>
  );
}

// ── Overview tab ─────────────────────────────────────────────────────

function OverviewTab({ ship, vessel, loading, flag, vesselType, duration, summary }: {
  ship: Ship; vessel?: Vessel; loading: boolean;
  flag?: string; vesselType?: string | null; duration?: number; summary?: string | null;
}) {
  return (
    <div className="space-y-2">
      {summary && (
        <p className="rounded border border-ink-800 bg-ink-900 p-2 text-[11px] leading-snug text-slate2-200">
          {summary}
        </p>
      )}
      {loading && !vessel ? (
        <Placeholder text="Loading vessel data…" />
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
            <Row label="MMSI"><span className="font-mono">{ship.mmsi}</span></Row>
            {vessel?.imo && <Row label="IMO"><span className="font-mono">{vessel.imo}</span></Row>}
            {flag && <Row label="Flag">{flag}</Row>}
            {(vesselType ?? vessel?.gear_type) && (
              <Row label="Type / Gear"><span className="capitalize">{vesselType ?? vessel?.gear_type}</span></Row>
            )}
            {vessel?.length_m && <Row label="Length">{vessel.length_m} m</Row>}
            {vessel?.owner && <Row label="Owner">{vessel.owner}</Row>}
            {typeof ship.confidence === "number" && (
              <Row label="Confidence">{(ship.confidence * 100).toFixed(0)}%</Row>
            )}
            {typeof duration === "number" && (
              <Row label="SAR Duration">{duration.toFixed(1)} h</Row>
            )}
            {vessel?.last_seen && <Row label="Last Seen">{fmtDate(vessel.last_seen)}</Row>}
            <Row label="Source">{SOURCE_LABEL[ship.source]}</Row>
            <Row label="Position">
              <span className="font-mono">{ship.lat.toFixed(4)}, {ship.lon.toFixed(4)}</span>
            </Row>
          </dl>

          {vessel?.authorizations && vessel.authorizations.length > 0 && (
            <div className="space-y-1 border-t border-ink-800 pt-2">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-slate2-400">Authorizations</div>
              <div className="flex flex-wrap gap-1">
                {vessel.authorizations.map((a, i) => (
                  <span key={i} className="rounded bg-ink-800 px-1.5 py-0.5 text-[10px] text-slate2-300">{a}</span>
                ))}
              </div>
            </div>
          )}

          {ship.isHighRisk !== undefined && (
            <div className="flex items-center gap-1.5 border-t border-ink-800 pt-2">
              <span className={`h-2 w-2 flex-shrink-0 rounded-full ${ship.isHighRisk ? "bg-accent-iuu" : "bg-accent-safe"}`} />
              <span className="text-[11px] text-slate2-400">
                {ship.isHighRisk ? "Flagged as high-risk" : "No high-risk flag"}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Events tab ───────────────────────────────────────────────────────

function EventsTab({ events, loading, error }: { events: VesselEvent[]; loading: boolean; error: unknown }) {
  if (loading) return <Placeholder text="Loading events…" />;
  if (error) return <ErrBox error={error} />;
  if (!events.length) return <Placeholder text="No events recorded for this vessel" dashed />;

  return (
    <div className="space-y-1.5">
      {events.map((ev) => {
        const meta = EVENT_META[ev.type] ?? { label: ev.type, color: "text-slate2-400", dot: "bg-slate2-400" };
        return (
          <div key={ev.event_id} className="rounded border border-ink-800 bg-ink-900/60 p-2 text-[11px]">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${meta.dot}`} />
                <span className={`font-semibold ${meta.color}`}>{meta.label}</span>
              </div>
              <span className="flex-shrink-0 font-mono text-[10px] text-slate2-400">{fmtDateTime(ev.start)}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-slate2-400">
              {ev.duration_hours != null && (
                <span>Duration: <span className="text-slate2-200">{ev.duration_hours.toFixed(1)} h</span></span>
              )}
              {ev.end && (
                <span>Until: <span className="text-slate2-200">{fmtDateTime(ev.end)}</span></span>
              )}
              <span className="font-mono">{ev.position.lat.toFixed(3)}, {ev.position.lon.toFixed(3)}</span>
            </div>
            {ev.metadata && Object.keys(ev.metadata).length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {Object.entries(ev.metadata).map(([k, v]) => (
                  <span key={k} className="rounded bg-ink-800 px-1 py-0.5 text-[10px] text-slate2-300">
                    {k}: {String(v)}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Risk tab ─────────────────────────────────────────────────────────

function RiskTab({ assessment, loading, error }: { assessment?: RiskAssessment; loading: boolean; error: unknown }) {
  if (loading) return <Placeholder text="Loading risk assessment…" />;
  if (error) return <ErrBox error={error} />;
  if (!assessment) return <Placeholder text="No risk assessment available" dashed />;

  const cls = assessment.classification;
  const score = assessment.risk_score;

  return (
    <div className="space-y-3">
      {/* Score */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-slate2-400">Risk Score</span>
          <span className={`font-mono font-bold ${RISK_TEXT[cls]}`}>{(score * 100).toFixed(0)}%</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-ink-800">
          <div className={`h-full rounded-full ${RISK_BAR[cls]} transition-all`} style={{ width: `${score * 100}%` }} />
        </div>
        <div className="flex items-center gap-2">
          <RiskBadge risk={cls} />
          <span className="text-[10px] text-slate2-400">Region: {assessment.region_id}</span>
        </div>
      </div>

      {/* Triggered rules */}
      {assessment.triggered_rules.length > 0 && (
        <div className="space-y-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate2-400">
            Triggered Rules ({assessment.triggered_rules.length})
          </div>
          <div className="space-y-1">
            {assessment.triggered_rules.map((rule, i) => (
              <div key={i} className="flex gap-1.5 text-[11px]">
                <span className="mt-0.5 flex-shrink-0 text-accent-iuu">▪</span>
                <span className="text-slate2-200">{rule}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reasoning */}
      {assessment.reasoning && (
        <div className="space-y-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate2-400">Reasoning</div>
          <p className="rounded border border-ink-800 bg-ink-900 p-2 text-[11px] leading-snug text-slate2-200">
            {assessment.reasoning}
          </p>
        </div>
      )}

      {/* Evidence */}
      {assessment.evidence.length > 0 && (
        <div className="space-y-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate2-400">
            Evidence ({assessment.evidence.length} event{assessment.evidence.length !== 1 ? "s" : ""})
          </div>
          <div className="space-y-1">
            {assessment.evidence.map((ev) => {
              const meta = EVENT_META[ev.type] ?? { label: ev.type, color: "text-slate2-400", dot: "bg-slate2-400" };
              return (
                <div key={ev.event_id} className="flex items-center gap-2 text-[11px]">
                  <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${meta.dot}`} />
                  <span className={meta.color}>{meta.label}</span>
                  <span className="ml-auto font-mono text-[10px] text-slate2-400">{fmtDateTime(ev.start)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────

export function VesselDetailPanel({ ship, onClose, onRequestAgent: _onRequestAgent }: Props) {
  const { isError: vesselCardsFailed, error: vesselCardsError } = useVesselCards();
  const card = useVesselCard(ship?.mmsi);
  const localUrl = card?.image_path;
  const remoteUrl = card?.image_source_url;

  const [img, setImg] = useState<ImgState>(() => resolveImage(localUrl, remoteUrl));
  const lastKeyRef = useRef<string>("");
  const [tab, setTab] = useState<Tab>("overview");

  useEffect(() => {
    if (!ship) return;
    const key = `${ship.mmsi}|${localUrl ?? ""}|${remoteUrl ?? ""}`;
    if (key === lastKeyRef.current) return;
    lastKeyRef.current = key;
    setImg(resolveImage(localUrl, remoteUrl));
    setTab("overview");
  }, [ship, localUrl, remoteUrl]);

  const vesselQ = useQuery({
    queryKey: ["vessel", ship?.mmsi],
    queryFn: () => api.vessel(ship!.mmsi),
    enabled: !!ship?.mmsi,
    staleTime: 60_000,
    retry: 1,
  });

  const eventsQ = useQuery({
    queryKey: ["vessel-events", ship?.mmsi],
    queryFn: () => api.vesselEvents(ship!.mmsi),
    enabled: !!ship?.mmsi,
    staleTime: 60_000,
    retry: 1,
  });

  const riskQ = useQuery({
    queryKey: ["vessel-risk", ship?.mmsi],
    queryFn: () => api.vesselRisk(ship!.mmsi),
    enabled: !!ship?.mmsi,
    staleTime: 60_000,
    retry: 1,
  });

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
  const flag = card?.flag ?? ship.flag ?? vesselQ.data?.flag ?? undefined;
  const vesselType = card?.vessel_type ?? ship.vesselType ?? vesselQ.data?.gear_type;
  const risk = (card?.risk ?? ship.risk) as Risk | undefined;
  const duration = card?.duration_hours ?? ship.durationHours;
  const events = eventsQ.data ?? [];

  const handleImgError = () => {
    setImg((prev) => {
      if (prev.stage === "local" && remoteUrl) return { src: remoteUrl, stage: "remote" };
      return { src: null, stage: "missing" };
    });
  };

  const TABS: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "events",   label: events.length ? `Events (${events.length})` : "Events" },
    { id: "risk",     label: "Risk" },
  ];

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
            Vessel cards unavailable: {(vesselCardsError as Error).message}
          </p>
        )}

        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="font-display text-sm font-semibold leading-tight text-slate2-100">{name}</div>
            <div className="font-mono text-[11px] text-slate2-400">MMSI {ship.mmsi}</div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <RiskBadge risk={risk} />
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1 text-slate2-400 transition hover:bg-ink-800 hover:text-slate2-200"
              aria-label="Close vessel detail"
            >
              <X size={12} />
            </button>
          </div>
        </div>

        {/* Image */}
        <div className="overflow-hidden rounded border border-ink-800 bg-ink-900">
          {img.src ? (
            <img
              key={img.src}
              src={img.src}
              alt={`${name} (MMSI ${ship.mmsi})`}
              onError={handleImgError}
              loading="lazy"
              className="block h-36 w-full object-cover"
            />
          ) : (
            <div className="flex h-24 w-full flex-col items-center justify-center gap-1 text-slate2-500">
              <ImageOff size={18} />
              <span className="text-[11px]">No image available</span>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-0.5 rounded-lg bg-ink-900 p-0.5">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`flex-1 rounded-md px-2 py-1 text-[10px] font-semibold uppercase tracking-wide transition ${
                tab === id ? "bg-ink-800 text-slate2-100" : "text-slate2-400 hover:text-slate2-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="max-h-72 overflow-y-auto">
          {tab === "overview" && (
            <OverviewTab
              ship={ship}
              vessel={vesselQ.data}
              loading={vesselQ.isLoading}
              flag={flag}
              vesselType={vesselType}
              duration={duration}
              summary={card?.summary}
            />
          )}
          {tab === "events" && (
            <EventsTab events={events} loading={eventsQ.isLoading} error={eventsQ.error} />
          )}
          {tab === "risk" && (
            <RiskTab assessment={riskQ.data} loading={riskQ.isLoading} error={riskQ.error} />
          )}
        </div>

        {/* Notify port */}
        <div className="border-t border-ink-800 pt-2">
          <button
            onClick={() => notify.mutate()}
            disabled={notify.isPending}
            className="flex w-full items-center justify-center gap-1.5 rounded bg-accent-safe/10 px-2 py-1.5 text-xs font-medium text-accent-safe ring-1 ring-accent-safe/40 transition hover:bg-accent-safe/20 disabled:opacity-50"
          >
            <Phone size={12} />
            {notify.isPending ? "Notifying..." : "Notify Port"}
          </button>
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

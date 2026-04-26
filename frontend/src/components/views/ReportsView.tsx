import { api } from "@/lib/api";
import { supabase, EVIDENCE_BUCKET } from "@/lib/supabase";
import type { DocumentArtifact, Vessel } from "@/types/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Eye, FileText, Loader2, MapPin, Phone, PhoneCall, PlayCircle } from "lucide-react";
import { useEffect, useState } from "react";
import CountUp from "react-countup";
import { LiquidGlass } from "../LiquidGlass";

const REVEAL_DELAY_MS = 250;
const SHIMMER_MS = 600;

const DEMO_CASE_ID = "demo";

const DOC_LABELS: Record<DocumentArtifact["doc_type"], string> = {
    notice_of_violation: "Notice of Violation",
    cease_and_desist_order: "Cease & Desist",
    port_inspection_order: "Port Inspection Order",
    evidence_package: "Evidence Package",
    combined_legal_package: "Combined Legal Package",
};

type PortPrediction = { name: string; un_locode: string; lat: number; lon: number; weight: number };

interface Props {
    documents: DocumentArtifact[];
    onPreview: (doc: DocumentArtifact) => void;
    onSetDocuments: (docs: DocumentArtifact[]) => void;
    onPortCallReady: (call: { startLat: number; startLng: number; endLat: number; endLng: number }) => void;
    selectedVessel?: Vessel | null;
}

/**
 * Reports view — surfaces the agent-driven enforcement workflow:
 *  1. RUN DEMO FLOW → POST /case/:id/documents → list of DocumentArtifact
 *  2. NOTIFY PORT   → POST /case/:id/notify-port → port-call arc on globe
 *  3. Document downloads with previews and PDF links
 */
export function ReportsView({
    documents,
    onPreview,
    onSetDocuments,
    onPortCallReady,
    selectedVessel,
}: Props) {
    const queryClient = useQueryClient();
    const [revealedCount, setRevealedCount] = useState(0);
    const [completed, setCompleted] = useState<Set<string>>(new Set());
    const [predictions, setPredictions] = useState<PortPrediction[]>([]);

    // Staggered reveal when documents arrive or reset
    useEffect(() => {
        if (documents.length === 0) {
            setRevealedCount(0);
            setCompleted(new Set());
            return;
        }
        const revealTimers = documents.map((_, i) =>
            setTimeout(() => setRevealedCount(i + 1), i * REVEAL_DELAY_MS),
        );
        const completeTimers = documents.map((doc, i) =>
            setTimeout(
                () => setCompleted((prev) => new Set(prev).add(doc.artifact_id)),
                i * REVEAL_DELAY_MS + SHIMMER_MS,
            ),
        );
        return () => {
            [...revealTimers, ...completeTimers].forEach(clearTimeout);
        };
    }, [documents]);

    const fineQ = useQuery({
        queryKey: ["fine", DEMO_CASE_ID],
        queryFn: () => api.caseFine(DEMO_CASE_ID),
    });

    const renderDocsM = useMutation({
        mutationFn: () => api.renderDocumentFamily(DEMO_CASE_ID),
        onSuccess: (docs) => {
            onSetDocuments(docs);
            queryClient.invalidateQueries({ queryKey: ["fine"] });
        },
    });

    const notifyPortM = useMutation({
        mutationFn: () => api.notifyPort(DEMO_CASE_ID),
        onSuccess: (data) => {
            const startLat = selectedVessel?.last_position?.lat ?? -0.7533;
            const startLng = selectedVessel?.last_position?.lon ?? -90.3689;
            onPortCallReady({
                startLat,
                startLng,
                endLat: data.port.lat,
                endLng: data.port.lon,
            });
            setPredictions(data.predictions ?? []);
        },
    });

    const totalFine = fineQ.data?.total_fine_usd ?? 0;

    return (
        <aside className="w-80 h-full flex flex-col gap-4 p-4 pointer-events-auto overflow-y-auto">
            {/* Hero — case summary + civil penalty */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-3">
                    <div className="text-[10px] font-mono tracking-[0.22em] text-slate-400 uppercase">
                        Case · {DEMO_CASE_ID.toUpperCase()}
                    </div>
                    <div className="text-base font-semibold text-slate-100">
                        Galápagos IUU Enforcement
                    </div>
                    <div className="flex items-baseline justify-between pt-2 border-t border-white/[0.06]">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                            Civil Penalty
                        </span>
                        <span className="text-2xl font-bold text-red-300 tabular-nums">
                            {totalFine > 0 ? (
                                <CountUp end={totalFine} duration={1.5} separator="," prefix="$" decimals={0} />
                            ) : "—"}
                        </span>
                    </div>
                </div>
            </LiquidGlass>

            {/* Actions */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-3">
                    <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Actions</h2>
                    <div className="space-y-2">
                        <ActionButton
                            onClick={() => renderDocsM.mutate()}
                            disabled={renderDocsM.isPending}
                            icon={renderDocsM.isPending ? Loader2 : PlayCircle}
                            iconClass={renderDocsM.isPending ? "animate-spin" : ""}
                            label={renderDocsM.isPending ? "Rendering…" : "Run Demo Flow"}
                            tone="danger"
                        />
                        <ActionButton
                            onClick={() => notifyPortM.mutate()}
                            disabled={notifyPortM.isPending}
                            icon={notifyPortM.isPending ? Loader2 : Phone}
                            iconClass={notifyPortM.isPending ? "animate-spin" : ""}
                            label={notifyPortM.isPending ? "Dialing…" : "Notify Port"}
                            tone="warning"
                        />
                    </div>
                    {renderDocsM.isError && (
                        <div className="text-[11px] text-red-400">Failed to render documents.</div>
                    )}
                    {notifyPortM.isError && (
                        <div className="text-[11px] text-red-400">Port notification failed.</div>
                    )}
                </div>
            </LiquidGlass>

            {/* Documents — staggered reveal */}
            <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                <div className="p-5 space-y-2">
                    <div className="flex items-center justify-between mb-3">
                        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Documents</h2>
                        <span className="text-[10px] font-mono text-slate-500">{documents.length}</span>
                    </div>

                    <div className="space-y-2">
                        <EvidenceBrowser />
                        {documents.length > 0 && (
                          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest pt-1 pb-0.5">
                            Generated
                          </div>
                        )}
                        <AnimatePresence>
                            {documents.slice(0, revealedCount).map((doc, i) => {
                                const done = completed.has(doc.artifact_id);
                                return (
                                    <motion.div
                                        key={doc.artifact_id}
                                        initial={{ opacity: 0, x: -12 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1], delay: i * 0.03 }}
                                    >
                                        <DocumentRow
                                            doc={doc}
                                            shimmer={!done}
                                            onPreview={() => onPreview(doc)}
                                        />
                                    </motion.div>
                                );
                            })}
                        </AnimatePresence>
                    </div>
                </div>
            </LiquidGlass>

            {/* Port destination predictions */}
            <AnimatePresence>
                {predictions.length > 0 && (
                    <motion.div
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 12 }}
                        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                    >
                        <LiquidGlass className="rounded-[30px]" chromaticAberration={2} depth={8}>
                            <div className="p-5 space-y-3">
                                <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">
                                    Port Destinations
                                </h2>
                                <ul className="space-y-2">
                                    {predictions.slice(0, 4).map((p) => (
                                        <li key={p.un_locode} className="flex items-center gap-3">
                                            <MapPin className="w-3.5 h-3.5 text-amber-300 flex-shrink-0" />
                                            <div className="flex-1 min-w-0">
                                                <div className="text-[12px] text-slate-100 font-medium truncate">{p.name}</div>
                                                <div className="text-[10px] font-mono text-slate-500">{p.un_locode}</div>
                                            </div>
                                            <div className="text-[11px] font-mono text-amber-300 flex-shrink-0">
                                                {Math.round(p.weight * 100)}%
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        </LiquidGlass>
                    </motion.div>
                )}
            </AnimatePresence>
        </aside>
    );
}

function ActionButton({
    onClick,
    disabled,
    icon: Icon,
    iconClass = "",
    label,
    tone,
}: {
    onClick: () => void;
    disabled?: boolean;
    icon: typeof PlayCircle;
    iconClass?: string;
    label: string;
    tone: "danger" | "warning";
}) {
    const toneCls =
        tone === "danger"
            ? "bg-red-500/10 border-red-500/40 text-red-200 hover:bg-red-500/20 hover:border-red-500/70"
            : "bg-amber-500/10 border-amber-500/40 text-amber-200 hover:bg-amber-500/20 hover:border-amber-500/70";
    return (
        <button
            onClick={onClick}
            disabled={disabled}
            className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border text-[12px] font-semibold tracking-wide transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${toneCls}`}
        >
            <Icon className={`w-4 h-4 ${iconClass}`} />
            <span className="font-mono uppercase tracking-[0.18em] text-[11px]">{label}</span>
        </button>
    );
}

function DocumentRow({
    doc,
    onPreview,
    shimmer = false,
}: {
    doc: DocumentArtifact;
    onPreview: () => void;
    shimmer?: boolean;
}) {
    return (
        <div className={`flex items-center gap-3 p-2.5 border rounded-xl transition-colors ${shimmer ? "bg-cyan-500/5 border-cyan-500/20 animate-pulse" : "bg-white/[0.03] border-white/[0.06] hover:border-cyan-400/40"}`}>
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${shimmer ? "bg-cyan-500/10 border border-cyan-500/20" : "bg-emerald-500/15 border border-emerald-500/30"}`}>
                <Check className={`w-4 h-4 transition-colors ${shimmer ? "text-cyan-400/50" : "text-emerald-400"}`} strokeWidth={3} />
            </div>
            <div className="flex-1 min-w-0">
                <div className="text-[12.5px] text-slate-100 font-medium truncate">{DOC_LABELS[doc.doc_type]}</div>
                <div className="text-[9.5px] font-mono text-slate-500 truncate">{doc.sha256.slice(0, 24)}…</div>
            </div>
            <div className="text-[10px] font-mono text-slate-500 flex-shrink-0">{doc.page_count}p</div>
            <div className="flex gap-1 flex-shrink-0">
                <button
                    onClick={onPreview}
                    className="p-1.5 rounded-md hover:bg-cyan-500/10 transition-colors"
                    title="Preview"
                >
                    <Eye className="w-3.5 h-3.5 text-cyan-300" />
                </button>
            </div>
        </div>
    );
}

// ── Evidence Browser ────────────────────────────────────────────────────────

interface EvidenceFile {
  title: string;   // folder name
  filePath: string; // full path for URL
  fileName: string;
}

async function fetchEvidenceFiles(): Promise<EvidenceFile[]> {
  if (!supabase) throw new Error("Supabase not configured");

  // List root folders
  const { data: folders, error: fErr } = await supabase.storage
    .from(EVIDENCE_BUCKET)
    .list("", { limit: 100, sortBy: { column: "name", order: "asc" } });
  if (fErr) throw new Error(fErr.message);

  const results: EvidenceFile[] = [];

  await Promise.all(
    (folders ?? [])
      .filter((f) => f.id === null || f.metadata === null) // folders only
      .map(async (folder) => {
        const { data: files, error: fileErr } = await supabase!.storage
          .from(EVIDENCE_BUCKET)
          .list(folder.name, { limit: 100, sortBy: { column: "name", order: "asc" } });
        if (fileErr || !files) return;
        for (const file of files) {
          if (file.id !== null) {
            results.push({
              title: folder.name,
              filePath: `${folder.name}/${file.name}`,
              fileName: file.name,
            });
          }
        }
      })
  );

  return results.sort((a, b) => a.title.localeCompare(b.title));
}

const BACKEND_URL = (import.meta.env.VITE_BACKEND_URL as string | undefined ?? "").replace(/\/$/, "");
const VOICE_PROXY = "/voiceapi";

function EvidenceBrowser() {
  const filesQ = useQuery({
    queryKey: ["evidence-flat"],
    queryFn: fetchEvidenceFiles,
  });

  const [callingFile, setCallingFile] = useState<string | null>(null);
  const [phoneNumber, setPhoneNumber] = useState("+1");
  const [callState, setCallState] = useState<Record<string, { sid: string } | { error: string } | "pending">>({});

  const getPublicUrl = (filePath: string) => {
    if (!supabase) return "#";
    const { data } = supabase.storage.from(EVIDENCE_BUCKET).getPublicUrl(filePath);
    return data.publicUrl;
  };

  const placeCall = async (file: EvidenceFile) => {
    const pdfUrl = getPublicUrl(file.filePath);
    setCallState((s) => ({ ...s, [file.filePath]: "pending" }));
    setCallingFile(null);
    try {
      const res = await fetch(`${VOICE_PROXY}/voice/call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pdf_url: pdfUrl,
          to_number: phoneNumber,
          public_base_url: BACKEND_URL,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const json = await res.json() as { call_sid: string; status: string };
      setCallState((s) => ({ ...s, [file.filePath]: { sid: json.call_sid } }));
    } catch (e) {
      setCallState((s) => ({ ...s, [file.filePath]: { error: String(e) } }));
    }
  };

  const files = filesQ.data ?? [];

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Evidence</span>
        {filesQ.isPending && <Loader2 className="w-3 h-3 animate-spin text-slate-500" />}
      </div>

      {filesQ.isError && (
        <div className="text-[11px] text-red-400">{(filesQ.error as Error).message}</div>
      )}
      {!filesQ.isPending && files.length === 0 && (
        <div className="text-[11px] text-slate-500">No evidence files found.</div>
      )}

      <div className="space-y-2">
        {files.map((file) => {
          const state = callState[file.filePath];
          const isDialing = state === "pending";
          const queued = state && state !== "pending" && "sid" in state;
          const failed = state && state !== "pending" && "error" in state;

          return (
            <div key={file.filePath} className="space-y-1.5">
              <div className="flex items-center gap-3 p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:border-cyan-400/30 transition-colors group">
                <div className="w-8 h-8 rounded-lg bg-red-500/15 border border-red-500/30 flex items-center justify-center flex-shrink-0">
                  <FileText className="w-4 h-4 text-red-300" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[12px] font-semibold text-slate-100 truncate">{file.title}</div>
                  <div className="text-[10px] font-mono text-slate-500 truncate">{file.fileName}</div>
                </div>
                <div className="flex gap-1 flex-shrink-0">
                  <a
                    href={getPublicUrl(file.filePath)}
                    target="_blank"
                    rel="noreferrer"
                    className="p-1.5 rounded-md hover:bg-cyan-500/10 transition-colors"
                    title="View PDF"
                  >
                    <Eye className="w-3.5 h-3.5 text-cyan-300" />
                  </a>
                  <button
                    onClick={() => setCallingFile(callingFile === file.filePath ? null : file.filePath)}
                    disabled={isDialing}
                    className={`p-1.5 rounded-md transition-colors ${
                      queued ? "text-green-400" : isDialing ? "text-slate-500" : "text-amber-300 hover:bg-amber-500/10"
                    }`}
                    title="Call vessel"
                  >
                    {isDialing
                      ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      : queued
                        ? <PhoneCall className="w-3.5 h-3.5" />
                        : <Phone className="w-3.5 h-3.5" />
                    }
                  </button>
                </div>
              </div>

              {/* Inline call form */}
              {callingFile === file.filePath && (
                <div className="flex gap-2 px-1">
                  <input
                    type="tel"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                    placeholder="+16198871884"
                    className="flex-1 rounded-lg border border-ink-800 bg-ink-900 px-3 py-1.5 font-mono text-[11px] text-slate-200 focus:border-amber-400/60 focus:outline-none"
                  />
                  <button
                    onClick={() => void placeCall(file)}
                    className="flex items-center gap-1.5 rounded-lg bg-amber-500/15 border border-amber-500/40 px-3 py-1.5 text-[11px] font-semibold text-amber-200 hover:bg-amber-500/25 transition-colors"
                  >
                    <Phone className="w-3 h-3" /> Call
                  </button>
                </div>
              )}

              {/* Call status */}
              {queued && (
                <div className="px-1 text-[10px] font-mono text-green-400">
                  ✓ Queued · {(state as { sid: string }).sid.slice(0, 18)}…
                </div>
              )}
              {failed && (
                <div className="px-1 text-[10px] text-red-400">{(state as { error: string }).error}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

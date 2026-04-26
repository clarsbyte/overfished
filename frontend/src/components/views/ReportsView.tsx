import { api } from "@/lib/api";
import type { DocumentArtifact, Vessel } from "@/types/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Download, Eye, FileText, Loader2, MapPin, Phone, PlayCircle } from "lucide-react";
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
            <LiquidGlass className="rounded-[30px] flex-1 min-h-0" chromaticAberration={2} depth={8}>
                <div className="p-5 flex flex-col h-full min-h-0">
                    <div className="flex items-center justify-between mb-3">
                        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-widest">Documents</h2>
                        <span className="text-[10px] font-mono text-slate-500">{documents.length}</span>
                    </div>

                    <div className="flex-1 overflow-y-auto -mx-2 px-2 space-y-2">
                        {documents.length === 0 && (
                            <div className="text-[11px] text-slate-500 py-2">
                                Run the demo flow to generate the enforcement document family.
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
                <a
                    href={doc.pdf_url}
                    download
                    className="p-1.5 rounded-md hover:bg-cyan-500/10 transition-colors"
                    title="Download PDF"
                >
                    <Download className="w-3.5 h-3.5 text-cyan-300" />
                </a>
            </div>
        </div>
    );
}

// Suppress unused warning for FileText (kept here in case re-styling brings it back).
void FileText;

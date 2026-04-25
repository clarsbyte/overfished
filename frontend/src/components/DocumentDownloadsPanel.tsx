import type { DocumentArtifact } from "@/types/schemas";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Download, Eye, FileText } from "lucide-react";
import { useEffect, useState } from "react";
import CountUp from "react-countup";

const DOC_LABELS: Record<DocumentArtifact["doc_type"], string> = {
  notice_of_violation: "Notice of Violation & Civil Penalty",
  cease_and_desist_order: "Cease and Desist Order",
  port_inspection_order: "Port State Inspection Order",
  evidence_package: "Evidence Package",
};

const REVEAL_DELAY_MS = 250;
const SHIMMER_MS = 600;

interface Props {
  documents: DocumentArtifact[];
  totalFineUsd: number;
  visible: boolean;
  onPreview: (doc: DocumentArtifact) => void;
}

export function DocumentDownloadsPanel({ documents, totalFineUsd, visible, onPreview }: Props) {
  const [revealedCount, setRevealedCount] = useState(0);
  const [completed, setCompleted] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!visible) {
      setRevealedCount(0);
      setCompleted(new Set());
      return;
    }
    const revealTimers = documents.map((_, i) =>
      setTimeout(() => setRevealedCount(i + 1), i * REVEAL_DELAY_MS),
    );
    const completeTimers = documents.map((doc, i) =>
      setTimeout(() => {
        setCompleted((prev) => new Set(prev).add(doc.artifact_id));
      }, i * REVEAL_DELAY_MS + SHIMMER_MS),
    );
    return () => {
      [...revealTimers, ...completeTimers].forEach(clearTimeout);
    };
  }, [visible, documents]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: 40, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 40, opacity: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="bg-ink-900 border border-cyan-500/20 rounded-lg p-5 shadow-[0_0_24px_rgba(0,212,255,0.08)] backdrop-blur"
        >
          <div className="flex items-start justify-between mb-5 gap-6">
            <div className="min-w-0">
              <div className="text-[10px] font-mono tracking-[0.2em] text-slate-500 uppercase mb-1">
                Case Finalized · Document Family
              </div>
              <div className="text-base font-medium text-slate-200">
                Enforcement package ready for download
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <div className="text-[10px] font-mono tracking-[0.2em] text-slate-500 uppercase mb-1">
                Total Civil Penalty
              </div>
              <div className="text-3xl font-semibold tabular text-red-400">
                $
                <CountUp
                  end={totalFineUsd}
                  duration={1.6}
                  separator=","
                  decimals={2}
                  delay={(documents.length * REVEAL_DELAY_MS + SHIMMER_MS) / 1000}
                />
              </div>
            </div>
          </div>

          <div className="space-y-2">
            {documents.slice(0, revealedCount).map((doc) => (
              <DocumentRow
                key={doc.artifact_id}
                doc={doc}
                isComplete={completed.has(doc.artifact_id)}
                onPreview={() => onPreview(doc)}
              />
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function DocumentRow({
  doc,
  isComplete,
  onPreview,
}: {
  doc: DocumentArtifact;
  isComplete: boolean;
  onPreview: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3 }}
      className="flex items-center gap-3 p-3 bg-ink-800 border border-slate-700/50 rounded hover:border-cyan-500/40 transition-colors"
    >
      <div className="flex-shrink-0">
        {isComplete ? (
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 320, damping: 18 }}
            className="w-8 h-8 rounded bg-emerald-500/20 flex items-center justify-center"
          >
            <Check className="w-4 h-4 text-emerald-400" strokeWidth={3} />
          </motion.div>
        ) : (
          <div className="w-8 h-8 rounded bg-slate-700/50 flex items-center justify-center">
            <FileText className="w-4 h-4 text-slate-500" />
          </div>
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="text-sm text-slate-200 font-medium truncate">{DOC_LABELS[doc.doc_type]}</div>
        <div className="text-[10px] font-mono text-slate-500 truncate mt-0.5">
          {isComplete ? <TypedHash hash={doc.sha256} /> : <ShimmerLine />}
        </div>
      </div>

      <div className="text-[10px] font-mono text-slate-500 tabular flex-shrink-0">
        {isComplete ? `${doc.page_count}p` : "—"}
      </div>

      <div className="flex gap-1 flex-shrink-0">
        <button
          onClick={onPreview}
          disabled={!isComplete}
          className="p-2 rounded hover:bg-cyan-500/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          title="Preview"
        >
          <Eye className="w-4 h-4 text-cyan-400" />
        </button>
        <a
          href={isComplete ? doc.pdf_url : undefined}
          download
          className={`p-2 rounded hover:bg-cyan-500/10 transition-colors inline-flex items-center justify-center ${
            !isComplete ? "opacity-30 pointer-events-none" : ""
          }`}
          title="Download PDF"
        >
          <Download className="w-4 h-4 text-cyan-400" />
        </a>
      </div>
    </motion.div>
  );
}

function ShimmerLine() {
  return (
    <div className="relative w-48 h-2 bg-slate-700/50 rounded overflow-hidden mt-1">
      <motion.div
        className="absolute inset-y-0 w-12 bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent"
        initial={{ x: "-100%" }}
        animate={{ x: "300%" }}
        transition={{ duration: 0.9, repeat: Infinity, ease: "linear" }}
      />
    </div>
  );
}

function TypedHash({ hash }: { hash: string }) {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    if (idx < hash.length) {
      const t = setTimeout(() => setIdx((i) => i + 2), 12);
      return () => clearTimeout(t);
    }
  }, [idx, hash.length]);
  return (
    <span>
      <span className="text-slate-600">SHA-256: </span>
      {hash.slice(0, idx)}
    </span>
  );
}

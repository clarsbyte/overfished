import type { DocumentArtifact } from "@/types/schemas";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

interface Props {
  doc: DocumentArtifact | null;
  onClose: () => void;
}

export function DocumentPreviewModal({ doc, onClose }: Props) {
  return (
    <Dialog.Root open={doc !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[1000] data-[state=open]:animate-in data-[state=open]:fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[90vw] h-[90vh] max-w-[1100px] bg-ink-900 border border-cyan-500/20 rounded-lg shadow-2xl z-[1001] overflow-hidden flex flex-col">
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-700">
            <div>
              <Dialog.Title className="text-sm font-medium text-slate-200">
                {doc?.doc_type.replace(/_/g, " ")}
              </Dialog.Title>
              <Dialog.Description className="text-[10px] font-mono text-slate-500 mt-0.5">
                {doc?.sha256 ?? ""}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button className="p-2 hover:bg-slate-800 rounded transition-colors">
                <X className="w-4 h-4 text-slate-400" />
              </button>
            </Dialog.Close>
          </div>
          {doc && (
            <iframe
              src={doc.html_url}
              title={doc.doc_type}
              className="flex-1 w-full bg-white"
            />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

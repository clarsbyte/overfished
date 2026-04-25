import { Eye, Info, type LucideIcon, MapPin, Send, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { Card } from "./Card";

interface Suggestion {
  id: string;
  label: string;
  icon: LucideIcon;
}

const SUGGESTIONS: Suggestion[] = [
  { id: "summary", label: "Summarize recent high risk activity", icon: Sparkles },
  { id: "dark", label: "Show vessels with AIS dark activity", icon: Eye },
  { id: "offenders", label: "Find repeated offenders in West Africa", icon: MapPin },
  { id: "explain", label: "Explain this alert", icon: Info },
];

interface Props {
  onClose?: () => void;
}

export function AICopilotPanel({ onClose }: Props) {
  const [input, setInput] = useState("");

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-gradient-to-br from-cyan-400 to-blue-500 flex items-center justify-center shadow-[0_0_10px_rgba(34,211,238,0.4)]">
            <Sparkles className="w-3 h-3 text-white" strokeWidth={2.5} />
          </div>
          <span className="text-[12px] font-semibold text-white font-display">AI Copilot</span>
          <span className="px-1.5 py-0.5 rounded text-[9px] font-mono tracking-[0.12em] uppercase bg-emerald-500/15 text-emerald-300 border border-emerald-400/20">
            Beta
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-slate-300 transition-colors"
          aria-label="Close copilot"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="text-[12px] text-slate-300 mb-3">How can I help you today?</div>

      <div className="space-y-1.5">
        {SUGGESTIONS.map((s) => {
          const Icon = s.icon;
          return (
            <button
              key={s.id}
              onClick={() => setInput(s.label)}
              className="group w-full flex items-center gap-2 px-2.5 py-2 rounded-md bg-white/[0.03] border border-white/[0.05] hover:border-cyan-400/30 hover:bg-cyan-400/[0.05] transition-colors text-left"
            >
              <Icon
                className="w-3.5 h-3.5 text-cyan-300/80 flex-shrink-0 group-hover:text-cyan-300"
                strokeWidth={1.75}
              />
              <span className="text-[11.5px] text-slate-300 truncate group-hover:text-slate-100">
                {s.label}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-3 relative">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything..."
          className="w-full pl-3 pr-9 py-2 text-[12px] bg-[#050913] border border-white/[0.07] rounded-md text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-400/40 focus:ring-1 focus:ring-cyan-400/20"
        />
        <button
          aria-label="Send"
          className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1.5 rounded text-cyan-300/70 hover:text-cyan-200 hover:bg-cyan-400/10 transition-colors"
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </div>
    </Card>
  );
}

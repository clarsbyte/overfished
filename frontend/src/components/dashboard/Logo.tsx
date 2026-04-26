/**
 * Overfished wordmark + sub-title. Small wave glyph in cyan.
 */
export function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="relative w-7 h-7 rounded-lg bg-gradient-to-br from-cyan-400/20 to-cyan-500/10 border border-cyan-400/30 flex items-center justify-center shadow-[0_0_18px_rgba(34,211,238,0.25)]">
        <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 text-cyan-300">
          <path
            d="M3 12c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
          <path
            d="M3 17c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            opacity="0.55"
          />
        </svg>
      </div>
      <div className="leading-tight">
        <div className="text-[15px] font-semibold tracking-tight text-white font-display">
          Overfished
        </div>
        <div className="text-[10px] tracking-[0.12em] text-slate-400/80">
          Illegal Fishing Intelligence
        </div>
      </div>
    </div>
  );
}

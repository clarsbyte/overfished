import { Bell, Search, User } from "lucide-react";
import { useEffect, useState } from "react";

const FIXED_DATE = new Date("2024-05-15T14:32:18Z");

function formatDate(d: Date) {
  return d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
}

function formatTime(d: Date) {
  const h = String(d.getUTCHours()).padStart(2, "0");
  const m = String(d.getUTCMinutes()).padStart(2, "0");
  const s = String(d.getUTCSeconds()).padStart(2, "0");
  return `${h}:${m}:${s} UTC`;
}

export function TopBar() {
  // Tick the clock once a second around the mock baseline so the UI feels live.
  const [time, setTime] = useState(FIXED_DATE);
  useEffect(() => {
    const id = setInterval(() => setTime((t) => new Date(t.getTime() + 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  const glassPill = "liquid-glass-pill";

  return (
    <div className="flex items-center gap-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
        <input
          placeholder="Search vessels, incidents, zones..."
          className={`w-[380px] h-[38px] pl-9 pr-4 text-[12.5px] rounded-full text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-cyan-400/45 focus:ring-1 focus:ring-cyan-400/25 ${glassPill}`}
        />
      </div>

      <div className={`flex items-center gap-3 px-4 h-[38px] rounded-full ${glassPill}`}>
        <div className="text-right leading-tight">
          <div className="text-[11px] text-slate-300 font-medium">{formatDate(time)}</div>
          <div className="text-[10px] font-mono tracking-wider text-slate-500">
            {formatTime(time)}
          </div>
        </div>
      </div>

      <button
        aria-label="Notifications"
        className={`relative w-[38px] h-[38px] rounded-full flex items-center justify-center hover:border-cyan-400/40 transition-colors ${glassPill}`}
      >
        <Bell className="w-4 h-4 text-slate-300" strokeWidth={1.75} />
        <span className="absolute -top-1 -right-1 min-w-[16px] h-[16px] px-1 rounded-full bg-red-500 text-[9px] font-bold text-white flex items-center justify-center shadow-[0_0_8px_rgba(239,68,68,0.6)]">
          3
        </span>
      </button>

      <button
        aria-label="Account"
        className="w-[38px] h-[38px] rounded-full flex items-center justify-center hover:border-cyan-300/70 transition-colors liquid-glass-pill border-cyan-300/35"
      >
        <User className="w-4 h-4 text-cyan-200" strokeWidth={1.75} />
      </button>
    </div>
  );
}

import {
  AlertOctagon,
  BarChart3,
  FileText,
  LayoutGrid,
  LayoutDashboard,
  Settings,
  Ship,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { Card } from "./Card";

interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
}

const ITEMS: NavItem[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "incidents", label: "Incidents", icon: AlertOctagon },
  { id: "vessels", label: "Vessels", icon: Ship },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
  { id: "reports", label: "Reports", icon: FileText },
  { id: "settings", label: "Settings", icon: Settings },
];

export function BottomNav() {
  const [active, setActive] = useState("overview");

  return (
    <Card className="px-2 py-1.5 flex items-center gap-1 bg-[linear-gradient(165deg,rgba(18,29,52,0.62)_0%,rgba(8,14,27,0.48)_100%)] border-white/[0.18]">
      {ITEMS.map((item) => {
        const Icon = item.icon;
        const isActive = item.id === active;
        return (
          <button
            key={item.id}
            onClick={() => setActive(item.id)}
            className={[
              "relative flex items-center gap-2 px-3.5 py-2 rounded-md text-[12px] font-medium transition-colors",
              isActive
                ? "text-cyan-200 bg-cyan-300/14 border border-cyan-300/24 shadow-[0_0_0_1px_rgba(255,255,255,0.04)_inset]"
                : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.06]",
            ].join(" ")}
          >
            <Icon className="w-3.5 h-3.5" strokeWidth={1.75} />
            {item.label}
            {isActive && (
              <span className="absolute left-3 right-3 -bottom-px h-px bg-gradient-to-r from-transparent via-cyan-400 to-transparent" />
            )}
          </button>
        );
      })}

      <div className="mx-1 w-px h-5 bg-white/[0.08]" />

      <button
        aria-label="App grid"
        className="w-8 h-8 flex items-center justify-center rounded-md text-slate-400 hover:text-cyan-200 hover:bg-cyan-400/10 transition-colors"
      >
        <LayoutGrid className="w-4 h-4" strokeWidth={1.75} />
      </button>
    </Card>
  );
}

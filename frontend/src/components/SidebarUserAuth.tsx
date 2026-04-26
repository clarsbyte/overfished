import { useAuth0 } from "@auth0/auth0-react";
import { LogOut, User } from "lucide-react";

import { useDevFakeAuth } from "@/components/DevFakeAuthContext";
import { isDevFakeAuthEnabled } from "@/lib/devFakeAuth";

function SidebarAuth0Account() {
  const { user, logout } = useAuth0();
  const label = user?.email ?? user?.name ?? user?.sub ?? "Signed in";

  return (
    <div className="pt-2 border-t border-white/10 space-y-2">
      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Account</div>
      <div className="flex items-start gap-2 min-w-0">
        <User className="w-4 h-4 text-cyan-400/80 flex-shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] text-slate2-200 truncate" title={label}>
            {label}
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
        className="w-full flex items-center justify-center gap-2 rounded-xl py-2.5 text-xs font-medium text-slate2-300 hover:bg-white/5 border border-white/10 transition"
      >
        <LogOut className="w-3.5 h-3.5" />
        Log out
      </button>
    </div>
  );
}

function SidebarDevFakeAccount() {
  const { user, logout } = useDevFakeAuth();
  const label = user?.email ?? "Signed in";

  return (
    <div className="pt-2 border-t border-white/10 space-y-2">
      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Account</div>
      <div className="flex items-start gap-2 min-w-0">
        <User className="w-4 h-4 text-cyan-400/80 flex-shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] text-slate2-200 truncate" title={label}>
            {label}
          </p>
          <p className="text-[9px] text-slate-500 mt-0.5">Dev fake auth</p>
        </div>
      </div>
      <button
        type="button"
        onClick={() => logout()}
        className="w-full flex items-center justify-center gap-2 rounded-xl py-2.5 text-xs font-medium text-slate2-300 hover:bg-white/5 border border-white/10 transition"
      >
        <LogOut className="w-3.5 h-3.5" />
        Log out
      </button>
    </div>
  );
}

export function SidebarUserAuth() {
  return isDevFakeAuthEnabled() ? <SidebarDevFakeAccount /> : <SidebarAuth0Account />;
}

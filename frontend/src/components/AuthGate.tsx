import { useAuth0 } from "@auth0/auth0-react";
import { Waves } from "lucide-react";

import { LiquidGlass } from "./LiquidGlass";

type Props = {
  children: React.ReactNode;
};

export function AuthGate({ children }: Props) {
  const { isLoading, isAuthenticated, error, loginWithRedirect, logout } = useAuth0();

  if (isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center space-canvas text-slate2-200">
        <p className="text-sm text-slate2-400">Signing in…</p>
      </div>
    );
  }
  if (error) {
    const code = "error" in error ? String((error as { error: string }).error) : "";
    const desc =
      "error_description" in error
        ? String((error as { error_description: string }).error_description)
        : error.message;
    return (
      <div className="flex h-screen w-screen items-center justify-center space-canvas p-6 text-slate2-200">
        <div className="max-w-lg space-y-3 text-left">
          <p className="text-xs font-bold uppercase tracking-widest text-red-400/80">Sign-in error</p>
          {code && <p className="font-mono text-sm text-red-300 break-words">{code}</p>}
          <p className="text-sm text-slate2-300 whitespace-pre-wrap break-words">{desc}</p>
          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              onClick={async () => {
                const url = new URL(window.location.href);
                for (const k of ["code", "state", "error", "error_description"]) {
                  url.searchParams.delete(k);
                }
                window.history.replaceState({}, "", url.toString());
                try {
                  await logout({ openUrl: false });
                } catch {
                  /* nothing */
                }
                window.location.href = url.pathname + (url.search ? url.search : "");
              }}
              className="rounded-lg bg-white/10 px-3 py-2 text-sm text-slate2-200 hover:bg-white/15"
            >
              Clear error and start over
            </button>
            <button
              type="button"
              onClick={() => loginWithRedirect({ appState: { returnTo: window.location.pathname } })}
              className="rounded-lg bg-cyan-600/80 px-3 py-2 text-sm text-white hover:bg-cyan-500/90"
            >
              Log in again
            </button>
          </div>
        </div>
      </div>
    );
  }
  if (!isAuthenticated) {
    return (
      <div className="flex h-screen w-screen items-center justify-center space-canvas p-6 text-slate2-200">
        <LiquidGlass className="rounded-[40px] w-full max-w-sm p-10" chromaticAberration={2} depth={10}>
          <div className="flex flex-col items-center gap-6 text-center">
            <div className="w-12 h-12 bg-cyan-600/20 rounded-xl flex items-center justify-center border border-cyan-500/30">
              <Waves className="w-7 h-7 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Overfished</h1>
              <p className="text-[10px] text-cyan-500/80 font-bold uppercase tracking-widest mt-1">
                Sign in to continue
              </p>
            </div>
            <button
              type="button"
              onClick={() => loginWithRedirect({ appState: { returnTo: window.location.pathname } })}
              className="w-full rounded-xl bg-cyan-600/80 hover:bg-cyan-500/90 text-white text-sm font-semibold py-3 px-4 transition"
            >
              Log in
            </button>
          </div>
        </LiquidGlass>
      </div>
    );
  }
  return <>{children}</>;
}

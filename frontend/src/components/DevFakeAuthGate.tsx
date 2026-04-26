import { Waves } from "lucide-react";

import { useDevFakeAuth } from "@/components/DevFakeAuthContext";
import { LiquidGlass } from "./LiquidGlass";

type Props = {
  children: React.ReactNode;
};

/**
 * Same look as AuthGate, but login is a local toggle (no OAuth round-trip).
 */
export function DevFakeAuthGate({ children }: Props) {
  const { isAuthenticated, login } = useDevFakeAuth();

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
              <p className="text-[9px] text-slate-500 mt-2 leading-relaxed">
                Dev mode: no Auth0. Use <span className="font-mono">AUTH0_BYPASS=1</span> on the BFF
                (port 8001).
              </p>
            </div>
            <button
              type="button"
              onClick={() => login()}
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

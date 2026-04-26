import { LiquidGlass } from "./LiquidGlass";

export function Auth0SetupMissing() {
  return (
    <div className="flex h-screen w-screen items-center justify-center space-canvas p-6 text-slate2-200">
      <LiquidGlass className="rounded-[40px] w-full max-w-lg p-8" chromaticAberration={2} depth={10}>
        <h1 className="text-lg font-bold text-white mb-2">Auth0 is not configured</h1>
        <p className="text-sm text-slate2-400 mb-4">
          Set the following in your environment (repo root or <code className="text-cyan-400/90">frontend/.env</code>
          ) and restart Vite:
        </p>
        <ul className="text-left text-sm font-mono text-slate2-300 space-y-1 list-disc pl-5">
          <li>VITE_AUTH0_DOMAIN</li>
          <li>VITE_AUTH0_CLIENT_ID</li>
          <li>VITE_AUTH0_AUDIENCE</li>
        </ul>
        <p className="text-xs text-slate2-400 mt-4">
          Or skip OAuth for local dev: set <code className="text-cyan-400/90">VITE_DEV_FAKE_AUTH=1</code> and{" "}
          <code className="text-cyan-400/90">AUTH0_BYPASS=1</code> on the API, then restart Vite.
        </p>
        <p className="text-xs text-slate2-500 mt-2">See <code className="text-cyan-400/90">frontend/.env.example</code>.</p>
      </LiquidGlass>
    </div>
  );
}

import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import glsl from "vite-plugin-glsl";

export default defineConfig(({ mode }) => {
  // envDir matches the production envDir below so we read the same .env files.
  const env = loadEnv(mode, path.resolve(__dirname, ".."), ["VITE_", "BACKEND_", "AGENT_"]);

  const backendTarget = env.BACKEND_URL?.trim() || "http://127.0.0.1:8000";
  const agentTarget = env.AGENT_BACKEND_URL?.trim() || backendTarget;

  // ngrok-free.app blocks browser-style requests unless this header is set.
  const ngrokHeaders = /ngrok/.test(backendTarget) || /ngrok/.test(agentTarget)
    ? { "ngrok-skip-browser-warning": "true" }
    : undefined;

  return {
    plugins: [react(), glsl()],
    envDir: path.resolve(__dirname, ".."),
    envPrefix: ["VITE_", "MAP_BOX_"],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
          secure: false,
          rewrite: (p) => p.replace(/^\/api/, ""),
          headers: ngrokHeaders,
        },
        "/static": {
          target: backendTarget,
          changeOrigin: true,
          secure: false,
          headers: ngrokHeaders,
        },
        "/agentapi": {
          target: agentTarget,
          changeOrigin: true,
          secure: false,
          rewrite: (p) => p.replace(/^\/agentapi/, ""),
          headers: ngrokHeaders,
        },
      },
    },
  };
});

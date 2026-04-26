import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import glsl from "vite-plugin-glsl";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, ".."), "VITE_");
  const backendUrl = env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

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
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ""),
        },
        "/static": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
        },
        "/agentapi": {
          target: backendUrl,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/agentapi/, ""),
        },
        "/voiceapi": {
          target: backendUrl,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/voiceapi/, ""),
        },
      },
    },
  };
});

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Do NOT include "three" here — transpiling it creates a second Three.js
  // instance that conflicts with react-globe.gl's copy and breaks WebGL layers.
  transpilePackages: ["three-globe", "react-globe.gl"],

  turbopack: {
    resolveAlias: {
      // Force every import of "three" through the same installed copy so
      // react-globe.gl and any direct usage share one WebGL context.
      three: "./node_modules/three/build/three.module.js",
    },
  },
};

export default nextConfig;

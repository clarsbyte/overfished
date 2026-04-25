"use client";

import dynamic from "next/dynamic";

// globe.gl uses WebGL/canvas — skip SSR entirely
const GlobeClient = dynamic(() => import("./GlobeClient"), { ssr: false });

export default function GlobeWrapper() {
  return <GlobeClient />;
}

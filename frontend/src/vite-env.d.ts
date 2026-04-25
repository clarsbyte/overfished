/// <reference types="vite/client" />
/// <reference types="geojson" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_AGENT_API_URL?: string;
  readonly MAP_BOX_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

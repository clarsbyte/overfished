import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { GlobeControlsProvider } from "./components/GlobeControlsContext";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      retry: 1,
    },
  },
});

const debug =
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).has("debug");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>

      <GlobeControlsProvider>
        <App />
      </GlobeControlsProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);

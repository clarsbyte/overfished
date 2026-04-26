import { Auth0Provider } from "@auth0/auth0-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { AuthGate } from "./components/AuthGate";
import { Auth0SetupMissing } from "./components/Auth0SetupMissing";
import { Auth0TokenBridge } from "./components/Auth0TokenBridge";
import { DevFakeAuthGate } from "./components/DevFakeAuthGate";
import { DevFakeAuthProvider } from "./components/DevFakeAuthContext";
import { DevFakeTokenBridge } from "./components/DevFakeTokenBridge";
import { GlobeControlsProvider } from "./components/GlobeControlsContext";
import { isAuth0Configured } from "./lib/auth0Env";
import { isDevFakeAuthEnabled } from "./lib/devFakeAuth";
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

const withAuth = isDevFakeAuthEnabled() ? (
  <DevFakeAuthProvider>
    <DevFakeTokenBridge />
    <DevFakeAuthGate>
      <GlobeControlsProvider>
        <App />
      </GlobeControlsProvider>
    </DevFakeAuthGate>
  </DevFakeAuthProvider>
) : isAuth0Configured() ? (
  <Auth0Provider
    domain={String(import.meta.env.VITE_AUTH0_DOMAIN ?? "").trim()}
    clientId={String(import.meta.env.VITE_AUTH0_CLIENT_ID ?? "").trim()}
    authorizationParams={{
      audience: String(import.meta.env.VITE_AUTH0_AUDIENCE ?? "").trim(),
      redirect_uri: window.location.origin,
      scope: "openid profile email",
    }}
    cacheLocation="localstorage"
  >
    <Auth0TokenBridge />
    <AuthGate>
      <GlobeControlsProvider>
        <App />
      </GlobeControlsProvider>
    </AuthGate>
  </Auth0Provider>
) : (
  <Auth0SetupMissing />
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>{withAuth}</QueryClientProvider>
  </React.StrictMode>,
);

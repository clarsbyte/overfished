import { useAuth0 } from "@auth0/auth0-react";
import { useLayoutEffect, useRef } from "react";

import { setAccessTokenGetter } from "@/lib/authToken";

const AUTH0_AUDIENCE = String(import.meta.env.VITE_AUTH0_AUDIENCE ?? "").trim();

function isInteractiveAuthError(e: unknown): boolean {
  if (e == null || typeof e !== "object") return false;
  const o = e as { error?: string; error_subcode?: string; message?: string };
  if (o.error === "login_required" || o.error === "consent_required") return true;
  if (o.error === "missing_refresh_token") return true;
  return o.message === "Login required" || o.message === "Consent required";
}

/**
 * Registers the async access-token getter for shared fetch() helpers. Runs
 * useLayoutEffect so the getter is ready before the tree paints children.
 */
export function Auth0TokenBridge() {
  const { isAuthenticated, getAccessTokenSilently, loginWithRedirect, isLoading } = useAuth0();
  const getTokenRef = useRef(getAccessTokenSilently);
  getTokenRef.current = getAccessTokenSilently;

  useLayoutEffect(() => {
    if (isLoading) {
      return () => {
        setAccessTokenGetter(null);
      };
    }
    if (!isAuthenticated) {
      setAccessTokenGetter(async () => undefined);
      return () => {
        setAccessTokenGetter(null);
      };
    }
    setAccessTokenGetter(async () => {
      try {
        return await getTokenRef.current(
          AUTH0_AUDIENCE
            ? {
                authorizationParams: {
                  audience: AUTH0_AUDIENCE,
                  redirect_uri: window.location.origin,
                },
              }
            : undefined,
        );
      } catch (e: unknown) {
        if (isInteractiveAuthError(e)) {
          await loginWithRedirect({ appState: { returnTo: window.location.pathname } });
          return undefined;
        }
        throw e;
      }
    });
    return () => {
      setAccessTokenGetter(null);
    };
  }, [isAuthenticated, loginWithRedirect, isLoading]);

  return null;
}

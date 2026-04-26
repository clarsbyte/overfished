import { useLayoutEffect } from "react";

import { useDevFakeAuth } from "@/components/DevFakeAuthContext";
import { setAccessTokenGetter } from "@/lib/authToken";

/**
 * Registers a no-op token getter when “signed in” so fetch helpers do not send a
 * bogus Bearer. The BFF must run with AUTH0_BYPASS=1 for protected routes.
 */
export function DevFakeTokenBridge() {
  const { isAuthenticated } = useDevFakeAuth();

  useLayoutEffect(() => {
    if (!isAuthenticated) {
      setAccessTokenGetter(null);
      return () => {
        setAccessTokenGetter(null);
      };
    }
    setAccessTokenGetter(async () => undefined);
    return () => {
      setAccessTokenGetter(null);
    };
  }, [isAuthenticated]);

  return null;
}

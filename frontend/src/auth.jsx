import { createContext, useContext, useEffect, useState } from "react";
import {
  api,
  clearToken,
  getCachedUser,
  getToken,
  setCachedUser,
  setToken,
} from "./api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => (
    window.location.hash.startsWith("#token=") ? null : getCachedUser()
  ));
  const [loading, setLoading] = useState(Boolean(
    (getToken() || window.location.hash.startsWith("#token=")) && !user,
  ));
  const [dataVersion, setDataVersion] = useState(0);

  useEffect(() => {
    setCachedUser(user);
  }, [user]);

  // Capture #token=... handed back by the Google callback redirect.
  useEffect(() => {
    const hash = window.location.hash;
    if (hash.startsWith("#token=")) {
      setToken(hash.slice("#token=".length));
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  async function refresh() {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const path = window.location.pathname;
      const routeRequest = (
        path === "/" || path === "/feed"
          ? api.feed(50, { force: true })
          : path === "/reveals" || path === "/history"
            ? api.history(200, { force: true })
            : path === "/categories"
              ? api.categories({ force: true })
              : null
      );
      const routeWarmup = routeRequest?.catch(() => {});
      const data = await api.bootstrap({ force: true });
      if (routeWarmup) await routeWarmup;
      setUser(data.user);
      setDataVersion((current) => current + 1);
    } catch (error) {
      // A transient cold-start or network failure should not blank a previously
      // loaded app. Authentication failures clear the token inside the client.
      if (!getToken() || !getCachedUser()) setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  // Login responses already contain the user, so let the app open immediately
  // and warm the summary screens in the background.
  useEffect(() => {
    if (user?.id && !api.peek("profileStats")) {
      void api.bootstrap().then(() => {
        setDataVersion((current) => current + 1);
      }).catch(() => {});
    }
  }, [user?.id]);

  function logout() {
    clearToken();
    setUser(null);
  }

  return (
    <AuthCtx.Provider value={{ user, setUser, loading, dataVersion, refresh, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);

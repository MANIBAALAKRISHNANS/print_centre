import { createContext, useState, useEffect, useCallback, useMemo } from "react";
import { useFetch, useAuth } from "./AuthContext";
import { API_BASE_URL } from "../config";
import { useWebSocket } from "../hooks/useWebSocket";
import { getCache, setCache, isFresh } from "../utils/cache";

export const AppData = createContext();

const CACHE_TTL = 30000; // 30 seconds — data this fresh is shown instantly

function AppDataProvider({ children }) {
  const [printers,  setPrinters]  = useState(() => getCache("printers")  ?? []);
  const [locations, setLocations] = useState(() => getCache("locations") ?? []);
  const [categories,setCategories]= useState(() => getCache("categories")  ?? []);
  const [agents,    setAgents]    = useState(() => getCache("agents")    ?? []);

  const [loading, setLoading] = useState({
    printers:   !getCache("printers"),
    locations:  !getCache("locations"),
    categories: !getCache("categories"),
    agents:     !getCache("agents"),
  });

  const [errors, setErrors] = useState({
    printers: null, locations: null, categories: null, agents: null
  });

  const authFetch = useFetch();
  const { token } = useAuth();

  // Stale-while-revalidate: if cache is fresh → show instantly (silent=true auto),
  // if stale/empty → show loading spinner. Either way, fetch fresh data.
  const fetchResource = useCallback(async (url, setter, key) => {
    const cached = getCache(key);
    const fresh  = isFresh(key, CACHE_TTL);

    // If we have ANY cached data, show it immediately — no spinner
    if (cached !== null) {
      setter(cached);
    }

    // If fresh enough, skip the network call entirely
    if (fresh) return;

    // Show loading only if we have nothing to show yet
    if (cached === null) {
      setLoading(prev => ({ ...prev, [key]: true }));
    }
    setErrors(prev => ({ ...prev, [key]: null }));

    try {
      const res = await authFetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setCache(key, data);
      setter(data);
    } catch (err) {
      console.log(`${key} load error`, err);
      setErrors(prev => ({ ...prev, [key]: err.message }));
    } finally {
      setLoading(prev => ({ ...prev, [key]: false }));
    }
  }, [authFetch]);

  const loadPrinters   = useCallback(() => fetchResource(`${API_BASE_URL}/printers`,  setPrinters,   "printers"),   [fetchResource]);
  const loadLocations  = useCallback(() => fetchResource(`${API_BASE_URL}/locations`,  setLocations,  "locations"),  [fetchResource]);
  const loadCategories = useCallback(() => fetchResource(`${API_BASE_URL}/categories`, setCategories, "categories"), [fetchResource]);
  const loadAgents     = useCallback(() => fetchResource(`${API_BASE_URL}/agents`,     setAgents,     "agents"),     [fetchResource]);

  // Load all four resources in parallel
  const loadAll = useCallback(() => {
    Promise.all([loadPrinters(), loadLocations(), loadCategories(), loadAgents()]);
  }, [loadPrinters, loadLocations, loadCategories, loadAgents]);

  useEffect(() => {
    const hasToken = document.cookie.includes("print_hub_session");
    if (hasToken) loadAll();
  }, [loadAll]);

  // Real-time WebSocket: silently refresh affected resource
  const handleWsMessage = useCallback((msg) => {
    if (msg.type === "printer_update") loadPrinters();
    if (msg.type === "agent_update")   loadAgents();
  }, [loadPrinters, loadAgents]);

  useWebSocket(handleWsMessage, !!token);

  const value = useMemo(() => ({
    printers,  setPrinters,
    locations, setLocations,
    categories,setCategories,
    agents,    setAgents,
    loading,   errors,
    loadPrinters, loadLocations, loadCategories, loadAgents, loadAll,
  }), [printers, locations, categories, agents, loading, errors,
      loadPrinters, loadLocations, loadCategories, loadAgents, loadAll]);

  return (
    <AppData.Provider value={value}>
      {children}
    </AppData.Provider>
  );
}

export default AppDataProvider;

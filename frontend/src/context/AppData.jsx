import React, { createContext, useState, useEffect, useCallback, useMemo } from "react";
import { useFetch } from "./AuthContext";
import { API_BASE_URL } from "../config";

export const AppData = createContext();

function AppDataProvider({ children }) {
  const [printers, setPrinters] = useState([]);
  const [locations, setLocations] = useState([]); 
  const [categories, setCategories] = useState([]);
  
  const [loading, setLoading] = useState({
    printers: true,
    locations: true,
    categories: true
  });

  const [errors, setErrors] = useState({
    printers: null,
    locations: null,
    categories: null
  });

  const authFetch = useFetch();

  const fetchResource = useCallback(async (url, setter, key, silent = false) => {
    if (!silent) {
      setLoading(prev => ({ ...prev, [key]: true }));
    }
    setErrors(prev => ({ ...prev, [key]: null }));
    
    try {
      const res = await authFetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setter(data);
    } catch (err) {
      console.log(`${key} load error`, err);
      setErrors(prev => ({ ...prev, [key]: err.message }));
    } finally {
      if (!silent) {
        setLoading(prev => ({ ...prev, [key]: false }));
      }
    }
  }, [authFetch]);

  const loadPrinters = useCallback((silent = false) => fetchResource(`${API_BASE_URL}/printers`, setPrinters, "printers", silent), [fetchResource]);
  const loadLocations = useCallback((silent = false) => fetchResource(`${API_BASE_URL}/locations`, setLocations, "locations", silent), [fetchResource]);
  const loadCategories = useCallback((silent = false) => fetchResource(`${API_BASE_URL}/categories`, setCategories, "categories", silent), [fetchResource]);

  const loadAll = useCallback((silent = false) => {
    loadPrinters(silent);
    loadLocations(silent);
    loadCategories(silent);
  }, [loadPrinters, loadLocations, loadCategories]);

  useEffect(() => {
    // ONLY fetch if we have a token. 
    // This prevents unauthorized calls (401) on the login screen.
    const hasToken = document.cookie.includes("print_hub_session");
    if (hasToken) {
      loadPrinters();
      loadLocations();
      loadCategories();
    }
  }, [loadPrinters, loadLocations, loadCategories]);

  const value = React.useMemo(() => ({
    printers, setPrinters,
    locations, setLocations,
    categories, setCategories,
    loading, errors,
    loadPrinters, loadLocations, loadCategories,
    loadAll
  }), [printers, locations, categories, loading, errors, loadPrinters, loadLocations, loadCategories, loadAll]);

  return (
    <AppData.Provider value={value}>
      {children}
    </AppData.Provider>
  );
}

export default AppDataProvider;

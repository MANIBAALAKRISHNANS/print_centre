/* eslint-disable react-refresh/only-export-components */
import { createContext, useState, useEffect, useCallback } from "react";
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

  const fetchResource = useCallback(async (url, setter, key) => {
    setLoading(prev => ({ ...prev, [key]: true }));
    setErrors(prev => ({ ...prev, [key]: null }));
    
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setter(data);
    } catch (err) {
      console.log(`${key} load error`, err);
      setErrors(prev => ({ ...prev, [key]: err.message }));
    } finally {
      setLoading(prev => ({ ...prev, [key]: false }));
    }
  }, []);

  const loadPrinters = () => fetchResource(`${API_BASE_URL}/printers`, setPrinters, "printers");
  const loadLocations = () => fetchResource(`${API_BASE_URL}/locations`, setLocations, "locations");
  const loadCategories = () => fetchResource(`${API_BASE_URL}/categories`, setCategories, "categories");

  useEffect(() => {
    // Independent, non-blocking loads
    loadPrinters();
    loadLocations();
    loadCategories();
  }, []); // eslint-disable-line

  return (
    <AppData.Provider
      value={{
        printers, setPrinters,
        locations, setLocations,
        categories, setCategories,
        loading, errors,
        loadPrinters, loadLocations, loadCategories
      }}
    >
      {children}
    </AppData.Provider>
  );
}

export default AppDataProvider;

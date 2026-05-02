/* eslint-disable react-refresh/only-export-components */
import { createContext, useState, useEffect } from "react";

export const AppData = createContext();

function AppDataProvider({ children }) {
  const [printers, setPrinters] = useState([]);
  const [locations, setLocations] = useState([]);
  const [categories, setCategories] = useState([]);

  const loadAll = async () => {
    const loadResource = async (url, setter, label) => {
      try {
        const res = await fetch(url);
        const data = await res.json();
        setter(data);
      } catch (err) {
        console.log(`${label} API error`, err);
      }
    };

    await Promise.all([
      loadResource("http://127.0.0.1:8000/printers", setPrinters, "Printers"),
      loadResource("http://127.0.0.1:8000/locations", setLocations, "Locations"),
      loadResource("http://127.0.0.1:8000/categories", setCategories, "Categories"),
    ]);
  };

  useEffect(() => {
    loadAll();
  }, []);

  return (
    <AppData.Provider
      value={{
        printers,
        setPrinters,
        locations,
        setLocations,
        categories,
        setCategories,
        loadAll
      }}
    >
      {children}
    </AppData.Provider>
  );
}

export default AppDataProvider;

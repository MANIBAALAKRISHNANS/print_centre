import { createContext, useState, useEffect } from "react";

export const AppData = createContext();

function AppDataProvider({ children }) {
  const [printers, setPrinters] = useState([]);
  const [locations, setLocations] = useState([]);
  const [categories, setCategories] = useState([]);

  const loadAll = async () => {
    try {
      const p = await fetch("http://127.0.0.1:8000/printers").then(r => r.json());
      const l = await fetch("http://127.0.0.1:8000/locations").then(r => r.json());
      const c = await fetch("http://127.0.0.1:8000/categories").then(r => r.json());

      setPrinters(p);
      setLocations(l);
      setCategories(c);
    } catch (err) {
      console.log("Error loading data", err);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  return (
    <AppData.Provider value={{
      printers,
      locations,
      categories,
      loadAll
    }}>
      {children}
    </AppData.Provider>
  );
}

export default AppDataProvider;
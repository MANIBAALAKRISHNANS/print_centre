import { useContext } from "react";
import { AppData } from "../context/AppData";
import { API_BASE_URL } from "../config";

function Locations() {
  const { locations, loading, errors, loadLocations } = useContext(AppData);

  const syncLocations = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/sync-locations`);
      const result = await res.json();
      if (result.error) {
        alert(result.error);
        return;
      }
      await loadLocations();
      alert(`Synced ${result.count} locations from hospital system`);
    } catch (err) {
      alert("Sync failed: " + err.message);
    }
  };

  return (
    <div className="page">
      <h1>Hospital Locations</h1>
      <p className="sub">Locations are synchronized automatically from the hospital HIS system.</p>

      <button className="btn" onClick={syncLocations}>🔄 Sync from Hospital</button>
      <br /><br />

      {loading.locations ? (
        <div className="emptyState pulse">Loading hospital locations...</div>
      ) : errors.locations ? (
        <div className="emptyState error">{errors.locations}. <button onClick={loadLocations}>Retry</button></div>
      ) : locations.length === 0 ? (
        <div className="emptyState">No locations synced yet. Click "Sync" above.</div>
      ) : (
        locations.map((item, index) => (
          <div className="listCard" key={index} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <strong style={{ display: "block" }}>{item.name}</strong>
              <small style={{ color: "#aaa", fontSize: "0.75rem" }}>ID: {item.external_id}</small>
            </div>
            <span style={{ fontSize: "0.8rem", color: "#888" }}>Synced</span>
          </div>
        ))
      )}
    </div>
  );
}

export default Locations;

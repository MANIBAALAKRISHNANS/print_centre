import { useContext } from "react";
import { AppData } from "../context/AppData";
import { useFetch } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { SkeletonLine } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import { API_BASE_URL } from "../config";

function Locations() {
  const { locations, loading, errors, loadLocations } = useContext(AppData);
  const authFetch = useFetch();
  const toast = useToast();

  const syncLocations = async () => {
    try {
      const res = await authFetch(`${API_BASE_URL}/sync-locations`);
      const result = await res.json();
      if (result.error) {
        toast.error(result.error);
        return;
      }
      await loadLocations();
      toast.success(`Synced ${result.count} locations successfully`);
    } catch (err) {
      toast.error("Sync failed: " + err.message);
    }
  };

  return (
    <div className="page">
      <h1>Hospital Locations</h1>
      <p className="sub">Locations are synchronized automatically from the hospital HIS system.</p>

      <button className="btn" onClick={syncLocations}>🔄 Sync from Hospital</button>
      <br /><br />

      {loading.locations ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <SkeletonLine height="60px" /><SkeletonLine height="60px" /><SkeletonLine height="60px" />
        </div>
      ) : errors.locations ? (
        <div className="emptyState error">{errors.locations}. <button onClick={loadLocations}>Retry</button></div>
      ) : locations.length === 0 ? (
        <EmptyState 
            icon="🏥"
            title="No locations synced"
            subtitle="Hospital locations are required to map printers to wards."
            action={syncLocations}
            actionLabel="Sync from Hospital"
        />
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

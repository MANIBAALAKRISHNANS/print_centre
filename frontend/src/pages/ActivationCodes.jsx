import { useState, useEffect } from "react";
import { useFetch } from "../context/AuthContext";
import { API_BASE_URL } from "../config";

function ActivationCodes() {
  const [codes, setCodes] = useState([]);
  const [locations, setLocations] = useState([]);
  const [selectedLocation, setSelectedLocation] = useState("");
  const [loading, setLoading] = useState(false);
  const [newCode, setNewCode] = useState(null);
  const [revokingId, setRevokingId] = useState(null);
  const authFetch = useFetch();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [codesRes, locsRes] = await Promise.all([
        authFetch(`${API_BASE_URL}/admin/activation-codes`),
        authFetch(`${API_BASE_URL}/locations`)
      ]);
      const codesData = await codesRes.json();
      const locsData = await locsRes.json();
      setCodes(codesData);
      setLocations(locsData);
      if (locsData.length > 0 && !selectedLocation) {
        setSelectedLocation(locsData[0].external_id);
      }
    } catch (err) {
      console.error("Failed to load activation data", err);
    }
  };

  const generateCode = async (e) => {
    e.preventDefault();
    if (!selectedLocation) return;
    
    setLoading(true);
    setNewCode(null);
    try {
      const res = await authFetch(`${API_BASE_URL}/admin/activation-codes?location_id=${selectedLocation}`, {
        method: "POST"
      });
      if (res.ok) {
        const data = await res.json();
        setNewCode(data);
        loadData();
      } else {
        alert("Failed to generate code");
      }
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const revokeCode = async (id) => {
    try {
      const res = await authFetch(`${API_BASE_URL}/admin/activation-codes/${id}`, {
        method: "DELETE"
      });
      if (res.ok) {
        setRevokingId(null);
        loadData();
      }
    } catch (err) {
      alert("Revoke failed");
    }
  };

  const copyToClipboard = (text) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
      alert("Copied to clipboard!");
    } else {
      // Fallback
      const el = document.createElement('textarea');
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      alert("Copied to clipboard!");
    }
  };

  return (
    <div className="page">
      <h1>Activation Codes</h1>
      <p className="sub">Manage workstation registration codes</p>

      <div className="grid">
        {/* Generation Form */}
        <div className="card">
          <h3>Generate New Code</h3>
          <form onSubmit={generateCode} style={{ marginTop: "12px" }}>
            <div style={{ marginBottom: "12px" }}>
              <label style={{ display: "block", marginBottom: "4px", fontSize: "0.9rem" }}>Workstation Location</label>
              {locations.length === 0 ? (
                <div style={{ color: "#ef4444", fontSize: "0.85rem", padding: "8px", background: "#fef2f2", borderRadius: "6px", border: "1px solid #fee2e2" }}>
                  ⚠ No locations found. Please <strong>Sync Locations</strong> from the Infrastructure menu first.
                </div>
              ) : (
                <select 
                  value={selectedLocation} 
                  onChange={(e) => setSelectedLocation(e.target.value)}
                  style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid #ddd" }}
                >
                  {locations.map(loc => (
                    <option key={loc.external_id} value={loc.external_id}>{loc.name} ({loc.external_id})</option>
                  ))}
                </select>
              )}
            </div>
            <button className="btn" disabled={loading || locations.length === 0} style={{ width: "100%" }}>
              {loading ? "Generating..." : "Create Activation Code"}
            </button>
          </form>

          {newCode && (
            <div style={{ 
              marginTop: "20px", 
              padding: "16px", 
              background: "#f0fdf4", 
              border: "2px dashed #22c55e", 
              borderRadius: "8px",
              textAlign: "center"
            }}>
              <p style={{ fontSize: "0.85rem", color: "#166534", marginBottom: "8px" }}>
                Activation Code for: <strong>{newCode.location_id}</strong>
              </p>
              <div style={{ display: "flex", gap: "8px", justifyContent: "center", alignItems: "center" }}>
                <code style={{ fontSize: "1.5rem", fontWeight: "bold", letterSpacing: "2px", color: "#15803d" }}>
                  {newCode.activation_code}
                </code>
                <button 
                  onClick={() => copyToClipboard(newCode.activation_code)}
                  style={{ padding: "4px 8px", fontSize: "0.75rem", cursor: "pointer" }}
                >
                  Copy
                </button>
              </div>
              <p style={{ fontSize: "0.75rem", color: "#dc2626", marginTop: "12px", fontWeight: "600" }}>
                ⚠ Copy this now — it will not be shown again!
              </p>
            </div>
          )}
        </div>

        {/* List of Codes */}
        <div className="card" style={{ gridColumn: "span 2" }}>
          <h3>Existing Codes</h3>
          <table style={{ marginTop: "12px" }}>
            <thead>
              <tr>
                <th>Location</th>
                <th>Code</th>
                <th>Status</th>
                <th>Details</th>
                <th>Created</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {codes.map(c => (
                <tr key={c.id}>
                  <td><strong>{c.location_id}</strong></td>
                  <td>
                    <code style={{ background: "#f5f5f5", padding: "2px 4px", borderRadius: "4px" }}>
                      {c.code}
                    </code>
                  </td>
                  <td>
                    <span className={`badge ${c.used ? 'gray' : 'live'}`}>
                      {c.used ? 'Used' : 'Unused'}
                    </span>
                  </td>
                  <td style={{ fontSize: "0.8rem", color: "#666" }}>
                    {c.used ? `Agent: ${c.agent_id}` : '—'}
                  </td>
                  <td style={{ fontSize: "0.75rem", color: "#888" }}>
                    {c.created_at ? new Date(c.created_at + "Z").toLocaleDateString() : "Unknown"}
                  </td>
                  <td>
                    {!c.used && (
                      revokingId === c.id ? (
                        <div style={{ display: "flex", gap: "4px" }}>
                          <button 
                            className="btn" 
                            style={{ background: "#ef4444", padding: "4px 8px", fontSize: "0.7rem" }}
                            onClick={() => revokeCode(c.id)}
                          >Confirm</button>
                          <button 
                            className="btn" 
                            style={{ background: "#6b7280", padding: "4px 8px", fontSize: "0.7rem" }}
                            onClick={() => setRevokingId(null)}
                          >Cancel</button>
                        </div>
                      ) : (
                        <button 
                          className="btn" 
                          style={{ padding: "4px 8px", fontSize: "0.7rem", opacity: 0.8 }}
                          onClick={() => setRevokingId(c.id)}
                        >Revoke</button>
                      )
                    )}
                  </td>
                </tr>
              ))}
              {codes.length === 0 && (
                <tr>
                  <td colSpan="6" style={{ textAlign: "center", color: "#999", padding: "20px" }}>No activation codes found</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default ActivationCodes;

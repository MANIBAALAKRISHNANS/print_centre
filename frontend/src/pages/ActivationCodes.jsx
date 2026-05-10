import { useState, useEffect, useContext } from "react";
import { useFetch } from "../context/AuthContext";
import { AppData } from "../context/AppData";
import { API_BASE_URL } from "../config";

const parseUTCDate = (str) => {
  if (!str) return null;
  const clean = str.replace(" UTC", "Z").replace(" ", "T");
  const d = new Date(clean);
  return isNaN(d.getTime()) ? null : d;
};

function ActivationCodes() {
  const { locations } = useContext(AppData);
  const [codes, setCodes] = useState([]);
  const [selectedLocation, setSelectedLocation] = useState("");
  const [loading, setLoading] = useState(false);
  const [newCode, setNewCode] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [copied, setCopied] = useState(false);
  const authFetch = useFetch();

  // Set default selected location when AppData locations load
  useEffect(() => {
    if (locations.length > 0 && !selectedLocation) {
      setSelectedLocation(locations[0].external_id);
    }
  }, [locations]); // eslint-disable-line

  useEffect(() => {
    loadCodes();
  }, []);

  const loadCodes = async () => {
    try {
      const res = await authFetch(`${API_BASE_URL}/admin/activation-codes`);
      const data = await res.json();
      setCodes(data);
    } catch (err) {
      console.error("Failed to load activation codes", err);
    }
  };

  const locationName = (id) => {
    const loc = locations.find(l => l.external_id === id);
    return loc ? loc.name : id;
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
        loadCodes();
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || "Failed to generate code");
      }
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteCode = async (id) => {
    try {
      const res = await authFetch(`${API_BASE_URL}/admin/activation-codes/${id}`, {
        method: "DELETE"
      });
      if (res.ok) {
        setDeletingId(null);
        loadCodes();
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || "Delete failed");
      }
    } catch (err) {
      alert("Delete failed: " + err.message);
    }
  };

  const copyToClipboard = async (text) => {
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(text);
      } else {
        const el = document.createElement("textarea");
        el.value = text;
        document.body.appendChild(el);
        el.select();
        document.execCommand("copy");
        document.body.removeChild(el);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      alert("Copy failed — please copy manually: " + text);
    }
  };

  return (
    <div className="page" style={{ padding: "40px" }}>
      <h1 className="clinical-title" style={{ margin: 0, fontSize: "2rem" }}>Activation Codes</h1>
      <p style={{ color: "var(--text-muted)", marginTop: "4px", fontSize: "0.95rem" }}>
        Manage workstation registration codes
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "24px", marginTop: "32px" }}>
        {/* Generation Form */}
        <div className="clinical-card" style={{ padding: "24px" }}>
          <h3 style={{ margin: "0 0 16px", fontWeight: 700 }}>Generate New Code</h3>
          <form onSubmit={generateCode}>
            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "block", marginBottom: "6px", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)" }}>
                Workstation Location
              </label>
              {locations.length === 0 ? (
                <div style={{ color: "#ef4444", fontSize: "0.85rem", padding: "10px", background: "#fef2f2", borderRadius: "8px", border: "1px solid #fee2e2" }}>
                  No locations found. Add locations first.
                </div>
              ) : (
                <select
                  value={selectedLocation}
                  onChange={(e) => setSelectedLocation(e.target.value)}
                  style={{ width: "100%", padding: "10px", borderRadius: "8px", border: "1px solid var(--border)", fontSize: "0.9rem", background: "white" }}
                >
                  {locations.map(loc => (
                    <option key={loc.external_id} value={loc.external_id}>
                      {loc.name} ({loc.external_id})
                    </option>
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
              marginTop: "20px", padding: "16px",
              background: "#f0fdf4", border: "2px dashed #22c55e",
              borderRadius: "10px", textAlign: "center"
            }}>
              <p style={{ fontSize: "0.8rem", color: "#166534", marginBottom: "8px" }}>
                Activation Code for: <strong>{locationName(newCode.location_id)}</strong>
              </p>
              <div style={{ display: "flex", gap: "8px", justifyContent: "center", alignItems: "center" }}>
                <code style={{ fontSize: "1.8rem", fontWeight: 800, letterSpacing: "4px", color: "#15803d" }}>
                  {newCode.activation_code}
                </code>
                <button
                  onClick={() => copyToClipboard(newCode.activation_code)}
                  className="btn"
                  style={{ padding: "6px 12px", fontSize: "0.75rem", background: copied ? "#16a34a" : undefined }}
                >
                  {copied ? "Copied!" : "Copy"}
                </button>
              </div>
              <p style={{ fontSize: "0.75rem", color: "#dc2626", marginTop: "10px", fontWeight: 600 }}>
                Copy this now — it will not be shown again!
              </p>
            </div>
          )}
        </div>

        {/* List of Codes */}
        <div className="clinical-card" style={{ padding: "0", overflow: "hidden" }}>
          <div style={{ padding: "20px 24px", borderBottom: "1px solid rgba(0,0,0,0.05)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0, fontWeight: 700 }}>Existing Codes</h3>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{codes.length} total</span>
          </div>
          <table className="clinical-table">
            <thead>
              <tr>
                <th>Location</th>
                <th>Code</th>
                <th>Status</th>
                <th>Agent</th>
                <th>Created</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {codes.map(c => {
                const created = parseUTCDate(c.created_at);
                return (
                  <tr key={c.id}>
                    <td style={{ fontWeight: 600, maxWidth: "180px" }}>
                      <div style={{ fontSize: "0.85rem" }}>{locationName(c.location_id)}</div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 400 }}>{c.location_id}</div>
                    </td>
                    <td>
                      <code style={{ background: "#f5f5f5", padding: "3px 6px", borderRadius: "4px", fontSize: "0.85rem" }}>
                        {c.code}
                      </code>
                    </td>
                    <td>
                      <span className={`badge ${c.used ? "gray" : "green"}`}>
                        {c.used ? "Used" : "Active"}
                      </span>
                    </td>
                    <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                      {c.used && c.agent_id ? <code style={{ fontSize: "0.75rem" }}>{c.agent_id}</code> : "—"}
                    </td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      {created ? created.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                    </td>
                    <td>
                      {deletingId === c.id ? (
                        <div style={{ display: "flex", gap: "4px" }}>
                          <button className="btn" style={{ background: "#ef4444", padding: "4px 10px", fontSize: "0.7rem" }} onClick={() => deleteCode(c.id)}>
                            Confirm
                          </button>
                          <button className="btn" style={{ background: "#6b7280", padding: "4px 10px", fontSize: "0.7rem" }} onClick={() => setDeletingId(null)}>
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          className="btn outline sm"
                          style={{ padding: "4px 10px", fontSize: "0.7rem", color: "#ef4444", borderColor: "#ef4444" }}
                          onClick={() => setDeletingId(c.id)}
                        >
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {codes.length === 0 && (
                <tr>
                  <td colSpan="6" style={{ textAlign: "center", color: "var(--text-muted)", padding: "32px" }}>
                    No activation codes found
                  </td>
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

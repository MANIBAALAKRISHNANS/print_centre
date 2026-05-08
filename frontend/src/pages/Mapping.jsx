import { useState, useEffect, useContext, useCallback } from "react";
import { AppData } from "../context/AppData";
import { useFetch } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { SkeletonTable } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import { API_BASE_URL } from "../config";

function Mapping() {
  const { printers } = useContext(AppData);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const toast = useToast();
  
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [formData, setFormData] = useState({
    location: "",
    external_id: "",
    a4Primary: "None",
    a4Secondary: "None",
    barPrimary: "None",
    barSecondary: "None",
  });
  const authFetch = useFetch();

  const loadMappings = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE_URL}/mapping`);
      if (!res.ok) throw new Error("Failed to load mappings");
      const data = await res.json();
      setRows(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => {
    loadMappings();
    const interval = setInterval(loadMappings, 10000); // 10s refresh for mapping
    return () => clearInterval(interval);
  }, [loadMappings]);

  const testPrint = async (locationId, category) => {
    try {
      const res = await authFetch(`${API_BASE_URL}/print-job`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          location_id: locationId, category: category,
          patient_name: "TEST PATIENT", age: "30", gender: "M", tube_type: "EDTA",
        }),
      });
      const data = await res.json();
      if (data.error) toast.error("Print Error: " + data.error);
      else toast.success("✅ Print job queued: " + data.job_id);
    } catch (err) { toast.error("Print failed: " + err.message); }
  };

  const validateMappings = async () => {
    try {
      const res = await authFetch(`${API_BASE_URL}/mapping-validate`);
      const result = await res.json();
      if (result.valid) toast.success("✅ All mappings are valid!");
      else toast.warning(`${result.issues.length} mapping issues found. Check details.`);
    } catch (err) { toast.error(`Error: ${err.message}`); }
  };

  const editMapping = (row) => {
    setEditId(row.id);
    setFormData({ ...row });
    setOpen(true);
  };

  const saveMapping = async () => {
    try {
      await authFetch(`${API_BASE_URL}/mapping/${editId}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      setOpen(false);
      toast.success("Mapping updated");
      loadMappings();
    } catch (err) { toast.error(err.message); }
  };

  return (
    <div className="page">
      <h1>Printer Mapping</h1>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <p className="sub">Assign primary and secondary printers by location</p>
        <button className="btn" onClick={validateMappings}>Validate All</button>
      </div>

      <br />
      <div className="card">
        {loading && rows.length === 0 ? (
          <SkeletonTable rows={5} cols={7} />
        ) : error ? (
          <p className="errorText">{error}. <button onClick={loadMappings}>Retry</button></p>
        ) : rows.length === 0 ? (
          <EmptyState
            icon="🗺️"
            title="No mappings configured"
            subtitle="Printers must be mapped to locations before they can be used."
          />
        ) : (
          <table>
            <thead>
              <tr><th rowSpan="2">Location</th><th rowSpan="2">ID</th><th colSpan="2">A4</th><th colSpan="2">Barcode</th><th rowSpan="2">Actions</th></tr>
              <tr><th>Primary</th><th>Secondary</th><th>Primary</th><th>Secondary</th></tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.location}</td>
                  <td><code style={{ fontSize: "0.75rem" }}>{row.external_id}</code></td>
                  <td>{row.a4Primary}</td><td>{row.a4Secondary}</td>
                  <td>{row.barPrimary}</td><td>{row.barSecondary}</td>
                  <td>
                    <button className="btn" onClick={() => editMapping(row)}>Edit</button>
                    <div style={{ marginTop: "5px", display: "flex", gap: "5px" }}>
                       <button className="btn mini blue" onClick={() => testPrint(row.external_id, "A4")}>A4</button>
                       <button className="btn mini green" onClick={() => testPrint(row.external_id, "Barcode")}>Bar</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {open && (
        <div className="modalOverlay">
          <div className="modalBox">
            <div className="modalHead"><h3>Edit Mapping</h3><button onClick={() => setOpen(false)}>✕</button></div>
            <div className="modalBody">
              <label>A4 Primary</label>
              <select value={formData.a4Primary} onChange={e => setFormData({ ...formData, a4Primary: e.target.value })}>
                <option>None</option>
                {printers.filter(p => p.category === "A4").map(p => <option key={p.id}>{p.name}</option>)}
              </select>
              <label>A4 Secondary</label>
              <select value={formData.a4Secondary} onChange={e => setFormData({ ...formData, a4Secondary: e.target.value })}>
                <option>None</option>
                {printers.filter(p => p.category === "A4").map(p => <option key={p.id}>{p.name}</option>)}
              </select>
              <label>Barcode Primary</label>
              <select value={formData.barPrimary} onChange={e => setFormData({ ...formData, barPrimary: e.target.value })}>
                <option>None</option>
                {printers.filter(p => p.category === "Barcode").map(p => <option key={p.id}>{p.name}</option>)}
              </select>
              <label>Barcode Secondary</label>
              <select value={formData.barSecondary} onChange={e => setFormData({ ...formData, barSecondary: e.target.value })}>
                <option>None</option>
                {printers.filter(p => p.category === "Barcode").map(p => <option key={p.id}>{p.name}</option>)}
              </select>
              <button className="btn full" onClick={saveMapping}>Update Mapping</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Mapping;

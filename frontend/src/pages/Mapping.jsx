import { useState, useEffect, useContext } from "react";
import { AppData } from "../context/AppData";
import { API_BASE_URL } from "../config";

function Mapping() {
  const { printers } = useContext(AppData);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
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

  const loadMappings = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/mapping`);
      if (!res.ok) throw new Error("Failed to load mappings");
      const data = await res.json();
      setRows(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMappings();
    const interval = setInterval(loadMappings, 10000); // 10s refresh for mapping
    return () => clearInterval(interval);
  }, []);

  const testPrint = async (locationId, category) => {
    try {
      const res = await fetch(`${API_BASE_URL}/print-job`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          location_id: locationId, category: category,
          patient_name: "TEST PATIENT", age: "30", gender: "M", tube_type: "EDTA",
        }),
      });
      const data = await res.json();
      if (data.error) alert("Print Error: " + data.error);
      else alert("✅ Print job queued: " + data.job_id);
    } catch (err) { alert("Print failed: " + err.message); }
  };

  const validateMappings = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/mapping-validate`);
      const result = await res.json();
      if (result.valid) alert("✅ All mappings are valid!");
      else alert(`⚠️ Issues:\n\n${result.issues.map(i => `${i.location}: ${i.issue}`).join("\n")}`);
    } catch (err) { alert(`Error: ${err.message}`); }
  };

  const editMapping = (row) => {
    setEditId(row.id);
    setFormData({ ...row });
    setOpen(true);
  };

  const saveMapping = async () => {
    try {
      await fetch(`${API_BASE_URL}/mapping/${editId}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      setOpen(false);
      loadMappings();
    } catch (err) { alert(err.message); }
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
          <p className="loadingText pulse">Loading mappings...</p>
        ) : error ? (
          <p className="errorText">{error}. <button onClick={loadMappings}>Retry</button></p>
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

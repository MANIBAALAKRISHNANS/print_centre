import { useState, useContext, useEffect, useCallback } from "react";
import { AppData } from "../context/AppData";

/* eslint-disable react-hooks/set-state-in-effect */

function Mapping() {
  const { printers, loadAll } = useContext(AppData);

  const [rows, setRows] = useState([]);

  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);


  const [newRow, setNewRow] = useState({
    location: "",
    a4Primary: "None",
    a4Secondary: "None",
    barPrimary: "None",
    barSecondary: "None",
  });

  /* ---------------- LOAD ACTIVE PRINTERS ---------------- */
  const loadActivePrinters = async (mappingData) => {
    // Already calculated by backend in /mapping endpoint
    // This function ensures data is loaded (no-op, kept for clarity)
    return mappingData;
  };

  /* ---------------- LOAD DATA WITH AUTO-REFRESH ---------------- */
  const loadMappings = useCallback(async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/mapping");
      const data = await res.json();

      setRows(data);

      // 👇 load failover results
      await loadActivePrinters(data);
    } catch (err) {
      console.log("Mapping load error", err);
    }
  }, []);

  useEffect(() => {
    loadMappings();

    // Auto-refresh every 5 seconds to show real-time printer status changes
    const interval = setInterval(loadMappings, 5000);

    return () => clearInterval(interval);
  }, [loadMappings]);

  /* ---------------- FILTER PRINTERS ---------------- */
  const printersA4 = [
    "None",
    ...printers
      .filter((p) => p.category === "A4")
      .map((p) => p.name),
  ];

  const printersBar = [
    "None",
    ...printers
      .filter((p) => p.category === "Barcode")
      .map((p) => p.name),
  ];

  /* ---------------- SAVE MAPPING (NEW OR EDIT) ---------------- */
  const saveMapping = async () => {
    // 🔴 VALIDATION START
 
    if (newRow.a4Primary !== "None" && newRow.a4Primary === newRow.a4Secondary) {
      alert("A4 Primary and Secondary cannot be the same");
      return;
    }

    if (newRow.barPrimary !== "None" && newRow.barPrimary === newRow.barSecondary) {
      alert("Barcode Primary and Secondary cannot be the same");
      return;
    }


    // 🔴 VALIDATION END

    try {
      const method = "PUT";
      const url = `http://127.0.0.1:8000/mapping/${editId}`;

      const res = await fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newRow),
      });

      const result = await res.json();

      if (result.error) {
        alert(`Error: ${result.error}`);
        return;
      }

      await Promise.all([
        loadMappings(),
        loadAll()
      ]);

      setEditId(null);
      setOpen(false);
    } catch (err) {
      alert(`Save error: ${err.message}`);
    }
  };

  const submitMappingOnEnter = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      saveMapping();
    }
  };

  /* ---------------- EDIT MAPPING ---------------- */
  const editMapping = (row) => {
    setNewRow({
      location: row.location,
      a4Primary: row.a4Primary || "None",
      a4Secondary: row.a4Secondary || "None",
      barPrimary: row.barPrimary || "None",
      barSecondary: row.barSecondary || "None",
    });

    setEditId(row.id);
    setOpen(true);
  };


  

  /* ------- VALIDATE ALL MAPPINGS ------- */
  const validateMappings = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/mapping-validate");
      const result = await res.json();

      if (result.valid) {
        alert("✅ All mappings are valid! No issues detected.");
      } else {
        alert(
          `⚠️ Found ${result.issues_count} issue(s):\n\n` +
          result.issues.map(i => `${i.location} - ${i.field}: ${i.issue}`).join("\n")
        );
      }
    } catch (err) {
      alert(`Validation error: ${err.message}`);
    }
  };
 
  /* ---------------- EDIT MAPPING (OLD) - REMOVE THIS DUPLICATE ----------------
  const editMapping = (row) => {
    setNewRow({
      location: row.location,
      a4Primary: row.a4Primary || "None",
      a4Secondary: row.a4Secondary || "None",
      barPrimary: row.barPrimary || "None",
      barSecondary: row.barSecondary || "None",
    });

    setEditId(row.id);
    setOpen(true);
  };
  ---- END DUPLICATE ---- */

 
  /* ---------------- UI COLOR ---------------- */
  const getColor = (type) => {
    if (type === "Primary") return "green";
    if (type === "Failover") return "orange";
    return "gray";
  };

  return (
    <div className="page">

      <h1>Printer Mapping</h1>

      <p className="sub">
        Assign primary and secondary printers by location (auto-refresh every 5s)
      </p>


      <button
        className="btn"
        style={{ marginLeft: "10px" }}
        onClick={validateMappings}
      >
        Validate All
      </button>

      <br /><br />

      <div className="card">
        <table>
          <thead>
            <tr>
              <th rowSpan="2">Location</th>
              <th colSpan="2">A4</th>
              <th colSpan="2">Barcode</th>
              <th rowSpan="2">Actions</th>
            </tr>
            <tr>
              <th>Primary (Active)</th>
              <th>Secondary</th>
              <th>Primary (Active)</th>
              <th>Secondary</th>
            </tr>
          </thead>

          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan="6" style={{ textAlign: "center" }}>
                  No mappings found.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.location}</td>

                  {/* A4 ACTIVE */}
                  <td>
                    {row.a4Active || "None"}
                    <br />
                    <small style={{ color: getColor(row.a4Type) }}>
                      ({row.a4Type || "-"})
                    </small>
                  </td>

                  {/* A4 SECONDARY */}
                  <td>{row.a4Secondary}</td>

                  {/* BARCODE ACTIVE */}
                  <td>
                    {row.barActive || "None"}
                    <br />
                    <small style={{ color: getColor(row.barType) }}>
                      ({row.barType || "-"})
                    </small>
                  </td>

                  {/* BARCODE SECONDARY */}
                  <td>{row.barSecondary}</td>

                  <td>
                    <button
                      className="btn"
                      onClick={() => editMapping(row)}
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>

        </table>
      </div>

      {/* MODAL */}
      {open && (
        <div className="modalOverlay">
          <div className="modalBox">

            <div className="modalHead">
              <h3>Edit Mapping</h3>
              <button onClick={() => {
                setOpen(false);
                setEditId(null);
              }}>✕</button>
            </div>

            <form
              className="modalBody"
              onSubmit={(e) => {
                e.preventDefault();
                saveMapping();
              }}
            >

              <input
                placeholder="Location"
                value={newRow.location}
                onChange={(e) => setNewRow({ ...newRow, location: e.target.value })}
                onKeyDown={submitMappingOnEnter}
                readOnly={true}
                style={{
                  background: "#f5f5f5",
                  cursor: "not-allowed",
                }}
              />

              {/* A4 PRIMARY */}
              <label>A4 Primary</label>
              <select
                value={newRow.a4Primary}
                onKeyDown={submitMappingOnEnter}
                onChange={(e) => {
                  const value = e.target.value;

                  if (value !== "None" && value === newRow.a4Secondary) {
                    alert("Primary and Secondary cannot be same");
                    return;
                  }

                  setNewRow({
                    ...newRow,
                    a4Primary: value,
                  });
                }}
              >
                {printersA4.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>

              {/* A4 SECONDARY */}
              <label>A4 Secondary (Failover)</label>
              <select
                value={newRow.a4Secondary}
                onKeyDown={submitMappingOnEnter}
                onChange={(e) => {
                  const value = e.target.value;

                  if (value !== "None" && value === newRow.a4Primary) {
                    alert("Primary and Secondary cannot be same");
                    return;
                  }

                  setNewRow({
                    ...newRow,
                    a4Secondary: value,
                  });
                }}
              >
                {printersA4.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>

              {/* BARCODE PRIMARY */}
              <label>Barcode Primary</label>
              <select
                value={newRow.barPrimary}
                onKeyDown={submitMappingOnEnter}
                onChange={(e) => {
                  const value = e.target.value;

                  if (value !== "None" && value === newRow.barSecondary) {
                    alert("Primary and Secondary cannot be same");
                    return;
                  }

                  setNewRow({
                    ...newRow,
                    barPrimary: value,
                  });
                }}
              >
                {printersBar.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>

              {/* BARCODE SECONDARY */}
              <label>Barcode Secondary (Failover)</label>
              <select
                value={newRow.barSecondary}
                onKeyDown={submitMappingOnEnter}
                onChange={(e) => {
                  const value = e.target.value;

                  if (value !== "None" && value === newRow.barPrimary) {
                    alert("Primary and Secondary cannot be same");
                    return;
                  }

                  setNewRow({
                    ...newRow,
                    barSecondary: value,
                  });
                }}
              >
                {printersBar.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>

              <button type="submit" className="btn full">
                Update Mapping
              </button>
            </form>

          </div>
        </div>
      )}

    </div>
  );
}

export default Mapping;

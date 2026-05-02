import { useState, useContext, useEffect, useCallback } from "react";
import { AppData } from "../context/AppData";

/* eslint-disable react-hooks/set-state-in-effect */

function Mapping() {
  const { printers, loadAll } = useContext(AppData);

  const [activeMap, setActiveMap] = useState({});
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
  const loadActivePrinters = useCallback(async (rowsData) => {
  const result = {};

  await Promise.all(
    rowsData.map(async (row) => {
      const a4 = await fetch(
        `http://127.0.0.1:8000/active-printer/${row.location}/A4`
      ).then((r) => r.json());

      const bar = await fetch(
        `http://127.0.0.1:8000/active-printer/${row.location}/Barcode`
      ).then((r) => r.json());

      result[row.location] = { a4, bar };
    })
  );

  setActiveMap(result);
}, []);

  /* ---------------- LOAD DATA ---------------- */
  const loadMappings = useCallback(async () => {
    const res = await fetch("http://127.0.0.1:8000/mapping");
    const data = await res.json();

    setRows(data);

    // 👇 load failover results
    await loadActivePrinters(data);
  }, [loadActivePrinters]);

  useEffect(() => {
    loadMappings();
  }, [printers, loadMappings]);

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

  /* ---------------- SAVE ---------------- */
  const saveMapping = async () => {

    // 🔴 STEP 6 VALIDATION START
 
    if (newRow.a4Primary === newRow.a4Secondary) {
      alert("A4 Primary and Secondary cannot be the same");
      return;
    }

    if (newRow.barPrimary === newRow.barSecondary) {
      alert("Barcode Primary and Secondary cannot be the same");
      return;
    }

    // 🔴 STEP 6 VALIDATION END


    const url = `http://127.0.0.1:8000/mapping/${editId}`;

    await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newRow),
    });

    await loadMappings();
    await loadAll();

    setEditId(null);
    setOpen(false);
  };

  const submitMappingOnEnter = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      saveMapping();
    }
  };

  /* ---------------- EDIT ---------------- */
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
        Assign primary and secondary printers by location
      </p>

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
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.location}</td>

                {/* A4 ACTIVE */}
                <td>
                  {activeMap[row.location]?.a4?.printer || "None"}
                  <br />
                  <small
                    style={{
                      color: getColor(
                        activeMap[row.location]?.a4?.type
                      ),
                    }}
                  >
                    ({activeMap[row.location]?.a4?.type || "-"})
                  </small>
                </td>

                {/* A4 SECONDARY */}
                <td>{row.a4Secondary}</td>

                {/* BARCODE ACTIVE */}
                <td>
                  {activeMap[row.location]?.bar?.printer || "None"}
                  <br />
                  <small
                    style={{
                      color: getColor(
                        activeMap[row.location]?.bar?.type
                      ),
                    }}
                  >
                    ({activeMap[row.location]?.bar?.type || "-"})
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
            ))}
          </tbody>

        </table>
      </div>

      {/* MODAL */}
      {open && (
        <div className="modalOverlay">
          <div className="modalBox">

            <div className="modalHead">
              <h3>Edit Mapping</h3>
              <button onClick={() => setOpen(false)}>✕</button>
            </div>

            <form
              className="modalBody"
              onSubmit={(e) => {
                e.preventDefault();
                saveMapping();
              }}
            >

              <input
              value={newRow.location}
              readOnly
              onKeyDown={submitMappingOnEnter}
              style={{
                background: "#f5f5f5",
                cursor: "not-allowed",
              }}
            />

            {/* A4 PRIMARY */}
            <select
              value={newRow.a4Primary}
              onKeyDown={submitMappingOnEnter}
              onChange={(e) => {
                const value = e.target.value;

                if (value === newRow.a4Secondary) {
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
            <select
              value={newRow.a4Secondary}
              onKeyDown={submitMappingOnEnter}
              onChange={(e) => {
                const value = e.target.value;

                if (value === newRow.a4Primary) {
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
            <select
              value={newRow.barPrimary}
              onKeyDown={submitMappingOnEnter}
              onChange={(e) => {
                const value = e.target.value;

                if (value === newRow.barSecondary) {
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
            <select
              value={newRow.barSecondary}
              onKeyDown={submitMappingOnEnter}
              onChange={(e) => {
                const value = e.target.value;

              if (value === newRow.barPrimary) {
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

          <button
            type="submit"
            className="btn full"
          >
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

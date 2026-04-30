import { useState, useContext, useEffect } from "react";
import { AppData } from "../context/AppData";

function Mapping() {
  const { printers } = useContext(AppData);

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
  const loadActivePrinters = async (rowsData) => {
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
};

  /* ---------------- LOAD DATA ---------------- */
  const loadMappings = async () => {
    const res = await fetch("http://127.0.0.1:8000/mapping");
    const data = await res.json();

    setRows(data);

    // 👇 load failover results
    await loadActivePrinters(data);
  };

  useEffect(() => {
    loadMappings();
  }, []);

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
    const url = `http://127.0.0.1:8000/mapping/${editId}`;

    await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newRow),
    });

    await loadMappings();

    setEditId(null);
    setOpen(false);
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

            <div className="modalBody">

              <input
                value={newRow.location}
                readOnly
                style={{
                  background: "#f5f5f5",
                  cursor: "not-allowed",
                }}
              />

              <select
                value={newRow.a4Primary}
                onChange={(e) =>
                  setNewRow({
                    ...newRow,
                    a4Primary: e.target.value,
                  })
                }
              >
                {printersA4.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>

              <select
                value={newRow.a4Secondary}
                onChange={(e) =>
                  setNewRow({
                    ...newRow,
                    a4Secondary: e.target.value,
                  })
                }
              >
                {printersA4.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>

              <select
                value={newRow.barPrimary}
                onChange={(e) =>
                  setNewRow({
                    ...newRow,
                    barPrimary: e.target.value,
                  })
                }
              >
                {printersBar.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>

              <select
                value={newRow.barSecondary}
                onChange={(e) =>
                  setNewRow({
                    ...newRow,
                    barSecondary: e.target.value,
                  })
                }
              >
                {printersBar.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>

              <button
                className="btn full"
                onClick={saveMapping}
              >
                Update Mapping
              </button>

            </div>

          </div>
        </div>
      )}

    </div>
  );
}

export default Mapping;
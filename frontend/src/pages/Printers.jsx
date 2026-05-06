import { useState, useContext, useEffect } from "react";
import { AppData } from "../context/AppData";
import { API_BASE_URL } from "../config";

function Printers() {
  const { printers, setPrinters, loadAll } = useContext(AppData);

  const [categories, setCategories] = useState([]);

  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);

  const [newPrinter, setNewPrinter] = useState({
    name: "",
    ip: "",
    category: "",
    status: "Online",
    language: "PS", 
    connection_type: "IP",
  });




  /* load categories */
  useEffect(() => {
    fetch(`${API_BASE_URL}/categories`)
      .then((res) => res.json())
      .then((data) => {
        setCategories(data);

        if (data.length > 0) {
          setNewPrinter((old) => ({
            ...old,
            category: data[0],
            language: data[0] === "Barcode" ? "ZPL" : "PS",
          }));
        }
      });
  }, []);

  useEffect(() => {
    const refreshPrinterStatus = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/printers`);
        const data = await res.json();
        setPrinters(data);
      } catch (err) {
        console.log("Printer status refresh error", err);
      }
    };

    refreshPrinterStatus();
    const interval = setInterval(refreshPrinterStatus, 10000); // 10s polling

    return () => clearInterval(interval);
  }, [setPrinters]);

  const getStatusColor = (status) => {
    const s = (status || "").toLowerCase();
    if (s === "online") return "green";
    if (s === "error") return "orange";
    if (s === "offline") return "red";
    return "gray"; 
  };

  const isStale = (last_updated) => {
    if (!last_updated) return true;
    // Backend format: "YYYY-MM-DD HH:MM:SS UTC"
    const cleanStr = last_updated.replace(" UTC", "Z").replace(" ", "T");
    const diff = Date.now() - new Date(cleanStr).getTime();
    return diff > 45000;
  };

  /* add / edit save */
  const savePrinter = async () => {
    const printerData = {
      ...newPrinter,
      name: newPrinter.name.trim(),
      ip: newPrinter.connection_type === "USB" ? "" : newPrinter.ip.trim(),
    };

    if (printerData.name === "") return;
    if (printerData.connection_type === "IP" && printerData.ip === "") return;

    const url = editId
      ? `${API_BASE_URL}/printers/${editId}`
      : `${API_BASE_URL}/printers`;

    const method = editId ? "PUT" : "POST";

    const res = await fetch(url, {
      method: method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(printerData),
    });

    const result = await res.json();

    if (result.error) {
      alert(result.error);
      return;
    }

    if (editId) {
      setPrinters((current) =>
        current.map((printer) =>
          printer.id === editId ? { ...printer, ...printerData, id: editId } : printer
        )
      );
    } else {
      setPrinters((current) => [
        ...current,
        { ...printerData, id: result.id },
      ]);
    }

    setNewPrinter({
      name: "",
      ip: "",
      category: categories[0] || "",
      status: "Online",
      language: "PS",
      connection_type: "IP",
    });

    setEditId(null);
    setOpen(false);
    loadAll();
  };

  /* open edit */
  const editPrinter = (printer) => {
    setNewPrinter({
      name: printer.name,
      ip: printer.ip || "",
      category: printer.category,
      status: printer.status,
      language: printer.language || "PS",
      connection_type: printer.connection_type || "IP",
    });

    setEditId(printer.id);
    setOpen(true);
  };

  /* delete */
  const deletePrinter = async (id) => {
    if (!window.confirm("Delete printer?")) return;

    const res = await fetch(
      `${API_BASE_URL}/printers/${id}`,
      {
        method: "DELETE",
      }
    );

    const result = await res.json();

    if (result.error) {
      alert(result.error);
      return;
    }

    setPrinters((current) => current.filter((printer) => printer.id !== id));
    loadAll();
  };

  /* add mode */
  const openAdd = () => {
    setEditId(null);

    setNewPrinter({
      name: "",
      ip: "",
      category: categories[0] || "",
      status: "Online",
      language: "PS",
      connection_type: "IP",
    });

    setOpen(true);
  };

  return (
    <div className="page">

      <h1>Printers</h1>

      <p className="sub">
        Manage all connected printers
      </p>

      <button className="btn" onClick={openAdd}>
        + Add Printer
      </button>

      <br /><br />

      <div className="card">

        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>IP</th>
              <th>Category</th>
              <th>Language</th>
              <th>Status</th>
              <th>Change</th>
              <th>Actions</th>
            </tr>
          </thead>

          <tbody>
            {printers.map((p, i) => {
              const normalizedStatus = (p.status || "").toLowerCase();
              let displayStatus = normalizedStatus;

              if (p.connection_type === "USB" && isStale(p.last_updated)) {
                displayStatus = "offline";
              }

              console.log({
                name: p.name,
                backendStatus: p.status,
                displayStatus,
                last_updated: p.last_updated
              });

              return (
                <tr key={i}>
                  <td>{p.name}</td>
                  <td>
                    <span style={{ fontSize: '0.8em', opacity: 0.7 }}>
                      {p.connection_type || 'IP'}
                    </span>
                  </td>
                  <td>{p.ip || '-'}</td>
                  <td>{p.category}</td>
                  <td>{p.language}</td>

                  <td>
                    <span className={`badge ${getStatusColor(displayStatus)}`}>
                      {displayStatus.charAt(0).toUpperCase() + displayStatus.slice(1)}
                    </span>
                  </td>

                  <td>
                    <button
                      className="btn"
                      onClick={() => editPrinter(p)}
                    >
                      Edit
                    </button>

                    <button
                      className="btn"
                      style={{ marginLeft: "8px" }}
                      onClick={() =>
                        deletePrinter(p.id)
                      }
                    >
                      Delete
                    </button>
                  </td>

                </tr>
              );
            })}
          </tbody>

        </table>

      </div>

      {open && (
        <div className="modalOverlay">

          <div className="modalBox">

            <div className="modalHead">
              <h3>
                {editId ? "Edit Printer" : "Add Printer"}
              </h3>

              <button onClick={() => setOpen(false)}>
                ✕
              </button>
            </div>

            <form
              className="modalBody"
              onSubmit={(e) => {
                e.preventDefault();
                savePrinter();
              }}
            >

              <input
                placeholder="Printer Name"
                value={newPrinter.name}
                onChange={(e) =>
                  setNewPrinter({
                    ...newPrinter,
                    name: e.target.value,
                  })
                }
              />

              <select
                value={newPrinter.connection_type}
                onChange={(e) =>
                  setNewPrinter({
                    ...newPrinter,
                    connection_type: e.target.value,
                    ip: e.target.value === "USB" ? "" : newPrinter.ip
                  })
                }
              >
                <option value="IP">Network Printer (IP)</option>
                <option value="USB">Local Printer (USB Agent)</option>
              </select>

              <input
                placeholder={newPrinter.connection_type === "USB" ? "No IP required for USB" : "IP Address"}
                value={newPrinter.ip}
                disabled={newPrinter.connection_type === "USB"}
                onChange={(e) =>
                  setNewPrinter({
                    ...newPrinter,
                    ip: e.target.value,
                  })
                }
              />

              <select
                value={newPrinter.category}
                onChange={(e) =>
                  setNewPrinter({
                    ...newPrinter,
                    category: e.target.value,
                    language: e.target.value === "Barcode" ? "ZPL" : "PS"
                  })
                }
              >
                {categories.map((cat, i) => (
                  <option key={i} value={cat}>{cat}</option>
                ))}
              </select>

              <select
                value={newPrinter.language}
                onChange={(e) =>
                  setNewPrinter({
                   ...newPrinter,
                   language: e.target.value,
                  })
                }
              >
                {newPrinter.category === "Barcode" ? (
                  <option value="ZPL">ZPL (Barcode)</option>
                ) : (
                  <>
                    <option value="PS">PostScript (A4)</option>
                    <option value="PCL">PCL (A4)</option>
                  </>
                )}
              </select>

              <button
                type="submit"
                className="btn full"
              >
                {editId ? "Update Printer" : "Save Printer"}
              </button>

            </form>

          </div>

        </div>
      )}

    </div>
  );
}

export default Printers;

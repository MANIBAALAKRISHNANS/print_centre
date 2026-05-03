import { useState, useContext, useEffect } from "react";
import { AppData } from "../context/AppData";

function Printers() {
  const { printers, setPrinters, loadAll } = useContext(AppData);

  const [categories, setCategories] = useState([]);

  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);

  const [newPrinter, setNewPrinter] = useState({
    name: "",
    ip: "",
    category: "",
    status: "Live",
    language: "PS", 
  });




  /* load categories */
  useEffect(() => {
    fetch("http://127.0.0.1:8000/categories")
      .then((res) => res.json())
      .then((data) => {
        setCategories(data);

        if (data.length > 0) {
          setNewPrinter((old) => ({
            ...old,
            category: data[0],
          }));
        }
      });
  }, []);

  useEffect(() => {
    const refreshPrinterStatus = async () => {
      try {
        const res = await fetch("http://127.0.0.1:8000/printers");
        const data = await res.json();
        setPrinters(data);
      } catch (err) {
        console.log("Printer status refresh error", err);
      }
    };

    refreshPrinterStatus();
    const interval = setInterval(refreshPrinterStatus, 3000);

    return () => clearInterval(interval);
  }, [setPrinters]);

  const badge = (status) => {
    if (status === "Live") return "live";
    if (status === "Maintenance") return "warn";
    return "offline";
  };

  

  /* add / edit save */
  const savePrinter = async () => {
    const printerData = {
      ...newPrinter,
      name: newPrinter.name.trim(),
      ip: newPrinter.ip.trim(),
    };

    if (printerData.name === "" || printerData.ip === "") return;

    const url = editId
      ? `http://127.0.0.1:8000/printers/${editId}`
      : "http://127.0.0.1:8000/printers";

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
      status: "Live",
      language: "PS",
    });

    setEditId(null);
    setOpen(false);
    loadAll();
  };

  /* open edit */
  const editPrinter = (printer) => {
    setNewPrinter({
      name: printer.name,
      ip: printer.ip,
      category: printer.category,
      status: printer.status,
      language: printer.language || "PS",
    });

    setEditId(printer.id);
    setOpen(true);
  };

  /* delete */
  const deletePrinter = async (id) => {
    if (!window.confirm("Delete printer?")) return;

    const res = await fetch(
      `http://127.0.0.1:8000/printers/${id}`,
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
      status: "Live",
      language: "PS",
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
              <th>IP</th>
              <th>Category</th>
              <th>Language</th>
              <th>Status</th>
              <th>Change</th>
              <th>Actions</th>
            </tr>
          </thead>

          <tbody>
            {printers.map((p, i) => (
              <tr key={i}>
                <td>{p.name}</td>
                <td>{p.ip}</td>
                <td>{p.category}</td>
                <td>{p.language}</td>

                <td>
                  <span className={`badge ${badge(p.status)}`}>
                    {p.status}
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
            ))}
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

              <input
                placeholder="IP Address"
                value={newPrinter.ip}
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
                  })
                }
              >
                {categories.map((cat, i) => (
                  <option key={i}>{cat}</option>
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
                <option value="ZPL">ZPL (Barcode)</option>
                <option value="PCL">PCL (A4)</option>
                <option value="PS">PostScript (A4)</option>
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

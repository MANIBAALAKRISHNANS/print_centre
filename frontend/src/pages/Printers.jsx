import { useState, useContext, useEffect, useRef, useMemo } from "react";
import { AppData } from "../context/AppData";
import { useFetch } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { SkeletonTable } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import { API_BASE_URL } from "../config";

function Printers() {
  const { printers, setPrinters, categories, loadAll, loading: appLoading, errors: appErrors } = useContext(AppData);

  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState(null);
  const [filter, setFilter] = useState("All");
  const [checking, setChecking] = useState({}); // { printerId: boolean }
  const lastStatuses = useRef({}); // { printerId: status }
  const [now, setNow] = useState(Date.now());

  const [newPrinter, setNewPrinter] = useState({
    name: "",
    ip: "",
    category: "",
    status: "Online",
    language: "PS", 
    connection_type: "IP",
  });

  const [confirmDelete, setConfirmDelete] = useState(null);
  const authFetch = useFetch();
  const toast = useToast();

  /* set default category when AppData categories become available */
  useEffect(() => {
    if (categories.length > 0 && !newPrinter.category) {
      setNewPrinter((old) => ({
        ...old,
        category: categories[0],
        language: categories[0] === "Barcode" ? "ZPL" : "PS",
      }));
    }
  }, [categories]); // eslint-disable-line

  useEffect(() => {
    const refreshPrinterStatus = async () => {
      try {
        const res = await authFetch(`${API_BASE_URL}/printers`);
        const data = await res.json();
        
        if (Array.isArray(data)) {
            // Check for status changes to trigger toasts
            data.forEach(p => {
                const prev = lastStatuses.current[p.id];
                const current = p.status;
                if (prev && prev !== current) {
                    if (current === "Online") toast.success(`Printer ${p.name} is back ONLINE`);
                    if (current === "Offline") toast.warning(`Printer ${p.name} has gone OFFLINE`);
                }
                lastStatuses.current[p.id] = current;
            });

            setPrinters(data);
        }
      } catch (err) {
        // Silent for background poll
      }
    };

    refreshPrinterStatus();
    const interval = setInterval(refreshPrinterStatus, 30000); // 30s polling
    const timeInterval = setInterval(() => setNow(Date.now()), 60000); // Update relative times

    return () => {
        clearInterval(interval);
        clearInterval(timeInterval);
    };
  }, [setPrinters, authFetch, toast]);

  const getStatusColor = (status) => {
    const s = (status || "").toLowerCase();
    if (s === "online") return "green";
    if (s === "error") return "orange";
    if (s === "offline") return "red";
    return "gray"; 
  };

  const isStale = (last_updated) => {
    if (!last_updated) return true;
    const cleanStr = last_updated.replace(" UTC", "Z").replace(" ", "T");
    const diff = Date.now() - new Date(cleanStr).getTime();
    return diff > 45000;
  };

  const getRelativeTime = (timeStr) => {
    if (!timeStr) return "Never";
    const cleanStr = timeStr.replace(" UTC", "Z").replace(" ", "T");
    const diff = Math.floor((now - new Date(cleanStr).getTime()) / 1000);
    
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} hr ago`;
    return `${Math.floor(diff / 86400)} d ago`;
  };

  const filteredPrinters = useMemo(() => {
    return printers.filter(p => {
        if (filter === "All") return true;
        if (filter === "Online") return p.status === "Online";
        if (filter === "Offline") return p.status === "Offline";
        if (filter === "USB") return p.connection_type === "USB";
        if (filter === "Network") return p.connection_type === "IP";
        return true;
    });
  }, [printers, filter]);

  const forceCheck = async (name, id) => {
    setChecking(prev => ({ ...prev, [id]: true }));
    try {
        const res = await authFetch(`${API_BASE_URL}/printers/${encodeURIComponent(name)}/status`);
        const data = await res.json();
        if (data.error) toast.error(data.error);
        else {
            toast.info(`Status Check: ${data.status}`);
            loadAll(true); // Silent refresh
        }
    } catch (err) {
        toast.error("Status check failed");
    } finally {
        setChecking(prev => ({ ...prev, [id]: false }));
    }
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

    const res = await authFetch(url, {
      method: method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(printerData),
    });

    const result = await res.json();

    if (result.error) {
      toast.error(result.error);
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
    toast.success(`Printer ${editId ? "updated" : "saved"}`);
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
    try {
      const res = await authFetch(
        `${API_BASE_URL}/printers/${id}`,
        {
          method: "DELETE",
        }
      );

      const result = await res.json();

      if (result.error) {
        toast.error(result.error);
        return;
      }

      setPrinters((current) => current.filter((printer) => printer.id !== id));
      loadAll();
      toast.success("Printer deleted");
      setConfirmDelete(null);
    } catch (err) {
      toast.error("Failed to delete printer");
    }
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

      <div style={{ 
          display: "flex", 
          gap: "12px", 
          marginBottom: "24px", 
          flexWrap: "wrap",
          alignItems: "center",
          background: "#f8fafc",
          padding: "12px",
          borderRadius: "8px",
          border: "1px solid #e2e8f0"
      }}>
          <span style={{ fontSize: "0.85rem", fontWeight: "bold", color: "#64748b", marginRight: "8px" }}>SUMMARY</span>
          <div className="badge blue">Total: {printers.length}</div>
          <div className="badge live">Online: {printers.filter(p => p.status === "Online").length}</div>
          <div className="badge offline">Offline: {printers.filter(p => p.status === "Offline").length}</div>
          <div className="badge gray">USB: {printers.filter(p => p.connection_type === "USB").length}</div>
          <div className="badge gray">Network: {printers.filter(p => p.connection_type === "IP").length}</div>
          
          <div style={{ marginLeft: "auto", display: "flex", gap: "6px" }}>
              <button className="btn" onClick={openAdd}>+ Add Printer</button>
          </div>
      </div>

      <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
          {[
              { id: "All", label: "All", count: printers.length },
              { id: "Online", label: "Online", count: printers.filter(p => p.status === "Online").length },
              { id: "Offline", label: "Offline", count: printers.filter(p => p.status === "Offline").length },
              { id: "USB", label: "USB", count: printers.filter(p => p.connection_type === "USB").length },
              { id: "Network", label: "Network", count: printers.filter(p => p.connection_type === "IP").length }
          ].map(f => (
              <button 
                key={f.id}
                onClick={() => setFilter(f.id)}
                style={{
                    padding: "6px 12px",
                    borderRadius: "20px",
                    border: filter === f.id ? "2px solid #4f46e5" : "2px solid #ddd",
                    background: filter === f.id ? "#4f46e5" : "white",
                    color: filter === f.id ? "white" : "#333",
                    cursor: "pointer",
                    fontSize: "0.85rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px"
                }}
              >
                  {f.label} <span style={{ opacity: 0.7, fontSize: "0.75rem" }}>{f.count}</span>
              </button>
          ))}
      </div>

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
               <th>Last Activity</th>
               <th>Actions</th>
            </tr>
          </thead>

          <tbody>
            {appLoading.printers ? (
               <tr>
                 <td colSpan="8">
                   <SkeletonTable rows={5} cols={8} />
                 </td>
               </tr>
            ) : filteredPrinters.length === 0 ? (
               <tr>
                 <td colSpan="8">
                    <EmptyState 
                        icon="🖨️"
                        title="No printers found"
                        subtitle={filter === "All" ? "Start by adding your first hospital printer." : `No printers found for filter "${filter}"`}
                        action={openAdd}
                        actionLabel="Add Printer"
                    />
                 </td>
               </tr>
            ) : filteredPrinters.map((p) => {
              const normalizedStatus = (p.status || "").toLowerCase();
              let displayStatus = normalizedStatus;
              const isUsb = p.connection_type === "USB";
              const stale = isUsb && isStale(p.last_updated);

              if (stale) displayStatus = "offline";

              return (
                <tr key={p.id}>
                  <td><strong>{p.name}</strong></td>
                  <td>
                    <span style={{ fontSize: '0.8em', opacity: 0.7 }}>
                      {p.connection_type || 'IP'}
                    </span>
                  </td>
                  <td>{p.ip || '-'}</td>
                  <td>{p.category}</td>
                  <td>{p.language}</td>

                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                       <span className={`dot ${displayStatus === "online" ? "pulse-green" : "red"}`} style={{ 
                           width: "8px", height: "8px", borderRadius: "50%",
                           background: displayStatus === "online" ? "#22c55e" : "#ef4444",
                           animation: displayStatus === "online" ? "pulse 2s infinite" : "none"
                       }}></span>
                       <span className={`badge ${getStatusColor(displayStatus)}`}>
                         {displayStatus.charAt(0).toUpperCase() + displayStatus.slice(1)}
                       </span>
                       {stale && <span className="badge offline" style={{ fontSize: "0.7rem" }}>⚠ Stale</span>}
                    </div>
                  </td>

                  <td style={{ fontSize: "0.85rem" }}>
                      <div style={{ color: "#333" }}>{getRelativeTime(p.last_updated)}</div>
                      {isUsb && (
                          <div style={{ fontSize: "0.75rem", color: "#888" }}>
                              Agent: {p.last_update_source || "Unknown"}
                          </div>
                      )}
                  </td>

                  <td>
                    <div style={{ display: "flex", gap: "6px" }}>
                       <button
                         className="btn"
                         disabled={checking[p.id]}
                         onClick={() => forceCheck(p.name, p.id)}
                         style={{ minWidth: "100px" }}
                       >
                         {checking[p.id] ? "Checking..." : "Force Check"}
                       </button>
                       <button
                         className="btn"
                         onClick={() => editPrinter(p)}
                       >
                         Edit
                       </button>
                       <button
                         className="btn"
                         style={{ background: "#ef4444" }}
                         onClick={() => setConfirmDelete(p)}
                       >
                         Delete
                       </button>
                    </div>
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

      {confirmDelete && (
        <div className="modalOverlay">
          <div className="modalBox" style={{ textAlign: "center", padding: "30px" }}>
            <h3 style={{ marginBottom: "15px" }}>Delete Printer?</h3>
            <p style={{ color: "#666", marginBottom: "25px" }}>
              Are you sure you want to delete <strong>{confirmDelete.name}</strong>?
            </p>
            <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
              <button 
                className="btn" 
                style={{ background: "#ef4444" }}
                onClick={() => deletePrinter(confirmDelete.id)}
              >Delete</button>
              <button 
                className="btn" 
                style={{ background: "#6b7280" }}
                onClick={() => setConfirmDelete(null)}
              >Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Printers;

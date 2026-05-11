import { useState, useEffect, useCallback } from "react";
import { useFetch, useAuth } from "../context/AuthContext";
import { API_BASE_URL } from "../config";

function AuditLogs() {
  const { user } = useAuth();
  const authFetch = useFetch();
  
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  const todayISO = new Date().toISOString().split("T")[0];

  const [filters, setFilters] = useState({
    actor: "",
    action: "",
    patient_id: "",
    from_date: todayISO,
    to_date: todayISO
  });

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      let url = `${API_BASE_URL}/admin/audit-logs?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`;
      if (filters.actor) url += `&actor=${encodeURIComponent(filters.actor)}`;
      if (filters.action) url += `&action=${encodeURIComponent(filters.action)}`;
      if (filters.patient_id) url += `&patient_id=${encodeURIComponent(filters.patient_id)}`;
      if (filters.from_date) url += `&from_date=${filters.from_date}`;
      if (filters.to_date) url += `&to_date=${filters.to_date}`;

      const res = await authFetch(url);
      const data = await res.json();
      setLogs(data.logs || []);
      setTotal(data.total || 0);
    } catch (err) {
      console.error("Audit fetch error", err);
    } finally {
      setLoading(false);
    }
  }, [authFetch, page, filters]);

  useEffect(() => {
    if (user?.role === "admin") {
      fetchLogs();
    }
  }, [fetchLogs, user]);

  const maskPatientId = (id) => {
    if (!id) return "—";
    if (id.length <= 3) return id + "***";
    return id.substring(0, 3) + "***";
  };

  const ACTION_TYPES = [
    "All", "LOGIN", "VIEW_JOBS", "CLEAR_JOBS", "CREATE_JOB", 
    "CREATE_CATEGORY", "DELETE_CATEGORY", "CREATE_ACTIVATION_CODE", "JOB_COMPLETED", "REGISTER_AGENT"
  ];

  if (user?.role !== "admin") {
    return <div className="page"><h1>Access Denied</h1><p>Admin permissions required.</p></div>;
  }

  return (
    <div className="page">
      <h1>Audit Logs</h1>
      <p className="sub">HIPAA Compliance: Immutable record of all PHI-adjacent activity.</p>

      <div className="card" style={{ marginBottom: "20px", padding: "15px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "10px", alignItems: "end" }}>
          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: "bold", display: "block", marginBottom: "4px" }}>Action Type</label>
            <select 
              value={filters.action} 
              onChange={e => { setPage(0); setFilters({ ...filters, action: e.target.value === "All" ? "" : e.target.value }); }}
              style={{ width: "100%", padding: "8px" }}
            >
              {ACTION_TYPES.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: "bold", display: "block", marginBottom: "4px" }}>Actor (Username/ID)</label>
            <input 
              placeholder="Filter by actor..." 
              value={filters.actor} 
              onChange={e => { setPage(0); setFilters({ ...filters, actor: e.target.value }); }}
              style={{ width: "100%", padding: "8px" }}
            />
          </div>
          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: "bold", display: "block", marginBottom: "4px" }}>Patient ID</label>
            <input 
              placeholder="Search PHI..." 
              value={filters.patient_id} 
              onChange={e => { setPage(0); setFilters({ ...filters, patient_id: e.target.value }); }}
              style={{ width: "100%", padding: "8px" }}
            />
          </div>
          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: "bold", display: "block", marginBottom: "4px" }}>From Date</label>
            <input 
              type="date" 
              value={filters.from_date} 
              onChange={e => { setPage(0); setFilters({ ...filters, from_date: e.target.value }); }}
              style={{ width: "100%", padding: "8px" }}
            />
          </div>
          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: "bold", display: "block", marginBottom: "4px" }}>To Date</label>
            <input
              type="date"
              value={filters.to_date}
              onChange={e => { setPage(0); setFilters({ ...filters, to_date: e.target.value }); }}
              style={{ width: "100%", padding: "8px" }}
            />
          </div>
          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: "bold", display: "block", marginBottom: "4px" }}>&nbsp;</label>
            <button
              className="btn outline sm"
              style={{ width: "100%", padding: "8px" }}
              onClick={() => { setPage(0); setFilters({ actor: "", action: "", patient_id: "", from_date: "", to_date: "" }); }}
            >
              Clear Filters
            </button>
          </div>
        </div>
      </div>

      <div className="card">
        {loading ? (
          <p className="loadingText pulse">Fetching audit records...</p>
        ) : logs.length === 0 ? (
          <p style={{ textAlign: "center", padding: "20px", color: "#888" }}>No audit logs match your filters.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Timestamp (UTC)</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Patient ID</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td style={{ fontSize: "0.8rem", whiteSpace: "nowrap" }}>{log.timestamp}</td>
                  <td>
                    <span style={{ fontWeight: "bold" }}>{log.actor}</span>
                    <br />
                    <small style={{ opacity: 0.6 }}>{log.actor_type}</small>
                  </td>
                  <td>
                    <span className={`badge ${log.status === "SUCCESS" ? "blue" : "red"}`} style={{ fontSize: "0.7rem" }}>
                      {log.action}
                    </span>
                  </td>
                  <td>
                    {log.resource_type ? `${log.resource_type}: ${log.resource_id || "—"}` : "—"}
                  </td>
                  <td>
                    <code style={{ background: "#f0f0f0", padding: "2px 5px", borderRadius: "3px" }}>
                      {maskPatientId(log.patient_id)}
                    </code>
                  </td>
                  <td>
                    <span style={{ color: log.status === "SUCCESS" ? "#10b981" : "#ef4444", fontWeight: "bold", fontSize: "0.8rem" }}>
                      {log.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {total > PAGE_SIZE && (
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: "20px", alignItems: "center" }}>
          <span style={{ fontSize: "0.9rem", color: "#666" }}>Page {page + 1} of {Math.ceil(total / PAGE_SIZE)}</span>
          <div style={{ display: "flex", gap: "10px" }}>
            <button className="btn" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Previous</button>
            <button className="btn" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage(p => p + 1)}>Next</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default AuditLogs;

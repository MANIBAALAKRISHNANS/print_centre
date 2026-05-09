import { useState, useEffect, useRef, useCallback } from "react";
import { useFetch, useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { SkeletonTableRow } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import { API_BASE_URL } from "../config";
import { useWebSocket } from "../hooks/useWebSocket";

function PrintJobs() {
  const [jobs, setJobs] = useState([]);
  const [filter, setFilter] = useState("All");
  const [selectedJob, setSelectedJob] = useState(null);
  const [jobLogs, setJobLogs] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const PAGE_SIZE = 50;
  const searchTimeout = useRef(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [loading, setLoading] = useState(true);
  const toast = useToast();

  // Cache: Map<job_id, { logs, fetchedAt }>
  const logCache = useRef({});
  const CACHE_TTL_MS = 10000; // 10 seconds TTL for active jobs; stable jobs cached forever
  const authFetch = useFetch();
  const { token } = useAuth();

  const loadJobs = useCallback(async (pageNum = 0, currentFilter = filter, search = searchQuery) => {
    try {
      let url = `${API_BASE_URL}/print-jobs?limit=${PAGE_SIZE}&offset=${pageNum * PAGE_SIZE}`;
      
      if (currentFilter !== "All") {
        if (currentFilter === "Retried") {
          url += "&retried=true";
        } else {
          url += `&status=${encodeURIComponent(currentFilter)}`;
        }
      }
      
      if (search) {
        url += `&search=${encodeURIComponent(search)}`;
      }

      const res = await authFetch(url);
      const data = await res.json();
      
      if (Array.isArray(data)) {
        setJobs(data);
      } else {
        setJobs(data.jobs ?? []);
        setTotal(data.total ?? 0);
      }
    } catch (err) {
      toast.error("Failed to load print jobs");
    } finally {
      setLoading(false);
    }
  }, [filter, authFetch]);

  // Reset to page 0 when filter changes
  useEffect(() => {
    setPage(0);
    loadJobs(0, filter, searchQuery);
  }, [filter]); // eslint-disable-line

  // Handle Search Debounce
  useEffect(() => {
    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    
    searchTimeout.current = setTimeout(() => {
      setPage(0);
      loadJobs(0, filter, searchQuery);
    }, 400);

    return () => clearTimeout(searchTimeout.current);
  }, [searchQuery]); // eslint-disable-line

  useEffect(() => {
    if (page > 0) loadJobs(page, filter, searchQuery);
  }, [page]); // eslint-disable-line

  // Safety-net poll — WebSocket handles real-time updates; this catches missed events
  useEffect(() => {
    const interval = setInterval(() => loadJobs(page, filter, searchQuery), 30000);
    return () => clearInterval(interval);
  }, [page, filter, searchQuery]); // eslint-disable-line

  // Real-time: refresh job list instantly on server push
  const handleWsMessage = useCallback((msg) => {
    if (msg.type === "job_update" || msg.type === "dashboard_refresh") {
      loadJobs(page, filter, searchQuery);
    }
  }, [loadJobs, page, filter, searchQuery]);

  useWebSocket(handleWsMessage, !!token);

  const clearJobs = async () => {
    try {
      await authFetch(`${API_BASE_URL}/print-jobs`, { method: "DELETE" });
      await loadJobs(page);
      toast.success("All jobs cleared");
      setShowClearConfirm(false);
    } catch (err) {
      toast.error("Failed to clear jobs");
    }
  };



  const openLogsModal = async (job) => {
    setSelectedJob(job);
    setIsModalOpen(true);

    const cached = logCache.current[job.id];
    const isStableJob = ["Completed", "Failed"].includes(job.status);
    const cacheValid = cached && (isStableJob || Date.now() - cached.fetchedAt < CACHE_TTL_MS);

    if (cacheValid) {
      setJobLogs(cached.logs);
      return;
    }

    setLoadingLogs(true);
    try {
      const res = await authFetch(`${API_BASE_URL}/print-logs/${job.id}`);
      const data = await res.json();
      logCache.current[job.id] = { logs: data, fetchedAt: Date.now() };
      setJobLogs(data);
    } catch (err) {
      setJobLogs([]);
    } finally {
      setLoadingLogs(false);
    }
  };

  const closeLogsModal = () => {
    setIsModalOpen(false);
    setSelectedJob(null);
    setJobLogs([]);
  };

  const statusBadge = (status) => {
    const n = (status || "").toLowerCase();
    if (n === "completed") return "blue";
    if (n === "printing" || n === "agent printing") return "live"; // Added: agent printing
    if (n === "queued" || n === "pending agent") return "warn"; // Added: pending agent
    if (n === "failed" || n === "failed agent") return "offline"; // Added: failed agent
    if (n === "retrying") return "orange"; // Added: retrying status
    return "gray";
  };

  const routeBadge = (type) => {
    if (type === "Primary") return "live";
    if (type === "Failover") return "warn";
    return "offline";
  };

  // Added: additional agent-related filters
  const FILTERS = [
    "All", "Queued", "Printing", "Completed",
    "Failed", "Pending Agent", "Agent Printing", "Failed Agent", "Retried"
  ];

  return (
    <div className="page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
        <div>
          <h1>Print Jobs</h1>
          <p className="sub">Real-time clinical queue — click any row for detailed logs</p>
        </div>
        <div className="badge green pulse" style={{ padding: "8px 12px", borderRadius: "20px", fontWeight: "bold" }}>
          ● LIVE MONITORING
        </div>
      </div>


      <div style={{ marginBottom: "16px" }}>
        <input 
          type="text"
          placeholder="Search by patient ID, printer, or category..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            width: "100%",
            padding: "12px 16px",
            borderRadius: "8px",
            border: "1px solid #ddd",
            fontSize: "1rem",
            outline: "none",
            boxShadow: "inset 0 1px 2px rgba(0,0,0,0.05)"
          }}
        />
      </div>

      {/* Filter Tabs */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "16px" }}>
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: "6px 14px",
              borderRadius: "20px",
              border: filter === f ? "2px solid #4f46e5" : "2px solid #ddd",
              background: filter === f ? "#4f46e5" : "white",
              color: filter === f ? "white" : "#333",
              cursor: "pointer",
              fontWeight: filter === f ? "bold" : "normal",
              fontSize: "0.85rem",
            }}
          >
            {f}
          </button>
        ))}
        <button
          className="btn"
          style={{ marginLeft: "auto" }}
          onClick={() => setShowClearConfirm(true)}
        >
          Clear Jobs
        </button>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Location</th>
              <th>Category</th>
              <th>Printer</th>
              <th>Route</th>
              <th>Status</th>
              <th>Retries</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <SkeletonTableRow cols={8} />
            ) : jobs.length === 0 ? (
              <tr>
                <td colSpan="8">
                  <EmptyState 
                    icon="🖨️"
                    title="No print jobs found"
                    subtitle={filter === "All" ? "Jobs will appear here as they are submitted." : `No jobs found with status "${filter}"`}
                  />
                </td>
              </tr>
            ) : (
              jobs.map((job) => (
                <tr
                  key={job.id}
                  onClick={() => openLogsModal(job)}
                  style={{
                    cursor: "pointer",
                    background: (job.retry_count || 0) > 0 ? "rgba(255, 165, 0, 0.05)" : "inherit",
                  }}
                >
                  <td><strong>JOB{String(job.id).padStart(3, "0")}</strong></td>
                  <td>{job.location}</td>
                  <td>{job.category}</td>
                  <td>{job.printer || "—"}</td>
                  <td>
                    <span className={`badge ${routeBadge(job.type)}`}>
                      {job.type || "None"}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${statusBadge(job.status)}`}>
                      {job.status}
                    </span>
                  </td>
                  <td>
                    {(job.retry_count || 0) > 0 ? (
                      <span style={{
                        color: "orange",
                        fontWeight: "bold",
                        fontSize: "0.95rem",
                      }}>
                        ⚠ {job.retry_count}
                      </span>
                    ) : (
                      <span style={{ color: "#aaa" }}>0</span>
                    )}
                  </td>
                  <td style={{ fontSize: "0.8rem", color: "#666", whiteSpace: "nowrap" }}>
                    {job.time ? (() => {
                      try {
                        let timeStr = String(job.time);
                        if (!timeStr.includes("-") && (timeStr.includes("AM") || timeStr.includes("PM"))) {
                          const todayPrefix = new Date().toISOString().split("T")[0];
                          timeStr = `${todayPrefix} ${timeStr}`;
                        }
                        const d = new Date(timeStr.includes("UTC") ? timeStr : timeStr + " UTC");
                        if (isNaN(d.getTime())) return String(job.time);
                        const today = new Date();
                        const isToday = d.toDateString() === today.toDateString();
                        return isToday
                          ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true })
                          : d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
                      } catch { return String(job.time); }
                    })() : "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      {total > PAGE_SIZE && (
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginTop: "14px",
          fontSize: "0.88rem",
          color: "#555"
        }}>
          <span>
            Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total} jobs
          </span>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              className="btn"
              disabled={page === 0}
              onClick={() => setPage(p => Math.max(p - 1, 0))}
              style={{ opacity: page === 0 ? 0.4 : 1 }}
            >
              ← Previous
            </button>
            <span style={{ lineHeight: "2rem" }}>Page {page + 1} / {Math.ceil(total / PAGE_SIZE)}</span>
            <button
              className="btn"
              disabled={(page + 1) * PAGE_SIZE >= total}
              onClick={() => setPage(p => p + 1)}
              style={{ opacity: (page + 1) * PAGE_SIZE >= total ? 0.4 : 1 }}
            >
              Next →
            </button>
          </div>
        </div>
      )}
      {isModalOpen && (
        <div
          className="modalOverlay"
          onClick={closeLogsModal}
        >
          <div
            className="modalBox"
            onClick={(e) => e.stopPropagation()}
            style={{ width: "640px", maxWidth: "92%" }}
          >
            <div className="modalHead">
              <div>
                <h3>JOB{String(selectedJob?.id).padStart(3, "0")} — Logs</h3>
                <p style={{ fontSize: "0.82rem", color: "#888", marginTop: "3px" }}>
                  {selectedJob?.location} · {selectedJob?.category} · {selectedJob?.printer}
                  {(selectedJob?.retry_count || 0) > 0 && (
                    <span style={{ marginLeft: "8px", color: "orange" }}>
                      ⚠ {selectedJob.retry_count} {selectedJob.retry_count === 1 ? "retry" : "retries"}
                    </span>
                  )}
                </p>
              </div>
              <button onClick={closeLogsModal}>✕</button>
            </div>

            <div className="modalBody" style={{ maxHeight: "460px", overflowY: "auto" }}>
              {loadingLogs ? (
                <p style={{ textAlign: "center", color: "#888", padding: "24px 0" }}>
                  Loading logs…
                </p>
              ) : jobLogs.length === 0 ? (
                <p style={{ textAlign: "center", color: "#666", padding: "20px 0" }}>
                  No logs available for this job.
                </p>
              ) : (
                <>
                  {/* Retry Timeline — shown only if retries exist */}
                  {(selectedJob?.retry_count || 0) > 0 && (() => {
                    const failLogs = jobLogs.filter(l => l.status === "Failed");
                    return (
                      <div style={{
                        background: "rgba(255,165,0,0.06)",
                        border: "1px solid rgba(255,165,0,0.25)",
                        borderRadius: "8px",
                        padding: "12px 16px",
                        marginBottom: "16px",
                        fontSize: "0.84rem",
                      }}>
                        <strong style={{ color: "darkorange" }}>⚠ Retry Timeline</strong>
                        <div style={{ marginTop: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
                          {[...failLogs].reverse().map((log, i) => (
                            <div key={log.id} style={{ display: "flex", gap: "10px", alignItems: "flex-start" }}>
                              <span style={{
                                background: "orange",
                                color: "white",
                                borderRadius: "50%",
                                width: "20px",
                                height: "20px",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                fontSize: "0.7rem",
                                flexShrink: 0,
                                fontWeight: "bold",
                              }}>{i + 1}</span>
                              <div>
                                <div style={{ color: "#333", fontWeight: "500" }}>{log.printer}</div>
                                <div style={{ color: "#e53e3e", fontSize: "0.78rem" }}>{log.message}</div>
                                <div style={{ color: "#aaa", fontSize: "0.72rem" }}>{log.time}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })()}

                  {/* Full Log Table */}
                  <table style={{ width: "100%", fontSize: "0.88rem" }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: "left", paddingBottom: "10px", width: "80px" }}>Time</th>
                        <th style={{ textAlign: "left", paddingBottom: "10px" }}>Printer</th>
                        <th style={{ textAlign: "left", paddingBottom: "10px", width: "90px" }}>Status</th>
                        <th style={{ textAlign: "left", paddingBottom: "10px" }}>Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobLogs.map((log) => (
                        <tr key={log.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                          <td style={{ padding: "8px 0", color: "#888", fontSize: "0.78rem" }}>
                            {log.time?.split(" ")[1] || log.time}
                          </td>
                          <td style={{ padding: "8px 0" }}>{log.printer}</td>
                          <td style={{ padding: "8px 0" }}>
                            <span
                              className={`badge ${log.status === "Completed" ? "blue" : log.status === "Failed" ? "offline" : "warn"}`}
                              style={{ fontSize: "0.72rem", padding: "2px 7px" }}
                            >
                              {log.status}
                            </span>
                          </td>
                          <td style={{
                            padding: "8px 0",
                            color: log.status === "Failed" ? "#e53e3e" : "#333",
                            fontWeight: log.status === "Failed" ? "500" : "normal",
                          }}>
                            {log.message}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>
          </div>
        </div>
      )}
      {showClearConfirm && (
        <div className="modalOverlay">
          <div className="modalBox" style={{ textAlign: "center", padding: "30px" }}>
            <h3 style={{ marginBottom: "15px" }}>Clear All Jobs?</h3>
            <p style={{ color: "#666", marginBottom: "25px" }}>
              Are you sure you want to delete all print job history? This cannot be undone.
            </p>
            <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
              <button 
                className="btn" 
                style={{ background: "#ef4444" }}
                onClick={clearJobs}
              >Clear All</button>
              <button 
                className="btn" 
                style={{ background: "#6b7280" }}
                onClick={() => setShowClearConfirm(false)}
              >Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PrintJobs;

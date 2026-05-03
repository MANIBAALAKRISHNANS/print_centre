import { useState, useEffect, useRef } from "react";

function PrintJobs() {
  const [jobs, setJobs] = useState([]);
  const [filter, setFilter] = useState("All");
  const [selectedJob, setSelectedJob] = useState(null);
  const [jobLogs, setJobLogs] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  // Cache: Map<job_id, { logs, fetchedAt }>
  const logCache = useRef({});
  const CACHE_TTL_MS = 10000; // 10 seconds TTL for active jobs; stable jobs cached forever

  const loadJobs = async (pageNum = 0, currentFilter = filter) => {
    try {
      let url = `http://127.0.0.1:8000/print-jobs?limit=${PAGE_SIZE}&offset=${pageNum * PAGE_SIZE}`;
      
      if (currentFilter !== "All") {
        if (currentFilter === "Retried") {
          url += "&retried=true";
        } else {
          url += `&status=${currentFilter}`;
        }
      }

      const res = await fetch(url);
      const data = await res.json();
      
      if (Array.isArray(data)) {
        setJobs(data);
      } else {
        setJobs(data.jobs ?? []);
        setTotal(data.total ?? 0);
      }
    } catch (err) {
      console.log("PrintJobs API error", err);
    }
  };

  // Reset to page 0 when filter changes
  useEffect(() => {
    setPage(0);
    loadJobs(0, filter);
  }, [filter]); // eslint-disable-line

  useEffect(() => {
    if (page > 0) loadJobs(page, filter);
  }, [page]); // eslint-disable-line

  useEffect(() => {
    const interval = setInterval(() => loadJobs(page, filter), 3000);
    return () => clearInterval(interval);
  }, [page, filter]); // eslint-disable-line

  const clearJobs = async () => {
    if (!window.confirm("Clear all print jobs?")) return;
    try {
      await fetch("http://127.0.0.1:8000/print-jobs", { method: "DELETE" });
      await loadJobs(page);
    } catch (err) {
      console.log("Clear jobs error", err);
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
      const res = await fetch(`http://127.0.0.1:8000/print-logs/${job.id}`);
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
    const n = status?.toLowerCase();
    if (n === "printing") return "live";
    if (n === "completed") return "blue";
    if (n === "queued") return "warn";
    if (n === "failed") return "offline";
    return "offline";
  };

  const routeBadge = (type) => {
    if (type === "Primary") return "live";
    if (type === "Failover") return "warn";
    return "offline";
  };

  const FILTERS = ["All", "Queued", "Printing", "Completed", "Failed", "Retried"];

  return (
    <div className="page">
      <h1>Print Jobs</h1>
      <p className="sub">Live queue — click any row to view detailed logs</p>

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
          onClick={clearJobs}
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
            {jobs.length === 0 ? (
              <tr>
                <td colSpan="8" style={{ textAlign: "center", color: "#888" }}>
                  No jobs found for "{filter}"
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
                    {job.time?.replace(" UTC", "") || "—"}
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
                    const retryLogs = jobLogs.filter(l => l.status === "Retrying" || l.message?.toLowerCase().includes("retry"));
                    const failLogs  = jobLogs.filter(l => l.status === "Failed");
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
    </div>
  );
}

export default PrintJobs;

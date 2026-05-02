import { useState, useEffect } from "react";

/* eslint-disable react-hooks/set-state-in-effect */

function PrintJobs() {
  const [jobs, setJobs] = useState([]);

  const loadJobs = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/print-jobs");
      const data = await res.json();
      setJobs(data);
    } catch (err) {
      console.log("PrintJobs API error", err);
    }
  };

  const clearJobs = async () => {
    if (!window.confirm("Clear all print jobs?")) return;

    try {
      await fetch("http://127.0.0.1:8000/print-jobs", {
        method: "DELETE",
      });

      await loadJobs();
    } catch (err) {
      console.log("Clear jobs error", err);
    }
  };

  useEffect(() => {
    loadJobs();
    const interval = setInterval(loadJobs, 3000);

    return () => clearInterval(interval);
  }, []);

  const statusBadge = (status) => {
    const normalized = status?.toLowerCase();

    if (normalized === "printing") return "live";
    if (normalized === "completed") return "blue";
    if (normalized === "queued") return "warn";
    if (normalized === "failed") return "offline";
    return "offline";
  };

  const routeBadge = (type) => {
    if (type === "Primary") return "live";
    if (type === "Failover") return "warn";
    return "offline";
  };

  return (
    <div className="page">
      <h1>Print Jobs</h1>
      <p className="sub">Live queue from HIS software</p>

      <button
        className="btn"
        style={{ marginBottom: "15px" }}
        onClick={clearJobs}
      >
        Clear Jobs
      </button>

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
              <th>Time</th>
            </tr>
          </thead>

          <tbody>
            {jobs.length === 0 ? (
              <tr>
                <td colSpan="7" style={{ textAlign: "center" }}>
                  No print jobs found
                </td>
              </tr>
            ) : (
              jobs.map((job) => (
                <tr key={job.id}>
                  <td>JOB{String(job.id).padStart(3, "0")}</td>
                  <td>{job.location}</td>
                  <td>{job.category}</td>
                  <td>{job.printer || "None"}</td>
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
                  <td>{job.time}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default PrintJobs;

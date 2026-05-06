import { useState, useEffect, useContext, useCallback } from "react";
import { AppData } from "../context/AppData";
import { API_BASE_URL } from "../config";

function Dashboard() {
  const { printers, loading: appLoading, errors: appErrors } = useContext(AppData);

  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/dashboard`);
      if (!res.ok) throw new Error("Dashboard failed");
      const data = await res.json();
      setStats(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStats();
    const interval = setInterval(loadStats, 15000); // 15s polling
    return () => clearInterval(interval);
  }, [loadStats]);

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

  const SkeletonCard = () => (
    <div className="statCard gray pulse" style={{ height: "100px", background: "#f0f0f0" }}></div>
  );

  return (
    <div className="page">
      <h1>Print Center Dashboard</h1>
      <p className="sub">Live printer health and job analytics</p>

      {error && <div className="errorBanner">Unable to load dashboard stats: {error}</div>}

      <h2 style={{ margin: "20px 0 10px", fontSize: "1rem", opacity: 0.7 }}>PRINTER HEALTH</h2>
      <div className="stats">
        {loading && !stats ? (
          <>
            <SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard />
          </>
        ) : (
          <>
            <div className="statCard blue"><h3>Total Printers</h3><h2>{stats?.total ?? 0}</h2></div>
            <div className="statCard green"><h3>Live</h3><h2>{stats?.live ?? 0}</h2></div>
            <div className="statCard red"><h3>Offline</h3><h2>{stats?.offline ?? 0}</h2></div>
          </>
        )}
      </div>

      <h2 style={{ margin: "28px 0 10px", fontSize: "1rem", opacity: 0.7 }}>JOB ANALYTICS</h2>
      <div className="stats">
        {loading && !stats ? (
          <>
            <SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard />
          </>
        ) : (
          <>
            <div className="statCard blue"><h3>Total Jobs</h3><h2>{stats?.jobs?.total ?? 0}</h2></div>
            <div className="statCard green"><h3>Completed</h3><h2>{stats?.jobs?.completed ?? 0}</h2></div>
            <div className="statCard red"><h3>Failed</h3><h2>{stats?.jobs?.failed ?? 0}</h2></div>
            <div className="statCard orange"><h3>Had Retries</h3><h2>{stats?.jobs?.retried ?? 0}</h2></div>
          </>
        )}
      </div>

      <div className="card" style={{ marginTop: "28px" }}>
        <h2 style={{ marginBottom: "15px" }}>Printer Live Status</h2>
        {appLoading.printers ? (
          <p className="loadingText pulse">Loading printers...</p>
        ) : appErrors.printers ? (
          <p className="errorText">{appErrors.printers}</p>
        ) : (
          <table>
            <thead>
              <tr><th>Printer</th><th>Category</th><th>Language</th><th>Status</th></tr>
            </thead>
            <tbody>
              {printers.map((item, index) => {
                const normalizedStatus = (item.status || "").toLowerCase();
                let displayStatus = normalizedStatus;

                if (item.connection_type === "USB" && isStale(item.last_updated)) {
                  displayStatus = "offline";
                }

                console.log({
                  name: item.name,
                  backendStatus: item.status,
                  displayStatus,
                  last_updated: item.last_updated
                });

                return (
                  <tr key={index}>
                    <td>{item.name}</td>
                    <td>{item.category}</td>
                    <td>{item.language}</td>
                    <td>
                      <span className={`badge ${getStatusColor(displayStatus)}`}>
                        {displayStatus.charAt(0).toUpperCase() + displayStatus.slice(1)}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default Dashboard;

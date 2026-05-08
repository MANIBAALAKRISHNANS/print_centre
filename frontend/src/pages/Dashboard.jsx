import { useState, useEffect, useContext, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { AppData } from "../context/AppData";
import { useFetch } from "../context/AuthContext";
import { SkeletonLine, SkeletonTable } from "../components/Skeleton";
import { API_BASE_URL } from "../config";

function Dashboard() {
  const navigate = useNavigate();
  const { printers, loading: appLoading, errors: appErrors } = useContext(AppData);

  const [stats, setStats] = useState(null);
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [health, setHealth] = useState({ warnings: [] });

  const authFetch = useFetch();

  const loadStats = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE_URL}/dashboard`);
      if (!res.ok) throw new Error("Dashboard failed");
      const data = await res.json();
      setStats(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  const loadHealth = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE_URL}/admin/job-health`);
      if (res.ok) {
        const data = await res.json();
        setHealth(data);
      }
    } catch (e) {
      /* silent */
    }
  }, [authFetch]);

  useEffect(() => {
    loadStats();
    loadHealth();
    const interval = setInterval(loadStats, 15000);
    const healthInterval = setInterval(loadHealth, 60000);
    return () => {
      clearInterval(interval);
      clearInterval(healthInterval);
    };
  }, [loadStats, loadHealth]);

  useEffect(() => {
    const loadAgents = async () => {
      try {
        const res = await authFetch(`${API_BASE_URL}/agents`);
        setAgents(await res.json());
      } catch (e) {
        /* silent */
      }
    };
    loadAgents();
    const t = setInterval(loadAgents, 15000);
    return () => clearInterval(t);
  }, [authFetch]);

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

  const isAgentStale = (last_seen) => {
    if (!last_seen) return true;
    const d = new Date(last_seen.replace(" UTC", "Z").replace(" ", "T"));
    return Date.now() - d.getTime() > 45000;
  };

  const StatSkeleton = () => (
    <div className="statCard gray" style={{ position: "relative", overflow: "hidden" }}>
        <SkeletonLine width="60%" height="14px" style={{ marginBottom: "12px" }} />
        <SkeletonLine width="40%" height="28px" />
    </div>
  );

  return (
    <div className="page">
      <h1>Print Center Dashboard</h1>
      <p className="sub">Live printer health and job analytics</p>

      {error && <div className="errorBanner">Unable to load dashboard stats: {error}</div>}

      {health.warnings?.map((w, idx) => (
        <div 
          key={idx} 
          className="warningBanner pulse" 
          style={{ 
            cursor: "pointer", 
            marginBottom: "15px", 
            background: "#fffbeb", 
            border: "1px solid #fde68a", 
            color: "#92400e",
            padding: "12px",
            borderRadius: "8px",
            fontWeight: "bold",
            display: "flex",
            alignItems: "center",
            gap: "10px"
          }} 
          onClick={() => navigate("/printjobs")}
        >
          <span>⚠</span> {w}
        </div>
      ))}

      <h2 style={{ margin: "20px 0 10px", fontSize: "1rem", opacity: 0.7 }}>PRINTER HEALTH</h2>
      <div className="stats">
        {loading && !stats ? (
          <>
            <StatSkeleton /><StatSkeleton /><StatSkeleton />
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
            <StatSkeleton /><StatSkeleton /><StatSkeleton /><StatSkeleton />
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

      <h2 style={{ margin: "28px 0 10px", fontSize: "1rem", opacity: 0.7 }}>AGENT STATUS</h2>
      <div className="stats">
        {loading && agents.length === 0 ? (
          <>
            <StatSkeleton /><StatSkeleton /><StatSkeleton />
          </>
        ) : (
          <>
            <div className="statCard blue">
              <h3>Total Agents</h3>
              <h2>{agents.length}</h2>
            </div>
            <div className="statCard green">
              <h3>Online</h3>
              <h2>{agents.filter((a) => !isAgentStale(a.last_seen)).length}</h2>
            </div>
            <div className="statCard red">
              <h3>Offline</h3>
              <h2>{agents.filter((a) => isAgentStale(a.last_seen)).length}</h2>
            </div>
          </>
        )}
      </div>

      <div className="card" style={{ marginTop: "28px" }}>
        <h2 style={{ marginBottom: "15px" }}>Printer Live Status</h2>
        {appLoading.printers ? (
          <SkeletonTable rows={5} cols={4} />
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

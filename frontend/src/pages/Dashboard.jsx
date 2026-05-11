import { useState, useEffect, useContext, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { AppData } from "../context/AppData";
import { useFetch, useAuth } from "../context/AuthContext";
import { SkeletonLine, SkeletonTable } from "../components/Skeleton";
import { API_BASE_URL } from "../config";
import { useWebSocket } from "../hooks/useWebSocket";

function Dashboard() {
  const navigate = useNavigate();
  const { printers, agents, loading: appLoading, errors: appErrors, loadAgents } = useContext(AppData);

  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [health, setHealth] = useState({ warnings: [] });
  const [now, setNow] = useState(Date.now());

  const authFetch = useFetch();
  const { token } = useAuth();

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
    loadAgents();
    const interval       = setInterval(loadStats,   30000);
    const healthInterval = setInterval(loadHealth,  30000);
    const agentInterval  = setInterval(loadAgents,  15000);
    const tickInterval   = setInterval(() => setNow(Date.now()), 5000);
    return () => {
      clearInterval(interval);
      clearInterval(healthInterval);
      clearInterval(agentInterval);
      clearInterval(tickInterval);
    };
  }, [loadStats, loadHealth, loadAgents]);

  // Real-time: refresh dashboard instantly when server pushes events
  const handleWsMessage = useCallback((msg) => {
    if (["dashboard_refresh", "printer_update", "agent_update", "job_update"].includes(msg.type)) {
      loadStats();
    }
    if (["agent_update", "dashboard_refresh"].includes(msg.type)) {
      loadAgents();
    }
  }, [loadStats, loadAgents]);

  useWebSocket(handleWsMessage, !!token);

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
    return now - d.getTime() > 45000;
  };

  const StatSkeleton = () => (
    <div className="clinical-card" style={{ padding: "20px", position: "relative", overflow: "hidden" }}>
        <SkeletonLine width="60%" height="14px" style={{ marginBottom: "12px" }} />
        <SkeletonLine width="40%" height="28px" />
    </div>
  );

  return (
    <div className="page" style={{ padding: "40px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "32px" }}>
        <div>
          <h1 className="clinical-title" style={{ margin: 0, fontSize: "2rem" }}>Hospital Print Overview</h1>
          <p style={{ color: "var(--text-muted)", marginTop: "4px", fontSize: "0.95rem" }}>
            Real-time health monitoring for Savetha Hospital Network
          </p>
        </div>
        <div className="live-monitor-badge">
          <div className="live-dot"></div>
          LIVE MONITORING
        </div>
      </div>

      {error && <div className="errorBanner">Unable to load dashboard stats: {error}</div>}

      {health.warnings?.map((w, idx) => (
        <div 
          key={idx} 
          className="warningBanner pulse" 
          style={{ 
            cursor: "pointer", 
            marginBottom: "20px", 
            background: "rgba(245, 158, 11, 0.1)", 
            border: "1px solid rgba(245, 158, 11, 0.2)", 
            color: "#b45309",
            padding: "16px",
            borderRadius: "12px",
            fontWeight: "600",
            display: "flex",
            alignItems: "center",
            gap: "12px",
            boxShadow: "var(--shadow-sm)"
          }} 
          onClick={() => navigate("/printjobs")}
        >
          <span style={{ fontSize: "1.2rem" }}>⚠️</span> {w}
        </div>
      ))}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "24px", marginBottom: "40px" }}>
        {loading && !stats ? (
          <><StatSkeleton /><StatSkeleton /><StatSkeleton /><StatSkeleton /></>
        ) : (
          <>
            <div className="clinical-card" style={{ padding: "24px" }}>
              <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", marginBottom: "8px" }}>Network Printers</p>
              <h2 style={{ margin: 0, fontSize: "2rem", fontWeight: 800 }}>{stats?.total ?? 0}</h2>
              <div style={{ display: "flex", gap: "12px", marginTop: "12px" }}>
                <span style={{ fontSize: "0.7rem", color: "var(--success)", fontWeight: 700 }}>● {stats?.live ?? 0} Online</span>
                <span style={{ fontSize: "0.7rem", color: "var(--danger)", fontWeight: 700 }}>● {stats?.offline ?? 0} Offline</span>
              </div>
            </div>

            <div className="clinical-card" style={{ padding: "24px" }}>
              <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", marginBottom: "8px" }}>Active Agents</p>
              <h2 style={{ margin: 0, fontSize: "2rem", fontWeight: 800 }}>{agents.length}</h2>
              <div style={{ display: "flex", gap: "12px", marginTop: "12px" }}>
                <span style={{ fontSize: "0.7rem", color: "var(--success)", fontWeight: 700 }}>● {agents.filter((a) => !isAgentStale(a.last_seen)).length} Connected</span>
              </div>
            </div>

            <div className="clinical-card" style={{ padding: "24px" }}>
              <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", marginBottom: "8px" }}>Today's Jobs</p>
              <h2 style={{ margin: 0, fontSize: "2rem", fontWeight: 800 }}>{stats?.jobs?.total ?? 0}</h2>
              <div style={{ display: "flex", gap: "12px", marginTop: "12px" }}>
                <span style={{ fontSize: "0.7rem", color: "var(--success)", fontWeight: 700 }}>{stats?.jobs?.completed ?? 0} Successful</span>
              </div>
            </div>

            <div className="clinical-card" style={{ padding: "24px", background: stats?.jobs?.failed > 0 ? "rgba(239, 68, 68, 0.05)" : "white" }}>
              <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", marginBottom: "8px" }}>System Alerts</p>
              <h2 style={{ margin: 0, fontSize: "2rem", fontWeight: 800, color: stats?.jobs?.failed > 0 ? "var(--danger)" : "inherit" }}>{stats?.jobs?.failed ?? 0}</h2>
              <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "12px" }}>{stats?.jobs?.retried ?? 0} jobs recovered automatically</p>
            </div>
          </>
        )}
      </div>

      <div className="clinical-card" style={{ padding: "0", overflow: "hidden" }}>
        <div style={{ padding: "24px", borderBottom: "1px solid rgba(0,0,0,0.05)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0, fontWeight: 700 }}>Real-time Hardware Status</h3>
          <button className="btn outline sm" onClick={() => navigate("/printers")}>View All Hardware</button>
        </div>
        
        {appLoading.printers ? (
          <div style={{ padding: "24px" }}><SkeletonTable rows={5} cols={4} /></div>
        ) : appErrors.printers ? (
          <p className="errorText" style={{ padding: "24px" }}>{appErrors.printers}</p>
        ) : (
          <table className="clinical-table">
            <thead>
              <tr><th>Hardware Name</th><th>Category</th><th>Protocol</th><th>Clinical Status</th></tr>
            </thead>
            <tbody>
              {printers.slice(0, 10).map((item, index) => {
                const normalizedStatus = (item.status || "").toLowerCase();
                let displayStatus = normalizedStatus;

                if (item.connection_type === "USB" && isStale(item.last_updated)) {
                  displayStatus = "offline";
                }

                return (
                  <tr key={index} style={{ cursor: "pointer" }} onClick={() => navigate("/printers")}>
                    <td style={{ fontWeight: 600 }}>{item.name}</td>
                    <td>{item.category}</td>
                    <td style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{item.language}</td>
                    <td>
                      <span className={`badge ${getStatusColor(displayStatus)}`}>
                        {displayStatus.toUpperCase()}
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

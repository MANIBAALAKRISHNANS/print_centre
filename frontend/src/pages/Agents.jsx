import { useState, useEffect, useContext } from "react";
import { useFetch, useAuth } from "../context/AuthContext";
import { AppData } from "../context/AppData";
import { useToast } from "../context/ToastContext";
import { SkeletonTable } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../config";
import { clearCache } from "../utils/cache";

function Agents() {
  const { agents, setAgents, loading, loadAgents } = useContext(AppData);
  const { user } = useAuth();
  const [deletingId, setDeletingId] = useState(null);
  const authFetch = useFetch();
  const toast = useToast();
  const navigate = useNavigate();
  const isAdmin = user?.role === "admin";

  // Refresh agents every 15s for live Online/Offline status
  useEffect(() => {
    loadAgents();
    const interval = setInterval(loadAgents, 15000);
    return () => clearInterval(interval);
  }, [loadAgents]);

  const deleteAgent = async (agentId) => {
    try {
      const res = await authFetch(`${API_BASE_URL}/agents/${agentId}`, { method: "DELETE" });
      if (res.ok) {
        setDeletingId(null);
        // Remove immediately from local state so UI updates without waiting for cache TTL
        setAgents(prev => prev.filter(a => a.agent_id !== agentId));
        clearCache("agents");
        toast.success("Agent removed");
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Failed to delete agent");
      }
    } catch {
      toast.error("Failed to delete agent");
    }
  };

  const parseAgentDate = (str) => {
    if (!str) return null;
    const clean = str.replace(" UTC", "Z").replace(" ", "T");
    const d = new Date(clean);
    return isNaN(d.getTime()) ? null : d;
  };

  const isStale = (last_seen) => {
    const d = parseAgentDate(last_seen);
    if (!d) return true;
    return Date.now() - d.getTime() > 45000;
  };

  const formatLastSeen = (last_seen) => {
    const d = parseAgentDate(last_seen);
    if (!d) return "Never";
    const diffMs = Date.now() - d.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div className="page">
      <h1>Agents</h1>
      <p className="sub">
        Monitor connected workstations running the local print agent
      </p>

      <br />

      <div className="card">
        {loading.agents && agents.length === 0 ? (
          <SkeletonTable rows={4} cols={5} />
        ) : agents.length === 0 ? (
          <EmptyState
            icon="🖥️"
            title="No agents registered yet"
            subtitle="Install the PrintHub agent on each workstation with a USB printer."
            action={() => navigate("/admin/activation-codes")}
            actionLabel="Generate Activation Code"
          />
        ) : (
          <table>
            <thead>
              <tr>
                <th>Agent ID</th>
                <th>Hostname</th>
                <th>Location ID</th>
                <th>Status</th>
                <th>Last Seen</th>
                {isAdmin && <th>Action</th>}
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => {
                const stale = isStale(agent.last_seen);
                const displayStatus = stale ? "Offline" : agent.status;
                const statusClass = displayStatus === "Online" ? "green" : "red";

                return (
                  <tr key={agent.agent_id}>
                    <td><code>{agent.agent_id}</code></td>
                    <td>{agent.hostname || "—"}</td>
                    <td>
                      <code style={{ fontSize: "0.75rem", opacity: 0.7 }}>
                        {agent.location_id || "None"}
                      </code>
                    </td>
                    <td>
                      <span className={`badge ${statusClass}`}>
                        {displayStatus}
                      </span>
                    </td>
                    <td style={{ fontSize: "0.85rem", color: "#666" }}>
                      {formatLastSeen(agent.last_seen)}
                    </td>
                    {isAdmin && (
                      <td>
                        {deletingId === agent.agent_id ? (
                          <div style={{ display: "flex", gap: "4px" }}>
                            <button
                              className="btn"
                              style={{ background: "#ef4444", padding: "4px 10px", fontSize: "0.7rem" }}
                              onClick={() => deleteAgent(agent.agent_id)}
                            >
                              Confirm
                            </button>
                            <button
                              className="btn"
                              style={{ background: "#6b7280", padding: "4px 10px", fontSize: "0.7rem" }}
                              onClick={() => setDeletingId(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            className="btn outline sm"
                            style={{ padding: "4px 10px", fontSize: "0.7rem", color: "#ef4444", borderColor: "#ef4444" }}
                            onClick={() => setDeletingId(agent.agent_id)}
                          >
                            Delete
                          </button>
                        )}
                      </td>
                    )}
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

export default Agents;

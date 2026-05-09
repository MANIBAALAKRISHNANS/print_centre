import { useState, useEffect, useCallback } from "react";
import { useFetch } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { SkeletonTable } from "../components/Skeleton";
import EmptyState from "../components/EmptyState";
import { useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../config";

function Agents() {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const authFetch = useFetch();
  const toast = useToast();
  const navigate = useNavigate();

  const fetchAgents = useCallback(async () => {
    try {
      const res = await authFetch(`${API_BASE_URL}/agents`);
      if (!res.ok) throw new Error("Failed to fetch agents");
      const data = await res.json();
      setAgents(data);
    } catch (err) {
      toast.error("Failed to fetch agents");
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchAgents();
    const interval = setInterval(fetchAgents, 15000); // 15s refresh
    return () => clearInterval(interval);
  }, [fetchAgents]);

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
        {loading && agents.length === 0 ? (
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
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => {
                const stale = isStale(agent.last_seen);
                const displayStatus = stale ? "Offline" : agent.status;
                const statusClass = displayStatus === "Online" ? "green" : "red";

                return (
                  <tr key={agent.id}>
                    <td>
                      <code>{agent.agent_id}</code>
                    </td>
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

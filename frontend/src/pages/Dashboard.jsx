import { useState, useEffect, useContext } from "react";
import { AppData } from "../context/AppData";

function Dashboard() {
  const { printers, setPrinters } = useContext(AppData);

  const [stats, setStats] = useState({
    total: 0,
    live: 0,
    offline: 0,
    maintenance: 0,
    jobs: { total: 0, completed: 0, failed: 0, retried: 0 },
    printer_stats: [],
  });

  useEffect(() => {
    const loadData = async () => {
      fetch("http://127.0.0.1:8000/dashboard")
        .then((res) => res.json())
        .then((data) => setStats(data))
        .catch((err) => console.log("Dashboard API error", err));

      fetch("http://127.0.0.1:8000/printers")
        .then((res) => res.json())
        .then((data) => setPrinters(data))
        .catch((err) => console.log("Printers API error", err));
    };

    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [setPrinters]);

  const badge = (status) => {
    if (status === "Live") return "live";
    if (status === "Maintenance") return "warn";
    return "offline";
  };

  return (
    <div className="page">
      <h1>Print Center Dashboard</h1>
      <p className="sub">Live printer health and job analytics</p>

      {/* Printer Health Cards */}
      <h2 style={{ margin: "20px 0 10px", fontSize: "1rem", opacity: 0.7 }}>PRINTER HEALTH</h2>
      <div className="stats">
        <div className="statCard blue">
          <h3>Total Printers</h3>
          <h2>{stats.total}</h2>
        </div>
        <div className="statCard green">
          <h3>Live</h3>
          <h2>{stats.live}</h2>
        </div>
        <div className="statCard red">
          <h3>Offline</h3>
          <h2>{stats.offline}</h2>
        </div>
        <div className="statCard orange">
          <h3>Maintenance</h3>
          <h2>{stats.maintenance}</h2>
        </div>
      </div>

      {/* Job Stats Cards */}
      <h2 style={{ margin: "28px 0 10px", fontSize: "1rem", opacity: 0.7 }}>JOB ANALYTICS</h2>
      <div className="stats">
        <div className="statCard blue">
          <h3>Total Jobs</h3>
          <h2>{stats.jobs?.total ?? 0}</h2>
        </div>
        <div className="statCard green">
          <h3>Completed</h3>
          <h2>{stats.jobs?.completed ?? 0}</h2>
        </div>
        <div className="statCard red">
          <h3>Failed</h3>
          <h2>{stats.jobs?.failed ?? 0}</h2>
        </div>
        <div className="statCard orange">
          <h3>Had Retries</h3>
          <h2>{stats.jobs?.retried ?? 0}</h2>
        </div>
      </div>

      {/* Printer Live Status Table */}
      <div className="card" style={{ marginTop: "28px" }}>
        <h2 style={{ marginBottom: "15px" }}>Printer Live Status</h2>
        <table>
          <thead>
            <tr>
              <th>Printer</th>
              <th>Category</th>
              <th>Language</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {printers.map((item, index) => (
              <tr key={index}>
                <td>{item.name}</td>
                <td>{item.category}</td>
                <td>{item.language}</td>
                <td>
                  <span className={`badge ${badge(item.status)}`}>
                    {item.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Printer-Level Analytics */}
      {stats.printer_stats && stats.printer_stats.length > 0 && (
        <div className="card" style={{ marginTop: "28px" }}>
          <h2 style={{ marginBottom: "15px" }}>Printer Job Analytics</h2>
          <table>
            <thead>
              <tr>
                <th>Printer</th>
                <th>Total Jobs</th>
                <th>Completed</th>
                <th>Failed</th>
                <th>Had Retries</th>
                <th>Success Rate</th>
              </tr>
            </thead>
            <tbody>
              {stats.printer_stats.map((p, i) => {
                const rate = p.success_rate ?? 0;
                return (
                  <tr key={i}>
                    <td><strong>{p.printer}</strong></td>
                    <td>{p.job_count}</td>
                    <td style={{ color: "green" }}>{p.completed}</td>
                    <td style={{ color: p.failed > 0 ? "red" : "inherit" }}>{p.failed}</td>
                    <td style={{ color: p.retried > 0 ? "orange" : "inherit" }}>{p.retried}</td>
                    <td>
                      <span className={`badge ${rate >= 80 ? "live" : rate >= 50 ? "warn" : "offline"}`}>
                        {rate}%
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default Dashboard;

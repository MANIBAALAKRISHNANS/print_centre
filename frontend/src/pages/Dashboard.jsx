import { useState, useEffect, useContext } from "react";
import { AppData } from "../context/AppData";

function Dashboard() {
  const { printers, setPrinters } = useContext(AppData);

  const [stats, setStats] = useState({
    total: 0,
    live: 0,
    offline: 0,
    maintenance: 0,
  });
  const [jobs, setJobs] = useState([]);

  /* load dashboard stats + printers from backend */
 useEffect(() => {
  const loadData = async () => {
    try {
      await fetch("http://127.0.0.1:8000/check-printers");
    } catch (err) {
      console.log("Printer status check error", err);
    }

    fetch("http://127.0.0.1:8000/dashboard")
      .then((res) => res.json())
      .then((data) => setStats(data))
      .catch((err) => console.log("Dashboard API error", err));

    fetch("http://127.0.0.1:8000/printers")
      .then((res) => res.json())
      .then((data) => setPrinters(data))
      .catch((err) => console.log("Printers API error", err));

    fetch("http://127.0.0.1:8000/print-jobs")
      .then((res) => res.json())
      .then((data) => setJobs(data))
      .catch((err) => console.log("Jobs API error", err));
  };

  // initial load
  loadData();

  // auto refresh every 5 sec
  const interval = setInterval(loadData, 3000);

  return () => clearInterval(interval);
}, [setPrinters]);

  const badge = (status) => {
    if (status === "Live") return "live";
    if (status === "Maintenance") return "warn";
    return "offline";
  };

  const getLocation = (category) => {
    if (category === "A4") return "Dental Clinic";
    return "Laboratory";
  };
  const totalJobs = jobs.length;
  const printing = jobs.filter(j => j.status === "Printing").length;
  const failovers = jobs.filter(j => j.type === "Failover").length;
  const errors = jobs.filter(j => j.status === "Failed").length;

  return (
    <div className="page">

      <h1>Print Center Dashboard</h1>

      <p className="sub">
        Live printer health and status
      </p>

      {/* cards from backend */}
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
      {/* 🔥 JOB CARDS */}
    <div className="stats" style={{ marginTop: "20px" }}>

       <div className="statCard blue">
         <h3>Total Jobs</h3>
         <h2>{totalJobs}</h2>
       </div>

       <div className="statCard green">
          <h3>Printing</h3>
          <h2>{printing}</h2>
      </div>

       <div className="statCard orange">
          <h3>Failovers</h3>
          <h2>{failovers}</h2>
       </div>

      <div className="statCard red">
         <h3>Errors</h3>
         <h2>{errors}</h2>
      </div>

    </div>

      {/* table */}
      <div className="card">

        <h2 style={{ marginBottom: "15px" }}>
          Printer Live Status
        </h2>

        <table>
          <thead>
            <tr>
              <th>Printer</th>
              <th>Location</th>
              <th>Status</th>
            </tr>
          </thead>

          <tbody>
            {printers.map((item, index) => (
              <tr key={index}>

                <td>{item.name}</td>

                <td>
                  {getLocation(item.category)}
                </td>

                <td>
                  <span
                    className={`badge ${badge(
                      item.status
                    )}`}
                  >
                    {item.status}
                  </span>
                </td>

              </tr>
            ))}
          </tbody>

        </table>

      </div>

    </div>
  );
}

export default Dashboard;

import { NavLink } from "react-router-dom";
import logo from "../assets/logo.png";
function Sidebar() {
  return (
    <div className="sidebar">

      <div className="brand">
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "20px" }}>
  
            <img 
               src={logo} 
               alt="logo"
               style={{ width: "40px", height: "40px" }}
            />

        <div>
          <h2 style={{ margin: 0 }}>PrintHub</h2>
          <small>Savetha Hospital</small>
        </div>

        </div>
        <p>Control Center</p>
      </div>

      <nav>
        <NavLink to="/">Dashboard</NavLink>
        <NavLink to="/locations">Locations</NavLink>
        <NavLink to="/printers">Printers</NavLink>
        <NavLink to="/categories">Categories</NavLink>
        <NavLink to="/mapping">Mapping</NavLink>
        <NavLink to="/printjobs">Print Jobs</NavLink>
      </nav>

      <div className="version">v1.0 Live</div>

    </div>
  );
}

export default Sidebar;
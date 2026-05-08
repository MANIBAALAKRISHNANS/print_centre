import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import logo from "../assets/logo.png";
function Sidebar() {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === 'admin';
  const isOperator = ['admin', 'operator'].includes(user?.role);

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
        <NavLink to="/printjobs">Print Jobs</NavLink>
        
        {isOperator && (
          <>
            <div className="sidebar-divider"></div>
            <p className="sidebar-header">Infrastructure</p>
            <NavLink to="/locations">Locations</NavLink>
            <NavLink to="/printers">Printers</NavLink>
            <NavLink to="/agents">Agents</NavLink>
            <NavLink to="/categories">Categories</NavLink>
            <NavLink to="/mapping">Mapping</NavLink>
          </>
        )}

        {isAdmin && (
          <>
            <div className="sidebar-divider"></div>
            <p className="sidebar-header">Administration</p>
            <NavLink to="/admin/activation-codes">Activation Codes</NavLink>
            <NavLink to="/audit-logs">Audit Logs</NavLink>
            <NavLink to="/admin/users">User Management</NavLink>
          </>
        )}
      </nav>

      <NavLink to="/profile" className="sidebarProfile" style={{ textDecoration: "none", color: "inherit" }}>
          <div className="profileInfo">
            <span className="username">{user?.username}</span>
            <span className="role">{user?.role}</span>
          </div>
          <button className="logoutBtn" onClick={(e) => { e.preventDefault(); logout(); }} title="Sign Out">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>
            </svg>
          </button>
      </NavLink>
    </div>
  );
}

export default Sidebar;
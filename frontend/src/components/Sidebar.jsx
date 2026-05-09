import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import logo from "../assets/logo.png";

function Sidebar() {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === 'admin';
  const isOperator = ['admin', 'operator'].includes(user?.role);

  const getInitials = (name) => {
    return name ? name.substring(0, 2).toUpperCase() : "PH";
  };

  return (
    <div className="sidebar">
      <div className="brand">
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <img
            src={logo}
            alt="logo"
            style={{ width: "40px", height: "40px", filter: "drop-shadow(0 4px 8px rgba(0,0,0,0.3))", flexShrink: 0 }}
          />
          <div>
            <h2 style={{ margin: 0, fontSize: "1.15rem", fontWeight: 800, letterSpacing: "-0.02em", color: "#fff" }}>PrintHub</h2>
            <small style={{ opacity: 0.55, fontSize: "0.68rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#fff" }}>Clinical Professional</small>
          </div>
        </div>
      </div>

      <nav style={{ flex: 1, overflowY: "auto", paddingTop: "10px", paddingBottom: "8px" }}>
        <p className="sidebar-header">Monitoring</p>
        <NavLink to="/" end className={({ isActive }) => isActive ? "active" : ""}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: "12px" }}><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
          Dashboard
        </NavLink>
        <NavLink to="/printjobs">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: "12px" }}><path d="M6 9V2h12v7"></path><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path><rect x="6" y="14" width="12" height="8"></rect></svg>
          Print Queue
        </NavLink>
        
        {isOperator && (
          <>
            <div className="sidebar-divider"></div>
            <p className="sidebar-header">Infrastructure</p>
            <NavLink to="/locations">Locations</NavLink>
            <NavLink to="/printers">Printers</NavLink>
            <NavLink to="/agents">Active Agents</NavLink>
            <NavLink to="/categories">Categories</NavLink>
            <NavLink to="/mapping">System Mapping</NavLink>
          </>
        )}

        {isAdmin && (
          <>
            <div className="sidebar-divider"></div>
            <p className="sidebar-header">Security & Admin</p>
            <NavLink to="/admin/activation-codes">Activation Codes</NavLink>
            <NavLink to="/audit-logs">Audit Trail</NavLink>
            <NavLink to="/admin/users">User Directory</NavLink>
          </>
        )}
      </nav>

      <NavLink to="/profile" className="sidebarProfile" style={{ textDecoration: "none" }}>
          <div className="profileAvatar">
            {getInitials(user?.username)}
          </div>
          <div className="profileInfo">
            <span className="username">{user?.username}</span>
            <span className="role">{user?.role}</span>
          </div>
          <button className="logoutBtn" onClick={(e) => { e.preventDefault(); logout(); }} title="Sign Out">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>
            </svg>
          </button>
      </NavLink>
    </div>
  );
}

export default Sidebar;
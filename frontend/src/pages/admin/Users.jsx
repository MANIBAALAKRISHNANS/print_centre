import { useState, useEffect } from "react";
import { useFetch } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";
import { API_BASE_URL } from "../../config";
import { SkeletonTable } from "../../components/Skeleton";
import EmptyState from "../../components/EmptyState";

function Users() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentUser, setCurrentUser] = useState(null);
  const [openAdd, setOpenAdd] = useState(false);
  const [openReset, setOpenReset] = useState(false);
  const [resetTarget, setResetTarget] = useState(null);
  const [showPass, setShowPass] = useState(false);
  
  const [formData, setFormData] = useState({ username: "", password: "", role: "viewer" });
  const [resetData, setResetData] = useState({ new_password: "" });
  
  const authFetch = useFetch();
  const toast = useToast();

  const loadUsers = async () => {
    try {
      const res = await authFetch(`${API_BASE_URL}/admin/users`);
      const data = await res.json();
      if (Array.isArray(data)) setUsers(data);
      
      const meRes = await authFetch(`${API_BASE_URL}/auth/me`);
      const meData = await meRes.json();
      setCurrentUser(meData);
    } catch (err) {
      toast.error("Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const handleAddUser = async (e) => {
    e.preventDefault();
    try {
      const res = await authFetch(`${API_BASE_URL}/admin/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData)
      });
      const result = await res.json();
      if (result.error) throw new Error(result.error);
      
      toast.success("User created successfully");
      setOpenAdd(false);
      setFormData({ username: "", password: "", role: "viewer" });
      loadUsers();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleUpdateRole = async (userId, newRole) => {
    try {
      const res = await authFetch(`${API_BASE_URL}/admin/users/${userId}/role`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: newRole })
      });
      if (!res.ok) throw new Error("Failed to update role");
      toast.success("Role updated");
      loadUsers();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    try {
      const res = await authFetch(`${API_BASE_URL}/admin/users/${resetTarget.id}/password`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(resetData)
      });
      const result = await res.json();
      if (result.error) throw new Error(result.error);
      
      toast.success("Password reset successfully");
      setOpenReset(false);
      setResetData({ new_password: "" });
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDeleteUser = async (id) => {
    if (!window.confirm("Are you sure you want to deactivate this user?")) return;
    try {
      const res = await authFetch(`${API_BASE_URL}/admin/users/${id}`, { method: "DELETE" });
      if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || "Failed to delete");
      }
      toast.success("User deactivated");
      loadUsers();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const getRoleColor = (role) => {
    switch (role) {
      case "admin": return "red";
      case "operator": return "blue";
      default: return "gray";
    }
  };

  return (
    <div className="page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
        <div>
          <h1>User Management</h1>
          <p className="sub">Manage system access and roles for clinical and IT staff</p>
        </div>
        <button className="btn" onClick={() => setOpenAdd(true)}>+ Add User</button>
      </div>

      <div className="card">
        {loading ? (
          <SkeletonTable rows={5} cols={5} />
        ) : users.length === 0 ? (
          <EmptyState icon="👥" title="No users found" subtitle="This shouldn't happen." />
        ) : (
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Role</th>
                <th>Created At</th>
                <th>Last Login</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td>
                    <strong>{u.username}</strong>
                    {u.username === currentUser?.username && <span className="badge blue" style={{ marginLeft: "8px", fontSize: "0.7rem" }}>You</span>}
                    {u.force_password_change === 1 && <span className="badge orange" style={{ marginLeft: "8px", fontSize: "0.7rem" }}>Reset Pending</span>}
                  </td>
                  <td>
                    <select 
                      value={u.role} 
                      onChange={(e) => handleUpdateRole(u.id, e.target.value)}
                      disabled={u.username === currentUser?.username}
                      style={{ 
                          padding: "4px 8px", 
                          borderRadius: "4px", 
                          border: `1px solid ${getRoleColor(u.role)}`,
                          background: `${getRoleColor(u.role)}10`,
                          color: "inherit",
                          fontWeight: "bold",
                          opacity: u.username === currentUser?.username ? 0.7 : 1,
                          cursor: u.username === currentUser?.username ? "not-allowed" : "pointer"
                      }}
                    >
                      <option value="admin">Administrator</option>
                      <option value="operator">IT Operator</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  </td>
                  <td><span style={{ fontSize: "0.85rem", color: "#666" }}>{u.created_at}</span></td>
                  <td><span style={{ fontSize: "0.85rem", color: "#666" }}>{u.last_login || "Never"}</span></td>
                  <td>
                    <div style={{ display: "flex", gap: "8px" }}>
                      <button className="btn mini" onClick={() => { setResetTarget(u); setOpenReset(true); }}>Reset PW</button>
                      <button 
                        className="btn mini red" 
                        disabled={u.username === currentUser?.username}
                        onClick={() => handleDeleteUser(u.id)}
                      >
                        Deactivate
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {openAdd && (
        <div className="modalOverlay">
          <div className="modalBox">
            <div className="modalHead"><h3>Add New User</h3><button onClick={() => setOpenAdd(false)}>✕</button></div>
            <form className="modalBody" onSubmit={handleAddUser}>
              <label>Username</label>
              <input 
                required 
                value={formData.username} 
                onChange={e => setFormData({ ...formData, username: e.target.value })} 
                placeholder="e.g. nurse_smith"
              />
              <label>Temporary Password</label>
              <div style={{ position: "relative" }}>
                <input 
                  required 
                  type={showPass ? "text" : "password"} 
                  value={formData.password} 
                  onChange={e => setFormData({ ...formData, password: e.target.value })} 
                  placeholder="Min 10 chars, 1 uppercase, 1 number"
                  style={{ paddingRight: "40px" }}
                />
                <button 
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  style={{ 
                    position: "absolute", right: "10px", top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", cursor: "pointer", opacity: 0.6
                  }}
                >
                  {showPass ? "👁️" : "👁️‍🗨️"}
                </button>
              </div>
              <label>System Role</label>
              <select value={formData.role} onChange={e => setFormData({ ...formData, role: e.target.value })}>
                <option value="viewer">Viewer (Nursing/Read-only)</option>
                <option value="operator">Operator (IT Support/Manage Hardware)</option>
                <option value="admin">Administrator (Full Control)</option>
              </select>
              <p style={{ fontSize: "0.75rem", color: "#666", marginTop: "-10px", marginBottom: "15px" }}>
                User will be forced to change this password on their first login.
              </p>
              <button className="btn full" type="submit">Create User Account</button>
            </form>
          </div>
        </div>
      )}

      {openReset && (
        <div className="modalOverlay">
          <div className="modalBox">
            <div className="modalHead"><h3>Reset Password: {resetTarget?.username}</h3><button onClick={() => setOpenReset(false)}>✕</button></div>
            <form className="modalBody" onSubmit={handleResetPassword}>
              <label>New Password</label>
              <div style={{ position: "relative" }}>
                <input 
                  required 
                  type={showPass ? "text" : "password"} 
                  value={resetData.new_password} 
                  onChange={e => setResetData({ ...resetData, new_password: e.target.value })} 
                  placeholder="Min 10 chars, 1 uppercase, 1 number"
                  style={{ paddingRight: "40px" }}
                />
                <button 
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  style={{ 
                    position: "absolute", right: "10px", top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", cursor: "pointer", opacity: 0.6
                  }}
                >
                  {showPass ? "👁️" : "👁️‍🗨️"}
                </button>
              </div>
              <button className="btn full" type="submit">Update Password</button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default Users;

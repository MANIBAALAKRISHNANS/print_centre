import { useState } from "react";
import { useAuth, useFetch } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { API_BASE_URL } from "../config";

function Profile() {
  const { user } = useAuth();
  const authFetch = useFetch();
  const toast = useToast();
  
  const [formData, setFormData] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    if (formData.new_password !== formData.confirm_password) {
      return toast.error("Passwords do not match");
    }

    setLoading(true);
    try {
      const res = await authFetch(`${API_BASE_URL}/auth/change-password`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: formData.current_password,
          new_password: formData.new_password
        })
      });

      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || "Failed to update password");

      toast.success("Password updated successfully");
      setFormData({ current_password: "", new_password: "", confirm_password: "" });
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div style={{ marginBottom: "20px" }}>
        <h1>My Profile</h1>
        <p className="sub">Manage your account details and security settings</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
        {/* Account Details */}
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", gap: "20px", marginBottom: "20px" }}>
            <div style={{ 
              width: "60px", height: "60px", borderRadius: "50%", background: "#4a90e2", 
              color: "white", display: "flex", alignItems: "center", justifyContent: "center", 
              fontSize: "1.5rem", fontWeight: "bold" 
            }}>
              {user?.username?.[0]?.toUpperCase() || "U"}
            </div>
            <div>
              <h3 style={{ margin: 0 }}>{user?.username}</h3>
              <span className="badge blue">{user?.role}</span>
            </div>
          </div>
          
          <div style={{ borderTop: "1px solid #eee", paddingTop: "20px" }}>
            <div style={{ marginBottom: "15px" }}>
              <label style={{ display: "block", color: "#666", fontSize: "0.85rem", marginBottom: "5px" }}>Username</label>
              <div style={{ fontWeight: "600" }}>{user?.username}</div>
            </div>
            <div style={{ marginBottom: "15px" }}>
              <label style={{ display: "block", color: "#666", fontSize: "0.85rem", marginBottom: "5px" }}>Account Role</label>
              <div style={{ fontWeight: "600" }}>{user?.role?.toUpperCase()}</div>
            </div>
            <div>
              <label style={{ display: "block", color: "#666", fontSize: "0.85rem", marginBottom: "5px" }}>System Status</label>
              <div style={{ color: "#27ae60", display: "flex", alignItems: "center", gap: "5px" }}>
                <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#27ae60" }}></span>
                Active
              </div>
            </div>
          </div>
        </div>

        {/* Change Password */}
        <div className="card">
          <h3 style={{ marginTop: 0, marginBottom: "20px" }}>Security Settings</h3>
          <form onSubmit={handlePasswordChange} style={{ display: "flex", flexDirection: "column", gap: "15px" }}>
            <div>
              <label>Current Password</label>
              <input 
                required 
                type="password" 
                value={formData.current_password}
                onChange={e => setFormData({ ...formData, current_password: e.target.value })}
              />
            </div>
            <div>
              <label>New Password</label>
              <div style={{ position: "relative" }}>
                <input 
                  required 
                  type={showPass ? "text" : "password"} 
                  value={formData.new_password}
                  onChange={e => setFormData({ ...formData, new_password: e.target.value })}
                  placeholder="Min 10 chars, 1 upper, 1 number"
                  style={{ paddingRight: "40px" }}
                />
                <button 
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  style={{ 
                    position: "absolute", right: "10px", top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", cursor: "pointer", fontSize: "1.1rem"
                  }}
                >
                  {showPass ? "👁️" : "👁️‍🗨️"}
                </button>
              </div>
            </div>
            <div>
              <label>Confirm New Password</label>
              <input 
                required 
                type="password" 
                value={formData.confirm_password}
                onChange={e => setFormData({ ...formData, confirm_password: e.target.value })}
              />
            </div>
            <button className="btn full" type="submit" disabled={loading}>
              {loading ? "Updating..." : "Update Password"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default Profile;

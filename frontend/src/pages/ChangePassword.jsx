import { useState } from "react";
import { useAuth, useFetch } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { API_BASE_URL } from "../config";
import { useNavigate } from "react-router-dom";

const PasswordInput = ({ label, value, onChange, show, setShow, placeholder }) => (
  <div>
    <label style={{ display: "block", marginBottom: "5px", fontSize: "0.85rem", fontWeight: "600" }}>{label}</label>
    <div style={{ position: "relative" }}>
      <input 
        required 
        type={show ? "text" : "password"} 
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        style={{ width: "100%", padding: "10px", paddingRight: "40px", borderRadius: "6px", border: "1px solid #ddd" }}
      />
      <button
        type="button"
        onClick={() => setShow(!show)}
        style={{
          position: "absolute",
          right: "10px",
          top: "50%",
          transform: "translateY(-50%)",
          background: "none",
          border: "none",
          cursor: "pointer",
          fontSize: "1.1rem",
          padding: "0"
        }}
      >
        {show ? "👁️" : "👁️‍🗨️"}
      </button>
    </div>
  </div>
);

function ChangePassword() {
  const [formData, setFormData] = useState({ current_password: "", new_password: "", confirm_password: "" });
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const { logout } = useAuth();
  const authFetch = useFetch();
  const toast = useToast();
  const navigate = useNavigate();

  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (formData.new_password !== formData.confirm_password) {
      return toast.error("Passwords do not match");
    }

    setLoading(true);
    try {
      const res = await authFetch("/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: formData.current_password,
          new_password: formData.new_password
        })
      });

      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || "Failed to update password");

      setSuccess(true);
      toast.success("Password changed successfully!");
      
      // Auto logout and redirect after 3 seconds
      setTimeout(() => {
        handleFinalRedirect();
      }, 3000);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleFinalRedirect = () => {
    logout();
    navigate("/login");
  };

  return (
    <div style={{ 
      display: "flex", 
      alignItems: "center", 
      justifyContent: "center", 
      height: "100vh", 
      background: "#f0f2f5" 
    }}>
      <div className="card" style={{ width: "100%", maxWidth: "400px", padding: "40px", textAlign: "center" }}>
        {success ? (
          <div style={{ animation: "fadeIn 0.5s ease-out" }}>
            <div style={{ fontSize: "3rem", marginBottom: "20px" }}>✅</div>
            <h2 style={{ marginBottom: "10px" }}>Password Updated</h2>
            <p style={{ color: "#666", marginBottom: "30px" }}>
              Your security credentials have been updated successfully.
            </p>
            <button 
              onClick={handleFinalRedirect}
              className="btn full"
              style={{ padding: "12px" }}
            >
              Sign In with New Password
            </button>
            <p style={{ marginTop: "20px", fontSize: "0.85rem", color: "#999" }}>
              Redirecting to login in a few seconds...
            </p>
          </div>
        ) : (
          <>
            <h2 style={{ textAlign: "center", marginBottom: "10px" }}>Security Update</h2>
            <p style={{ textAlign: "center", color: "#666", marginBottom: "30px", fontSize: "0.9rem" }}>
              You are required to change your password before continuing.
            </p>

            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "15px", textAlign: "left" }}>
              <PasswordInput 
                label="Current Password"
                value={formData.current_password}
                onChange={e => setFormData({ ...formData, current_password: e.target.value })}
                show={showCurrent}
                setShow={setShowCurrent}
              />

              <PasswordInput 
                label="New Password"
                value={formData.new_password}
                onChange={e => setFormData({ ...formData, new_password: e.target.value })}
                show={showNew}
                setShow={setShowNew}
                placeholder="Min 10 chars, 1 upper, 1 number"
              />

              <PasswordInput 
                label="Confirm New Password"
                value={formData.confirm_password}
                onChange={e => setFormData({ ...formData, confirm_password: e.target.value })}
                show={showConfirm}
                setShow={setShowConfirm}
              />

              <button 
                type="submit" 
                className="btn full" 
                disabled={loading}
                style={{ marginTop: "10px" }}
              >
                {loading ? "Updating..." : "Update & Sign In"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

export default ChangePassword;

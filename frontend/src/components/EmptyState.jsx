import React from 'react';

function EmptyState({ icon, title, subtitle, action, actionLabel }) {
    return (
        <div style={{ 
            textAlign: "center", 
            padding: "64px 24px", 
            color: "#666",
            background: "#fff",
            borderRadius: "12px",
            border: "1px dashed #ddd",
            marginTop: "20px"
        }}>
            <div style={{ fontSize: "3.5rem", marginBottom: "16px" }}>{icon}</div>
            <h3 style={{ fontSize: "1.2rem", color: "#333", marginBottom: "8px", fontWeight: "600" }}>{title}</h3>
            <p style={{ fontSize: "0.95rem", color: "#888", marginBottom: action ? "24px" : 0, maxWidth: "400px", margin: action ? "0 auto 24px" : "0 auto" }}>
                {subtitle}
            </p>
            {action && (
                <button className="btn" onClick={action}>{actionLabel}</button>
            )}
        </div>
    );
}

export default EmptyState;

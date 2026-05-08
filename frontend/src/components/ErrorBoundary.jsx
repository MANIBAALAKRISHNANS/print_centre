import React from 'react';

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }
    
    static getDerivedStateFromError(error) {
        // Update state so the next render will show the fallback UI.
        return { hasError: true, error };
    }
    
    componentDidCatch(error, errorInfo) {
        // You can also log the error to an error reporting service
        console.error("Uncaught error in component tree:", error, errorInfo);
    }
    
    render() {
        if (this.state.hasError) {
            return (
                <div style={{ 
                    padding: "60px 20px", 
                    textAlign: "center",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    minHeight: "400px"
                }}>
                    <div style={{ fontSize: "3rem", marginBottom: "20px" }}>⚠️</div>
                    <h2 style={{ color: "#111", marginBottom: "10px" }}>Something went wrong</h2>
                    <p style={{ color: "#666", maxWidth: "450px", lineHeight: "1.5", marginBottom: "24px" }}>
                        The interface encountered an unexpected error. Please try refreshing the page or 
                        navigating back to the dashboard.
                    </p>
                    <div style={{ display: "flex", gap: "12px" }}>
                        <button 
                            className="btn"
                            onClick={() => window.location.reload()}
                        >
                            Refresh Page
                        </button>
                        <button 
                            className="btn"
                            style={{ background: "#6b7280" }}
                            onClick={() => this.setState({ hasError: false, error: null })}
                        >
                            Dismiss & Try Again
                        </button>
                    </div>
                    <details style={{ marginTop: "40px", textAlign: "left", width: "100%", maxWidth: "600px" }}>
                        <summary style={{ cursor: "pointer", color: "#999", fontSize: "0.85rem" }}>
                            Show technical details
                        </summary>
                        <pre style={{ 
                            marginTop: "10px",
                            padding: "16px",
                            background: "#f8f9fa",
                            border: "1px solid #eee",
                            borderRadius: "6px",
                            fontSize: "0.8rem",
                            overflowX: "auto",
                            color: "#d00"
                        }}>
                            {this.state.error?.toString()}
                        </pre>
                    </details>
                </div>
            );
        }

        return this.props.children; 
    }
}

export default ErrorBoundary;

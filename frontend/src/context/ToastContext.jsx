import React, { createContext, useContext, useState, useCallback, useRef } from 'react';

const ToastContext = createContext(null);

export const ToastProvider = ({ children }) => {
    const [toasts, setToasts] = useState([]);
    const toastIdCounter = useRef(0);

    const removeToast = useCallback((id) => {
        setToasts(current => current.filter(t => t.id !== id));
    }, []);

    const addToast = useCallback((message, type = 'info') => {
        const id = ++toastIdCounter.current;
        const newToast = { id, message, type };
        
        setToasts(current => {
            // Keep max 4 toasts
            const next = [...current, newToast];
            if (next.length > 4) return next.slice(1);
            return next;
        });

        // Auto-remove after 4 seconds
        setTimeout(() => removeToast(id), 4000);
    }, [removeToast]);

    const toast = {
        success: (msg) => addToast(msg, 'success'),
        error: (msg) => addToast(msg, 'error'),
        warning: (msg) => addToast(msg, 'warning'),
        info: (msg) => addToast(msg, 'info')
    };

    return (
        <ToastContext.Provider value={{ toast, toasts, removeToast }}>
            {children}
            <ToastContainer />
        </ToastContext.Provider>
    );
};

const ToastContainer = () => {
    const { toasts, removeToast } = useContext(ToastContext);
    
    return (
        <div style={{
            position: 'fixed',
            bottom: '20px',
            right: '20px',
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            pointerEvents: 'none'
        }}>
            {toasts.map(t => (
                <ToastItem key={t.id} toast={t} onDismiss={() => removeToast(t.id)} />
            ))}
        </div>
    );
};

const ToastItem = ({ toast, onDismiss }) => {
    const [hovered, setHovered] = useState(false);
    const timerRef = useRef(null);

    // Color Mapping
    const colors = {
        success: { bg: '#dcfce7', border: '#22c55e', text: '#166534' },
        error: { bg: '#fee2e2', border: '#ef4444', text: '#991b1b' },
        warning: { bg: '#fef3c7', border: '#f59e0b', text: '#92400e' },
        info: { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' }
    };

    const style = colors[toast.type] || colors.info;

    return (
        <div 
            role="alert"
            aria-live="polite"
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            style={{
                pointerEvents: 'auto',
                minWidth: '280px',
                padding: '12px 16px',
                background: style.bg,
                borderLeft: `5px solid ${style.border}`,
                borderRadius: '6px',
                boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                animation: 'slideIn 0.3s ease-out forwards'
            }}
        >
            <span style={{ color: style.text, fontWeight: 500, fontSize: '0.9rem' }}>
                {toast.message}
            </span>
            <button 
                onClick={onDismiss}
                style={{
                    background: 'none',
                    border: 'none',
                    color: style.text,
                    cursor: 'pointer',
                    fontSize: '1.2rem',
                    padding: '0 4px',
                    opacity: 0.6
                }}
            >
                ×
            </button>
            <style>{`
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
            `}</style>
        </div>
    );
};

export const useToast = () => {
    const context = useContext(ToastContext);
    if (!context) throw new Error("useToast must be used within a ToastProvider");
    return context.toast;
};

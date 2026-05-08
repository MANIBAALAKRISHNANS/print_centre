import React, { createContext, useContext, useState, useEffect } from 'react';
import { API_BASE_URL } from '../config';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [token, setToken] = useState(null);
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Fallback for page refresh using session cookie
        const getCookie = (name) => {
            const value = `; ${document.cookie}`;
            const parts = value.split(`; ${name}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
            return null;
        };

        const savedToken = getCookie('print_hub_session');
        if (savedToken) {
            validateToken(savedToken);
        } else {
            setLoading(false);
        }
    }, []);

    const validateToken = async (t) => {
        try {
            const resp = await fetch(`${API_BASE_URL}/auth/me`, {
                headers: { 'Authorization': `Bearer ${t}` }
            });
            if (resp.ok) {
                const userData = await resp.json();
                setToken(t);
                setUser(userData); // Now includes force_password_change from backend
            } else {
                logout();
            }
        } catch (err) {
            console.error("Token validation failed", err);
            logout();
        } finally {
            setLoading(false);
        }
    };

    const login = React.useCallback(async (username, password) => {
        const resp = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        if (!resp.ok) {
            let errorMessage = 'Invalid credentials';
            try {
                const errorData = await resp.json();
                if (errorData.detail) {
                    if (typeof errorData.detail === 'string') {
                        errorMessage = errorData.detail;
                    } else if (Array.isArray(errorData.detail)) {
                        errorMessage = errorData.detail[0].msg || JSON.stringify(errorData.detail);
                    } else {
                        errorMessage = JSON.stringify(errorData.detail);
                    }
                }
            } catch (e) {
                errorMessage = `Server Error (${resp.status})`;
            }
            throw new Error(errorMessage);
        }

        const data = await resp.json();
        setToken(data.access_token);
        setUser({ 
            username: data.username, 
            role: data.role, 
            force_password_change: data.force_password_change 
        });
        
        // Secure Session Cookie (removed on browser close)
        document.cookie = `print_hub_session=${data.access_token}; path=/; SameSite=Strict`;
        return data;
    }, []);

    const logout = React.useCallback(() => {
        setToken(null);
        setUser(null);
        document.cookie = "print_hub_session=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
    }, []);

    const value = React.useMemo(() => ({
        token, user, loading, login, logout
    }), [token, user, loading]);

    return (
        <AuthContext.Provider value={value}>
            {!loading && children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) throw new Error("useAuth must be used within an AuthProvider");
    return context;
};

/**
 * 🔹 Custom hook for authenticated API calls
 * Automatically injects Bearer token and handles 401 redirects
 */
export const useFetch = () => {
    const { token, logout } = useAuth();

    return React.useCallback(async (endpoint, options = {}) => {
        const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
        
        const headers = {
            ...options.headers,
            'Authorization': `Bearer ${token}`
        };

        try {
            const response = await fetch(url, { ...options, headers });

            if (response.status === 401) {
                logout();
                window.location.href = '/login';
                return response;
            }

            return response;
        } catch (error) {
            console.error("Fetch error:", error);
            throw error;
        }
    }, [token, logout]);
};

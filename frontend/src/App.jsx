import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";

import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Printers from "./pages/Printers";
import Categories from "./pages/Categories";
import Locations from "./pages/Locations";
import Mapping from "./pages/Mapping";
import PrintJobs from "./pages/PrintJobs";
import Agents from "./pages/Agents";
import Login from "./pages/Login";
import AuditLogs from "./pages/AuditLogs";
import ActivationCodes from "./pages/ActivationCodes";
import Users from "./pages/admin/Users";
import ChangePassword from "./pages/ChangePassword";
import Profile from "./pages/Profile";
import ErrorBoundary from "./components/ErrorBoundary";
import { ToastProvider } from "./context/ToastContext";

const ProtectedRoute = ({ children, requireAdmin = false }) => {
  const { token, user } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  
  // Force password change redirection
  if (user?.force_password_change && window.location.pathname !== "/change-password") {
      return <Navigate to="/change-password" replace />;
  }

  // Admin access check
  if (requireAdmin && user?.role !== 'admin') {
      return <Navigate to="/" replace />;
  }

  return children;
};

const AuthenticatedLayout = ({ children }) => (
  <div className="app">
    <Sidebar />
    <div className="main">{children}</div>
  </div>
);

function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
            <Route path="/login" element={<Login />} />
            
            <Route path="/" element={
              <ProtectedRoute>
                <AuthenticatedLayout><ErrorBoundary><Dashboard /></ErrorBoundary></AuthenticatedLayout>
              </ProtectedRoute>
            } />
            
            <Route path="/printers" element={
              <ProtectedRoute>
                <AuthenticatedLayout><ErrorBoundary><Printers /></ErrorBoundary></AuthenticatedLayout>
              </ProtectedRoute>
            } />
            
            <Route path="/categories" element={
              <ProtectedRoute>
                <AuthenticatedLayout><ErrorBoundary><Categories /></ErrorBoundary></AuthenticatedLayout>
              </ProtectedRoute>
            } />
            
            <Route path="/locations" element={
              <ProtectedRoute>
                <AuthenticatedLayout><ErrorBoundary><Locations /></ErrorBoundary></AuthenticatedLayout>
              </ProtectedRoute>
            } />
            
            <Route path="/mapping" element={
              <ProtectedRoute>
                <AuthenticatedLayout><ErrorBoundary><Mapping /></ErrorBoundary></AuthenticatedLayout>
              </ProtectedRoute>
            } />
            
            <Route path="/printjobs" element={
              <ProtectedRoute>
                <AuthenticatedLayout><ErrorBoundary><PrintJobs /></ErrorBoundary></AuthenticatedLayout>
              </ProtectedRoute>
            } />
            
            <Route path="/agents" element={
              <ProtectedRoute>
                <AuthenticatedLayout><ErrorBoundary><Agents /></ErrorBoundary></AuthenticatedLayout>
              </ProtectedRoute>
            } />
            
            <Route path="/audit-logs" element={
              <ProtectedRoute requireAdmin>
                <AuthenticatedLayout><ErrorBoundary><AuditLogs /></ErrorBoundary></AuthenticatedLayout>
              </ProtectedRoute>
            } />

            <Route path="/admin/activation-codes" element={
              <ProtectedRoute requireAdmin>
                <AuthenticatedLayout><ErrorBoundary><ActivationCodes /></ErrorBoundary></AuthenticatedLayout>
              </ProtectedRoute>
            } />

            <Route path="/admin/users" element={
              <ProtectedRoute requireAdmin>
                <AuthenticatedLayout><ErrorBoundary><Users /></ErrorBoundary></AuthenticatedLayout>
              </ProtectedRoute>
            } />

            <Route path="/change-password" element={
              <ProtectedRoute>
                <ErrorBoundary><ChangePassword /></ErrorBoundary>
              </ProtectedRoute>
            } />

            <Route path="/profile" element={
              <ProtectedRoute>
                <AuthenticatedLayout><ErrorBoundary><Profile /></ErrorBoundary></AuthenticatedLayout>
              </ProtectedRoute>
            } />
          </Routes>
        </BrowserRouter>
    </ToastProvider>
  );
}

export default App;

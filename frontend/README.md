# PrintHub Frontend

React 18 + Vite admin dashboard for the PrintHub hospital print management system.

## Tech Stack

| | |
|---|---|
| Framework | React 18, Vite |
| Routing | React Router v6 |
| Real-time | WebSocket (`useWebSocket` hook, auto-reconnecting) |
| Auth | JWT via HTTP-only cookie, `AuthContext` |
| Styling | Plain CSS — `App.css` (components), `index.css` (tokens + utilities) |

## Setup

```bash
npm install
```

Create `frontend/.env`:
```env
VITE_API_URL=http://YOUR_SERVER_IP:8000
```

Start the dev server:
```bash
npm run dev
# → http://localhost:5173
```

Production build:
```bash
npm run build
# Output: frontend/dist/ — serve with nginx or any static host
```

## Key Files

```
src/
├── config.js               # API_BASE_URL + WS_BASE_URL (from VITE_API_URL)
├── context/
│   ├── AuthContext.jsx     # JWT login/logout, useFetch() helper
│   └── AppData.jsx         # Global printers list, shared across pages
├── hooks/
│   └── useWebSocket.js     # Auto-reconnecting WS hook with exponential backoff
├── components/
│   ├── Sidebar.jsx         # Navigation sidebar
│   ├── Skeleton.jsx        # Loading skeleton (use className="skeleton" in index.css)
│   └── ErrorBoundary.jsx   # Catches synchronous render errors
└── pages/
    ├── Dashboard.jsx       # Live stats + hardware table
    ├── Printers.jsx        # Printer CRUD
    ├── PrintJobs.jsx       # Job queue + retry
    ├── Agents.jsx          # Connected workstation agents
    ├── Users.jsx           # User management (Admin+)
    ├── AuditLogs.jsx       # HIPAA audit trail
    └── Login.jsx
```

## Real-time Architecture

The dashboard maintains a persistent WebSocket to `/ws?token=JWT`. The `useWebSocket` hook handles connection lifecycle (auto-reconnect with backoff). Pages subscribe via the `handleWsMessage` callback and call their data-loading functions in response to server-pushed events:

| Event | Pages that react |
|---|---|
| `job_update` | Dashboard, PrintJobs |
| `printer_update` | Dashboard, Printers |
| `agent_update` | Dashboard, Agents |
| `dashboard_refresh` | Dashboard |

**Important:** Any `useCallback` that appears in `handleWsMessage`'s dependency array must be declared **before** `handleWsMessage` in the component — React `const` declarations are subject to JavaScript's Temporal Dead Zone (TDZ). Accessing a `const` before its declaration throws `ReferenceError` synchronously during render and triggers the ErrorBoundary.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `VITE_API_URL` | ✅ | Backend base URL e.g. `http://192.168.1.14:8000` |

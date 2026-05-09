# PrintHub — Clinical-Grade Hospital Print Management System

**PrintHub** is a production-level, real-time hospital print management infrastructure. It connects a central FastAPI backend to local USB and network printers across nursing workstations via persistent WebSocket agent connections — delivering near-instant job execution instead of polling delays. Includes a full React admin dashboard, HIPAA-compliant audit logging, and cross-platform agents for Windows & macOS.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Tech Stack](#tech-stack)
3. [Prerequisites](#prerequisites)
4. [Step-by-Step: Running the Project](#step-by-step-running-the-project)
   - [Backend Setup](#1-backend-setup)
   - [Frontend Setup](#2-frontend-setup)
5. [Agent Installation — Windows](#agent-installation--windows)
6. [Agent Installation — macOS](#agent-installation--macos)
7. [How the Agent Connects to the Server (Real-time)](#how-the-agent-connects-to-the-server)
8. [Firewall Configuration](#firewall-configuration)
9. [PostgreSQL Setup](#postgresql-setup)
10. [Environment Variables Reference](#environment-variables-reference)
11. [Default Credentials](#default-credentials)
12. [API Endpoints](#api-endpoints)
13. [RBAC Roles](#rbac-roles)
14. [WebSocket Events](#websocket-events)
15. [Troubleshooting](#troubleshooting)
16. [Project Structure](#project-structure)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HOSPITAL NETWORK                             │
│                                                                     │
│  ┌──────────────────┐         ┌──────────────────────────────────┐ │
│  │  React Dashboard │◄──WS───►│  FastAPI Backend                 │ │
│  │  (Admin UI)      │◄─HTTP──►│  + PostgreSQL Pool               │ │
│  │  Port 5173       │         │  + APScheduler                   │ │
│  └──────────────────┘         │  Port 8000                       │ │
│                                └──────────┬───────────────────────┘ │
│                                           │                         │
│              ┌────────────────────────────┤                         │
│              │ /ws/agent (WebSocket)       │ /agent/jobs (HTTP)     │
│              │ instant job push            │ 30s safety-net poll    │
│              ▼                             ▼                         │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │            Print Agents  (Windows / macOS)                    │  │
│  │                                                               │  │
│  │  ┌──────────────────┐    ┌──────────────────────────────────┐ │  │
│  │  │  WebSocket Thread│    │  Main Poll Loop                  │ │  │
│  │  │  (daemon)        │    │  _job_trigger.wait(timeout=30s)  │ │  │
│  │  │  on job_available│───►│  Wakes immediately on WS push    │ │  │
│  │  │  → sets trigger  │    │  Falls back to 30s poll if WS    │ │  │
│  │  └──────────────────┘    │  is temporarily disconnected     │ │  │
│  │                           └──────────────────────────────────┘ │  │
│  └────────────────────────────────────────┬──────────────────────┘  │
│                                           │ USB / Network            │
│                               ┌───────────▼──────────────┐          │
│                               │  Physical Printers       │          │
│                               │  USB + Network           │          │
│                               └──────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

**Why Real-time WebSocket for Agents?**
- **Before**: Agent polled `/agent/jobs` every 5 seconds → up to 5s delay before printing starts
- **Now**: Server pushes `job_available` via `/ws/agent` → agent wakes in milliseconds
- **Safety-net**: If WebSocket disconnects, agent falls back to 30s HTTP polling automatically
- **No inbound ports**: Agent initiates outbound WS connection — firewall rules unchanged

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, FastAPI, APScheduler, psycopg2 |
| **Database** | PostgreSQL 14+ (ThreadedConnectionPool) |
| **Frontend** | React 18, Vite, React Router v6 |
| **Real-time (Dashboard)** | WebSocket `/ws` — dashboard clients |
| **Real-time (Agents)** | WebSocket `/ws/agent` — print agents |
| **Auth** | JWT (HS256), HTTP-only cookie |
| **Agent (Windows)** | Python 3.11+, win32print, pywin32, WMI, websocket-client |
| **Agent (macOS)** | Python 3.11+, CUPS (lpstat/lp), websocket-client |
| **Service (Windows)** | pywin32 Windows Service (`agent_service.py`) |
| **Service (macOS)** | launchd plist (`install_agent.sh`) |
| **Service (Linux)** | systemd unit (`install_agent.sh`) |

---

## Prerequisites

Install on **every machine** (server + workstations):

- **Python 3.11+** — [python.org/downloads](https://www.python.org/downloads/)
- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **PostgreSQL 14+** — [postgresql.org/download](https://www.postgresql.org/download/)
- **Git** — [git-scm.com](https://git-scm.com/)

---

## Step-by-Step: Running the Project

### 1. Backend Setup

**Step 1 — Clone the repository:**
```bash
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
cd print_centre
```

**Step 2 — Create and activate a Python virtual environment:**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

**Step 3 — Install dependencies:**
```bash
pip install -r backend/requirements.txt
```

**Step 4 — Create `backend/.env`:**
```env
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/printhub
SECRET_KEY=your-very-long-random-secret-key-change-this
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
STALE_THRESHOLD_SECONDS=45
PG_POOL_MIN=2
PG_POOL_MAX=20
```
> Generate `SECRET_KEY`: `python -c "import secrets; print(secrets.token_hex(32))"`

**Step 5 — Initialize the database:**
```bash
cd backend
python init_db.py
```

**Step 6 — Start the backend:**
```bash
# Development
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

Verify: `http://localhost:8000/health` → `{"status":"ok", "ws_agents": 0, ...}`

---

### 2. Frontend Setup

**Step 1 — Install Node.js dependencies:**
```bash
cd frontend
npm install
```

**Step 2 — Create `frontend/.env`:**
```env
VITE_API_URL=http://YOUR_SERVER_IP:8000
```

**Step 3 — Start the dev server:**
```bash
npm run dev
```

Dashboard at `http://localhost:5173`

**Step 4 — Production build:**
```bash
npm run build
# Serve frontend/dist/ with nginx or any static host
```

---

## Agent Installation — Windows

> Run on each **Windows workstation** connected to a printer.

### Quick Install (Recommended)

**Step 1 — Extract `PrintHub_Agent.zip` to `C:\PrintHubAgent\`.**

**Step 2 — Open Command Prompt as Administrator** (`Win+R` → `cmd` → `Ctrl+Shift+Enter`).

**Step 3 — Run the installer:**
```cmd
cd C:\PrintHubAgent
install_agent.bat
```

The installer will:
1. Check Python 3.11+ is installed
2. Create a virtual environment and install all dependencies (including `websocket-client`)
3. Prompt for server IP, port, HTTPS option, and activation code
4. Install the agent as a **Windows Service** (`PrintHubAgent`) that auto-starts on boot

**Step 4 — Verify** in the PrintHub dashboard → **Agents** → should show "Connected" within 15 seconds.

### Manual Install

```cmd
cd C:\PrintHubAgent
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

:: First-time setup
python agent_setup.py --code A3F9B2C1 --server http://192.168.1.50:8000

:: Install and start service
python agent_service.py --startup auto install
python agent_service.py start
```

### Service Management

Always use the venv Python when managing the service:

```cmd
cd C:\PrintHubAgent

:: Start / stop / restart
venv\Scripts\python.exe agent_service.py start
venv\Scripts\python.exe agent_service.py stop
venv\Scripts\python.exe agent_service.py restart

:: Check status (from anywhere)
sc query PrintHubAgent

:: View logs
type C:\PrintHubAgent\agent.log

:: Re-register (if server changes)
venv\Scripts\python.exe agent_setup.py --reset
venv\Scripts\python.exe agent_setup.py --code NEWCODE --server http://NEW_SERVER:8000
venv\Scripts\python.exe agent_service.py restart
```

**After updating `agent_service.py` or `agent.py`** you must do a full reinstall (restart alone is not enough):
```cmd
cd C:\PrintHubAgent
venv\Scripts\python.exe agent_service.py stop
venv\Scripts\python.exe agent_service.py remove
venv\Scripts\python.exe agent_service.py --startup auto install
venv\Scripts\python.exe agent_service.py start
sc query PrintHubAgent
```

### Security on Windows
- `agent_config.json` permissions locked to current user only via `icacls` (owner read/write)
- Agent never opens inbound ports — outbound WebSocket + HTTP only
- Rotating logs (5 MB × 3 files) at `C:\PrintHubAgent\agent.log`
- TLS verification enabled by default; for self-signed certs: `agent_setup.py --no-verify`

---

## Agent Installation — macOS

> Run on each **macOS workstation** connected to a printer.

**Step 1 — Extract and enter the agent directory:**
```bash
unzip PrintHub_Agent.zip -d ~/PrintHubAgent
cd ~/PrintHubAgent
```

**Step 2 — Run the installer:**
```bash
bash install_agent.sh
```

The installer:
1. Creates a Python virtual environment
2. Installs all dependencies including `websocket-client`
3. Prompts for server URL and activation code
4. Creates a **launchd plist** at `~/Library/LaunchAgents/com.printhub.agent.plist`
5. Loads it as a background service (auto-starts at login)

**Manage the service:**
```bash
# View live logs
tail -f ~/Library/Logs/PrintHubAgent/agent.log

# Stop
launchctl unload ~/Library/LaunchAgents/com.printhub.agent.plist

# Start
launchctl load ~/Library/LaunchAgents/com.printhub.agent.plist

# Restart
launchctl kickstart -k gui/$(id -u)/com.printhub.agent

# Re-register
python3 agent_setup.py --reset
python3 agent_setup.py --code NEWCODE --server http://SERVER:8000
launchctl kickstart -k gui/$(id -u)/com.printhub.agent

# Remove permanently
launchctl unload ~/Library/LaunchAgents/com.printhub.agent.plist
rm ~/Library/LaunchAgents/com.printhub.agent.plist
```

### Security on macOS
- Config file `agent_config.json` has `chmod 600` (owner-only)
- Log directory `~/Library/Logs/PrintHubAgent/` has `chmod 700`
- CUPS `lp`/`lpstat` commands used — no root required
- Outbound-only WebSocket + HTTP, no inbound ports

---

## How the Agent Connects to the Server

The agent uses **two communication channels** — both outbound-only (no inbound ports):

```
WORKSTATION                             SERVER (port 8000)
    │                                          │
    │── POST /agent/register ────────────────►│  (once, on first start)
    │◄─ { agent_id, token } ─────────────────│
    │                                          │
    │   ┌── Persistent WebSocket ─────────────┤
    │   │   wss://SERVER/ws/agent             │
    │   │   ?agent_id=X&token=Y               │
    │   │                                      │
    │   │   Server → Agent: job_available  ──►│  (instant, milliseconds)
    │   │   Agent → Server: ping/pong      ──►│  (keepalive every 30s)
    │   │                                      │
    │   │   On reconnect: exponential backoff  │
    │   │   1s → 2s → 4s → ... → 60s cap      │
    │   └─────────────────────────────────────┘
    │                                          │
    │   ┌── HTTP Safety-Net Poll ─────────────┤
    │   │   GET /agent/jobs every 30s         │
    │   │   (fallback if WS disconnected)      │
    │   └─────────────────────────────────────┘
    │                                          │
    │── POST /agent/heartbeat ───────────────►│  (every 15s)
    │── GET  /agent/config ──────────────────►│  (every 5 min)
    │── POST /agent/printer-status ─────────►│  (every 15s)
    │── GET  /agent/job/{id}/file ──────────►│  (streaming, on job)
    │── POST /agent/confirm ────────────────►│  (after success)
    │── POST /agent/fail ───────────────────►│  (after failure)
```

**Job execution timeline (real-time mode):**
1. Clinical staff submits print job → FastAPI saves to DB → **pushes `job_available` to agent via WebSocket** → `_job_trigger.set()`
2. Agent's `_job_trigger.wait()` wakes immediately — starts processing in **< 100 ms**
3. Agent downloads file → validates printer → sends to USB/network printer
4. Agent reports result → server broadcasts WebSocket event to dashboard → UI updates in real-time

**Job execution timeline (fallback mode — WebSocket disconnected):**
1. Clinical staff submits print job → saved to DB
2. Agent polls `/agent/jobs` every 30 seconds → picks up the job
3. Maximum delay: 30 seconds (vs 5 seconds in old polling architecture)

---

## Firewall Configuration

The agent only needs **outbound** access. No inbound rules required on workstations.

| Machine | Direction | Protocol | Port | Purpose |
|---|---|---|---|---|
| Workstation | **Outbound** | TCP | 8000 | Agent → Server (HTTP + WebSocket) |
| Server | Inbound | TCP | 8000 | Accept agents + dashboard |
| Server | Inbound | TCP | 5173 | Dev frontend (development only) |
| Server | Inbound | TCP | 80/443 | Production frontend (nginx) |

### Windows — Allow outbound to server
```cmd
netsh advfirewall firewall add rule name="PrintHub Agent" dir=out action=allow protocol=TCP remoteport=8000
```

### macOS Firewall
macOS blocks inbound by default but allows all outbound — **no configuration needed**.

### Corporate Proxy
```bash
# Windows
set HTTPS_PROXY=http://proxy.hospital.local:3128

# macOS / Linux
export HTTPS_PROXY=http://proxy.hospital.local:3128
```

---

## PostgreSQL Setup

```bash
# Connect as postgres superuser
psql -U postgres

CREATE DATABASE printhub;
CREATE USER printhub_user WITH PASSWORD 'strong_password_here';
GRANT ALL PRIVILEGES ON DATABASE printhub TO printhub_user;
\q

# Then run migrations
cd backend && python init_db.py
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | PostgreSQL connection string |
| `SECRET_KEY` | ✅ | — | JWT signing secret (min 32 chars) |
| `ALGORITHM` | ❌ | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ❌ | `1440` | Token lifetime (24h) |
| `STALE_THRESHOLD_SECONDS` | ❌ | `45` | Seconds before agent marked offline |
| `PG_POOL_MIN` | ❌ | `2` | Min DB connections in pool |
| `PG_POOL_MAX` | ❌ | `20` | Max DB connections in pool |

---

## Default Credentials

> **Change immediately after first login.**

| Username | Password | Role |
|---|---|---|
| `admin` | `Admin@PrintHub2026` | Super Admin |

---

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/login` | Login, returns JWT cookie |
| `POST` | `/auth/logout` | Clear session |
| `GET` | `/auth/me` | Current user info |
| `POST` | `/auth/change-password` | Change password |

### Dashboard & Health
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | System health (includes `ws_agents` count) |
| `GET` | `/dashboard` | Stats (printers, jobs, agents) |
| `GET` | `/admin/job-health` | Stale job warnings |
| `WS` | `/ws?token=JWT` | Real-time dashboard WebSocket |
| `WS` | `/ws/agent?agent_id=X&token=Y` | Real-time agent WebSocket |

### Printers
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/printers` | List all printers |
| `POST` | `/printers` | Add printer |
| `PUT` | `/printers/{id}` | Update printer |
| `DELETE` | `/printers/{id}` | Delete printer |

### Print Jobs
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/print-jobs` | List jobs with filters |
| `POST` | `/print-job` | Submit job (triggers WS push to agent) |
| `POST` | `/print-jobs/{id}/retry` | Retry failed job |
| `DELETE` | `/print-jobs/{id}` | Delete job |

### Agents
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/agents` | List all registered agents |
| `POST` | `/agent/register` | Agent self-registration |
| `GET` | `/agent/jobs` | Agent polls for work (HTTP fallback) |
| `GET` | `/agent/job/{id}/file` | Stream job file to agent |
| `POST` | `/agent/confirm` | Agent reports success |
| `POST` | `/agent/fail` | Agent reports failure |
| `POST` | `/agent/heartbeat` | Agent keepalive |
| `POST` | `/agent/printer-status` | Agent reports USB printer status |
| `GET` | `/agent/config` | Agent fetches mapped printers |
| `DELETE` | `/agents/{id}` | Deregister agent |
| `POST` | `/agents/generate-code` | Generate activation code |

### Locations & Categories
| Method | Endpoint | Description |
|---|---|---|
| `GET/POST/DELETE` | `/locations` | Manage hospital locations |
| `GET/POST` | `/categories` | Manage printer categories |

### Users (Admin only)
| Method | Endpoint | Description |
|---|---|---|
| `GET/POST/PUT/DELETE` | `/users` | Full user management |
| `POST` | `/users/{id}/reset-password` | Reset user password |

---

## RBAC Roles

| Role | Dashboard | Print Jobs | Printers | Users | Agents |
|---|---|---|---|---|---|
| **Super Admin** | ✅ | Full | Full | Full | Full |
| **Admin** | ✅ | Full | Full | View | View |
| **Clinical** | Read | Submit | View | ❌ | ❌ |
| **Agent** | ❌ | Poll/Report | ❌ | ❌ | ❌ |

---

## WebSocket Events

### Dashboard WebSocket (`/ws?token=JWT`)

| Event Type | Triggered When |
|---|---|
| `job_update` | A print job status changes |
| `printer_update` | A printer status changes |
| `agent_update` | An agent connects / goes offline |
| `dashboard_refresh` | General stats changed |

### Agent WebSocket (`/ws/agent?agent_id=X&token=Y`)

| Event Type | Direction | Description |
|---|---|---|
| `job_available` | Server → Agent | New job queued at agent's location |
| `ping` | Agent → Server | Keepalive |
| `pong` | Server → Agent | Keepalive response |

---

## Troubleshooting

### Agent shows "Offline" immediately after connecting
**Cause:** Workstation clock skewed or heartbeat blocked by firewall.  
**Fix:** `w32tm /resync` on Windows. Check outbound TCP 8000 is allowed.

### Agent WebSocket stays disconnected (backoff loop in logs)
**Cause:** Nginx proxy missing WebSocket upgrade headers.  
**Fix:** Add to nginx config:
```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

### "Registration code invalid or expired"
**Cause:** Codes expire after 10 minutes.  
**Fix:** Generate new code in dashboard → **Agents → Generate Code**.

### Print job stays "Pending" — never picked up
**Cause:** No agent online for that location, or agent crashed.  
**Fix:** Check **Agents** page. View `C:\PrintHubAgent\agent.log` for errors.

### Windows Service "did not respond to the start or control request in a timely fashion"
**Cause:** Old `agent_service.py` called `agent_thread.join(timeout=30)` inside `SvcDoRun`, blocking the service thread for 30 s before reporting `SERVICE_RUNNING`. SCM times out after ~30 s and marks the service as failed.  
**Fix:** `agent_service.py` now reports `SERVICE_RUNNING` **immediately** at the start of `SvcDoRun` and uses `WaitForSingleObject(hWaitStop, INFINITE)` for clean shutdown. After pulling the latest code, reinstall the service:
```cmd
cd C:\PrintHubAgent
venv\Scripts\python.exe agent_service.py stop
venv\Scripts\python.exe agent_service.py remove
venv\Scripts\python.exe agent_service.py --startup auto install
venv\Scripts\python.exe agent_service.py start
sc query PrintHubAgent
```
Expected: `STATE: 4 RUNNING`.

### `UnicodeEncodeError: 'charmap' codec can't encode character` on Windows Service start
**Cause:** Windows default console encoding is `cp1252`, which cannot represent Unicode characters (`→`, `—`, `…`). The logging `StreamHandler` writes to this stream, crashing the service on startup before any log file is created.  
**Fix:** `agent.py` now calls `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` on Windows at startup, opens the `RotatingFileHandler` with `encoding="utf-8"`, and replaces all Unicode characters in log strings with ASCII equivalents (`->`, `-`, `...`). Pull the latest version — no manual config change needed.

### Dashboard shows "Something went wrong" error boundary on every load
**Cause:** JavaScript Temporal Dead Zone (TDZ) — `handleWsMessage` useCallback referenced `loadAgents` in its `deps` array, but `loadAgents` was declared with `const` 11 lines **below** that reference. Every render synchronously threw `ReferenceError: Cannot access 'loadAgents' before initialization`, which the React ErrorBoundary caught and replaced with the error screen.  
**Fix:** `Dashboard.jsx` now declares `loadAgents` and its `useEffect` before `handleWsMessage`. Pull the latest version.

### Loading skeleton animations not playing (static gray blocks, no shimmer)
**Cause:** `Skeleton.jsx` used `className="skeleton-shimmer"` but the shimmer keyframe animation in `index.css` is attached to `.skeleton`, not `.skeleton-shimmer`. The animation was never applied.  
**Fix:** Changed to `className="skeleton"` and removed duplicate inline background styles. Pull the latest version.

### Sidebar brand section has excessive dead space at the top
**Cause:** A `marginBottom: "30px"` inline style was applied to the inner flex div inside the `.brand` container, creating visible dead space. The `<nav>` element also lacked `flex: 1; overflow-y: auto`, causing content layout issues.  
**Fix:** Removed the `marginBottom`, added `flex: 1; overflow-y: auto` to `<nav>`, set `flex-shrink: 0` on `.brand`, and added `overflow: hidden` to `.sidebar`. Pull the latest version.

### `ModuleNotFoundError: No module named 'websocket'`
**Cause:** `websocket-client` not installed (different from the `websocket` package).  
**Fix:** `pip install websocket-client>=1.6.0` — note the package name includes `-client`.

### `ModuleNotFoundError: No module named 'win32print'`
**Cause:** pywin32 not installed for this Python version.  
**Fix:** `pip install pywin32` then `python Scripts/pywin32_postinstall.py -install` as Administrator.

### Frontend blank / "Cannot connect to API"
**Cause:** `VITE_API_URL` wrong or backend not running.  
**Fix:** `curl http://SERVER:8000/health` — if that fails, restart backend.

---

## Project Structure

```
print_centre/
├── backend/
│   ├── main.py              # FastAPI app — routes, WebSocket (dashboard + agent), lifespan
│   ├── database.py          # PostgreSQL ThreadedConnectionPool
│   ├── models.py            # Pydantic models
│   ├── auth.py              # JWT helpers
│   ├── config.py            # Settings from .env
│   ├── init_db.py           # Schema init + admin seed
│   ├── requirements.txt
│   ├── services/
│   │   ├── recovery.py      # Stuck job auto-recovery
│   │   ├── alerts.py        # Operator alert system
│   │   ├── routing_service.py
│   │   ├── barcode_service.py
│   │   └── auth.py
│   └── .env                 # (create this — not in git)
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css          # Component styles
│   │   ├── index.css        # Design tokens + utilities
│   │   ├── config.js        # API_BASE_URL + WS_BASE_URL
│   │   ├── context/
│   │   │   ├── AuthContext.jsx
│   │   │   └── AppData.jsx       # Global data + WS printer updates
│   │   ├── hooks/
│   │   │   └── useWebSocket.js   # Auto-reconnecting WS hook
│   │   └── pages/
│   │       ├── Dashboard.jsx
│   │       ├── Printers.jsx
│   │       ├── PrintJobs.jsx
│   │       ├── Agents.jsx
│   │       ├── Users.jsx
│   │       ├── AuditLogs.jsx
│   │       └── Login.jsx
│   ├── .env                 # (create this — not in git)
│   └── package.json
│
├── agent/
│   ├── agent.py             # Main agent loop + WebSocket client (AgentWebSocket)
│   ├── agent_config.py      # Config R/W with secure permissions (chmod 600 / icacls)
│   ├── agent_setup.py       # Setup wizard (--code, --server, --no-verify, --reset)
│   ├── agent_service.py     # Windows Service wrapper (pywin32)
│   ├── agent_macos.py       # macOS CUPS integration
│   ├── requirements.txt     # requests, websocket-client, pywin32, wmi
│   ├── install_agent.bat    # Windows installer (prompts, installs service)
│   └── install_agent.sh     # macOS (launchd) + Linux (systemd) installer
│
└── PrintHub_Agent.zip       # Distributable agent package (all agent/ files)
```

---

## License

Proprietary — Savetha Hospital Network. All rights reserved.

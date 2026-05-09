# PrintHub — Clinical-Grade Hospital Print Management System

**PrintHub** is a production-level, high-reliability hybrid printing infrastructure designed for modern hospital environments. It connects a central FastAPI server to local USB and network printers across multiple nursing workstations, with a full React admin dashboard, HIPAA-compliant audit logging, and cross-platform print agents (Windows & macOS).

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
7. [How the Agent Connects to the Server](#how-the-agent-connects-to-the-server)
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
┌─────────────────────────────────────────────────────────────────┐
│                     HOSPITAL NETWORK                            │
│                                                                 │
│  ┌──────────────────┐        ┌──────────────────────────────┐  │
│  │   React Frontend │◄──WS──►│    FastAPI Backend           │  │
│  │   (Admin UI)     │◄─HTTP─►│    + PostgreSQL Pool         │  │
│  │   Port 5173      │        │    + APScheduler             │  │
│  └──────────────────┘        │    Port 8000                 │  │
│                               └──────────┬───────────────────┘  │
│                                          │ REST API (outbound)  │
│                               ┌──────────▼───────────────────┐  │
│                               │  Print Agents (Windows/Mac)  │  │
│                               │  Polling /agents/poll        │  │
│                               │  every 8 seconds             │  │
│                               └──────────┬───────────────────┘  │
│                                          │ USB / LAN            │
│                               ┌──────────▼───────────────────┐  │
│                               │  Physical Printers           │  │
│                               │  USB + Network               │  │
│                               └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Data Flow:**
1. Clinical staff submits print job via React UI → FastAPI queues job in PostgreSQL
2. Print agent polls `/agents/poll` → receives pending job → sends to local printer
3. Agent reports result via `/agents/report` → FastAPI updates DB + broadcasts WebSocket event
4. React dashboard receives WebSocket event → updates in real-time (no page refresh needed)

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, FastAPI, APScheduler, psycopg2 |
| **Database** | PostgreSQL 14+ (with ThreadedConnectionPool) |
| **Frontend** | React 18, Vite, React Router v6 |
| **Real-time** | WebSocket (native FastAPI + custom React hook) |
| **Auth** | JWT (HS256), HTTP-only cookie session |
| **Agent (Windows)** | Python 3.11+, win32print, pywin32, WMI |
| **Agent (macOS)** | Python 3.11+, CUPS via lpstat/lp subprocess |
| **Process Manager** | Windows: NSSM service / Task Scheduler; macOS: launchd plist |
| **Styling** | Pure CSS (no Tailwind), CSS custom properties |

---

## Prerequisites

Install these on **every machine** (server + workstations):

- **Python 3.11+** — [python.org/downloads](https://www.python.org/downloads/)
- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **PostgreSQL 14+** — [postgresql.org/download](https://www.postgresql.org/download/)
- **Git** — [git-scm.com](https://git-scm.com/)

On Windows workstations (agent only):
- **pywin32** (installed automatically by agent installer)

---

## Step-by-Step: Running the Project

### 1. Backend Setup

> Run these commands on your **server machine** (the machine running the FastAPI backend).

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

**Step 3 — Install Python dependencies:**
```bash
pip install -r backend/requirements.txt
```

**Step 4 — Configure environment variables:**

Create a file called `.env` inside the `backend/` folder:
```env
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/printhub
SECRET_KEY=your-very-long-random-secret-key-change-this
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
STALE_THRESHOLD_SECONDS=45
PG_POOL_MIN=2
PG_POOL_MAX=20
```

> Generate a strong SECRET_KEY with: `python -c "import secrets; print(secrets.token_hex(32))"`

**Step 5 — Initialize the database:**
```bash
cd backend
python init_db.py
```

This creates all tables and seeds the default admin user.

**Step 6 — Start the backend server:**
```bash
# From the backend/ directory
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Production (no --reload):
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

The API is now running at `http://YOUR_SERVER_IP:8000`

> Verify it works: open `http://localhost:8000/health` in your browser — you should see `{"status":"ok",...}`

---

### 2. Frontend Setup

> Run these commands on the **same machine** as the backend (or any machine on the same network).

**Step 1 — Navigate to the frontend directory:**
```bash
cd frontend
```

**Step 2 — Install Node.js dependencies:**
```bash
npm install
```

**Step 3 — Configure the API URL:**

Create a file called `.env` inside the `frontend/` folder:
```env
VITE_API_URL=http://YOUR_SERVER_IP:8000
```

Replace `YOUR_SERVER_IP` with the actual IP address of your backend server (e.g., `192.168.1.100`).

For local development:
```env
VITE_API_URL=http://127.0.0.1:8000
```

**Step 4 — Start the development server:**
```bash
npm run dev
```

The dashboard is now at `http://localhost:5173`

**Step 5 — Build for production (optional):**
```bash
npm run build
# Serve the dist/ folder with nginx or any static host
```

---

## Agent Installation — Windows

> Perform these steps on **each Windows workstation** that has a printer attached.

### Prerequisites
- Python 3.11+ installed and added to PATH
- The workstation can reach the server on port 8000 (check firewall)

### Step-by-Step Installation

**Step 1 — Copy the agent to the workstation.**

Option A — USB drive: Copy `PrintHub_Agent.zip` to the workstation and extract to `C:\PrintHubAgent\`

Option B — Network share: Copy from `\\SERVER\share\PrintHub_Agent.zip`

After extraction you should have:
```
C:\PrintHubAgent\
  agent.py
  agent_config.py
  agent_setup.py
  requirements.txt
  install_agent.bat
```

**Step 2 — Open Command Prompt as Administrator.**

Press `Win + R`, type `cmd`, press `Ctrl+Shift+Enter`.

**Step 3 — Run the installer:**
```cmd
cd C:\PrintHubAgent
install_agent.bat
```

The installer will:
- Check Python is installed
- Install Python packages (`requests`, `pywin32`, `wmi`, `urllib3`)
- Prompt you for the server URL (`http://SERVER_IP:8000`)
- Prompt you for a registration code (get this from the admin dashboard under **Agents → Generate Code**)
- Save config securely to `C:\PrintHubAgent\agent_config.json`
- Install the agent as a **Windows Service** using Task Scheduler

**Step 4 — Verify the agent registered.**

In the PrintHub admin dashboard, go to **Agents**. Within 30 seconds you should see a new agent appear with status "Connected" showing this workstation's hostname.

**Step 5 — (Optional) Run manually to see logs:**
```cmd
cd C:\PrintHubAgent
python agent.py
```

Logs are written to `C:\PrintHubAgent\agent.log` (rotating, max 5 MB × 3 files).

**Step 6 — Manage the service:**
```cmd
# Check status
schtasks /query /tn "PrintHubAgent" /fo LIST

# Stop the agent
schtasks /end /tn "PrintHubAgent"

# Start the agent
schtasks /run /tn "PrintHubAgent"

# Remove the agent service
schtasks /delete /tn "PrintHubAgent" /f
```

**Step 7 — Update the agent (when a new version is released):**
```cmd
# Stop the service first
schtasks /end /tn "PrintHubAgent"

# Overwrite agent.py and agent_config.py with new versions
# Your config (server URL, credentials) is preserved in agent_config.json

# Restart
schtasks /run /tn "PrintHubAgent"
```

### Security on Windows
- `agent_config.json` permissions are set to the current user only (via `icacls`)
- The agent never opens inbound ports — outbound HTTP only
- All credentials are stored in the local config file, not in the registry or environment
- TLS verification is enabled by default; disable only for self-signed certificates with `python agent_setup.py --no-verify`

---

## Agent Installation — macOS

> Perform these steps on **each macOS workstation** that has a printer attached.

### Prerequisites
- Python 3.11+ (`brew install python` or [python.org](https://www.python.org/downloads/))
- CUPS enabled (enabled by default on macOS)
- Terminal access

### Step-by-Step Installation

**Step 1 — Copy and extract the agent:**
```bash
cp /Volumes/USB/PrintHub_Agent.zip ~/Downloads/
cd ~/Downloads
unzip PrintHub_Agent.zip -d ~/PrintHubAgent
cd ~/PrintHubAgent
```

**Step 2 — Install Python dependencies:**
```bash
pip3 install -r requirements.txt
```

**Step 3 — Run the setup wizard:**
```bash
python3 agent_setup.py
```

Enter when prompted:
- **Server URL**: `http://SERVER_IP:8000`
- **Registration code**: from admin dashboard under **Agents → Generate Code**

The config is saved to `~/.printhub/agent_config.json` with `chmod 600` permissions.

**Step 4 — Install as a background service (launchd):**
```bash
bash install_agent.sh
```

This creates a launchd plist at `~/Library/LaunchAgents/com.printhub.agent.plist` and loads it immediately.

**Verify it is running:**
```bash
launchctl list | grep printhub
# Should show: -  0  com.printhub.agent
```

**Manage the service:**
```bash
# Stop
launchctl unload ~/Library/LaunchAgents/com.printhub.agent.plist

# Start
launchctl load ~/Library/LaunchAgents/com.printhub.agent.plist

# View live logs
tail -f ~/Library/Logs/PrintHubAgent/agent.log

# Remove permanently
launchctl unload ~/Library/LaunchAgents/com.printhub.agent.plist
rm ~/Library/LaunchAgents/com.printhub.agent.plist
```

### Security on macOS
- Config file at `~/.printhub/agent_config.json` has `chmod 600` (owner read/write only)
- Log directory `~/Library/Logs/PrintHubAgent/` is user-private
- Agent uses CUPS `lp` and `lpstat` commands — no root access required
- Outbound HTTP only — no inbound ports opened
- TLS verification enabled by default

---

## How the Agent Connects to the Server

The agent uses **outbound-only HTTP polling**. It never opens any ports or accepts inbound connections.

```
WORKSTATION                         SERVER (port 8000)
    │                                       │
    │──── POST /agents/register ───────────►│  (once, on first run)
    │◄─── { agent_id, token } ─────────────│
    │                                       │
    │  ┌─── Every 8 seconds ───────────┐   │
    │  │                               │   │
    │  │──── GET /agents/poll ────────►│   │
    │  │◄─── { job_id, pdf_url, ... } ─│   │
    │  │                               │   │
    │  │  [sends job to local printer] │   │
    │  │                               │   │
    │  │──── POST /agents/report ─────►│   │
    │  │◄─── { ok: true } ────────────│   │
    │  └───────────────────────────────┘   │
    │                                       │
    │──── POST /agents/heartbeat ──────────►│  (every 30 seconds)
    │◄─── { ok: true } ─────────────────────│
```

**Authentication flow:**
1. Agent calls `/agents/register` with a one-time registration code (generated in admin dashboard)
2. Server returns a permanent `agent_token` stored in `agent_config.json`
3. All subsequent requests include `Authorization: Bearer <agent_token>`
4. The token never expires unless the agent is deleted from the dashboard

**Job execution flow:**
1. Agent polls `/agents/poll` — if a job is queued for its location, the server returns job details
2. Agent downloads the PDF (if remote URL) or uses already-queued data
3. Agent sends the file to the local printer via win32print (Windows) or CUPS `lp` (macOS)
4. Agent reports success/failure to `/agents/report`
5. Server broadcasts a WebSocket event to all connected dashboard clients

**Error handling:**
- On network error: agent waits 5s, then retries with exponential backoff (max 60s delay)
- On printer error: reported to server, job marked as failed, self-healing scheduler retries eligible jobs
- On server unavailable (500/502/503/504): HTTP adapter retries up to 3 times automatically

---

## Firewall Configuration

The agent only needs **outbound** access. No inbound rules are required on workstations.

| Machine | Direction | Protocol | Port | Purpose |
|---|---|---|---|---|
| Workstation | **Outbound** | TCP | 8000 | Agent → Server API |
| Server | Inbound | TCP | 8000 | Accept agent + dashboard connections |
| Server | Inbound | TCP | 5173 | Accept frontend dev server (dev only) |
| Server | Inbound | TCP | 80/443 | Accept frontend (production with nginx) |

### Windows Firewall — Allow outbound to server
```cmd
# Run as Administrator
netsh advfirewall firewall add rule name="PrintHub Agent" dir=out action=allow protocol=TCP remoteport=8000
```

### macOS Firewall
macOS Application Firewall blocks **inbound** by default but allows all **outbound**.
No changes needed — the agent will work with the firewall enabled as long as the server is reachable.

### Corporate / Hospital Network
If the workstation is behind a web proxy, set these environment variables before running the agent:
```bash
# Windows
set HTTPS_PROXY=http://proxy.hospital.local:3128

# macOS / Linux
export HTTPS_PROXY=http://proxy.hospital.local:3128
```

---

## PostgreSQL Setup

**Step 1 — Install PostgreSQL 14+:**
- Windows: [postgresql.org/download/windows](https://www.postgresql.org/download/windows/)
- macOS: `brew install postgresql@14`
- Ubuntu: `sudo apt install postgresql postgresql-contrib`

**Step 2 — Create the database and user:**
```sql
-- Connect as postgres superuser
psql -U postgres

CREATE DATABASE printhub;
CREATE USER printhub_user WITH PASSWORD 'strong_password_here';
GRANT ALL PRIVILEGES ON DATABASE printhub TO printhub_user;
\q
```

**Step 3 — Update .env:**
```env
DATABASE_URL=postgresql://printhub_user:strong_password_here@localhost:5432/printhub
```

**Step 4 — Run migrations:**
```bash
cd backend
python init_db.py
```

---

## Environment Variables Reference

Create `backend/.env` with these variables:

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | Full PostgreSQL connection string |
| `SECRET_KEY` | ✅ | — | JWT signing key (min 32 chars) |
| `ALGORITHM` | ❌ | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ❌ | `1440` | Token lifetime (24h) |
| `STALE_THRESHOLD_SECONDS` | ❌ | `45` | Seconds before agent marked offline |
| `PG_POOL_MIN` | ❌ | `2` | Minimum DB connections in pool |
| `PG_POOL_MAX` | ❌ | `20` | Maximum DB connections in pool |

---

## Default Credentials

> **Change these immediately after first login.**

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | Super Admin |

Login at `http://localhost:5173` → use the credentials above → go to **Settings → Change Password**.

---

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/login` | Login, returns JWT cookie |
| `POST` | `/auth/logout` | Clear session cookie |
| `GET` | `/auth/me` | Current user info |

### Dashboard & Health
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | System health check |
| `GET` | `/dashboard` | Stats (printers, jobs, agents) |
| `GET` | `/admin/job-health` | Stale job warnings |
| `WS` | `/ws?token=JWT` | Real-time WebSocket stream |

### Printers
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/printers` | List all printers |
| `POST` | `/printers` | Add printer |
| `PUT` | `/printers/{id}` | Update printer |
| `DELETE` | `/printers/{id}` | Delete printer |
| `GET` | `/printers/{id}/jobs` | Jobs for a specific printer |

### Print Jobs
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/print-jobs` | List jobs (with filters) |
| `POST` | `/print-job` | Submit new print job |
| `GET` | `/print-jobs/{id}` | Job details |
| `POST` | `/print-jobs/{id}/retry` | Retry failed job |
| `DELETE` | `/print-jobs/{id}` | Delete job |

### Agents
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/agents` | List all registered agents |
| `POST` | `/agents/register` | Agent self-registration |
| `GET` | `/agents/poll` | Agent polls for work |
| `POST` | `/agents/report` | Agent reports job result |
| `POST` | `/agents/heartbeat` | Agent sends heartbeat |
| `DELETE` | `/agents/{id}` | Deregister agent |
| `POST` | `/agents/generate-code` | Generate registration code |

### Locations & Categories
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/locations` | List hospital locations |
| `POST` | `/locations` | Add location |
| `DELETE` | `/locations/{id}` | Delete location |
| `GET` | `/categories` | List printer categories |
| `POST` | `/categories` | Add category |

### Users (Admin only)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/users` | List all users |
| `POST` | `/users` | Create user |
| `PUT` | `/users/{id}` | Update user |
| `DELETE` | `/users/{id}` | Delete user |
| `POST` | `/users/{id}/reset-password` | Reset user password |

### Audit Logs
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/audit-logs` | Paginated audit trail |

---

## RBAC Roles

| Role | Dashboard | Print Jobs | Printers | Users | Agents | Audit Logs |
|---|---|---|---|---|---|---|
| **Super Admin** | ✅ | ✅ Full | ✅ Full | ✅ Full | ✅ Full | ✅ |
| **Admin** | ✅ | ✅ Full | ✅ Full | ✅ View | ✅ View | ✅ |
| **Clinical Professional** | ✅ Read | ✅ Submit only | ✅ View | ❌ | ❌ | ❌ |
| **Agent** | ❌ | Poll/Report only | ❌ | ❌ | ❌ | ❌ |

---

## WebSocket Events

Connect to `ws://SERVER:8000/ws?token=YOUR_JWT_TOKEN`

| Event Type | Triggered When | Payload |
|---|---|---|
| `job_update` | A print job status changes | `{ job_id, status, printer_id }` |
| `printer_update` | A printer status changes | `{ printer_id, status }` |
| `agent_update` | An agent connects/disconnects | `{ agent_id, status }` |
| `dashboard_refresh` | General stats changed | `{}` |

**Frontend usage (auto-handled):**
The `useWebSocket` hook in `frontend/src/hooks/useWebSocket.js` automatically reconnects with exponential backoff (1s → 30s cap) and delivers events to the registered handler function.

---

## Troubleshooting

### ❌ "Database is locked" or connection errors
**Cause:** PostgreSQL pool exhausted or SQLite leftover config.  
**Fix:** Increase `PG_POOL_MAX` in `.env`. Restart the backend. Confirm `DATABASE_URL` points to PostgreSQL, not SQLite.

### ❌ Agent shows "Offline" immediately after registering
**Cause:** Workstation clock skewed, or firewall blocking outbound 8000.  
**Fix:** Sync workstation time (`w32tm /resync` on Windows). Check firewall outbound rule for port 8000.

### ❌ "Registration code invalid or expired"
**Cause:** Codes expire after 10 minutes.  
**Fix:** Generate a new code from **Agents → Generate Code** in the dashboard and re-run `agent_setup.py`.

### ❌ Print job stays "Pending" forever
**Cause:** No agent is online for that location, or agent crashed.  
**Fix:** Check **Agents** page — verify the agent for that location shows "Connected". Check `C:\PrintHubAgent\agent.log` for errors.

### ❌ WebSocket keeps reconnecting (dashboard shows "connecting...")
**Cause:** Backend WebSocket endpoint not reachable (nginx proxy missing `Upgrade` header, or port blocked).  
**Fix:** In nginx, add: `proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`

### ❌ `ModuleNotFoundError: No module named 'win32print'`
**Cause:** pywin32 not installed or not installed for the correct Python version.  
**Fix:** `pip install pywin32` then run `python Scripts/pywin32_postinstall.py -install` from the Python install directory as Administrator.

### ❌ Frontend shows blank page / "Cannot connect to API"
**Cause:** `VITE_API_URL` in `frontend/.env` is wrong, or backend is not running.  
**Fix:** Confirm backend is running (`curl http://SERVER:8000/health`). Update `VITE_API_URL` and restart `npm run dev`.

---

## Project Structure

```
print_centre/
├── backend/
│   ├── main.py              # FastAPI app, lifespan, WebSocket, routes
│   ├── database.py          # PostgreSQL connection pool
│   ├── models.py            # Pydantic request/response models
│   ├── auth.py              # JWT authentication helpers
│   ├── config.py            # Settings (loaded from .env)
│   ├── init_db.py           # Database schema init + admin seed
│   ├── requirements.txt     # Python dependencies
│   └── .env                 # (you create this — not in git)
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Root layout + routing
│   │   ├── App.css          # Component styles
│   │   ├── index.css        # Global design tokens + utilities
│   │   ├── config.js        # API_BASE_URL + WS_BASE_URL
│   │   ├── context/
│   │   │   ├── AuthContext.jsx   # JWT + authFetch hook
│   │   │   └── AppData.jsx       # Global printers/locations/categories
│   │   ├── hooks/
│   │   │   └── useWebSocket.js   # Auto-reconnecting WS hook
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Printers.jsx
│   │   │   ├── PrintJobs.jsx
│   │   │   ├── Agents.jsx
│   │   │   ├── Users.jsx
│   │   │   ├── AuditLogs.jsx
│   │   │   └── Login.jsx
│   │   └── components/
│   │       └── Skeleton.jsx
│   ├── .env                 # (you create this — not in git)
│   └── package.json
│
└── PrintHub_Agent.zip       # Distributable agent package
    ├── agent.py             # Main agent loop
    ├── agent_config.py      # Config read/write with secure permissions
    ├── agent_setup.py       # Interactive setup wizard
    ├── requirements.txt     # Agent dependencies
    ├── install_agent.bat    # Windows installer
    └── install_agent.sh     # macOS/Linux installer
```

---

## License

Proprietary — Savetha Hospital Network. All rights reserved.

# PrintHub — Hospital Print Management System

---

## What is PrintHub?

PrintHub is a system that lets hospital staff send print jobs from a central dashboard to any USB printer in any ward or department — automatically, instantly, over the hospital network.

**Without PrintHub:** A nurse downloads a file, copies it to a USB, walks to a printer, plugs in the USB, prints. Slow and error-prone.

**With PrintHub:** A staff member clicks Print on the dashboard. The printer at the correct ward prints it in seconds. No USB sticks. No walking.

---

## How the System Works (Non-Technical)

Think of PrintHub like a post office inside the hospital:

```
┌─────────────────────────────────────────────────────────────┐
│                    SERVER (runs 24/7)                        │
│                                                             │
│   Dashboard (Frontend)  ◄────►  Backend (Brain)             │
│   Staff open this in         Receives print jobs,           │
│   their browser              stores them, sends to          │
│   Port: 5173                 the right printer PC           │
│                              Port: 8000                     │
└─────────────────────────┬───────────────────────────────────┘
                          │  Hospital Network (WiFi/LAN)
          ┌───────────────┼────────────────┐
          │               │                │
┌─────────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
│  Ward A PC     │ │  ICU PC     │ │  OPD PC     │
│  Agent running │ │  Agent      │ │  Agent      │
│  USB Printer   │ │  USB Printer│ │  USB Printer│
└────────────────┘ └─────────────┘ └─────────────┘
```

**3 parts — 2 locations:**

| Part | What it does | Where it runs |
|---|---|---|
| **Backend** | The brain — manages all print jobs, agents, and users | SERVER only |
| **Frontend** | The dashboard website staff use | SERVER only |
| **Agent** | Receives jobs and prints them | Every PRINTER PC |

---

## How the System Works (Technical)

- **Backend:** Python FastAPI app with SQLite database. Exposes REST API on port 8000 and WebSocket endpoint `/ws/agent` for real-time agent communication.
- **Frontend:** React 18 + Vite SPA. Connects to backend via `VITE_API_URL` (set in `.env`). Served on port 5173 during development.
- **Agent:** Python script on each printer PC. Maintains a persistent WebSocket connection to the backend. Receives `job_available` push events instantly. Falls back to HTTP polling every 30 seconds. Uses `win32print` (Windows) or CUPS `lp` (Mac) to send jobs to the physical printer.
- **Authentication:** JWT (HS256). All API routes are protected. The admin account is seeded at backend startup.
- **Real-time:** Both the dashboard and agents use WebSocket connections — the dashboard shows live agent status and job updates without refreshing.

---

## Project Structure

```
print_centre/
├── backend/
│   ├── main.py              # FastAPI app — all routes, WebSocket, startup
│   ├── database.py          # SQLite schema and DB helpers
│   ├── config.py            # Settings loaded from .env
│   ├── requirements.txt     # Python packages
│   ├── start_backend.bat    # One-click start (Windows)
│   ├── .env                 # Your local config (NOT in git)
│   └── services/
│       ├── auth.py          # JWT + password hashing
│       ├── routing_service.py  # Printer failover logic
│       ├── barcode_service.py  # Label/barcode generation
│       └── audit.py         # Audit log writing
│
├── frontend/
│   ├── src/
│   │   ├── config.js        # Reads VITE_API_URL from .env
│   │   └── pages/           # Dashboard, Agents, Printers, Jobs, Users...
│   ├── .env                 # VITE_API_URL — must be server's network IP
│   ├── vite.config.js       # Port 5173, host: true
│   ├── start_frontend.bat   # One-click start (Windows)
│   └── package.json
│
└── agent/                   # Source — also published separately:
    ├── agent.py             # Main agent loop + WebSocket + print
    ├── agent_config.py      # Read/write local config file
    ├── agent_setup.py       # One-time registration with activation code
    ├── requirements.txt     # Agent Python packages
    ├── install_agent.bat    # Windows installer
    └── install_agent.sh     # Mac/Linux installer
```

---

## Default Login

| Username | Password |
|---|---|
| `admin` | `Admin@PrintHub2026` |

The admin account is created automatically the first time the backend starts. Change the password after first login.

---

---

# PART 1 — Start the Backend

The backend is the brain. It must be running before anything else.

## Windows

### First time only

**Step 1 — Download the project**
```powershell
cd C:\Users\YourName\Desktop
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
cd print_centre\backend
```

**Step 2 — Create virtual environment**
```powershell
python -m venv venv
```

**Step 3 — Install packages**
```powershell
.\venv\Scripts\pip.exe install -r requirements.txt
```

**Step 4 — Configure `.env`**

Open `backend\.env` in Notepad:
```powershell
notepad .env
```

Check that these values are set correctly:
```
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development
JWT_SECRET_KEY=<any long random string>
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://YOUR_SERVER_IP:5173
DATABASE_PATH=./printhub.db
```

Replace `YOUR_SERVER_IP` with your server's actual IP address. To find it:
```powershell
ipconfig
```
Look for **IPv4 Address** — example: `192.168.1.14`

### Every day — start the backend

Double-click this file in File Explorer:
```
backend\start_backend.bat
```

Or run in PowerShell:
```powershell
cd backend
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

You will see:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Do not close this window.** The backend stops if you close it.

**Verify it is working** — open a browser and go to:
```
http://localhost:8000/health
```
You should see: `{"status": "healthy", ...}`

---

## Mac / Linux

### First time only

```bash
cd ~/Desktop
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
cd print_centre/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

Update `ALLOWED_ORIGINS` to include your server's IP:
```
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://YOUR_SERVER_IP:5173
```

Press `Ctrl+X` → `Y` → Enter to save.

### Every day — start the backend

```bash
cd ~/Desktop/print_centre/backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Do not close this Terminal.** Open a new tab for the frontend.

---

---

# PART 2 — Start the Frontend

The frontend is the dashboard website. It runs on the same machine as the backend.

## Windows

### First time only

**Step 1 — Install Node.js** (if not already installed)
Go to [nodejs.org](https://nodejs.org/) → download LTS → install it.
Verify: open PowerShell → `node --version` → should show `v18.x.x` or higher.

**Step 2 — Go to the frontend folder**
```powershell
cd C:\Users\YourName\Desktop\print_centre\frontend
```

**Step 3 — Install JavaScript packages**
```powershell
npm install
```
This takes 1–2 minutes.

**Step 4 — Configure `.env`**
```powershell
notepad .env
```

You will see:
```
VITE_API_URL=http://192.168.1.14:8000
```

Replace `192.168.1.14` with your server's actual IP address (same IP you used in the backend `.env`).

> **Why this matters:** This URL is baked into the frontend bundle. When any PC on the network opens the dashboard, their browser uses this URL to reach the backend. If you put `127.0.0.1` here, it will only work on the server itself — not from other PCs.

### Every day — start the frontend

Double-click:
```
frontend\start_frontend.bat
```

Or run in PowerShell:
```powershell
cd frontend
npm run dev
```

You will see:
```
VITE ready in 261ms
  Local:   http://localhost:5173/
  Network: http://192.168.1.14:5173/
```

**Do not close this window.**

**Open the dashboard:**
- On the server PC: `http://localhost:5173`
- From any other PC on the network: `http://YOUR_SERVER_IP:5173`

---

## Mac / Linux

### First time only

```bash
cd ~/Desktop/print_centre/frontend
npm install
nano .env
```

Set `VITE_API_URL` to your server's IP:
```
VITE_API_URL=http://YOUR_SERVER_IP:8000
```

Press `Ctrl+X` → `Y` → Enter.

### Every day — start the frontend

Open a **new Terminal tab** (keep the backend tab open):
```bash
cd ~/Desktop/print_centre/frontend
npm run dev
```

Open the dashboard: `http://localhost:5173`

---

---

# PART 3 — Install the Agent on Printer PCs

The agent is installed on every PC that has a USB printer. It runs silently in the background and starts automatically at every login.

**You install it once. It runs forever automatically.**

## Before installing — generate an activation code

1. Open the dashboard → click **Activation Codes** in the left menu
2. Click **Generate Code**
3. Note down the 8-character code (example: `6F166AC4`)

> Codes expire in 10 minutes. Generate one right before you install.

---

## Windows — Install the Agent

### Step 1 — Download the agent files

Download the agent from:
**https://github.com/MANIBAALAKRISHNANS/PrintHub_agent**

Click **Code → Download ZIP** → extract the ZIP → you get a folder like `PrintHub_agent-main`.

Or copy the `agent` folder from the main project — it contains the same files.

The folder must contain:
```
PrintHub_agent-main\
├── agent.py
├── agent_config.py
├── agent_setup.py
├── agent_service.py
├── requirements.txt
└── install_agent.bat    ← the installer
```

### Step 2 — Right-click → Run as administrator

In File Explorer, find `install_agent.bat`.

**Right-click** on it → **Run as administrator**

> Do NOT just double-click. It must say "Run as administrator". If Windows asks "Allow this app to make changes?" click **Yes**.

A black window opens. It will stay open the whole time.

### Step 3 — Answer the questions

```
Server IP address (e.g. 192.168.1.14):
```
→ Type the server's IP address. Example: `192.168.1.14`

```
Server port (press Enter for 8000):
```
→ Just press **Enter**

```
Use HTTPS? (y/N):
```
→ Just press **Enter**

```
Enter the 8-character activation code:
```
→ Type the code from the dashboard. Example: `6F166AC4`

### Step 4 — Wait for it to complete

You will see all these lines appear:
```
[OK] Running as Administrator
[OK] Python 3.x found
[STEP 1] Preparing C:\PrintHubAgent...
[OK] Files copied to C:\PrintHubAgent
[STEP 2] Creating virtual environment...
[OK] Virtual environment created.
[STEP 3] Installing dependencies...
[OK] Dependencies installed.
[STEP 4] Checking configuration...
[OK] Configuration saved.
[STEP 5] Creating Task Scheduler task...
[OK] Task Scheduler task created (auto-starts at every login).
[STEP 6] Starting agent now...
[OK] Agent started in background.

============================================================
  SUCCESS! PrintHub Agent is installed and running.
  It will start automatically every time you log in.
============================================================
```

Press any key to close. **Installation is complete.**

---

## Mac — Install the Agent

### Step 1 — Download the agent files

Download from **https://github.com/MANIBAALAKRISHNANS/PrintHub_agent** → Code → Download ZIP → extract.

Or copy the `agent` folder from the main project.

### Step 2 — Open Terminal

Press `Cmd + Space` → type **Terminal** → press Enter.

### Step 3 — Run the installer

```bash
cd ~/Desktop/PrintHub_agent-main
bash install_agent.sh
```

The installer will ask for:
- Server IP address (e.g. `192.168.1.14`)
- Server port (press Enter for 8000)
- HTTPS? (press Enter for No)
- Activation code from the dashboard

### Step 4 — Wait for it to complete

You will see:
```
[OK] Python 3.x found
[OK] Virtual environment ready
[OK] Dependencies installed.
[OK] Configuration saved.
[STEP 4] Setting up launchd auto-start service...
[OK] launchd service created.

SUCCESS! PrintHub Agent is installed and running.
It starts automatically at every login.
```

---

---

# PART 4 — Verify the Agent is Connected

## Windows — 5 ways to check

### Method 1 — Dashboard (easiest)

Open the PrintHub Dashboard → click **Agents** in the left menu.

This PC should appear with a green **Online** badge within 15–30 seconds.

### Method 2 — Command Prompt (if the install window is still open)

The install window shows `C:\Windows\System32>`. Type:
```cmd
type C:\PrintHubAgent\agent.log
```

### Method 3 — Open a new Command Prompt

Press `Win + R` → type `cmd` → press Enter. Then run:
```cmd
type C:\PrintHubAgent\agent.log
```

### Method 4 — PowerShell

Press `Win + X` → click **Terminal** or **PowerShell**. Then run:
```powershell
Get-Content C:\PrintHubAgent\agent.log -Tail 20
```

### Method 5 — Notepad

```cmd
notepad C:\PrintHubAgent\agent.log
```

**What to look for in the log:**
```
[WS] Connected to server
```
This line means the agent is fully connected and working.

**Also check Task Manager:**
Press `Ctrl + Shift + Esc` → **Details** tab → look for `python.exe` — if it is there, the agent is running.

---

## Mac — 4 ways to check

### Method 1 — Dashboard (easiest)

Open the PrintHub Dashboard → click **Agents**.
This Mac should appear with a green **Online** badge within 15–30 seconds.

### Method 2 — Last 20 lines of the log

Open Terminal and run:
```bash
tail -20 ~/Library/Logs/PrintHubAgent/agent.log
```

### Method 3 — Watch live log output

```bash
tail -f ~/Library/Logs/PrintHubAgent/agent.log
```
Press `Ctrl + C` to stop.

### Method 4 — Check if the service is registered

```bash
launchctl list | grep printhub
```
If a line appears, the service is loaded and running.

**What to look for in the log:**
```
[WS] Connected to server
```

---

---

# PART 5 — Full Project Details

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, APScheduler, SQLite |
| WebSocket server | uvicorn + websockets |
| Frontend | React 18, Vite, React Router v6 |
| Real-time dashboard | WebSocket `/ws` |
| Real-time agents | WebSocket `/ws/agent` |
| Authentication | JWT HS256 |
| Agent — Windows | Python, win32print, pywin32, websocket-client |
| Agent — Mac | Python, CUPS (lp/lpstat), websocket-client |

## Dashboard Pages

| Page | What it does |
|---|---|
| **Dashboard** | Overview — active agents, pending jobs, printer status |
| **Printers** | Add and manage physical printers |
| **Locations / Mapping** | Map each department to its printers |
| **Print Jobs** | View all print jobs, retry failed ones |
| **Agents** | See all agent PCs — Online/Offline status |
| **Users** | Create and manage staff accounts |
| **Activation Codes** | Generate codes to register new agent PCs |
| **Audit Logs** | Full history of every action |

## How a Print Job Flows (step by step)

```
1. Staff clicks Print on the dashboard
2. Frontend sends HTTP POST to backend (port 8000)
3. Backend saves the job in the database (status: pending)
4. Backend sends a WebSocket push "job_available" to the correct agent
5. Agent receives the push instantly (< 1 second)
6. Agent fetches the job details via HTTP GET
7. Agent sends the document to the USB printer via win32print / CUPS
8. Agent reports success → backend updates job status to "printed"
9. Dashboard updates in real time (WebSocket push to browser)
```

## What Happens if the Network Drops?

- The agent's WebSocket connection breaks
- The agent reconnects automatically (every 10 seconds)
- While disconnected, the agent falls back to polling every 30 seconds
- Any jobs that arrived during downtime are picked up on reconnect
- The dashboard shows the agent as "Offline" until it reconnects

## Environment Variables — Backend (`backend/.env`)

| Variable | Default | What it does |
|---|---|---|
| `HOST` | `0.0.0.0` | Listen on all network interfaces (required for other PCs to connect) |
| `PORT` | `8000` | Port the backend listens on |
| `ENVIRONMENT` | `development` | Set to `production` on a real hospital server |
| `JWT_SECRET_KEY` | (long hex string) | Secret for signing login tokens — keep this private |
| `ALLOWED_ORIGINS` | (comma-separated URLs) | Which browser addresses can talk to the backend |
| `DATABASE_PATH` | `./printhub.db` | Where the SQLite database is stored |
| `STALE_THRESHOLD_SECONDS` | `45` | Seconds without heartbeat before agent is marked Offline |
| `MAX_RETRY_COUNT` | `3` | Times a failed job is retried automatically |

## Environment Variables — Frontend (`frontend/.env`)

| Variable | What it does |
|---|---|
| `VITE_API_URL` | Full URL of the backend. Must be the server's network IP so browsers from other PCs can reach it. |

---

---

# PART 6 — Deployment: What to Update and Where

When you deploy PrintHub on a real server (or change the server PC), you must update the IP address in exactly **2 files**. Here is exactly what to change and where.

---

## Step 1 — Find your server's IP address

On the server PC, open a terminal and run:

**Windows:**
```powershell
ipconfig
```
Look for **IPv4 Address** under your network adapter. Example: `192.168.1.14`

**Mac/Linux:**
```bash
ifconfig | grep "inet "
```
Or on Linux: `hostname -I`

Note this IP down. You will use it in the next 2 steps.

---

## Step 2 — Update `frontend/.env`

**File location:** `print_centre/frontend/.env`

**Open it:**
- Windows: `notepad frontend\.env`
- Mac: `nano frontend/.env`

**Change this line:**
```
VITE_API_URL=http://YOUR_SERVER_IP:8000
```

**Example:**
```
VITE_API_URL=http://192.168.1.14:8000
```

**Why:** This URL is baked into the frontend when it starts. Every browser — on any PC — uses this URL to reach the backend. If it says `127.0.0.1`, only the server itself can use the dashboard. Any other PC on the network will fail to connect.

**After changing:** Restart the frontend (`start_frontend.bat` or `npm run dev`).

---

## Step 3 — Update `backend/.env`

**File location:** `print_centre/backend/.env`

**Open it:**
- Windows: `notepad backend\.env`
- Mac: `nano backend/.env`

**Find this line and update it:**
```
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://YOUR_SERVER_IP:5173
```

**Example:**
```
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.14:5173
```

**Why:** CORS (Cross-Origin Resource Sharing) — the backend only accepts requests from URLs listed here. If the frontend's URL is not in this list, browsers will block all API requests with a CORS error.

**After changing:** Restart the backend (`start_backend.bat` or `uvicorn main:app ...`).

---

## Step 4 — Firewall: open the required ports on the server

Run these commands on the **server PC** (as Administrator on Windows):

**Windows:**
```powershell
netsh advfirewall firewall add rule name="PrintHub Backend" dir=in action=allow protocol=TCP localport=8000
netsh advfirewall firewall add rule name="PrintHub Frontend" dir=in action=allow protocol=TCP localport=5173
```

**Linux:**
```bash
sudo ufw allow 8000
sudo ufw allow 5173
```

**Why:** Without opening these ports, PCs on the network cannot reach the backend (8000) or the dashboard (5173). Agents also connect to port 8000.

---

## Step 5 — When installing the agent on each printer PC

During agent installation (`install_agent.bat`), enter the **same server IP** when asked:
```
Server IP address (e.g. 192.168.1.14): 192.168.1.14
```

The agent saves this in `C:\PrintHubAgent\agent_config.json`. If the server IP ever changes, delete this file and run `install_agent.bat` again.

---

## Complete Deployment Checklist

```
SERVER MACHINE
  [ ] Python 3.11+ installed
  [ ] Node.js 18+ installed
  [ ] backend/.env → ALLOWED_ORIGINS updated with server IP
  [ ] frontend/.env → VITE_API_URL updated with server IP
  [ ] Firewall: port 8000 open (backend)
  [ ] Firewall: port 5173 open (frontend)
  [ ] Backend running (start_backend.bat)
  [ ] Frontend running (start_frontend.bat)
  [ ] Dashboard accessible at http://SERVER_IP:5173

EACH PRINTER PC
  [ ] Python 3.11+ installed
  [ ] Agent files downloaded (PrintHub_agent repo)
  [ ] install_agent.bat run as Administrator
  [ ] Correct server IP entered during install
  [ ] Fresh activation code entered during install
  [ ] Agent appears Online in Dashboard → Agents page
  [ ] Test print job successful
```

---

## Troubleshooting

### Dashboard shows blank page or "Cannot connect"

**Cause:** `VITE_API_URL` in `frontend/.env` is wrong (likely `127.0.0.1` instead of server IP).

**Fix:** Update `frontend/.env` → restart the frontend.

---

### Agent shows Offline in dashboard

**Cause 1 — Agent not running.** Open Command Prompt on printer PC:
```cmd
C:\PrintHubAgent\venv\Scripts\python.exe C:\PrintHubAgent\agent.py
```
Look for `[WS] Connected to server`.

**Cause 2 — Cannot reach server.** On the printer PC, open a browser and go to `http://SERVER_IP:8000/health`. If this does not load, port 8000 is blocked on the server. Open the firewall port.

**Cause 3 — Wrong server IP in agent config.** Delete `C:\PrintHubAgent\agent_config.json` and run `install_agent.bat` again.

---

### `install_agent.bat` closes immediately

**Fix:** You must right-click → **Run as administrator**. Do not just double-click.

---

### Activation code says "invalid or expired"

**Fix:** Codes expire in 10 minutes. Generate a fresh code from Dashboard → Activation Codes → Generate Code.

---

### Backend fails to start — pydantic validation errors

**Fix:** Make sure `backend/.env` does not contain `SERVER_URL` or `HEARTBEAT_INTERVAL`. These are agent-only settings and must not be in the backend config.

---

### Print job stays Pending and never prints

Checklist:
1. Dashboard → **Agents** — is the agent for that location **Online**?
2. Dashboard → **Mapping** — does the location have a printer assigned?
3. Is the USB printer plugged in and turned on?
4. Check the log: `type C:\PrintHubAgent\agent.log`

---

## GitHub Repositories

| Repository | Contents |
|---|---|
| [print_centre](https://github.com/MANIBAALAKRISHNANS/print_centre) | Full project — backend, frontend, agent source |
| [PrintHub_agent](https://github.com/MANIBAALAKRISHNANS/PrintHub_agent) | Agent installer only — download and run on printer PCs |

---

*PrintHub — Savetha Hospital IT Engineering*

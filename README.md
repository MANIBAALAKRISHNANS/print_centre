# PrintHub — Hospital Print Management System

---

## Table of Contents

1. [What is PrintHub?](#1-what-is-printhub)
2. [How It Works — Non-Technical](#2-how-it-works--non-technical)
3. [How It Works — Technical](#3-how-it-works--technical)
4. [Project Structure](#4-project-structure)
5. [What You Need Before Starting](#5-what-you-need-before-starting)
6. [Deployment Configuration — Exactly What to Change and Where](#6-deployment-configuration--exactly-what-to-change-and-where)
7. [How to Start the Backend](#7-how-to-start-the-backend)
8. [How to Start the Frontend](#8-how-to-start-the-frontend)
9. [Daily Operations — Starting, Stopping and Common Situations](#9-daily-operations--starting-stopping-and-common-situations)
10. [How to Install the Agent](#10-how-to-install-the-agent)
11. [How to Verify the Agent is Connected](#11-how-to-verify-the-agent-is-connected)
12. [Default Login and First-Time Dashboard Setup](#12-default-login-and-first-time-dashboard-setup)
13. [How to Stop and Uninstall the Agent](#13-how-to-stop-and-uninstall-the-agent)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. What is PrintHub?

**Without PrintHub:**
A nurse downloads a patient label file, copies it to a USB stick, walks to the printer, plugs in the stick, prints. This is slow, error-prone, and leaves no record.

**With PrintHub:**
A staff member clicks Print on the dashboard. The printer at the correct ward prints it within seconds. No USB sticks. No walking. Every job is logged automatically.

PrintHub is a centralised hospital print management system — a central server controls USB printers on every workstation in the building, over the hospital's existing network.

---

## 2. How It Works — Non-Technical

Think of PrintHub like a post office inside the hospital:

```
                    ┌──────────────────────────────────────────┐
                    │            SERVER PC  (runs 24/7)         │
                    │                                           │
                    │   Frontend (Dashboard)  ◄──►  Backend    │
                    │   Staff open this            The brain — │
                    │   in their browser           receives     │
                    │   Port 5173                  print jobs,  │
                    │                              stores them, │
                    │                              sends to     │
                    │   IP: 192.168.1.14           right PC     │
                    │         (example)            Port 8000    │
                    └──────────────────┬───────────────────────┘
                                       │  Hospital Network
                  ┌────────────────────┼────────────────────┐
                  │                    │                    │
       ┌──────────▼──────┐  ┌──────────▼──────┐  ┌─────────▼───────┐
       │  Ward A PC      │  │  ICU PC         │  │  OPD PC         │
       │  Agent running  │  │  Agent running  │  │  Agent running  │
       │  USB Printer    │  │  USB Printer    │  │  USB Printer    │
       └─────────────────┘  └─────────────────┘  └─────────────────┘
```

| Part | What it is | Where it runs |
|---|---|---|
| **Backend** | The brain — receives jobs, stores data, sends to correct printer PC | SERVER only |
| **Frontend** | The dashboard website staff open in any browser | SERVER only |
| **Agent** | Silent background software that receives jobs and prints them | Every PRINTER PC |

**The agent has no window. You never open it or interact with it.** It runs invisibly in the background and starts automatically every time Windows logs in.

---

## 3. How It Works — Technical

- **Backend:** Python 3.11, FastAPI, SQLite database, APScheduler for background tasks. Exposes a REST API on port 8000 and a WebSocket endpoint `/ws/agent` for real-time agent communication.
- **Frontend:** React 18 + Vite SPA. Reads `VITE_API_URL` from `frontend/.env` at startup. Served on port 5173. Communicates with the backend over HTTP and WebSocket.
- **Agent:** Python script. Maintains a persistent WebSocket connection to `ws://SERVER_IP:8000/ws/agent`. Receives `job_available` push events instantly. Falls back to HTTP polling every 30 seconds. Uses `win32print` on Windows or CUPS `lp` on Mac to send jobs to the physical printer.
- **Authentication:** JWT (HS256). All API routes are protected. The admin account is seeded automatically at first startup.
- **Real-time updates:** Both the dashboard and agents use WebSocket — the dashboard shows live agent status and job updates without any page refresh.

### Print job flow (step by step)

```
1. Staff submits job in the dashboard browser
        ↓  HTTP POST /jobs
2. Backend saves job to SQLite, status = "pending"
        ↓  WebSocket push to matching agent
3. Agent on the correct PC receives the job instantly
        ↓  win32print (Windows) or CUPS lp (Mac)
4. USB printer prints
        ↓  HTTP PATCH /jobs/{id}  (agent reports result)
5. Backend marks job "completed"
        ↓  WebSocket push to dashboard
6. Dashboard shows "Completed" in real time
```

---

## 4. Project Structure

```
print_centre/
│
├── backend/                        ← Python FastAPI server
│   ├── main.py                     ← All API routes, WebSocket handler, app startup
│   ├── database.py                 ← SQLite connection pool and schema helpers
│   ├── config.py                   ← Settings loaded from .env (pydantic-settings)
│   ├── requirements.txt            ← Python packages list
│   ├── start_backend.bat           ← One-click start script for Windows
│   ├── start_backend.sh            ← One-click start script for Mac/Linux
│   ├── .env                        ← Your local config (NOT committed to git)
│   ├── .env.example                ← Template — copy this to .env
│   └── services/
│       ├── auth.py                 ← Password hashing and JWT token helpers
│       ├── audit.py                ← Writes audit log entries
│       ├── alerts.py               ← Email/Slack alert integration (optional)
│       ├── routing_service.py      ← Printer failover routing logic
│       └── barcode_service.py      ← Label and barcode generation
│
├── frontend/                       ← React dashboard (SPA)
│   ├── src/
│   │   ├── config.js               ← Reads VITE_API_URL from .env
│   │   ├── context/
│   │   │   ├── AuthContext.jsx     ← Login state and authenticated API fetch
│   │   │   └── AppData.jsx         ← Shared data cache across pages
│   │   └── pages/
│   │       ├── Dashboard.jsx       ← Overview — jobs, agents, printers
│   │       ├── Agents.jsx          ← Agent list with Online/Offline status
│   │       ├── Printers.jsx        ← Add and manage physical printers
│   │       ├── Mapping.jsx         ← Map wards/departments to printers
│   │       ├── PrintJobs.jsx       ← View and retry print jobs
│   │       ├── Users.jsx           ← Create and manage staff accounts
│   │       ├── ActivationCodes.jsx ← Generate codes to register new agents
│   │       ├── AuditLogs.jsx       ← Full action history for compliance
│   │       └── Login.jsx           ← Login page
│   ├── .env                        ← VITE_API_URL (NOT committed to git)
│   ├── .env.example                ← Template — copy this to .env
│   ├── vite.config.js              ← Port 5173, host: true
│   ├── start_frontend.bat          ← One-click start script for Windows
│   ├── start_frontend.sh           ← One-click start script for Mac/Linux
│   ├── rebuild_frontend.bat        ← Rebuild when server IP changes (Windows)
│   ├── rebuild_frontend.sh         ← Rebuild when server IP changes (Mac/Linux)
│   └── package.json
│
└── agent/                          ← Agent source files (also in separate repo)
    ├── agent.py                    ← Main agent — WebSocket + print job loop
    ├── agent_config.py             ← Reads and writes the local config file
    ├── agent_setup.py              ← One-time registration using an activation code
    ├── agent_service.py            ← Legacy Windows Service wrapper
    ├── agent_macos.py              ← macOS CUPS printing helpers
    ├── debug_wmi.py                ← Lists printers visible to Windows (diagnostic)
    ├── requirements.txt            ← Agent Python packages
    ├── install_agent.bat           ← Windows installer
    └── install_agent.sh            ← Mac / Linux installer
```

**Agent installer (distribute this to printer PCs):**
https://github.com/MANIBAALAKRISHNANS/PrintHub_agent

---

## 5. What You Need Before Starting

### On the SERVER PC (backend + frontend)

| Software | Minimum Version | How to check |
|---|---|---|
| Python | 3.11 | Open PowerShell → `python --version` |
| Node.js | 18 | Open PowerShell → `node --version` |
| npm | 9 | Open PowerShell → `npm --version` |

**Install Python on Windows:**
1. Go to https://www.python.org/downloads/ and click Download
2. Run the installer
3. **CRITICAL: tick "Add Python to PATH"** on the very first screen before clicking Install
4. After install, open PowerShell and run `python --version` — must show `3.11.x` or higher

**Install Node.js on Windows:**
1. Go to https://nodejs.org/ and click the **LTS** button (left side)
2. Run the installer, click Next through all steps
3. After install, open PowerShell and run `node --version` — must show `v18.x.x` or higher

**Install Python on Mac:**
```bash
brew install python@3.11
```
If you do not have Homebrew: https://brew.sh

**Install Node.js on Mac:**
```bash
brew install node
```

### On each PRINTER PC (agent only)

| Software | Minimum Version |
|---|---|
| Python | 3.11 |

Node.js is **not needed** on printer PCs — only Python.

---

## 6. Deployment Configuration — Exactly What to Change and Where

> Read this before doing anything else. These are the **exact files and exact lines** you must update with your server's IP address. If you skip this step, the dashboard will not work from other PCs and agents will not connect.

### Step 1 — Find your server's IP address

Run this on the server PC:

**Windows:**
```powershell
ipconfig
```
Look for **IPv4 Address** under your active network adapter. It looks like `192.168.1.XX`.

**Mac:**
```bash
ipconfig getifaddr en0
```
Or: Apple menu → System Settings → Wi-Fi → Details → IP Address.

Write this IP down. You will use it in both files below.

---

### File 1 — `frontend/.env`

**Full path:** `print_centre/frontend/.env`

**Open it:**
```
notepad frontend\.env        (Windows — run from the print_centre folder)
nano frontend/.env           (Mac)
```

**Find this line:**
```
VITE_API_URL=http://192.168.1.14:8000
```

**Change it to your server's IP:**
```
VITE_API_URL=http://YOUR_SERVER_IP:8000
```

Example — if your server IP is `192.168.1.50`:
```
VITE_API_URL=http://192.168.1.50:8000
```

Save and close.

> **Why this matters:** `VITE_API_URL` is baked into the frontend when it starts. When anyone opens the dashboard on any PC in the hospital, their browser uses this URL to talk to the backend. If you leave `127.0.0.1` here, every other PC will look for the backend on their **own** machine instead of the server — and fail.

---

### File 2 — `backend/.env`

**Full path:** `print_centre/backend/.env`

**Open it:**
```
notepad backend\.env         (Windows)
nano backend/.env            (Mac)
```

**Find this line:**
```
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.14:5173
```

**Replace only the IP in the third entry:**
```
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://YOUR_SERVER_IP:5173
```

Example — if your server IP is `192.168.1.50`:
```
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.50:5173
```

Keep all three entries separated by commas. Save and close.

> **Why this matters:** CORS is a browser security rule. The backend only accepts requests from URLs in this list. If your server's IP is missing, the dashboard will show "Cannot connect" errors when opened from any other PC.

---

### Quick reference — everything to change

| File | Line | Replace with |
|---|---|---|
| `frontend/.env` | `VITE_API_URL=http://...` | `http://YOUR_SERVER_IP:8000` |
| `backend/.env` | `ALLOWED_ORIGINS=...` | Replace the IP in the third entry with YOUR_SERVER_IP |

**You do NOT change anything in the agent files.** The agent installer asks for the server IP interactively during installation.

---

## 7. How to Start the Backend

The backend must start **first** — before the frontend or any agents.

---

### Windows

#### First time only

**Step 1 — Download the project**

Open PowerShell (`Win + X` → Windows PowerShell):
```powershell
cd C:\Users\YourName\Desktop
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
cd print_centre\backend
```
Replace `YourName` with your Windows username.

**Step 2 — Create a virtual environment**
```powershell
python -m venv venv
```
A `venv` folder will appear. This is an isolated Python environment — it keeps packages separate from your system Python.

**Step 3 — Install Python packages**
```powershell
.\venv\Scripts\pip.exe install -r requirements.txt
```
This takes 2–3 minutes. Many lines scroll by — this is normal.

**Step 4 — Create and configure the `.env` file**
```powershell
copy .env.example .env
notepad .env
```
Update `ALLOWED_ORIGINS` with your server IP as described in [Section 6](#6-deployment-configuration--exactly-what-to-change-and-where). Save and close Notepad.

---

#### Every day — start the backend

Double-click this file in File Explorer:
```
print_centre\backend\start_backend.bat
```

A black window opens and shows:
```
===========================================================
 PrintHub Backend
===========================================================
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Leave this window open.** Closing it stops the backend and nothing will work.

**Verify the backend is running** — open a browser and go to:
```
http://localhost:8000/health
```
You should see: `{"status": "healthy", ...}`

---

### Mac

#### First time only

Open Terminal (`Cmd + Space` → type Terminal → Enter):

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

Update `ALLOWED_ORIGINS` with your server IP. Press `Ctrl+X` → `Y` → Enter to save.

#### Every day — start the backend

Open Terminal (`Cmd + Space` → type Terminal → Enter):
```bash
cd ~/Desktop/print_centre/backend
./start_backend.sh
```

The script will ask for your Mac password once to apply firewall rules, then start the server:
```
[OK] Firewall rules applied.

 Local:   http://127.0.0.1:8000
 Network: http://192.168.1.14:8000
 Press Ctrl+C to stop
```

**Do NOT close this Terminal window.** Open a new tab (`Cmd+T`) for the frontend.

**Verify:** Open Safari → go to `http://localhost:8000/health`

---

## 8. How to Start the Frontend

Start the frontend **after** the backend is already running.

> The frontend uses a **production build** (not the dev server). This means it is stable, fast, and never drops connections. The `start_frontend.bat` script handles everything automatically.

---

### Windows

#### First time only

**Step 1 — Go to the frontend folder**
```powershell
cd C:\Users\YourName\Desktop\print_centre\frontend
```

**Step 2 — Install JavaScript packages**
```powershell
npm install
```
This takes 1–2 minutes.

**Step 3 — Create and configure the `.env` file**
```powershell
copy .env.example .env
notepad .env
```
Update `VITE_API_URL` with your server IP as described in [Section 6](#6-deployment-configuration--exactly-what-to-change-and-where). Save and close.

---

#### Every day — start the frontend

Double-click this file in File Explorer:
```
print_centre\frontend\start_frontend.bat
```

A black window opens. If `dist\` already exists it starts immediately:
```
[OK] Serving production build on port 5173

 Dashboard (this PC)  : http://localhost:5173
 Dashboard (network)  : http://192.168.1.14:5173
```

If no build exists yet (first ever run), it builds automatically first — wait 30–60 seconds, then it starts serving.

**Leave this window open.** Closing it takes down the dashboard.

**Open the dashboard:**

| Who | URL to use |
|---|---|
| On the server PC itself | `http://localhost:5173` |
| From any other PC on the same network | `http://YOUR_SERVER_IP:5173` |

---

### Mac

#### First time only

```bash
cd ~/Desktop/print_centre/frontend
npm install
cp .env.example .env
nano .env
```
Set `VITE_API_URL=http://YOUR_SERVER_IP:8000`. Save with `Ctrl+X` → `Y` → Enter.

#### Every day — start the frontend

Open a **new** Terminal tab (`Cmd+T`) — keep the backend tab open:
```bash
cd ~/Desktop/print_centre/frontend
./start_frontend.sh
```

The script asks for your Mac password once to apply firewall rules. If no build exists yet, it builds automatically first (30–60 seconds). Then it starts serving:
```
[OK] Serving production build on ALL network interfaces, port 5173

 Dashboard (this Mac)  : http://localhost:5173
 Dashboard (network)   : http://192.168.1.14:5173
```

**Do NOT close this Terminal tab.** Closing it takes down the dashboard.

| Who | URL to use |
|---|---|
| On the server Mac itself | `http://localhost:5173` |
| From any other PC on the same network | `http://YOUR_SERVER_IP:5173` |

---

## 9. Daily Operations — Starting, Stopping and Common Situations

There are three situations you will encounter. Each is explained step by step below.

---

### Situation 1 — Normal Restart (Every Day)

This is what you do every time you start or restart the server. No special commands needed — just the start scripts.

---

#### Windows

**Step 1 — Stop everything (if running)**

Close the black `start_backend.bat` window → click the X or press `Ctrl+C`

Close the black `start_frontend.bat` window → same

**Step 2 — Start the backend first**

Open File Explorer → go to `print_centre\backend\`

Double-click `start_backend.bat` → click **Yes** on the UAC prompt (needed for firewall rules)

Wait until you see:
```
[OK] Firewall rules applied.

INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```
**Leave this window open.**

**Step 3 — Start the frontend**

Open File Explorer → go to `print_centre\frontend\`

Double-click `start_frontend.bat` → click **Yes** on the UAC prompt

Since `dist\` already exists from the previous build, it skips the build and starts in 2–3 seconds:
```
[OK] Firewall rules applied.
[OK] Serving production build on ALL network interfaces, port 5173

 Dashboard (this PC)  : http://localhost:5173
 Dashboard (network)  : http://192.168.1.14:5173
```
**Leave this window open.**

**Step 4 — Done**

Open any browser on any PC on the network:
```
http://192.168.1.14:5173
```

---

#### Mac

**Step 1 — Stop everything (if running)**

In the Terminal tab running the backend → press `Ctrl+C`

In the Terminal tab running the frontend → press `Ctrl+C`

**Step 2 — Start the backend first**

Open Terminal (`Cmd + Space` → Terminal → Enter):
```bash
cd ~/Desktop/print_centre/backend
./start_backend.sh
```
Enter your Mac password when asked (for firewall rules — asked once).

Wait until you see:
```
[OK] Firewall rules applied.

INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```
**Do NOT close this Terminal window.**

**Step 3 — Start the frontend**

Open a **new** Terminal tab (`Cmd+T`):
```bash
cd ~/Desktop/print_centre/frontend
./start_frontend.sh
```
Enter your Mac password when asked. The script starts in 2–3 seconds:
```
[OK] Firewall rules applied.
[OK] Serving production build on ALL network interfaces, port 5173

 Dashboard (this Mac)  : http://localhost:5173
 Dashboard (network)   : http://192.168.1.14:5173
```
**Do NOT close this Terminal tab.**

**Step 4 — Done**

Open any browser on any PC on the network:
```
http://192.168.1.14:5173
```

---

### Situation 2 — Server IP Changed

This happens when the router restarts and assigns a new IP to the server PC (e.g. was `192.168.1.14`, now it is `192.168.1.20`). The dashboard stops loading from other PCs because the old IP is no longer valid.

---

#### Windows

**Step 1 — Find the new IP**

On the server PC, open PowerShell (`Win + X` → Windows PowerShell):
```powershell
ipconfig
```
Look for **IPv4 Address** under your active network adapter. Write it down.
Example: `192.168.1.20`

**Step 2 — Update `frontend\.env`**

Open File Explorer → `print_centre\frontend\` → right-click `.env` → Open with Notepad

Find this line:
```
VITE_API_URL=http://192.168.1.14:8000
```
Replace with the new IP:
```
VITE_API_URL=http://192.168.1.20:8000
```
Save and close.

**Step 3 — Update `backend\.env`**

Open File Explorer → `print_centre\backend\` → right-click `.env` → Open with Notepad

Find this line:
```
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.14:5173
```
Replace only the last IP:
```
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.20:5173
```
Save and close.

**Step 4 — Rebuild the frontend**

Open File Explorer → `print_centre\frontend\` → double-click `rebuild_frontend.bat`

It shows your current `.env` setting. Confirm it shows the new IP and press any key.

Wait for the build to finish (~30–60 seconds):
```
Build complete!
Now run start_frontend.bat to start the dashboard.
```
Press any key to close.

**Step 5 — Restart both scripts**

Double-click `start_backend.bat` → wait for startup complete

Double-click `start_frontend.bat` → starts immediately with the new IP baked in

**Step 6 — Open the dashboard with the new IP**
```
http://192.168.1.20:5173
```

> **Permanent fix — prevent the IP from ever changing again:**
> Windows Settings → Network & Internet → your Wi-Fi or Ethernet → click **Edit** next to IP assignment → switch to **Manual** → enter the current IP as fixed. After this the IP will never change even after router restarts.

---

#### Mac

**Step 1 — Find the new IP**

Open Terminal:
```bash
ipconfig getifaddr en0
```
Example: `192.168.1.20`

**Step 2 — Update `frontend/.env`**
```bash
nano ~/Desktop/print_centre/frontend/.env
```
Find `VITE_API_URL=http://192.168.1.14:8000` → change the IP to the new one:
```
VITE_API_URL=http://192.168.1.20:8000
```
Press `Ctrl+X` → `Y` → Enter to save.

**Step 3 — Update `backend/.env`**
```bash
nano ~/Desktop/print_centre/backend/.env
```
Find `ALLOWED_ORIGINS=...` → replace the last IP:
```
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.20:5173
```
Press `Ctrl+X` → `Y` → Enter to save.

**Step 4 — Rebuild the frontend**
```bash
cd ~/Desktop/print_centre/frontend
./rebuild_frontend.sh
```
It shows your current `.env` setting. Press Enter to confirm and wait for the build (~30–60 seconds):
```
Build complete!
Now run ./start_frontend.sh to start the dashboard.
```

**Step 5 — Restart both scripts**
```bash
cd ~/Desktop/print_centre/backend
./start_backend.sh
```
Open a new tab (`Cmd+T`):
```bash
cd ~/Desktop/print_centre/frontend
./start_frontend.sh
```

**Step 6 — Open the dashboard with the new IP**
```
http://192.168.1.20:5173
```

> **Permanent fix — prevent the IP from ever changing again:**
> Apple menu → System Settings → Network → your Wi-Fi or Ethernet → Details → TCP/IP → Configure IPv4 → switch to **Manually** → enter the current IP as fixed.

---

### Situation 3 — First Time on a New Machine

This is what you do when setting up PrintHub on a brand new PC/Mac that has never run it before.

---

#### Windows

**Step 1 — Install Python**

Go to https://www.python.org/downloads/ → Download → Run the installer

On the very first screen: **tick "Add Python to PATH"** → click Install Now

Verify: open PowerShell → run `python --version` → must show `3.11` or higher

**Step 2 — Install Node.js**

Go to https://nodejs.org/ → click **LTS** → Run the installer → click Next through all steps

Verify: open PowerShell → run `node --version` → must show `v18` or higher

**Step 3 — Download the project**

Open PowerShell:
```powershell
cd C:\Users\YourName\Desktop
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
```

**Step 4 — Set up the backend (one time only)**

```powershell
cd print_centre\backend
python -m venv venv
.\venv\Scripts\pip.exe install -r requirements.txt
copy .env.example .env
notepad .env
```
Update `ALLOWED_ORIGINS` with your server IP. Save and close.

**Step 5 — Set up the frontend (one time only)**

```powershell
cd ..\frontend
npm install
copy .env.example .env
notepad .env
```
Update `VITE_API_URL` with your server IP. Save and close.

**Step 6 — Start normally**

Double-click `start_backend.bat` → click Yes on UAC → backend starts

Double-click `start_frontend.bat` → click Yes on UAC → builds the frontend automatically (30–60 seconds), then starts serving

From this point on every restart is just **Situation 1** — double-click the two bat files, nothing else.

---

#### Mac

**Step 1 — Install Python and Node.js**

Open Terminal (`Cmd + Space` → Terminal → Enter):
```bash
brew install python@3.11 node
```
If you do not have Homebrew: https://brew.sh

Verify:
```bash
python3 --version   # must show 3.11 or higher
node --version      # must show v18 or higher
```

**Step 2 — Download the project**
```bash
cd ~/Desktop
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
```

**Step 3 — Set up the backend (one time only)**
```bash
cd print_centre/backend
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env
```
Update `ALLOWED_ORIGINS` with your server IP. Press `Ctrl+X` → `Y` → Enter to save.

**Step 4 — Make the scripts executable (one time only)**
```bash
chmod +x ~/Desktop/print_centre/backend/start_backend.sh
chmod +x ~/Desktop/print_centre/frontend/start_frontend.sh
chmod +x ~/Desktop/print_centre/frontend/rebuild_frontend.sh
```

**Step 5 — Set up the frontend (one time only)**
```bash
cd ~/Desktop/print_centre/frontend
npm install
cp .env.example .env
nano .env
```
Update `VITE_API_URL` with your server IP. Press `Ctrl+X` → `Y` → Enter to save.

**Step 6 — Start normally**
```bash
cd ~/Desktop/print_centre/backend
./start_backend.sh
```
Open a new tab (`Cmd+T`):
```bash
cd ~/Desktop/print_centre/frontend
./start_frontend.sh
```
The frontend builds automatically on the first run (30–60 seconds), then starts serving.

From this point on every restart is just **Situation 1** — run the two `.sh` scripts, nothing else.

---

| Situation | When it happens | Windows | Mac |
|---|---|---|---|
| **Normal restart** | Every day | Double-click `start_backend.bat` then `start_frontend.bat` | Run `./start_backend.sh` then `./start_frontend.sh` |
| **IP changed** | After router restart | Update `.env` files → `rebuild_frontend.bat` → restart bat files | Update `.env` files → `./rebuild_frontend.sh` → restart sh scripts |
| **New machine** | First-time setup | Install Python + Node → `npm install` → configure `.env` → run bat files | Install Python + Node → `npm install` → `chmod +x *.sh` → configure `.env` → run sh scripts |

---

## 10. How to Install the Agent

Install the agent on **every PC that has a USB printer plugged in**. You install it once per PC — after that it runs automatically.

---

### Before installing — generate an activation code

1. Make sure the backend is running
2. Open the dashboard → click **Activation Codes** in the left menu
3. Click **Generate Code**
4. Write down the 8-character code (example: `B79EC6FC`)
5. **Use it within 10 minutes** — codes expire after 10 minutes

---

### Windows — Step by Step

**Step 1 — Download the agent installer**

Download from: https://github.com/MANIBAALAKRISHNANS/PrintHub_agent

Click **Code → Download ZIP** → extract it to the printer PC Desktop.

The extracted folder must contain:
```
PrintHub_agent-main\
├── agent.py
├── agent_config.py
├── agent_setup.py
├── agent_service.py
├── requirements.txt
└── install_agent.bat   ← this is the installer
```

**Step 2 — Right-click the installer → Run as administrator**

In File Explorer, find `install_agent.bat` in the extracted folder.

**Right-click it** → click **"Run as administrator"**

If Windows asks "Do you want to allow this app to make changes to your device?" → click **Yes**.

A black window opens and stays open the entire time.

> Do NOT just double-click. It MUST be "Run as administrator" or the installer will fail.

**Step 3 — Answer the 4 questions**

Press **Enter** after each answer:

```
Server IP address (e.g. 192.168.1.14):
```
→ Type the IP address of your server (the PC running the backend). Example: `192.168.1.14`

```
Server port (press Enter for 8000):
```
→ Just press **Enter**

```
Use HTTPS? (y/N):
```
→ Just press **Enter** (No)

```
Enter the 8-character activation code:
```
→ Type the code from the dashboard. Example: `B79EC6FC`

**Step 4 — Wait for SUCCESS**

Watch for all these lines to appear:
```
[OK] Running as Administrator.
[OK] Python 3.x found.
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

Press any key to close the window. **Installation is complete.**

> **Reinstalling?** If `C:\PrintHubAgent\agent_config.json` already exists (you installed before), the installer skips the questions entirely and goes straight to Step 5. No need to enter anything.

---

### Mac — Step by Step

**Step 1 — Download the agent installer**

Download from https://github.com/MANIBAALAKRISHNANS/PrintHub_agent and copy to the Mac.

**Step 2 — Open Terminal**

Press `Cmd + Space` → type **Terminal** → press Enter.

**Step 3 — Go to the folder and run the installer**
```bash
cd ~/Desktop/PrintHub_agent-main
bash install_agent.sh
```

**Step 4 — Answer the questions** (same as Windows above — server IP, port, HTTPS, activation code)

**Step 5 — Wait for SUCCESS**
```
SUCCESS! PrintHub Agent is installed and running.
It starts automatically at every login.
```

---

## 11. How to Verify the Agent is Connected

After installing, confirm the agent is running and talking to the server.

---

### Windows — 5 ways to check

**Method 1 — Dashboard (easiest)**

Open the PrintHub Dashboard → click **Agents** in the left menu.

Within 15–30 seconds, this PC appears with a green **Online** badge.
If it shows Offline or does not appear at all — see [Troubleshooting](#12-troubleshooting).

---

**Method 2 — Read the log in Command Prompt**

After the installer closes, a regular Command Prompt window shows `C:\Windows\System32>`.
Type this and press Enter:
```cmd
type C:\PrintHubAgent\agent.log
```

Or open a new Command Prompt: press `Win + R` → type `cmd` → Enter, then run the command above.

---

**Method 3 — Read the log in PowerShell**

Press `Win + X` → click **Terminal** or **Windows PowerShell**:
```powershell
Get-Content C:\PrintHubAgent\agent.log -Tail 20
```

---

**Method 4 — Open the log in Notepad**
```cmd
notepad C:\PrintHubAgent\agent.log
```

---

**Method 5 — Check Task Manager**

Press `Ctrl + Shift + Esc` → click the **Details** tab → look for `python.exe`.
If it is in the list, the agent process is running.

---

**Method 6 — Quick command-line check (fastest)**

Open Command Prompt on the printer PC and run:
```powershell
powershell -Command "Get-Content C:\PrintHubAgent\agent.log -Tail 5"
```
Read the last line:
- `[WS] Connected to server` → agent is running and connected ✓
- `ConnectTimeoutError` → agent is running but cannot reach the backend
- `[WS] Reconnecting in Xs` → agent is running but disconnected, retrying automatically

---

**Check task status directly:**
```cmd
schtasks /query /tn "PrintHubAgent" /fo LIST
```
- `Status: Running` → agent process is active
- `Status: Ready` → installed but not currently running

**Start the agent manually (if stopped):**
```cmd
schtasks /run /tn "PrintHubAgent"
```

**Stop the agent:**
```cmd
schtasks /end /tn "PrintHubAgent"
```

---

**What a healthy log looks like:**
```
[INFO] Starting PrintHub Agent...
[INFO] Agent ID: agent_cc35811fad03
[INFO] Server: http://192.168.1.14:8000
[WS] Connecting to ws://192.168.1.14:8000/ws/agent/...
[WS] Connected to server
[INFO] Waiting for print jobs...
```

The line `[WS] Connected to server` confirms the agent is live and connected to the backend.

---

### Mac — 4 ways to check

**Method 1 — Dashboard (easiest)**

Open the PrintHub Dashboard → click **Agents**. This Mac appears with a green **Online** badge within 15 seconds.

---

**Method 2 — Read the last 20 lines of the log**

Open Terminal (`Cmd + Space` → Terminal → Enter):
```bash
tail -20 ~/Library/Logs/PrintHubAgent/agent.log
```

---

**Method 3 — Watch the log in real time**
```bash
tail -f ~/Library/Logs/PrintHubAgent/agent.log
```
This keeps scrolling as the agent runs. Press `Ctrl + C` to stop.

---

**Method 4 — Check if launchd service is registered**
```bash
launchctl list | grep printhub
```
If a line appears with `com.printhub.agent`, the service is loaded and running.

---

**What a healthy log looks like (same as Windows):**
```
[WS] Connected to server
[INFO] Waiting for print jobs...
```

---

## 12. Default Login and First-Time Dashboard Setup

Open the dashboard in any browser and log in:

| Username | Password |
|---|---|
| `admin` | `Admin@PrintHub2026` |

The admin account is created automatically the first time the backend starts. **Change the password after your first login** — click the user icon at the top-right → Change Password.

---

### First-time setup order

Do these steps **in order** when setting up PrintHub for the first time:

**1. Add your physical printers**

Go to **Printers** → Add Printer. Fill in:
- Name — something descriptive, e.g. `Ward A Barcode Printer`
- Type — A4 or Barcode
- Printer name — the **exact** name Windows uses for the printer

To find the exact printer name, open PowerShell on the printer PC:
```powershell
Get-Printer | Select-Object Name
```

**2. Add locations (wards/departments)**

Go to **Locations** → add each ward or department (e.g. `Ward A`, `ICU`, `OPD`, `Pharmacy`).

**3. Map printers to locations**

Go to **Mapping** → assign a Primary printer and a Secondary (backup) printer to each location.

**4. Install agents on all printer PCs**

For each PC with a USB printer:
- Go to **Activation Codes** → Generate Code
- Go to that PC → run `install_agent.bat` as Administrator → enter the code
- Come back to the dashboard → Agents → confirm it shows Online

**5. Test a print job**

Go to **Mapping** → find a location with an Online agent → click the **test** button (A4 or Bar).
The physical printer should print within a few seconds.

**6. Create accounts for clinical staff**

Go to **Users** → Add User. Clinical users can submit jobs but cannot change system settings.

---

### Dashboard pages reference

| Page | What it does |
|---|---|
| **Dashboard** | Overview — active agents, pending jobs, printer status |
| **Printers** | Add and manage physical printers |
| **Locations / Mapping** | Map departments to printers |
| **Print Jobs** | View all jobs, retry failed ones |
| **Agents** | All PCs running the agent — Online/Offline status |
| **Users** | Create and manage staff accounts |
| **Activation Codes** | Generate codes to register new printer PCs |
| **Audit Logs** | Full history of every action — required for compliance |

---

## 14. Troubleshooting

### Agent shows Offline in the dashboard

**Check 1 — Is the agent process running?**

Windows (open Command Prompt):
```cmd
type C:\PrintHubAgent\agent.log
```
Look for `[WS] Connected to server`. If the file is empty or the last line is old, the agent is not running.

Start it manually to see any errors:
```cmd
C:\PrintHubAgent\venv\Scripts\python.exe C:\PrintHubAgent\agent.py
```

Mac:
```bash
tail -20 ~/Library/Logs/PrintHubAgent/agent.log
```

**Check 2 — Can the printer PC reach the backend?**

Open a browser on the printer PC and go to:
```
http://YOUR_SERVER_IP:8000/health
```
If this page does not load, the server firewall is blocking port 8000.

Open ports on the server (run PowerShell as Administrator on the server):
```powershell
netsh advfirewall firewall add rule name="PrintHub Backend 8000" dir=in action=allow protocol=TCP localport=8000
netsh advfirewall firewall add rule name="PrintHub Frontend 5173" dir=in action=allow protocol=TCP localport=5173
```

**Check 3 — Wrong server IP in the agent config?**

Windows:
```cmd
type C:\PrintHubAgent\agent_config.json
```
Check the `server_url` value. If it is wrong, delete the file and reinstall:
```cmd
del C:\PrintHubAgent\agent_config.json
```
Run `install_agent.bat` again — it will ask for the server IP again.

---

### Dashboard shows "This site can't be reached" or ERR_CONNECTION_TIMED_OUT

This is the most common issue when opening the dashboard from another PC on the network. The frontend is running fine on the server but the firewall is blocking the connection before it gets through.

---

#### If the server is a Windows PC

**Step 1 — Confirm the frontend is running on the server**

On the server PC, check that `start_frontend.bat` is open and shows:
```
Local:   http://localhost:5173/
Network: http://192.168.1.14:5173/
```
If it does not show the Network line, make sure `frontend\vite.config.js` contains `host: true` inside the `server` block.

**Step 2 — Confirm the server IP is correct**

On the server PC, open PowerShell and run:
```powershell
ipconfig
```
Look for **IPv4 Address** under your active network adapter. Confirm it matches the IP you are typing in the browser. If it has changed (e.g. after a router restart), update `frontend\.env` and `backend\.env` with the new IP and restart both.

**Step 3 — Open ports in Windows Firewall**

On the server PC, open PowerShell **as Administrator** (`Win + X` → Windows PowerShell (Admin)) and run:
```powershell
netsh advfirewall firewall add rule name="PrintHub Frontend 5173" dir=in action=allow protocol=TCP localport=5173

netsh advfirewall firewall add rule name="PrintHub Backend 8000" dir=in action=allow protocol=TCP localport=8000
```
You should see `Ok.` after each command.

**Step 4 — Try again**

On the other PC, open a browser and go to:
```
http://YOUR_SERVER_IP:5173
```

> **Why this happens:** Windows Firewall blocks all inbound connections by default, even from PCs on the same local network. The rules above allow other PCs to reach port 5173 (dashboard) and port 8000 (backend API).

---

#### If the server is a Mac

**Step 1 — Make sure you are using the `.sh` start scripts**

The `./start_backend.sh` and `./start_frontend.sh` scripts automatically apply macOS firewall rules every time they start. If you were starting the server manually (e.g. `uvicorn ...` or `npx serve ...` directly in Terminal), the firewall rules were never applied.

Stop what is running (`Ctrl+C`) and use the scripts instead:
```bash
cd ~/Desktop/print_centre/backend
./start_backend.sh
```
Open a new tab (`Cmd+T`):
```bash
cd ~/Desktop/print_centre/frontend
./start_frontend.sh
```
Both scripts will ask for your Mac password once — this is required to apply the firewall rules. After that, other PCs can connect.

**Step 2 — Confirm the server IP is correct**

On the server Mac, open Terminal and run:
```bash
ipconfig getifaddr en0
```
Confirm the IP matches what you are typing in the browser. If it has changed, follow **Situation 2** in [Section 9](#9-daily-operations--starting-stopping-and-common-situations) to update the `.env` files and rebuild.

**Step 3 — If the scripts already ran and it is still blocked**

The macOS Application Firewall may need Node added manually. Run:
```bash
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add $(which node)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp $(which node)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add $(which python3)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp $(which python3)
```

**Step 4 — Try again**

On the other PC, open a browser and go to:
```
http://YOUR_SERVER_IP:5173
```

> **Why this happens:** macOS Firewall (if enabled) blocks inbound connections to Python and Node processes. The `./start_backend.sh` and `./start_frontend.sh` scripts handle this automatically — always use them instead of running commands manually.

---

### Other PCs cannot reach the server — "Destination host unreachable"

This is different from ERR_CONNECTION_TIMED_OUT. Run `ping YOUR_SERVER_IP` from a non-server PC:

```
ping 192.168.1.14
```

If you see:
```
Reply from 192.168.1.12: Destination host unreachable.
```
(the reply comes from **your own PC's IP**, not the server) — this means **AP Isolation is enabled on your router**.

---

**What is AP Isolation?**

Many ISP-provided routers (Airtel, BSNL, Jio) enable wireless client isolation by default. It prevents WiFi devices from talking directly to each other — every device can reach the internet but not other devices on the same WiFi network. This causes ERR_CONNECTION_TIMED_OUT for all non-server PCs regardless of what firewall rules are set.

---

**Solution 1 — Ethernet cable (recommended)**

Plug a LAN cable from any yellow/LAN port on the router directly into the **server PC**. Ethernet connections completely bypass AP isolation. All WiFi devices can then reach the server.

After plugging in, check the server's new IP (`ipconfig`) — it may change from the WiFi IP. Update `frontend/.env` and `backend/.env` if it does, then rebuild the frontend.

---

**Solution 2 — Use the server laptop's Mobile Hotspot**

If a cable is not available, create a Windows Mobile Hotspot on the server laptop and connect all non-server PCs to it instead of the main router WiFi.

The server's hotspot IP is always **`192.168.137.1`**. After switching, update these on every affected PC and on the server:

**On each non-server PC — update agent config:**
```cmd
notepad C:\PrintHubAgent\agent_config.json
```
Change `server_url` to:
```json
"server_url": "http://192.168.137.1:8000"
```
Then restart the agent:
```cmd
schtasks /end /tn "PrintHubAgent"
schtasks /run /tn "PrintHubAgent"
```

**On the server — update `frontend/.env`:**
```
VITE_API_URL=http://192.168.137.1:8000
```

**On the server — update `backend/.env`:**
Add the hotspot origin to `ALLOWED_ORIGINS`:
```
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.14:5173,http://192.168.137.1:5173
```

**On the server — rebuild the frontend:**
```
rebuild_frontend.bat   (Windows)
./rebuild_frontend.sh  (Mac)
```

**Access the dashboard from non-server PCs at:**
```
http://192.168.137.1:5173
```

Confirm the agent is reconnected:
```powershell
powershell -Command "Get-Content C:\PrintHubAgent\agent.log -Tail 5"
```
You should see `[WS] Connected to server`.

---

**Solution 3 — Disable AP Isolation in router settings**

Log in to the router admin page (`http://192.168.1.1`). Look under **Wireless / WLAN settings** for **AP Isolation**, **Client Isolation**, or **Wireless Isolation** and disable it. Note: many ISP-locked routers (e.g. Airtel Titanium-2122A) do not expose this setting in the UI — use Solution 1 or 2 instead.

---

### Dashboard shows blank page or "Cannot connect to API"

The frontend is pointing at the wrong backend address.

1. Open `frontend\.env`
2. Make sure `VITE_API_URL=http://YOUR_SERVER_IP:8000` — must be the real server IP, not `127.0.0.1`
3. Stop the frontend window and restart `start_frontend.bat`

---

### `install_agent.bat` shows `: was unexpected at this time`

Old installer version. Download the latest from:
https://github.com/MANIBAALAKRISHNANS/PrintHub_agent

---

### Activation code says "invalid or expired"

Codes expire after 10 minutes. Generate a fresh one:
Dashboard → Activation Codes → Generate Code → use it immediately.

---

### Backend fails to start — pydantic validation error

`backend/.env` contains `SERVER_URL` or `HEARTBEAT_INTERVAL`. These are agent-only settings and cause an error if placed in the backend config. Remove those lines from `backend/.env`.

---

### Print job stays Pending and never prints

1. Dashboard → Agents — is the printer PC showing **Online**?
2. Dashboard → Mapping — does the location have a printer assigned?
3. Is the USB printer plugged in and turned on?
4. Check the agent log on the printer PC for error lines

---

### Backend startup warning: MISSING DEPENDENCIES: soffice, gswin64c

Not a problem. These are optional tools for converting Word/PDF files. Label and barcode printing work perfectly without them. Ignore this warning.

---

### Login fails — "Invalid credentials"

Reset the admin account on the server:

Windows:
```powershell
cd C:\...\print_centre\backend
.\venv\Scripts\python.exe restore_admin.py
```

Mac:
```bash
cd ~/Desktop/print_centre/backend
source venv/bin/activate
python restore_admin.py
```

---

## 13. How to Stop and Uninstall the Agent


---

### Windows — Stop and Uninstall

**Step 1 — Stop the agent process**

Press `Ctrl + Shift + Esc` to open Task Manager → click the **Details** tab → find `python.exe` → right-click it → **End Task** → click End Process.

> If there are multiple `python.exe` entries, end all of them.

**Step 2 — Remove the Task Scheduler entry (stops it from auto-starting)**

Open Command Prompt as Administrator (`Win + R` → type `cmd` → `Ctrl + Shift + Enter`):
```cmd
schtasks /delete /tn "PrintHubAgent" /f
```
You should see: `SUCCESS: The scheduled task "PrintHubAgent" was successfully deleted.`

**Step 3 — Delete the agent folder**
```cmd
rmdir /s /q C:\PrintHubAgent
```
This deletes everything — the agent files, virtual environment, config, and log files.

**Done.** The agent is completely removed. It will not start again on next login.

---

### Mac — Stop and Uninstall

**Step 1 — Stop the agent process**

Open Terminal (`Cmd + Space` → Terminal → Enter):
```bash
launchctl unload ~/Library/LaunchAgents/com.printhub.agent.plist
```

**Step 2 — Remove the auto-start service**
```bash
rm ~/Library/LaunchAgents/com.printhub.agent.plist
```

**Step 3 — Delete the log files**
```bash
rm -rf ~/Library/Logs/PrintHubAgent
```

**Done.** The agent is completely removed.

---

### Verify it is gone (Windows)

Open Task Manager → Details tab → confirm `python.exe` is no longer in the list.

Also confirm the scheduled task is deleted:
```cmd
schtasks /query /tn "PrintHubAgent"
```
You should see: `ERROR: The system cannot find the file specified.` — that means it is fully removed.

---

### Want to reinstall later?

Just run `install_agent.bat` again as Administrator — it will set everything up fresh from scratch.

---

*PrintHub — Savetha Hospital IT Engineering*

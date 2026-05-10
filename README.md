# PrintHub — Clinical-Grade Hospital Print Management System

**PrintHub** connects a central server to USB printers on every nursing workstation in the hospital. When a doctor submits a print job from the dashboard, the correct printer at the correct location prints it within milliseconds — no manual file transfers, no shared drives, no delays.

---

## Table of Contents

1. [How The System Works](#1-how-the-system-works)
2. [What Runs Where — Deployment Architecture](#2-what-runs-where--deployment-architecture)
3. [What You Need Before Starting](#3-what-you-need-before-starting)
4. [Part A — Start the Backend (The Brain)](#part-a--start-the-backend)
   - [On Windows (Laptop or Server)](#on-windows-laptop-or-server)
   - [On Mac (Laptop or Server)](#on-mac-laptop-or-server)
   - [On Linux Server (Production)](#on-linux-server-production)
5. [Part B — Start the Frontend (The Dashboard Website)](#part-b--start-the-frontend)
   - [On Windows](#on-windows)
   - [On Mac](#on-mac)
   - [Production Build with nginx](#production-build-with-nginx)
6. [Part C — Install the Agent on Printer Workstations](#part-c--install-the-agent-on-printer-workstations)
   - [Windows — Step by Step](#windows--step-by-step)
   - [Mac — Step by Step](#mac--step-by-step)
7. [Part D — Using the Dashboard](#part-d--using-the-dashboard)
8. [Default Login Credentials](#default-login-credentials)
9. [Environment Variables Reference](#environment-variables-reference)
10. [Firewall and Network Ports](#firewall-and-network-ports)
11. [Troubleshooting](#troubleshooting)
12. [Architecture Overview (Technical)](#architecture-overview-technical)

---

## 1. How The System Works

Think of PrintHub as a post office system:

- The **Backend** is the main post office building — it receives print requests, stores them, and sends them to the right printer PC
- The **Frontend** is the glass window at the post office — staff open it in their browser to see all jobs and manage printers
- The **Agent** is the delivery person at each nursing station — it waits for the backend to send a job, then sends it to the USB printer plugged into that PC

```
┌─────────────────────────────────────────────────────────────────┐
│                    ONE SERVER (stays on 24/7)                    │
│                                                                  │
│   ┌─────────────────┐        ┌────────────────────────────┐     │
│   │   Frontend      │        │   Backend                  │     │
│   │   (Dashboard)   │◄──────►│   (Brain)                  │     │
│   │   Port 5173     │        │   Port 8000                │     │
│   └─────────────────┘        └─────────────┬──────────────┘     │
│                                            │                    │
│   Server IP: 192.168.1.14 (example)        │                    │
└────────────────────────────────────────────┼────────────────────┘
                                             │  (same network)
                         ┌───────────────────┤
                         │                   │
              ┌──────────▼──────┐  ┌─────────▼───────┐
              │  Printer PC 1   │  │  Printer PC 2   │
              │                 │  │                 │
              │  Agent running  │  │  Agent running  │
              │  USB Printer ▼  │  │  USB Printer ▼  │
              └─────────────────┘  └─────────────────┘
```

**Key rule:** The backend and frontend run on ONE machine (the server). The agent runs on EVERY PC that has a printer. The agents connect TO the server over the network.

---

## 2. What Runs Where — Deployment Architecture

| Component | Runs on | Started by | Who accesses it |
|---|---|---|---|
| **Backend** | Server only | `start_backend.bat` (double-click) | Nobody opens this in browser — it runs silently |
| **Frontend** | Server only | `start_frontend.bat` (double-click) | Anyone on the network opens `http://SERVER_IP:5173` in their browser |
| **Agent** | Every printer PC | Auto-starts at Windows login after one-time install | Runs silently in background — no window |

### The most important thing to understand

When a nurse on **another PC** opens the dashboard in her browser, her browser makes API requests to the backend. The URL in `frontend/.env` must be the **server's network IP**, not `127.0.0.1` (which means "this computer"). If it says `127.0.0.1`, her browser looks for the backend on her own PC instead of the server.

**Correct `frontend/.env` for production:**
```
VITE_API_URL=http://192.168.1.14:8000
```
(Replace `192.168.1.14` with your actual server IP.)

---

## 3. What You Need Before Starting

Install these on the **server machine** (the one that will run backend + frontend). The printer PCs only need Python.

### Python 3.11 or newer

**Windows:**
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the big yellow Download button
3. Run the installer
4. **CRITICAL:** On the first screen, tick **"Add Python to PATH"** before clicking Install Now
5. After install, open PowerShell and run: `python --version` — it must show `Python 3.11.x`

> If you use Anaconda, use Anaconda Prompt instead of regular PowerShell for all Python commands.

**Mac:**
1. Go to [python.org/downloads](https://www.python.org/downloads/) and download the macOS installer
2. Run it and follow the steps
3. Open Terminal (`Cmd + Space` → type Terminal → Enter) and run: `python3 --version`

### Node.js 18 or newer (server only — not needed on printer PCs)

**Windows:**
1. Go to [nodejs.org](https://nodejs.org/)
2. Click the **LTS** button (left side)
3. Run the installer, click Next through all steps
4. Open PowerShell and run: `node --version` — should show `v18.x.x` or higher

**Mac:**
1. Go to [nodejs.org](https://nodejs.org/)
2. Download the macOS LTS version and run the `.pkg` file
3. Open Terminal and run: `node --version`

### Git (to download the code)

**Windows:**
1. Go to [git-scm.com](https://git-scm.com/) and download the installer
2. Run it, click Next through all steps — defaults are fine
3. After install, right-click your Desktop — you should see "Git Bash Here"

**Mac:**
Open Terminal and run `git --version`. If Git is not installed, macOS will prompt you to install it automatically.

---

## Part A — Start the Backend

The backend is the brain. It must always be running first before anything else.

### On Windows (Laptop or Server)

#### First-time setup (do this once)

**Step 1 — Download the project**

Open PowerShell:
```powershell
cd C:\Users\YourName\Desktop
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
cd print_centre\backend
```
> Replace `YourName` with your Windows username.

**Step 2 — Create a virtual environment**

A virtual environment is a clean, separate box for Python packages. It keeps things organised.
```powershell
python -m venv venv
```
You will see a `venv` folder appear.

> If you see "Permission denied" or "Access denied", the venv already exists. Skip this step and go to Step 3.

**Step 3 — Install all required packages**
```powershell
.\venv\Scripts\pip.exe install -r requirements.txt
```
This takes 2–3 minutes. Many lines will scroll by — that is normal.

**Step 4 — Set up your configuration file**

The backend reads settings from a file called `.env` in the backend folder. A `.env` file is already set up in this project. Open it and check the values:
```powershell
notepad .env
```

You will see:
```
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development
JWT_SECRET_KEY=f059b3e79d923a7f21c6b5e771fc5e891e923c8036384cc36eaaf1f06e72b328
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.14:5173
DATABASE_PATH=./printhub.db
```

**Update `ALLOWED_ORIGINS`** — replace `192.168.1.14` with your server's actual IP address. Keep all three entries, just replace the IP in the third one.

To find your server's IP, open PowerShell and run:
```powershell
ipconfig
```
Look for `IPv4 Address` — it will look like `192.168.1.XX`.

Save and close Notepad.

#### Every day — starting the backend

The project includes a ready-made start script. Simply go to the backend folder and double-click it:

```
backend\start_backend.bat
```

A black window will appear with:
```
===========================================================
 PrintHub Backend Server
 Local:   http://127.0.0.1:8000
 Network: http://192.168.1.14:8000
===========================================================
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Leave this window open.** Do not close it — closing it stops the backend and nothing will work.

**Verify the backend is working:**

Open Chrome and go to: `http://localhost:8000/health`

You should see something like: `{"status": "healthy", ...}`

---

### On Mac (Laptop or Server)

#### First-time setup

**Step 1 — Download the project**

Open Terminal (`Cmd + Space` → Terminal → Enter):
```bash
cd ~/Desktop
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
cd print_centre/backend
```

**Step 2 — Create and activate a virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate
```

Your terminal prompt will now start with `(venv)` — this means it is activated.

**Step 3 — Install packages**
```bash
pip install -r requirements.txt
```

**Step 4 — Configure .env**
```bash
cp .env.example .env
nano .env
```

Update `ALLOWED_ORIGINS` to include your server IP:
```
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://YOUR_IP:5173
```

To find your Mac's IP: Apple menu → System Settings → Wi-Fi → Details → IP Address.

Press `Ctrl+X`, then `Y`, then Enter to save.

#### Every day — starting the backend

```bash
cd ~/Desktop/print_centre/backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

You will see `Application startup complete.` — the backend is running.

**Do NOT close this Terminal window.**

Verify: Open Safari and go to `http://localhost:8000/health`

---

### On Linux Server (Production)

**Step 1 — SSH into the server and download the project**
```bash
ssh username@YOUR_SERVER_IP
cd /opt
sudo mkdir printhub && sudo chown $USER:$USER printhub
cd printhub
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
cd print_centre/backend
```

**Step 2 — Create venv and install packages**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Step 3 — Configure .env**
```bash
cp .env.example .env
nano .env
```
Set `ALLOWED_ORIGINS` to include your server's IP.

**Step 4 — Create a systemd service so the backend starts automatically on reboot**

```bash
sudo nano /etc/systemd/system/printhub.service
```

Paste this (replace paths and username as needed):
```ini
[Unit]
Description=PrintHub Backend
After=network.target

[Service]
Type=simple
User=YOUR_LINUX_USERNAME
WorkingDirectory=/opt/printhub/print_centre/backend
ExecStart=/opt/printhub/print_centre/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Save, then enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable printhub
sudo systemctl start printhub
sudo systemctl status printhub
```

You should see `Active: active (running)` in green.

**Open port 8000 in firewall:**
```bash
sudo ufw allow 8000
sudo ufw allow 5173
```

---

## Part B — Start the Frontend

The frontend is the dashboard website. You open it in your browser. It must be started on the same machine as the backend.

### On Windows

#### First-time setup (do this once)

**Step 1 — Go to the frontend folder**
```powershell
cd C:\Users\YourName\Desktop\print_centre\frontend
```

**Step 2 — Install JavaScript packages**
```powershell
npm install
```
This takes 1–2 minutes.

**Step 3 — Configure the backend URL**

Open the file `frontend\.env`:
```powershell
notepad .env
```

You will see:
```
VITE_API_URL=http://192.168.1.14:8000
```

Replace `192.168.1.14` with your server's actual IP address (the same IP you used in the backend `.env`).

> **Why this matters:** This URL is baked into the frontend when it starts. When anyone opens the dashboard on ANY computer on the network, their browser uses this URL to talk to the backend. It must be the server's IP, not `127.0.0.1` (which means "my own computer").

Save and close Notepad.

#### Every day — starting the frontend

Double-click the start script in the frontend folder:

```
frontend\start_frontend.bat
```

A black window will appear with:
```
===========================================================
 PrintHub Frontend (Dashboard)
 Local:   http://localhost:5173
 Network: http://192.168.1.14:5173
===========================================================
VITE v8.x  ready in 261 ms
  Local:   http://localhost:5173/
  Network: http://192.168.1.14:5173/
```

**Leave this window open.**

**Open the dashboard:**

On the server PC: `http://localhost:5173`
From any other PC on the network: `http://192.168.1.14:5173` (replace with your server IP)

---

### On Mac

#### First-time setup (do this once)

**Step 1 — Go to the frontend folder**
```bash
cd ~/Desktop/print_centre/frontend
```

**Step 2 — Install packages**
```bash
npm install
```

**Step 3 — Configure the backend URL**
```bash
nano .env
```

Set it to your server's IP:
```
VITE_API_URL=http://YOUR_SERVER_IP:8000
```

Save (`Ctrl+X`, `Y`, Enter).

#### Every day — starting the frontend

Open a **new** Terminal tab (`Cmd+T`) — keep the backend tab open:
```bash
cd ~/Desktop/print_centre/frontend
npm run dev
```

Open the dashboard: `http://localhost:5173`

---

### Production Build with nginx

In production, you build the frontend into static files served by nginx so it works without Node.js running.

**Step 1 — Build the frontend**
```bash
cd /opt/printhub/print_centre/frontend
echo "VITE_API_URL=http://YOUR_SERVER_IP:8000" > .env
npm install
npm run build
```
This creates a `dist/` folder with all the HTML/CSS/JS files.

**Step 2 — Install nginx**
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install nginx

# CentOS/RHEL
sudo yum install nginx
```

**Step 3 — Configure nginx**
```bash
sudo nano /etc/nginx/sites-available/printhub
```

Paste:
```nginx
server {
    listen 80;
    server_name YOUR_SERVER_IP;

    root /opt/printhub/print_centre/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

Enable and restart:
```bash
sudo ln -s /etc/nginx/sites-available/printhub /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

Open a browser and go to `http://YOUR_SERVER_IP` — you should see the dashboard.

---

## Part C — Install the Agent on Printer Workstations

The agent is installed on every PC that has a USB printer plugged in. It runs silently in the background, connects to the backend, and prints jobs when they arrive.

**You install the agent ONCE per PC. After that, it starts automatically every time Windows logs in.**

### What you need before installing

1. The backend must be running on the server
2. You need an **activation code** from the dashboard — generate one fresh before starting (it expires in 10 minutes)

**How to generate an activation code:**
1. Open the dashboard → click **Activation Codes** in the left menu
2. Click **Generate Code**
3. Write down or copy the 8-character code (example: `6F166AC4`)

---

### Windows — Step by Step

#### Step 1 — Copy the agent folder to the printer PC

Get the `PrintHub_Agent` folder (or zip file) from your server:
- USB stick, network share, or any way you prefer
- Copy it to the printer PC (e.g., to the Desktop)

The folder must contain these files:
```
PrintHub_Agent\
├── agent.py
├── agent_config.py
├── agent_setup.py
├── agent_service.py
├── install_agent.bat     ← this is the installer
└── requirements.txt
```

#### Step 2 — Right-click the installer → Run as administrator

In File Explorer, navigate to the `PrintHub_Agent` folder.

**Right-click** on `install_agent.bat` → click **"Run as administrator"**.

> Do NOT just double-click. It must say "Run as administrator". If Windows asks "Do you want to allow this app to make changes?" click **Yes**.

#### Step 3 — Answer the questions (first time only)

The installer will ask you 4 questions. Answer them one by one and press Enter after each:

```
Server IP address (e.g. 192.168.1.50):
```
→ Type the IP address of your server (the PC running the backend). Example: `192.168.1.14`

```
Server port (press Enter for 8000):
```
→ Just press **Enter** (8000 is the default and is correct).

```
Use HTTPS? (y/N):
```
→ Just press **Enter** (choose No unless your IT team set up HTTPS specifically).

```
Enter the 8-character activation code:
```
→ Type the code you generated from the dashboard. Example: `6F166AC4`

> If this PC already has a saved config (you installed before), it will say "Existing configuration found — skipping setup" and skip straight to creating the scheduled task. No questions asked.

#### Step 4 — Watch it complete

You will see these lines appear one by one:

```
[OK] Running as Administrator
[OK] Python 3.11.5 found
[STEP 1] Preparing installation directory C:\PrintHubAgent...
[OK] Agent files copied to C:\PrintHubAgent
[OK] Virtual environment ready
[STEP 3] Installing dependencies...
[OK] Dependencies installed.
[OK] pywin32 post-install complete.
[OK] Existing configuration found   (or "Configuration saved" on first run)
[STEP 4] Creating Task Scheduler task (PrintHubAgent)...
[OK] Task Scheduler task created (runs at every login automatically).
[STEP 5] Starting agent now...
[OK] Agent started in background (minimized window).
```

When you see all those `[OK]` lines — **installation is complete**.

A minimized window called **"PrintHubAgent"** will appear in your taskbar. The agent is running inside it.

#### Step 5 — Confirm the agent is connected

Go to the dashboard (`http://YOUR_SERVER_IP:5173`) → click **Agents** in the left menu.

Within 15–30 seconds, the printer PC should appear in the list with a green **"Online"** badge.

---

#### Verify the agent is running correctly (Windows)

**Method 1 — Check the dashboard (easiest):**
Open the PrintHub Dashboard in your browser → click **Agents** in the left menu.
This PC should appear with a green **Online** badge within 15–30 seconds of the agent starting.

**Method 2 — Check the log file in Command Prompt:**

If the installer window is still open (it shows `C:\Windows\System32>`), run:
```cmd
type C:\PrintHubAgent\agent.log
```

**Method 3 — Check the log file in PowerShell:**

Press `Win + X` → click **Terminal** or **PowerShell**, then run:
```powershell
Get-Content C:\PrintHubAgent\agent.log -Tail 20
```

**Method 4 — Open the log in Notepad:**
```cmd
notepad C:\PrintHubAgent\agent.log
```

In the log, look for this line — it confirms the agent is fully connected:
```
[WS] Connected to server
```

**Method 5 — Check Task Manager:**
Press `Ctrl + Shift + Esc` → click the **Details** tab → look for `python.exe` in the list.
If it is there, the agent is running.

---

#### Managing the agent on Windows

The agent starts automatically at every Windows login. You normally never need to touch it. But if you need to:

**Stop the agent:**
Open Task Manager → Details tab → find `python.exe` → End Task.

**Start the agent manually (Command Prompt):**
```cmd
C:\PrintHubAgent\venv\Scripts\python.exe C:\PrintHubAgent\agent.py
```

**Run the agent in a visible window (for troubleshooting):**
Open a regular Command Prompt or PowerShell window (not admin) and run:
```cmd
C:\PrintHubAgent\venv\Scripts\python.exe C:\PrintHubAgent\agent.py
```
You will see live log output. When you see `[WS] Connected to server`, the agent is fully working.

**Uninstall the agent completely (run Command Prompt as Administrator):**
```cmd
schtasks /delete /tn "PrintHubAgent" /f
rmdir /s /q C:\PrintHubAgent
```

---

### Mac — Step by Step

#### Step 1 — Copy the agent folder to the printer Mac

Copy the `PrintHub_Agent` folder to the Mac (USB, AirDrop, or network share).

#### Step 2 — Open Terminal

Press `Cmd + Space` → type "Terminal" → press Enter.

#### Step 3 — Go to the agent folder
```bash
cd ~/Desktop/PrintHub_Agent
```
(Replace `~/Desktop` with wherever you copied the folder.)

#### Step 4 — Make the installer executable
```bash
chmod +x install_agent.sh
```

#### Step 5 — Run the installer
```bash
bash install_agent.sh
```

The installer will ask for:
- Server URL: `http://192.168.1.14:8000` (replace with your server IP)
- Activation code: the 8-character code from the dashboard

#### Step 6 — Verify the agent is running correctly (Mac)

**Method 1 — Check the dashboard (easiest):**
Open the PrintHub Dashboard in your browser → click **Agents** in the left menu.
This Mac should appear with a green **Online** badge within 15–30 seconds.

**Method 2 — Check the log file in Terminal:**

Open Terminal (`Cmd + Space` → Terminal → Enter) and run:
```bash
tail -20 ~/Library/Logs/PrintHubAgent/agent.log
```

Look for this line — it confirms the agent is fully connected:
```
[WS] Connected to server
```

**Method 3 — Watch live log output (useful for troubleshooting):**
```bash
tail -f ~/Library/Logs/PrintHubAgent/agent.log
```
This keeps scrolling in real time. Press `Ctrl + C` to stop.

**Method 4 — Check if the launchd service is registered:**
```bash
launchctl list | grep printhub
```
If a line appears, the service is loaded. If it is blank, run the installer again.

---

#### Managing the agent on Mac

The agent starts automatically at every login via launchd. You normally never need to touch it.

**Stop the agent:**
```bash
launchctl unload ~/Library/LaunchAgents/com.printhub.agent.plist
```

**Start the agent:**
```bash
launchctl load ~/Library/LaunchAgents/com.printhub.agent.plist
```

**Run the agent manually in Terminal (for troubleshooting):**
```bash
~/Library/Application\ Support/PrintHubAgent/venv/bin/python3 ~/Library/Application\ Support/PrintHubAgent/agent.py
```
Or from wherever you copied the agent folder:
```bash
/path/to/agent/venv/bin/python3 /path/to/agent/agent.py
```
You will see live log output. When you see `[WS] Connected to server`, the agent is fully working.

**Uninstall completely:**
```bash
launchctl unload ~/Library/LaunchAgents/com.printhub.agent.plist
rm ~/Library/LaunchAgents/com.printhub.agent.plist
```

---

## Part D — Using the Dashboard

### Opening the dashboard

| Situation | URL to open in browser |
|---|---|
| On the server PC itself | `http://localhost:5173` |
| From any other PC on the same network | `http://192.168.1.14:5173` (replace with your server IP) |
| In production with nginx | `http://192.168.1.14` (no port number needed) |

### Logging in

| Username | Password |
|---|---|
| `admin` | `Admin@PrintHub2026` |

> Change the password immediately after first login. Go to the user icon at the top-right → Change Password.

---

### Pages in the Dashboard

| Page | What it does |
|---|---|
| **Dashboard** | Overview — active agents, pending jobs, printer status |
| **Printers** | Add and manage physical printers (name, type, connection) |
| **Locations / Mapping** | Map each department/ward to specific printers |
| **Print Jobs** | View all print jobs, retry failed ones |
| **Agents** | See all PCs running the agent — Online/Offline status |
| **Users** | Create and manage staff accounts (Admin / Viewer roles) |
| **Activation Codes** | Generate codes to register new agent workstations |
| **Audit Logs** | Full history of every action — required for compliance |

---

### First-time setup order

Follow these steps in order when setting up PrintHub for the first time:

**1. Add your printers**

Go to **Printers** → click **Add Printer**. Fill in:
- Name (e.g., `Ward A Barcode Printer`)
- Type: A4 or Barcode
- The printer's name exactly as Windows knows it

To find the exact printer name on Windows, open PowerShell and run:
```powershell
Get-Printer | Select-Object Name
```

**2. Set up locations and mapping**

Go to **Locations** → add each department/ward (e.g., `Ward A`, `ICU`, `OPD`).

Then go to **Mapping** → assign a Primary printer and a Secondary (backup) printer to each location.

**3. Install agents on workstations**

For each PC with a USB printer:
1. Go to **Activation Codes** → Generate Code
2. Go to that PC → run `install_agent.bat` as Administrator → enter the code
3. Come back to the dashboard → Agents → confirm it shows Online

**4. Test a print job**

Go to **Mapping** → find a location with an agent Online → click the **test** button (A4 or Bar). Check the physical printer — it should print within seconds.

**5. Create user accounts for clinical staff**

Go to **Users** → Add User. Clinical users can submit print jobs but cannot change system settings.

---

## Default Login Credentials

| Username | Password | Role |
|---|---|---|
| `admin` | `Admin@PrintHub2026` | Super Admin — full access |

> The admin account is automatically created when the backend starts for the first time. Change the password immediately.

---

## Environment Variables Reference

These go in `backend/.env`. This file controls how the backend behaves.

| Variable | Default | What it does |
|---|---|---|
| `HOST` | `0.0.0.0` | Which interface to listen on. `0.0.0.0` means all interfaces — required so other PCs on the network can reach it. |
| `PORT` | `8000` | Which port the backend listens on. |
| `ENVIRONMENT` | `development` | Set to `production` on a real hospital server. Production mode enforces stronger security rules. |
| `JWT_SECRET_KEY` | (random 64-char hex) | Secret used to sign login tokens. Generate a new one with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_CLEANUP_TOKEN` | `CHANGE_ME_...` | Token for admin maintenance endpoints. Change this in production. |
| `ALLOWED_ORIGINS` | (comma-separated URLs) | Which browser origins (URLs) are allowed to talk to the backend. Must include the frontend URL. |
| `DATABASE_PATH` | `./printhub.db` | Where the SQLite database file is stored. |
| `STALE_THRESHOLD_SECONDS` | `45` | Seconds without a heartbeat before an agent is marked Offline. |
| `MAX_RETRY_COUNT` | `3` | How many times a failed print job is retried automatically. |
| `JOB_LOCK_TIMEOUT_SECONDS` | `300` | Seconds before a locked print job is considered stuck and released. |

**Frontend `frontend/.env`:**

| Variable | What it does |
|---|---|
| `VITE_API_URL` | The full URL of the backend server. **Must be the server's network IP** (not `127.0.0.1`) so that browsers from other PCs can reach the backend. Example: `http://192.168.1.14:8000` |

---

## Firewall and Network Ports

| Machine | Port | Direction | Why |
|---|---|---|---|
| Server | 8000 | Inbound | Backend — agents and browsers connect here |
| Server | 5173 | Inbound | Frontend dev server — users open dashboard here |
| Server | 80 | Inbound | Frontend in production (nginx) |
| Printer PCs | (none) | Outbound only | Agents connect out to server port 8000 — no inbound ports needed |

**Windows — Open ports (run PowerShell as Administrator on the server):**
```powershell
netsh advfirewall firewall add rule name="PrintHub Backend 8000" dir=in action=allow protocol=TCP localport=8000
netsh advfirewall firewall add rule name="PrintHub Frontend 5173" dir=in action=allow protocol=TCP localport=5173
```

**Linux — Open ports:**
```bash
sudo ufw allow 8000
sudo ufw allow 5173
```

---

## Troubleshooting

### Agent log shows `[WS] Error: Handshake status 404 Not Found`

**Cause:** The `websockets` package is missing from the backend virtual environment. Without it, uvicorn cannot handle WebSocket connections.

**Fix:** Stop the backend and run:
```powershell
# Windows
cd C:\...\backend
.\venv\Scripts\pip.exe install websockets "uvicorn[standard]"
```
```bash
# Mac/Linux
cd .../backend
source venv/bin/activate
pip install websockets "uvicorn[standard]"
```
Then restart the backend.

---

### install_agent.bat shows `: was unexpected at this time.`

**Cause:** This is a bug with the old `schtasks` command on Windows 11. The installer has been updated to use PowerShell's `Register-ScheduledTask` instead.

**Fix:** Make sure you are using the latest `install_agent.bat` from the project. The updated installer uses PowerShell internally for the Task Scheduler step and does not have this error.

---

### Agent shows "Offline" in the dashboard

**Cause 1 — Agent is not running on that PC.**

Fix: Open PowerShell on the printer PC and run:
```powershell
C:\PrintHubAgent\venv\Scripts\python.exe C:\PrintHubAgent\agent.py
```
If you see `[WS] Connected to server`, it is working. Leave it running.

**Cause 2 — Backend is not reachable from the printer PC.**

Fix: On the printer PC, open a browser and go to `http://SERVER_IP:8000/health`. If you can't reach it, the firewall on the server is blocking port 8000. Run the firewall commands above.

**Cause 3 — Wrong server IP saved in agent config.**

Fix: Delete `C:\PrintHubAgent\agent_config.json` and run `install_agent.bat` again to re-enter the correct server IP.

---

### Dashboard shows blank page or "Cannot connect to API"

**Cause:** The frontend is connecting to the wrong backend address.

**Fix:**
1. Open `frontend/.env`
2. Make sure `VITE_API_URL=http://SERVER_IP:8000` — with the actual IP, not `127.0.0.1`
3. Stop the frontend and restart it (`start_frontend.bat`)

---

### "Permission denied: venv\Scripts\python.exe" when running `python -m venv venv`

**Cause:** A venv folder already exists and its files are locked (OneDrive sync or a running process).

**Fix:** Skip the `python -m venv venv` step — the venv already exists. Just run:
```powershell
.\venv\Scripts\pip.exe install -r requirements.txt
```

---

### Activation code says "invalid or expired"

**Cause:** Codes expire after 10 minutes.

**Fix:** Generate a fresh code: Dashboard → Activation Codes → Generate Code → use it within 10 minutes.

---

### Print job stays "Pending" and never prints

Checklist:
1. Dashboard → **Agents** — is the agent for that location showing as **Online**?
2. Dashboard → **Mapping** — does that location have a printer assigned?
3. Is the USB printer physically plugged in and turned on?
4. View the agent log on the printer PC: `notepad C:\PrintHubAgent\agent.log`

---

### Backend startup shows `CRITICAL: MISSING DEPENDENCIES: soffice, gswin64c`

**This is not a problem.** These are optional tools for converting Word/PDF files. All label printing and barcode printing works perfectly without them. Ignore this warning.

---

### Login fails with "Invalid credentials"

**Cause:** Wrong password or the database was reset.

**Fix:** Reset the admin password on the server:
```powershell
# Windows
cd C:\...\backend
.\venv\Scripts\python.exe restore_admin.py
```
```bash
# Mac/Linux
cd .../backend
source venv/bin/activate
python restore_admin.py
```

---

### Backend fails to start — pydantic validation errors

**Cause:** Unknown or incorrectly named variables in `backend/.env`. The backend only accepts variables that are defined in `backend/config.py`.

**Fix:** Make sure `backend/.env` does not contain `SERVER_URL` or `HEARTBEAT_INTERVAL` — these are agent-only settings and must not be in the backend config file.

---

## Architecture Overview (Technical)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HOSPITAL NETWORK                             │
│                                                                     │
│  ┌──────────────────┐         ┌──────────────────────────────────┐ │
│  │  React Dashboard │◄──WS───►│  FastAPI Backend                 │ │
│  │  (Admin UI)      │◄─HTTP──►│  + SQLite / PostgreSQL           │ │
│  │  Port 5173       │         │  + APScheduler                   │ │
│  └──────────────────┘         │  Port 8000                       │ │
│                                └──────────┬───────────────────────┘ │
│                                           │                         │
│                    ┌──────────────────────┤                         │
│                    │  /ws/agent (WS)       │ /agent/jobs (HTTP)     │
│                    │  real-time job push   │ 30s fallback poll      │
│                    ▼                       ▼                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Print Agents  (Windows / macOS)                │   │
│  │                                                             │   │
│  │  ┌──────────────────┐    ┌──────────────────────────────┐  │   │
│  │  │  WebSocket Thread│    │  Main Poll Loop              │  │   │
│  │  │  on job_available│───►│  Wakes on WS push            │  │   │
│  │  │  → sets trigger  │    │  Falls back to 30s poll      │  │   │
│  │  └──────────────────┘    └──────────────────────────────┘  │   │
│  └──────────────────────────────────────┬───────────────────────┘  │
│                                         │ USB / Network             │
│                             ┌───────────▼──────────────┐           │
│                             │  Physical Printers       │           │
│                             └──────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11, FastAPI, APScheduler, SQLite (default) / PostgreSQL (production) |
| **WebSocket server** | uvicorn + websockets package |
| **Frontend** | React 18, Vite, React Router v6 |
| **Real-time dashboard** | WebSocket `/ws` |
| **Real-time agents** | WebSocket `/ws/agent` |
| **Authentication** | JWT (HS256) |
| **Agent — Windows** | Python, win32print, pywin32, websocket-client |
| **Agent — macOS** | Python, CUPS (lpstat/lp), websocket-client |

### Project Structure

```
print_centre/
├── backend/
│   ├── main.py                   # FastAPI app — all routes, WebSocket, lifespan
│   ├── database.py               # DB connection pool + schema helpers
│   ├── config.py                 # Settings loaded from .env (pydantic-settings)
│   ├── logging_config.py         # Structured logging setup
│   ├── requirements.txt          # Python packages (must include websockets)
│   ├── start_backend.bat         # One-click start script (Windows)
│   ├── .env                      # Your local config (NOT committed to git)
│   ├── services/
│   │   ├── auth.py               # Password hashing + JWT helpers
│   │   ├── recovery.py           # Stuck job auto-recovery
│   │   ├── alerts.py             # Email/Slack alert integration
│   │   ├── routing_service.py    # Printer failover logic
│   │   ├── barcode_service.py    # Label/barcode generation
│   │   └── audit.py              # Audit log writing
│   └── backups/                  # Automatic database backups
│
├── frontend/
│   ├── src/
│   │   ├── config.js             # API_BASE_URL from VITE_API_URL env var
│   │   ├── context/
│   │   │   ├── AuthContext.jsx   # Login state + authenticated fetch
│   │   │   └── AppData.jsx       # Shared data cache
│   │   └── pages/
│   │       ├── Dashboard.jsx
│   │       ├── Agents.jsx
│   │       ├── Mapping.jsx
│   │       ├── PrintJobs.jsx
│   │       ├── Printers.jsx
│   │       ├── Users.jsx
│   │       ├── ActivationCodes.jsx
│   │       ├── AuditLogs.jsx
│   │       └── Login.jsx
│   ├── .env                      # VITE_API_URL — must be the server's network IP
│   ├── vite.config.js            # Vite config — port 5173, host: true
│   ├── start_frontend.bat        # One-click start script (Windows)
│   └── package.json
│
└── agent/                        # Source files for the agent
    ├── agent.py                  # Main agent — WebSocket + print loop
    ├── agent_config.py           # Config read/write (stored at C:\PrintHubAgent\)
    ├── agent_setup.py            # One-time setup with activation code
    ├── agent_service.py          # Windows Service wrapper (legacy)
    ├── agent_macos.py            # macOS CUPS printing helpers
    ├── requirements.txt          # Agent Python dependencies
    ├── install_agent.bat         # Windows installer (right-click → Run as admin)
    └── install_agent.sh          # macOS/Linux installer
```

---

*PrintHub — Savetha Hospital IT Engineering*

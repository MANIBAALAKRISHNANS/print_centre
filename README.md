# PrintHub — Clinical-Grade Hospital Print Management System

**PrintHub** connects a central server to USB printers on every nursing workstation in the hospital. When a doctor submits a print job from the dashboard, the correct printer at the correct location prints it within milliseconds — no manual file transfers, no shared drives, no delays.

---

## Table of Contents

1. [How It Works (Simple Explanation)](#how-it-works)
2. [What You Need Before Starting](#what-you-need-before-starting)
3. [Part A — Running the Backend (Brain of the System)](#part-a--running-the-backend)
   - [On Your Laptop — Windows](#on-your-laptop--windows)
   - [On Your Laptop — Mac](#on-your-laptop--mac)
   - [On a Dedicated Server — Windows Server](#on-a-dedicated-server--windows-server)
   - [On a Dedicated Server — Linux / Mac Server](#on-a-dedicated-server--linux--mac-server)
4. [Part B — Running the Frontend (The Website/UI)](#part-b--running-the-frontend)
   - [On Your Laptop — Windows](#on-your-laptop--windows-1)
   - [On Your Laptop — Mac](#on-your-laptop--mac-1)
   - [On a Dedicated Server (Production)](#on-a-dedicated-server-production)
5. [Part C — Installing the Agent on Workstations](#part-c--installing-the-agent-on-workstations)
   - [Windows — Full Step-by-Step](#windows--full-step-by-step)
   - [Mac — Full Step-by-Step](#mac--full-step-by-step)
6. [Part D — Using the Dashboard After Everything is Running](#part-d--using-the-dashboard)
7. [Default Login Credentials](#default-login-credentials)
8. [Environment Variables Reference](#environment-variables-reference)
9. [Firewall & Network](#firewall--network)
10. [Troubleshooting](#troubleshooting)
11. [Architecture Overview (Technical)](#architecture-overview-technical)

---

## How It Works

Think of PrintHub as three separate programs that all need to be running at the same time:

```
┌─────────────────┐      talks to      ┌──────────────────┐      talks to      ┌──────────────────────┐
│   FRONTEND      │  ◄──────────────►  │    BACKEND       │  ◄──────────────►  │   AGENT              │
│  (The Website)  │                    │  (The Brain)     │                    │  (On each workstation)│
│  Port 5173      │                    │  Port 8000       │                    │  Installed locally    │
│                 │                    │                  │                    │                      │
│  You open this  │                    │  Stores all data │                    │  Receives jobs and    │
│  in Chrome or   │                    │  Processes jobs  │                    │  sends them to the    │
│  Edge to use    │                    │  Handles logins  │                    │  physical printer     │
│  the system     │                    │                  │                    │                      │
└─────────────────┘                    └──────────────────┘                    └──────────────────────┘
```

- **Backend** = Must always be running. All data goes through here.
- **Frontend** = The admin dashboard website. Open it in your browser.
- **Agent** = Installed on each PC connected to a printer. Receives jobs and prints them.

---

## What You Need Before Starting

You must install these programs **before** doing anything else. Each one is listed with exactly where to download it and how to install it.

### 1. Python 3.11 or newer

The backend and agent are written in Python.

**Windows:**
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the big yellow "Download Python 3.11.x" button
3. Run the installer
4. **VERY IMPORTANT:** On the first screen of the installer, check the box that says **"Add Python to PATH"** before clicking Install Now
5. After install, open PowerShell and type: `python --version` — it should say `Python 3.11.x`

**Mac:**
1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download the macOS installer
3. Run it and follow the steps
4. After install, open Terminal (press `Cmd + Space`, type "Terminal", press Enter) and type: `python3 --version` — it should say `Python 3.11.x`

> If you have Anaconda installed on Windows, use the Anaconda Prompt instead of regular PowerShell to run Python commands.

### 2. Node.js 18 or newer

The frontend is built with React and needs Node.js to run.

**Windows:**
1. Go to [nodejs.org](https://nodejs.org/)
2. Click the "LTS" (Long Term Support) version — the left button
3. Run the installer, click Next through all steps
4. Open PowerShell and type: `node --version` — should say `v18.x.x` or higher

**Mac:**
1. Go to [nodejs.org](https://nodejs.org/)
2. Download the macOS LTS version
3. Run the .pkg file and follow the steps
4. Open Terminal and type: `node --version`

### 3. Git (to download the code)

**Windows:**
1. Go to [git-scm.com](https://git-scm.com/)
2. Download and run the installer. Click Next through all steps — defaults are fine.
3. After install, right-click on your Desktop → you should see "Git Bash Here" in the menu

**Mac:**
Git usually comes pre-installed. Open Terminal and type `git --version`. If it asks you to install, click Install.

---

## Part A — Running the Backend

The backend is the brain of the whole system. It must be running before anything else works.

### On Your Laptop — Windows

**Step 1 — Download the code**

Open PowerShell (press `Win + S`, type PowerShell, press Enter):
```powershell
cd C:\Users\YourName\Desktop
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
cd print_centre
```

> Replace `YourName` with your actual Windows username.

**Step 2 — Go into the backend folder**
```powershell
cd backend
```

**Step 3 — Create a virtual environment**

A virtual environment is like a clean, separate box for Python to install packages into. It prevents conflicts with other Python projects on your computer.
```powershell
python -m venv venv
```

You should now see a `venv` folder appear in the backend directory.

> If you get a permission error saying "Access is denied" or "Permission denied", it means the venv folder already exists (from a previous install). Skip this step and continue to Step 4.

**Step 4 — Install all required packages**
```powershell
.\venv\Scripts\pip.exe install -r requirements.txt
```

This downloads and installs everything the backend needs. It may take 2-3 minutes. You will see many lines scrolling by — that is normal.

**Step 5 — Set up the configuration file**

The backend reads settings from a file called `.env`. Create it now:
```powershell
copy .env.example .env
```

Now open the `.env` file in Notepad:
```powershell
notepad .env
```

You will see something like this. Change these values:
```
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development
JWT_SECRET_KEY=CHANGE_ME_use_openssl_rand_hex_32
ALLOWED_ORIGINS=http://localhost:5173
DATABASE_PATH=./printhub.db
```

For `JWT_SECRET_KEY`, replace `CHANGE_ME_use_openssl_rand_hex_32` with a long random string. You can generate one by running:
```powershell
.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```
Copy the output and paste it as your `JWT_SECRET_KEY`.

Save and close Notepad.

**Step 6 — Start the backend**
```powershell
.\venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Started server process [XXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**The backend is now running.** Do NOT close this window — closing it stops the backend.

**Step 7 — Verify it is working**

Open Chrome or Edge and go to: `http://localhost:8000/health`

You should see a JSON response like `{"status": "healthy", ...}`. If you see this, the backend is working.

---

### On Your Laptop — Mac

**Step 1 — Download the code**

Open Terminal (Cmd + Space, type "Terminal"):
```bash
cd ~/Desktop
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
cd print_centre
```

**Step 2 — Go into the backend folder**
```bash
cd backend
```

**Step 3 — Create a virtual environment**
```bash
python3 -m venv venv
```

**Step 4 — Activate the virtual environment**

On Mac you need to activate the venv before using it:
```bash
source venv/bin/activate
```

You will notice your terminal prompt now starts with `(venv)` — this means it is activated.

**Step 5 — Install all required packages**
```bash
pip install -r requirements.txt
```

**Step 6 — Set up the configuration file**
```bash
cp .env.example .env
nano .env
```

This opens a text editor inside Terminal. Use the arrow keys to navigate. Change `JWT_SECRET_KEY` to a random string. To generate one:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

After editing, press `Ctrl + X`, then `Y`, then Enter to save.

**Step 7 — Start the backend**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

You should see `Application startup complete.` — the backend is running.

**Do NOT close the Terminal window.**

**Step 8 — Verify**

Open Safari or Chrome and go to: `http://localhost:8000/health`

You should see a JSON health response.

---

### On a Dedicated Server — Windows Server

A dedicated server is a computer that stays ON all the time and is only used to run the backend. This is what you use in a hospital production environment.

**Step 1 — Log into the server**

Connect to the server via Remote Desktop (on Windows, search for "Remote Desktop Connection", type the server's IP address).

**Step 2 — Install Python on the server**

Follow the same Python installation steps as above (laptop section). Make sure "Add Python to PATH" is checked during installation.

**Step 3 — Download the code on the server**

Open PowerShell on the server:
```powershell
cd C:\
mkdir PrintHub
cd PrintHub
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
cd print_centre\backend
```

**Step 4 — Create venv and install packages**
```powershell
python -m venv venv
.\venv\Scripts\pip.exe install -r requirements.txt
```

**Step 5 — Configure .env**
```powershell
copy .env.example .env
notepad .env
```

For a production server, also set:
```
ENVIRONMENT=production
ALLOWED_ORIGINS=http://YOUR_SERVER_IP:5173,http://YOUR_SERVER_IP
```

Replace `YOUR_SERVER_IP` with the actual IP address of your server (e.g., `192.168.1.14`).

**Step 6 — Run the backend automatically on boot using Task Scheduler**

So the backend starts automatically when the server reboots:

1. Press `Win + S`, type "Task Scheduler", open it
2. Click "Create Basic Task" on the right
3. Name: `PrintHub Backend`
4. Trigger: Select "When the computer starts"
5. Action: Select "Start a program"
6. Program: `C:\PrintHub\print_centre\backend\venv\Scripts\uvicorn.exe`
7. Arguments: `main:app --host 0.0.0.0 --port 8000`
8. Start in: `C:\PrintHub\print_centre\backend`
9. Click Finish

**Step 7 — Start it now (first time)**
```powershell
cd C:\PrintHub\print_centre\backend
.\venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000
```

**Step 8 — Find out your server's IP address**

Other people on the network will access the backend using this IP:
```powershell
ipconfig
```

Look for `IPv4 Address` — something like `192.168.1.14`. This is what you will put in the agent config and frontend config.

**Step 9 — Open the firewall port**

Run this in PowerShell as Administrator so other computers can reach the backend:
```powershell
netsh advfirewall firewall add rule name="PrintHub Backend Port 8000" dir=in action=allow protocol=TCP localport=8000
```

**Verify from another computer:**

Open a browser on a different computer on the same network and go to:
`http://192.168.1.14:8000/health` (replace with your server's actual IP)

If you see the health response, the server is accessible from the network.

---

### On a Dedicated Server — Linux / Mac Server

**Step 1 — SSH into the server**
```bash
ssh username@YOUR_SERVER_IP
```

**Step 2 — Download the code**
```bash
cd /opt
sudo mkdir printhub
sudo chown $USER:$USER printhub
cd printhub
git clone https://github.com/MANIBAALAKRISHNANS/print_centre.git
cd print_centre/backend
```

**Step 3 — Create venv and install packages**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Step 4 — Configure .env**
```bash
cp .env.example .env
nano .env
```

Set `ALLOWED_ORIGINS` to include your network IP:
```
ALLOWED_ORIGINS=http://YOUR_SERVER_IP:5173,http://YOUR_SERVER_IP,http://localhost:5173
```

**Step 5 — Run as a systemd service (auto-start on boot)**

Create a service file:
```bash
sudo nano /etc/systemd/system/printhub.service
```

Paste this content (replace `/opt/printhub/print_centre` with your actual path):
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

Press `Ctrl + X`, `Y`, Enter to save.

Enable and start it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable printhub
sudo systemctl start printhub
sudo systemctl status printhub
```

You should see `Active: active (running)` in green.

**Step 6 — Open the port in the firewall**
```bash
# Ubuntu/Debian
sudo ufw allow 8000

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

---

## Part B — Running the Frontend

The frontend is the website/dashboard you open in your browser to use PrintHub. It must be able to reach the backend.

### On Your Laptop — Windows

This is for testing/development. You run both the backend and the frontend on the same computer.

**Step 1 — Open a NEW PowerShell window**

Keep the backend window open. Open a separate new PowerShell window for the frontend.

**Step 2 — Go into the frontend folder**
```powershell
cd C:\Users\YourName\Desktop\print_centre\frontend
```

**Step 3 — Install packages**
```powershell
npm install
```

This downloads all the JavaScript packages needed. It may take 1-2 minutes.

**Step 4 — Configure the API address**

The frontend needs to know where the backend is. Open the config file:
```powershell
notepad src\config.js
```

You will see something like:
```js
export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
```

For local testing, `http://localhost:8000` is already correct. No changes needed.

If your backend is on a different computer (e.g., a server at `192.168.1.14`), create a `.env` file:
```powershell
notepad .env
```

Add this line:
```
VITE_API_URL=http://192.168.1.14:8000
```

**Step 5 — Start the frontend**
```powershell
npm run dev
```

You should see:
```
  VITE v5.x.x  ready in 300ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: http://192.168.1.xx:5173/
```

**Do NOT close this window.**

**Step 6 — Open the dashboard**

Open Chrome or Edge and go to: `http://localhost:5173`

You should see the PrintHub login screen.

---

### On Your Laptop — Mac

**Step 1 — Open a NEW Terminal tab**

Press `Cmd + T` to open a new tab (keep the backend tab open).

**Step 2 — Go to the frontend folder**
```bash
cd ~/Desktop/print_centre/frontend
```

**Step 3 — Install packages**
```bash
npm install
```

**Step 4 — Configure the API address**

For local testing, it defaults to `http://localhost:8000` automatically.

For a remote backend, create a `.env` file:
```bash
echo "VITE_API_URL=http://192.168.1.14:8000" > .env
```
Replace `192.168.1.14` with your server's actual IP.

**Step 5 — Start the frontend**
```bash
npm run dev
```

**Step 6 — Open the dashboard**

Open Safari or Chrome and go to: `http://localhost:5173`

---

### On a Dedicated Server (Production)

In production, you build the frontend into static files and serve them with nginx. This way the frontend works even without Node.js running.

**Step 1 — Build the frontend**

On the server (or on your laptop — you can copy the built files):
```bash
cd /opt/printhub/print_centre/frontend

# Create a .env file pointing to your backend
echo "VITE_API_URL=http://YOUR_SERVER_IP:8000" > .env

# Build the static files
npm install
npm run build
```

This creates a `dist/` folder with all the HTML/CSS/JS files.

**Step 2 — Install nginx**

On Ubuntu/Debian:
```bash
sudo apt update
sudo apt install nginx
```

On Windows Server:
1. Download nginx from [nginx.org/en/download.html](http://nginx.org/en/download.html)
2. Extract to `C:\nginx\`

**Step 3 — Configure nginx to serve the frontend and proxy the backend**

On Linux, edit the config:
```bash
sudo nano /etc/nginx/sites-available/printhub
```

Paste this:
```nginx
server {
    listen 80;
    server_name YOUR_SERVER_IP;

    # Serve the React frontend
    root /opt/printhub/print_centre/frontend/dist;
    index index.html;

    # For React Router — always serve index.html for unknown paths
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API requests to the backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Proxy WebSocket connections to the backend
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

Enable and start:
```bash
sudo ln -s /etc/nginx/sites-available/printhub /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

Now open a browser and go to `http://YOUR_SERVER_IP` — you should see the dashboard.

---

## Part C — Installing the Agent on Workstations

The agent is a small program you install on each workstation (nursing station PC) that has a USB printer plugged in. It connects to the backend and receives print jobs.

**Before installing the agent you need:**
1. The backend must be running
2. You must generate an **activation code** from the dashboard (see instructions below)

### How to Generate an Activation Code

1. Open the PrintHub dashboard in your browser
2. Log in as admin
3. Go to the **Agents** page (in the left menu)
4. Click **"Generate Activation Code"**
5. You will see an 8-character code like `A3F9B2C1`
6. Copy this code — it expires in 10 minutes. You will need it during agent install.

---

### Windows — Full Step-by-Step

#### What the agent does on Windows

The agent runs as a background program. When you log into Windows, it automatically starts and connects to the backend. You don't see a window — it runs silently in the background.

#### Step-by-step installation

**Step 1 — Get the agent files**

Get the `PrintHub_Agent.zip` file from your IT administrator or from the project folder.

Copy the zip file to the workstation. You can put it anywhere — for example the Desktop.

**Step 2 — Extract the zip**

Right-click on `PrintHub_Agent.zip` → Extract All → Choose `C:\` as the destination → Click Extract.

You should now have a folder: `C:\PrintHub_Agent\`

> If Windows asks about replacing existing files, click Yes.

**Step 3 — Open PowerShell as Administrator**

This is important — the installer MUST run as Administrator.

1. Press the Windows key
2. Type `PowerShell`
3. Right-click on "Windows PowerShell"
4. Click **"Run as administrator"**
5. If Windows asks "Do you want to allow this app to make changes?", click **Yes**

You will know it's running as Administrator because the title bar says "Administrator: Windows PowerShell".

**Step 4 — Check Python is installed**

In the Administrator PowerShell window, type:
```powershell
python --version
```

You should see `Python 3.11.x`. If you see an error, Python is not installed — go back and install it first.

**Step 5 — Run the installer**
```powershell
cd C:\PrintHub_Agent
.\install_agent.bat
```

The installer will now run automatically. It will show you:
```
===========================================================
 PrintHub Print Agent - Windows Installer
===========================================================

[OK] Running as Administrator.
[OK] Python 3.11.x found.
[STEP 1] Preparing installation directory C:\PrintHubAgent...
[INFO] Copying agent files...
[OK] Agent files copied to C:\PrintHubAgent
[STEP 2] Creating virtual environment...
[OK] Virtual environment created.
[STEP 3] Installing dependencies...
[OK] Dependencies installed.
```

**Step 6 — Enter the server IP and port**

The installer will ask:
```
  Server IP address (e.g. 192.168.1.50):
```
Type the IP address of the computer running the backend (e.g., `192.168.1.14`) and press Enter.

```
  Server port (press Enter for 8000):
```
Just press Enter (8000 is correct).

```
  Use HTTPS? (y/N):
```
Type `N` and press Enter (unless your IT team specifically set up HTTPS).

**Step 7 — Enter the activation code**

The installer will ask:
```
  Enter the 8-character activation code:
```
Type the code you generated from the dashboard (e.g., `A3F9B2C1`) and press Enter.

**Step 8 — Wait for installation to complete**

The installer will finish with either:
```
===========================================================
 SUCCESS! PrintHub Agent is running.
 It starts automatically on every boot.
===========================================================
```

Or if the Windows Service failed, it uses Task Scheduler:
```
[OK] Task Scheduler task created for current user.
```

Both methods mean the agent is successfully installed and running.

**Step 9 — Verify the agent is connected**

Open the PrintHub dashboard in your browser, go to **Agents** page. Within 15-30 seconds, you should see this workstation appear with a green **"Online"** badge.

#### Starting and stopping the agent manually (Windows)

The agent starts automatically when Windows starts. But if you need to manage it:

**To stop the agent:**
```powershell
schtasks /end /tn "PrintHubAgent"
```
Or open Task Manager → Details → find `python.exe` → End Task.

**To start the agent again:**
```powershell
schtasks /run /tn "PrintHubAgent"
```

**To run the agent in a visible window (for debugging):**

Open a regular (non-admin) PowerShell window:
```powershell
C:\PrintHubAgent\venv\Scripts\python.exe C:\PrintHubAgent\agent.py
```

You will see the agent's log output in real time. This is very useful for diagnosing problems. When you see `[WS] Connected`, the agent is fully working.

**To view the agent logs:**
```powershell
type C:\PrintHubAgent\agent.log
```

Or open it in Notepad:
```powershell
notepad C:\PrintHubAgent\agent.log
```

---

### Mac — Full Step-by-Step

#### What the agent does on Mac

On Mac, the agent installs as a **LaunchAgent** — a background service that starts automatically when you log in.

#### Step-by-step installation

**Step 1 — Get the agent files**

Copy `PrintHub_Agent.zip` to the Mac.

**Step 2 — Extract the zip**

Double-click `PrintHub_Agent.zip`. A folder called `PrintHub_Agent` will appear in the same location.

**Step 3 — Open Terminal**

Press `Cmd + Space`, type "Terminal", press Enter.

**Step 4 — Go to the agent folder**
```bash
cd ~/Desktop/PrintHub_Agent
```
(Replace `~/Desktop` with wherever you extracted the files.)

**Step 5 — Make the installer executable**
```bash
chmod +x install_agent.sh
```

**Step 6 — Run the installer**
```bash
bash install_agent.sh
```

The installer will ask you for:
- Server URL (e.g., `http://192.168.1.14:8000`)
- Activation code (the 8-character code from the dashboard)

**Step 7 — Enter the details**

```
  Enter server URL (e.g. http://192.168.1.50:8000): http://192.168.1.14:8000
  Enter 8-character activation code: A3F9B2C1
```

**Step 8 — Installation completes**

You should see:
```
[OK] Agent installed and started.
[OK] LaunchAgent registered — starts at login automatically.
```

**Step 9 — Verify**

Open the dashboard → Agents page. The Mac should appear as Online within 15 seconds.

#### Managing the agent on Mac

**View live logs:**
```bash
tail -f ~/Library/Logs/PrintHubAgent/agent.log
```

**Stop the agent:**
```bash
launchctl unload ~/Library/LaunchAgents/com.printhub.agent.plist
```

**Start the agent:**
```bash
launchctl load ~/Library/LaunchAgents/com.printhub.agent.plist
```

**Run in visible window (for debugging):**
```bash
~/PrintHubAgent/venv/bin/python ~/PrintHubAgent/agent.py
```

**Remove the agent completely:**
```bash
launchctl unload ~/Library/LaunchAgents/com.printhub.agent.plist
rm ~/Library/LaunchAgents/com.printhub.agent.plist
rm -rf ~/PrintHubAgent
```

---

## Part D — Using the Dashboard

Once the backend is running, the frontend is running, and at least one agent is installed and online, here is how to use the system.

### Opening the Dashboard

Open Chrome or Edge and go to:
- **If everything is on your laptop (testing):** `http://localhost:5173`
- **If there is a dedicated server:** `http://YOUR_SERVER_IP:5173` (replace with actual IP)

### Logging In

Use these default credentials (change them immediately after first login):

| Username | Password |
|---|---|
| `admin` | `Admin@PrintHub2026` |

### Pages in the Dashboard

| Page | What It Does |
|---|---|
| **Dashboard** | Overview — shows active agents, pending jobs, printer status |
| **Printers** | Add and manage physical printers |
| **Mapping** | Map each location/department to specific printers |
| **Print Jobs** | See all print jobs, retry failed ones |
| **Agents** | See all workstations running the agent (Online/Offline status) |
| **Users** | Create/delete admin and clinical user accounts |
| **Activation Codes** | Generate codes for registering new agent workstations |
| **Audit Logs** | HIPAA compliance — see every action ever taken in the system |

### Setting Up the System (First Time)

Follow this order when setting up PrintHub for the first time:

**Step 1 — Add your printers**

Go to **Printers** → click **Add Printer**. Fill in:
- Name (e.g., "Nurses Station A4 Printer")
- Category (A4 or Barcode)
- The printer's name exactly as Windows knows it (run `Get-Printer` in PowerShell to see the exact name)

**Step 2 — Set up locations/departments**

Go to **Mapping** — each row is a department/location. Click Edit on a row to assign which printer should be the Primary and which should be the Secondary (backup) for that location.

**Step 3 — Install agents on workstations**

For each workstation with a printer:
1. Go to **Activation Codes** → Generate Code (copies to your clipboard)
2. Go to that workstation → run the agent installer → enter the code

**Step 4 — Test a print job**

Go to **Mapping** → find a location that has an agent online → click the small **"A4"** or **"Bar"** test button. Check the physical printer — it should print a test page within seconds.

**Step 5 — Create user accounts for clinical staff**

Go to **Users** → Add User. Clinical users can submit print jobs but cannot change system settings.

---

## Default Login Credentials

> Change these immediately after your first login. Go to the top-right user menu → Change Password.

| Username | Password | Role |
|---|---|---|
| `admin` | `Admin@PrintHub2026` | Super Admin — full access to everything |

---

## Environment Variables Reference

These settings go in `backend/.env`. The file controls how the backend behaves.

| Variable | Required | Example | What It Does |
|---|---|---|---|
| `HOST` | No | `0.0.0.0` | Which network interface to listen on. `0.0.0.0` means all interfaces (needed so other computers can reach it). |
| `PORT` | No | `8000` | Which port the backend listens on. |
| `ENVIRONMENT` | No | `development` | Set to `production` on a real server. |
| `JWT_SECRET_KEY` | YES | (long random string) | Secret used to sign login tokens. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ALLOWED_ORIGINS` | No | `http://localhost:5173` | Which websites are allowed to talk to the backend. Add your server's IP here. Comma-separated. |
| `DATABASE_PATH` | No | `./printhub.db` | Where the SQLite database file is stored. |
| `STALE_THRESHOLD_SECONDS` | No | `45` | How many seconds without a heartbeat before an agent is marked Offline. |
| `MAX_RETRY_COUNT` | No | `3` | How many times a failed print job is retried automatically. |

---

## Firewall & Network

The backend listens on port 8000. The frontend listens on port 5173 (development) or port 80 (production with nginx).

**What ports need to be open:**

| Computer | Direction | Port | Why |
|---|---|---|---|
| Backend server | Inbound | 8000 | So agents and the dashboard can reach it |
| Backend server | Inbound | 5173 | So users can open the dashboard (dev mode) |
| Backend server | Inbound | 80 | So users can open the dashboard (production/nginx) |
| Workstations (agents) | Outbound | 8000 | So the agent can connect to the backend |

**Windows Server — Open port 8000:**
```powershell
# Run as Administrator
netsh advfirewall firewall add rule name="PrintHub Port 8000" dir=in action=allow protocol=TCP localport=8000
netsh advfirewall firewall add rule name="PrintHub Port 5173" dir=in action=allow protocol=TCP localport=5173
```

**Mac / Linux — Open port 8000:**
```bash
# Linux (Ubuntu)
sudo ufw allow 8000
sudo ufw allow 5173

# Mac — no configuration needed (Mac allows all inbound by default)
```

---

## Troubleshooting

### The backend starts but WebSocket connection fails (agent shows 404 error)

**Symptom:** Agent log shows `[WS] Error: Handshake status 404 Not Found` repeatedly.

**Cause:** The `websockets` package is not installed in the backend's virtual environment. Without it, uvicorn cannot handle WebSocket connections and returns 404 for all WebSocket routes.

**Fix:** Stop the backend, install the package, restart:
```powershell
# Windows
cd C:\...\backend
.\venv\Scripts\pip.exe install websockets "uvicorn[standard]"
.\venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000
```
```bash
# Mac/Linux
cd .../backend
source venv/bin/activate
pip install websockets "uvicorn[standard]"
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

### Agent shows "Offline" in the dashboard

**Cause 1:** The agent is not running on that workstation.

**Fix:** Open PowerShell on the workstation and run:
```powershell
C:\PrintHubAgent\venv\Scripts\python.exe C:\PrintHubAgent\agent.py
```
If you see `[WS] Connected`, the agent connects. Leave it running.

**Cause 2:** The backend is not reachable from the workstation.

**Fix:** On the workstation, open a browser and go to `http://BACKEND_IP:8000/health`. If you can't reach it, check the firewall on the server.

---

### "Cannot connect to API" or blank white screen in browser

**Cause:** The frontend cannot reach the backend.

**Fix checklist:**
1. Is the backend running? Check the backend terminal window — is it still open?
2. Is the URL correct? In `frontend/src/config.js`, does `API_BASE_URL` point to the right IP and port?
3. Is the backend port open in the firewall? Test: `http://BACKEND_IP:8000/health` in your browser.

---

### "Permission denied: venv\Scripts\python.exe" when running `python -m venv venv`

**Cause:** A venv folder already exists and its files are locked (by a running server or OneDrive).

**Fix:** You don't need to create a new venv. Skip the `python -m venv venv` step — just use the existing one with `.\venv\Scripts\pip.exe install ...`.

---

### Activation code "invalid or expired"

**Cause:** Codes expire after 10 minutes.

**Fix:** Generate a fresh code: Dashboard → Activation Codes → Generate Code → use it within 10 minutes.

---

### Print job stays "Pending" and never prints

**Fix checklist:**
1. Go to **Agents** page — is the agent for that location showing as **Online**?
2. Go to **Mapping** page — does that location have a printer assigned?
3. Is the USB printer plugged in and turned on?
4. View the agent log: `type C:\PrintHubAgent\agent.log` (Windows) or `tail -f ~/Library/Logs/PrintHubAgent/agent.log` (Mac)

---

### Frontend shows login page but login fails with "Invalid credentials"

**Cause:** Wrong username or password, or the database was reset.

**Fix:** Reset the admin password by running this on the server:
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

### Backend startup shows `CRITICAL: MISSING DEPENDENCIES: soffice, gswin64c`

**This is NOT a problem for normal operation.** These are optional tools for converting Word/PDF documents. Label printing and barcode printing work fine without them. Ignore this warning unless you specifically need to print Word or PDF documents.

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
│  │  │  on job_available│───►│  Wakes immediately on WS push│  │   │
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
| **WebSocket server** | uvicorn + websockets package (required for WebSocket support) |
| **Frontend** | React 18, Vite, React Router v6 |
| **Real-time (Dashboard)** | WebSocket `/ws` |
| **Real-time (Agents)** | WebSocket `/ws/agent` |
| **Auth** | JWT (HS256) |
| **Agent (Windows)** | Python, win32print, pywin32, websocket-client |
| **Agent (macOS)** | Python, CUPS (lpstat/lp), websocket-client |

### Project Structure

```
print_centre/
├── backend/
│   ├── main.py              # FastAPI app — all routes, WebSocket, lifespan
│   ├── database.py          # Database connection pool + helpers
│   ├── config.py            # Settings loaded from .env
│   ├── requirements.txt     # Python packages (must include websockets)
│   ├── services/
│   │   ├── recovery.py      # Stuck job auto-recovery
│   │   ├── alerts.py        # Email/SMS alerts
│   │   ├── routing_service.py # Printer failover logic
│   │   ├── barcode_service.py # Label/barcode generation
│   │   └── auth.py          # Password hashing + JWT helpers
│   └── .env                 # Your local config (NOT committed to git)
│
├── frontend/
│   ├── src/
│   │   ├── config.js        # API_BASE_URL — change this to point to your backend
│   │   ├── context/
│   │   │   └── AuthContext.jsx   # Login state + authenticated fetch helper
│   │   └── pages/
│   │       ├── Dashboard.jsx
│   │       ├── Agents.jsx
│   │       ├── Mapping.jsx
│   │       ├── PrintJobs.jsx
│   │       ├── Printers.jsx
│   │       ├── Users.jsx
│   │       ├── AuditLogs.jsx
│   │       └── Login.jsx
│   ├── .env                 # VITE_API_URL — set this for non-localhost backends
│   └── package.json
│
├── agent/
│   ├── agent.py             # Main agent — WebSocket client + print loop
│   ├── agent_config.py      # Config file read/write (stored at C:\PrintHubAgent\)
│   ├── agent_setup.py       # Setup wizard (run once with activation code)
│   ├── agent_service.py     # Windows Service wrapper
│   ├── requirements.txt     # Agent dependencies
│   ├── install_agent.bat    # Windows installer (run as Administrator)
│   └── install_agent.sh     # macOS/Linux installer
│
└── PrintHub_Agent.zip       # Ready-to-distribute agent package
```

---

*PrintHub — Savetha Hospital IT Engineering. All rights reserved.*

# 🖨️ PrintHub: Clinical-Grade Hospital Print Infrastructure

PrintHub is a robust, production-ready hybrid printing ecosystem designed for high-stakes hospital environments. It bridges the gap between modern web applications and legacy clinical hardware (Zebra Barcode Printers, Network A4 Printers) by using a distributed architecture of a central backend and local workstation agents.

---

## 🏗️ System Architecture

PrintHub consists of three core components that work in perfect synchronization:

1.  **Central Backend (FastAPI):** The brain of the system. It handles job routing, atomic leasing, HIPAA-compliant audit logging, and RBAC (Role-Based Access Control).
2.  **Management Dashboard (React):** A premium, glassmorphic UI for IT staff to monitor system health, manage users, and track real-time hardware status across the hospital.
3.  **Lightweight Print Agent (Python):** A secure service installed on local nursing workstations. It manages physical USB communication (Direct I/O) and performs hardware-level health validation.

---

## 🌟 Key Features

### 🛡️ Clinical Reliability
*   **Atomic Job Leasing:** Prevents duplicate prints in high-traffic wards. Only one agent can "own" a job at a time.
*   **Hardware-Level Validation:** Unlike standard drivers, PrintHub uses **WMI (Windows Management Instrumentation)** to detect if a USB printer is physically unplugged or in an error state.
*   **Automatic Failover:** Smart routing logic automatically redirects jobs to a secondary printer if the primary device is offline.

### 🔒 Security & Compliance
*   **HIPAA Audit Logging:** A comprehensive, immutable record of every system event. It tracks **who** did **what**, **when**, and from **which IP address**.
*   **Secure Activation:** Agents use one-time **Activation Codes** to link to the backend, eliminating the need for hardcoded passwords.
*   **Granular RBAC:** Detailed access levels tailored for Hospital IT and Clinical staff.

---

## 👥 Role-Based Access Control (RBAC)

PrintHub enforces strict access control to ensure patient data privacy and system stability.

| Role | Label | Permissions |
| :--- | :--- | :--- |
| **Admin** | Administrator | **Full System Control:** Can create/delete users, reset passwords, generate agent activation codes, view full audit logs, and manage all hardware. |
| **Operator** | IT Operator | **Infrastructure Management:** Can add/remove printers, update location mappings, and clear print queues. Cannot manage users or view sensitive audit logs. |
| **Viewer** | Clinical Staff | **Read-Only:** Can monitor the status of print jobs and see printer health. Suitable for nursing stations to verify if a label has been printed. |

---

## 📋 HIPAA Audit Logging (Admin Log)

The "Audit Log" (accessible via the Administration panel) is a forensic record designed for HIPAA compliance. Every critical action triggers an entry:

### **What is captured?**
*   **Actor:** The username or Agent ID that performed the action.
*   **Action:** Specific event type (e.g., `LOGIN`, `PRINT_JOB`, `USER_CREATE`, `PRINTER_OFFLINE`).
*   **Resource ID:** The specific printer, user, or job affected.
*   **Patient ID:** (For print jobs) The encrypted identifier of the patient whose record was printed.
*   **IP Address:** The network location of the actor.
*   **Status:** Whether the action succeeded or failed.
*   **Details:** Expanded JSON metadata for technical debugging.

---

## 📄 Intelligent Document Processing
*   **Dynamic Conversion:** Automatically converts clinical documents (DOCX/PDF) into high-fidelity print streams.
*   **ZPL Support:** Direct-to-hardware ZPL (Zebra Programming Language) support for millimetre-perfect barcode label printing.

---

## 🚀 Installation & Setup

### 1. Prerequisites
*   **Python 3.10+** (System-wide)
*   **Node.js 18+** (For the Dashboard)
*   **System Dependencies (Backend Host only):**
    *   [LibreOffice](https://www.libreoffice.org/): Required for converting clinical documents to A4 PDF.
    *   [Ghostscript](https://ghostscript.com/): Required for advanced PDF processing.
    *   *Note: Ensure both are added to your System PATH.*

### 2. Backend Installation
```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
# Run the server
uvicorn main:app --reload --port 8000
```

### 3. Frontend Dashboard
```powershell
cd frontend
npm install
npm run dev
```

### 4. Print Agent Setup (Workstation Installation)

The Print Agent is cross-platform but requires specific steps depending on the Operating System of the nursing workstation.

#### **A. Windows Installation (Recommended for Zebra USB)**
Windows agents use **WMI** and **Win32Print** for high-precision hardware monitoring.
```powershell
cd agent
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Provision the agent (Requires Code from Dashboard Admin -> Activation Codes)
python agent_setup.py --code YOUR_CODE_HERE

# Run the agent
python agent.py
```

#### **B. macOS Installation**
macOS agents use **CUPS** (`lpstat` and `lp -o raw`) for document routing.
```bash
cd agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Provision the agent
python3 agent_setup.py --code YOUR_CODE_HERE

# Run the agent
python3 agent.py
```

---

## ⚙️ How the Print Agent Works

The Print Agent is a lightweight bridge that transforms high-level API requests into physical hardware signals.

### **1. Secure Heartbeat & Polling**
The agent maintains a persistent heartbeat with the backend. Every 15 seconds, it reports its system health and local printer availability. It polls the print queue using a secure, rotating token established during the **Activation Code** handshake.

### **2. Deep Hardware Validation (Windows Only)**
Standard Windows drivers often report "Online" even if the USB cable is unplugged. PrintHub's Windows Agent bypasses the driver cache and queries the **Windows Management Instrumentation (WMI)** service directly to inspect the `WorkOffline` bit and the `DetectedErrorState` of the physical device.

### **3. Direct I/O Spooling**
*   **Barcode (ZPL):** The agent sends raw ZPL bytes directly to the printer's interface (USB Port or CUPS Raw Spooler), bypassing the print processor to ensure millimetre-perfect label alignment.
*   **A4 Documents:** The agent retrieves the processed PDF/DOCX from the backend and utilizes the system's native spooler (Win32Print or CUPS) to manage multi-page clinical records.

### **4. Atomic State Management**
The agent ensures that no two workstations can print the same job. Once it locks a job, it enters a "Printing" state. If the hardware fails mid-print, the agent reports a "Failed Agent" status, allowing IT staff to re-route the job from the dashboard.

---

## 🔗 Agent-Server Connection Protocol

The connection between a local workstation and the PrintHub server is secured via a three-phase handshake:

### **Phase 1: Activation (One-Time Handshake)**
To prevent unauthorized devices from accessing the clinical network, the agent cannot connect by simply knowing the URL. 
1.  An Administrator generates a unique **8-character Activation Code** in the Dashboard.
2.  The IT staff runs `python agent_setup.py --code CODE`.
3.  The agent sends this code + its local hostname to the server.

### **Phase 2: Identity Assignment**
If the code is valid, the server:
1.  Invalidates the code (it can never be used again).
2.  Assigns a unique **Agent ID** (e.g., `agent_489a7f`).
3.  Generates a long-lived **Security Token**.
4.  The agent saves these credentials locally in a hidden `agent_config.json` file.

### **Phase 3: Persistent Authenticated Polling**
Once activated, the agent uses its unique ID and Token for every request:
*   **Heartbeats:** Sent every 30 seconds to update the "Live" status in the Dashboard.
*   **Job Polling:** Every 5 seconds, the agent asks: *"Are there any new jobs for my assigned Location?"*
*   **Configuration Sync:** The agent automatically downloads printer mapping updates if the IT staff changes them in the Dashboard.

---

## 🔄 How the Print Flow Works

1.  **Job Creation:** A clinical system sends a job to the API (e.g., a patient wristband).
2.  **Routing:** The backend identifies the category (Barcode) and checks for an available printer in the requested ward.
3.  **Polling:** The local Print Agent (at the ward station) polls the backend via a secure token.
4.  **Atomic Lease:** The Agent "locks" the job. If the Agent crashes, the job is released for others after 60 seconds (Self-Healing).
5.  **Hardware Check:** Before printing, the Agent uses **WMI** to verify the USB cable is connected.
6.  **Direct I/O:** The Agent streams the data directly to the hardware.
7.  **Completion:** The backend is notified, and the job is moved to the Audit Log.

---

## 🌐 Remote Deployment Guide

To run the Backend on a central server and the Print Agent on nursing workstations:

### **1. Server Preparation**
1.  Run the Backend on your central server.
2.  Find the server's local IP address (Run `ipconfig` on Windows or `ifconfig` on Linux).
3.  Ensure the server's firewall allows incoming traffic on port **8000**.

### **2. Agent Deployment**
1.  **Package the Agent:** Zip the `/agent` folder from this repository.
2.  **Transfer:** Move `agent.zip` to the destination workstation.
3.  **Extract:** Unzip to a location like `C:\PrintAgent`.

### **3. Remote Setup**
On the destination workstation:
1.  **Install Python 3.10+**.
2.  **Initialize Environment:**
    ```powershell
    python -m venv venv
    .\venv\Scripts\activate
    pip install -r requirements.txt
    ```
3.  **Activate & Connect:**
    *(Replace `192.168.1.50` with your Server's IP)*
    ```powershell
    python agent_setup.py --code YOUR_CODE --server http://192.168.1.50:8000
    ```
4.  **Launch:**
    ```powershell
    python agent.py
    ```

---

## 🛠️ Common Troubleshooting

| Issue | Solution |
| :--- | :--- |
| **"Failed to Fetch"** | Ensure the Backend is running on `127.0.0.1:8000` and check CORS settings in `main.py`. |
| **"ModuleNotFoundError: wmi"** | Ensure you are running the agent with the virtual environment: `.\venv\Scripts\python.exe agent.py`. |
| **Printer shows "Offline"** | Verify the USB connection. Check `debug_wmi.py` to see the hardware-level state reporting. |
| **DOCX/PDF failing** | Verify LibreOffice (`soffice`) is installed and available in the terminal by typing `soffice --version`. |

---

## 👨‍💻 Administration Defaults
*   **Initial Username:** `admin`
*   **Initial Password:** `Admin@PrintHub2026`
*   **Security Note:** You will be forced to change this password on your first login to comply with security protocols.

---
*Developed by Savetha Hospital Clinical IT for optimized patient care and infrastructure reliability.*

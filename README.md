# 🏥 PrinterHub: Clinical-Grade Hospital Print Management

**PrinterHub** is a production-level, high-reliability hybrid printing system designed for modern hospital environments. It connects central healthcare servers with local USB and Network printers across multiple nursing workstations (Windows & macOS).

---

## 🚀 Key Production Features

*   **⚡ Real-Time Monitoring:** 5-second "Heartbeat" dashboard updates with a live visual monitor.
*   **🔌 Universal Agent:** Native support for **Windows (WMI/Win32)** and **macOS (CUPS)**.
*   **🛡️ HIPAA Compliant:** Granular Role-Based Access Control (RBAC) and detailed forensic audit logging.
*   **💾 Enterprise Database:** Supports high-concurrency **PostgreSQL** for thousands of concurrent print jobs.
*   **🤖 Automated Maintenance:** 
    *   Daily database backups at midnight.
    *   Automated 24h job expiration for clinical safety.
    *   60-second stuck-job recovery watchdog.
*   **🔥 Secure Network:** One-click firewall configuration for hospital-wide communication.

---

## 🛠️ Installation & Setup

### **1. Central Server (Backend)**
The server should be installed on a central machine accessible by all workstations.

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
*   **Security:** Run `open_server_port.bat` as Administrator to open Port 8000.
*   **Database:** See [DATABASE_MIGRATION.md](./DATABASE_MIGRATION.md) to upgrade from SQLite to PostgreSQL.

### **2. Nursing Workstations (Agent)**
Deploy the agent on any laptop or desktop connected to a USB printer.

#### **Windows Setup**
1.  Unzip `PrintHub_Agent.zip`.
2.  Right-click **`install_agent.bat`** -> **Run as Administrator**.
3.  Enter your **Server IP** and **Activation Code** when prompted.

#### **macOS Setup**
1.  Unzip `PrintHub_Agent.zip`.
2.  Open Terminal in the folder.
3.  Run: `chmod +x install_agent.sh && ./install_agent.sh`
4.  Enter your **Server IP** and **Activation Code** when prompted.

---

## 🛠️ Developer & Admin Reference

### **RBAC Roles**
| Role | Permissions |
| :--- | :--- |
| **Admin** | Full system access, users, categories, and logs. |
| **Operator** | Monitor dashboard, manage printers and jobs. |
| **Viewer** | View-only access to dashboard and logs. |

### **Connection Architecture**
The agent uses a **Token-Based Handshake**:
1.  **Handshake:** Agent uses a one-time code to get a permanent token from `/agent/register`.
2.  **Memory:** Credentials and Server IP are stored in `agent_config.json`.
3.  **Polling:** Agent polls every 5 seconds for new clinical jobs.

---

## 📜 Legal & Security
*   **Disclaimer:** This software is designed for clinical environments but should be validated by local IT staff before production use.
*   **Privacy:** All patient data is transmitted over local network protocols. Ensure your hospital network is secured (VPN/VLAN).

**Project Maintained by:** Hospital IT Engineering Team
**GitHub:** [https://github.com/MANIBAALAKRISHNANS/print_centre](https://github.com/MANIBAALAKRISHNANS/print_centre)

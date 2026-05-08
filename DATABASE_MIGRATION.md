# 🗄️ PostgreSQL Migration Guide

To upgrade your hospital infrastructure from SQLite to **PostgreSQL** for professional-grade concurrency and reliability, follow these steps.

## 1. Install PostgreSQL
1.  **Download:** [PostgreSQL for Windows](https://www.postgresql.org/download/windows/)
2.  **Install:** Follow the wizard. Set a password for the `postgres` user.
3.  **Create Database:** 
    *   Open **pgAdmin 4**.
    *   Right-click "Databases" -> Create -> Database...
    *   Name it `printhub`.

## 2. Configure the Backend
Update your `backend/config.py` or create a `.env` file in the `backend/` folder:

```ini
DB_TYPE=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=printhub
```

## 3. Re-install Dependencies
On the Server:
```powershell
cd backend
.\venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Run the Project
Start the backend normally. On startup, it will detect the new database type and automatically create all the necessary tables and indexes.

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🔒 Security Note: Windows "Unknown Publisher" Warnings
When running the `install_agent.bat` file, you may see a blue screen or a warning saying "Unknown Publisher." 

### **Why this happens:**
This is a standard Windows security feature for script files (`.bat`, `.ps1`) that do not have an expensive Digital Signature Certificate. 

### **How to verify safety:**
1.  **Transparency:** You can right-click any `.bat` or `.sh` file and select **Edit**.
2.  **Code Review:** You will see the exact same code that is pushed to your GitHub. There are no compiled "black boxes" or hidden scripts.
3.  **Action:** Click **"More info"** -> **"Run anyway"**.

*This system is designed by clinical IT professionals for hospital reliability. The scripts only manage Python environments and Windows Services.*

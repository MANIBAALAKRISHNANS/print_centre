import os
import uuid
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import init_db, get_connection, utcnow, JobStatus, VALID_STATUSES
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from datetime import datetime, timezone

from services.barcode_service import build_print_payload, generate_patient_id
from services.routing_service import print_with_failover, mark_job, log_print_event
from services.printer_service import send_to_printer

print_queue = Queue()
try:
    import win32api
    import win32print
except ImportError:
    win32api = None
    win32print = None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# Models
class Printer(BaseModel):
    name: str
    ip: str
    category: str
    status: str
    language: str 

class Location(BaseModel):
    name: str

class Category(BaseModel):
    name: str

def print_barcode(
    printer_ip,
    patient_name,
    age,
    gender,
    patient_id,
    tube_type,
    location,
    job_id,
    visit_id,
    datetime_str
):
    # 🔹 Limit long name (prevents overlap on label)
    patient_name = (patient_name or "")[:20]

    # 🔹 Handle empty visit_id safely
    visit_id = visit_id if visit_id else ""
    tube_type = (tube_type or "")[:30]
    try:
        zpl = f"""
^XA
^PW812
^LL230
^CI28

^CF0,24

^FO20,10^FD{age}Y / {gender}^FS

^BY2,2,60
^FO20,50
^BCN,60,Y,N,N
^FD{patient_id}^FS

^CF0,22

^FO20,130^FD{patient_id}^FS

^CF0,20

^FO20,170^FD{datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S").strftime("%d/%m")}^FS
^FO140,170^FD{datetime_str.split(" ")[1]}^FS

^XZ
"""

        send_to_printer(printer_ip, zpl.encode("utf-8"))

        import time
        time.sleep(2)

        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "UPDATE print_jobs SET status=? WHERE id=?",
            ("Completed", job_id)
        )

        conn.commit()
        conn.close()

    except Exception as e:
        print("Barcode Print Error:", e)
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "UPDATE print_jobs SET status=? WHERE id=?",
            ("Failed", job_id)
        )

        conn.commit()
        conn.close()



@app.post("/print-a4-file")
async def print_a4_file_api(
    location: str = Form(...),
    file: UploadFile = File(...)
):
    """API for uploading and printing A4 documents with validation."""
    if not file.filename.lower().endswith((".pdf", ".doc", ".docx", ".txt")):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF, DOC, DOCX, TXT allowed.")

    os.makedirs("uploads", exist_ok=True)
    unique_name = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join("uploads", unique_name)
    file_type = file.filename.split(".")[-1].lower()
    
    file_size = 0
    try:
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > 10 * 1024 * 1024:
                    raise Exception("File too large. Limit is 10MB.")
                buffer.write(chunk)
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(e))

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO print_jobs 
        (location, category, printer, status, type, time, file_path, file_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            location,
            "A4",
            "Pending",
            "Queued",
            "File",
            utcnow(),
            file_path,
            file_type
        )
    )
    conn.commit()
    job_id = cur.lastrowid
    conn.close()

    print_queue.put({
        "job_id": job_id,
        "location": location,
        "category": "A4",
        "file_path": file_path
    })

    return {"message": "A4 Print Job Queued", "job_id": job_id}

def process_queue():
    """Background worker to process queued print jobs."""
    while True:
        try:
            job = print_queue.get(timeout=1)
        except:
            continue

        if not job:
            continue

        try:
            job_id = job["job_id"]
            location = job["location"]
            category = job["category"]
            if category == "A4":
                payload = job.get("file_path", "")
            else:
                payload = job.get("payload", "")

            print(f"[QUEUE] Processing job {job_id} - {category} at {location}")

            # Use routing service to handle failover
            try:
                final_printer, final_type = print_with_failover(
                    job_id,
                    location,
                    category,
                    payload
                )
                print(f"[QUEUE] Job {job_id} completed on {final_printer['name']} ({final_type})")
            except Exception as routing_err:
                err_msg = str(routing_err)
                if "RETRY" in err_msg:
                    print(f"[QUEUE] Retrying job {job_id}: {err_msg}")
                    import time
                    time.sleep(2)  # Wait briefly before putting back
                    print_queue.put(job)
                else:
                    print(f"[QUEUE] Job {job_id} failed: {err_msg}")
                    mark_job(job_id, "Failed")
                    log_print_event(job_id, "Queue", "Failed", err_msg)

        except Exception as e:
            print(f"[QUEUE] Unexpected error: {e}")

        finally:
            print_queue.task_done()
def check_printer(ip, printer_name=None):
    """Check if printer is accessible via IP or USB."""
    ip_live = False
    usb_live = False

    # 🔹 1. Try IP check
    if ip and ip.strip():
        is_valid_ip = False
        try:
            # Simple validation to ensure it's not a weird string like '192.168.0.37_1'
            socket.inet_aton(ip.split(':')[0]) # Handle IP or IP:port
            is_valid_ip = True
        except:
            pass

        if is_valid_ip:
            try:
                with socket.create_connection((ip, 9100), timeout=0.75):
                    print(f"[CHECK] Printer {printer_name or ip} - Live (IP: {ip})")
                    ip_live = True
            except (socket.timeout, socket.error):
                pass
            except Exception as e:
                print(f"[CHECK] IP check error for {ip}: {e}")

    # 🔹 2. USB / Windows Printer Check (if not already live via IP)
    if not ip_live:
        try:
            if win32print is not None:
                # Enum local and network printers
                printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)

                for p in printers:
                    system_name = p[2]

                    # Match printer name EXACTLY (case-insensitive)
                    # This prevents "Printer" from matching "Printer-1"
                    if printer_name and printer_name.strip().lower() == system_name.strip().lower():
                        try:
                            handle = win32print.OpenPrinter(system_name)
                            # GetPrinter level 2 includes Attributes and Status
                            info = win32print.GetPrinter(handle, 2)
                            win32print.ClosePrinter(handle)
                            
                            status = info.get("Status", 0)
                            attr = info.get("Attributes", 0)
                            
                            # Check for Offline status or Work Offline attribute
                            # PRINTER_STATUS_OFFLINE = 0x80
                            # PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x400
                            is_offline = (status & 0x80) or (attr & 0x400)
                            
                            if is_offline:
                                print(f"[CHECK] Printer {printer_name} - Offline (Windows reported Offline)")
                                continue
                                
                            print(f"[CHECK] Printer {printer_name} - Live (USB/Windows)")
                            usb_live = True
                            break # Found our exact match and it's live
                        except Exception as e:
                            print(f"[CHECK] Error getting printer details for {system_name}: {e}")
                            continue
        except Exception as e:
            print(f"[CHECK] USB check error: {e}")

    return ip_live or usb_live

@app.get("/check-printers")
def check_printers():
    """Check status of all printers with optimized worker pool."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT id, ip, name FROM printers")
        printers = [dict(row) for row in cur.fetchall()]
        conn.close()

        if not printers:
            return {"message": "No printers to check", "printers": []}

        def status_for_printer(printer):
            try:
                is_live = check_printer(printer["ip"], printer.get("name"))
                status = "Live" if is_live else "Offline"
                return (status, printer["id"])
            except Exception as e:
                print(f"[CHECK] Error checking printer {printer['id']}: {e}")
                return ("Offline", printer["id"])

        # Use fewer workers to reduce database lock contention
        with ThreadPoolExecutor(max_workers=8) as executor:
            updates = list(executor.map(status_for_printer, printers))

        # Batch update with transaction
        if updates:
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.executemany(
                    "UPDATE printers SET status=? WHERE id=?",
                    updates
                )
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"[CHECK] Database update error: {e}")

        return {
            "message": "Printer status updated",
            "printers": [
                {"id": printer["id"], "status": status}
                for printer, (status, _) in zip(printers, updates)
            ]
        }
    except Exception as e:
        print(f"[CHECK] Unexpected error: {e}")
        return {"error": str(e), "printers": []}


@app.get("/")
def home():
    return {"message": "Backend Running"}

# ---------------- MAPPING
@app.get("/mapping")
def get_mapping():
    conn = get_connection()
    cur = conn.cursor()

    # 🔹 Get mapping
    cur.execute("SELECT * FROM mapping")
    mappings = [dict(row) for row in cur.fetchall()]

    # 🔹 Get printers status
    cur.execute("SELECT name, status FROM printers")
    printers = {row["name"]: row["status"] for row in cur.fetchall()}

    conn.close()

    result = []

    for m in mappings:

        # ---------- A4 ----------
        a4_primary_status = printers.get(m["a4Primary"], "Offline")
        a4_secondary_status = printers.get(m["a4Secondary"], "Offline")

        if a4_primary_status == "Live":
            m["a4Active"] = m["a4Primary"]
            m["a4Type"] = "Primary"
        else:
            m["a4Active"] = m["a4Secondary"]
            m["a4Type"] = "Failover"

        # ---------- BARCODE ----------
        bar_primary_status = printers.get(m["barPrimary"], "Offline")
        bar_secondary_status = printers.get(m["barSecondary"], "Offline")

        if bar_primary_status == "Live":
            m["barActive"] = m["barPrimary"]
            m["barType"] = "Primary"
        else:
            m["barActive"] = m["barSecondary"]
            m["barType"] = "Failover"

        result.append(m)

    return result


@app.get("/mapping-validate")
def validate_mapping():
    """Validate all mappings for missing or offline printers."""
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Get all mappings
        cur.execute("SELECT * FROM mapping")
        mappings = [dict(row) for row in cur.fetchall()]

        # Get all printers
        cur.execute("SELECT name, status FROM printers")
        printers = {row["name"]: row["status"] for row in cur.fetchall()}

        conn.close()

        issues = []

        for mapping in mappings:
            location = mapping["location"]

            # Check each printer reference
            for field, printer_name in [
                ("a4Primary", mapping["a4Primary"]),
                ("a4Secondary", mapping["a4Secondary"]),
                ("barPrimary", mapping["barPrimary"]),
                ("barSecondary", mapping["barSecondary"]),
            ]:
                if printer_name and printer_name != "None":
                    if printer_name not in printers:
                        issues.append({
                            "location": location,
                            "field": field,
                            "printer": printer_name,
                            "issue": "Printer does not exist"
                        })
                    elif printers[printer_name] != "Live":
                        issues.append({
                            "location": location,
                            "field": field,
                            "printer": printer_name,
                            "status": printers[printer_name],
                            "issue": "Printer is offline"
                        })

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "total_mappings": len(mappings),
            "issues_count": len(issues)
        }

    except Exception as e:
        return {"error": str(e), "valid": False}




@app.put("/mapping/{mapping_id}")
def update_mapping(mapping_id: int, data: dict):
    """Update an existing printer mapping."""
    try:
        a4_primary = data.get("a4Primary", "None")
        a4_secondary = data.get("a4Secondary", "None")
        bar_primary = data.get("barPrimary", "None")
        bar_secondary = data.get("barSecondary", "None")

       

        conn = get_connection()
        cur = conn.cursor()

        # Check mapping exists
        cur.execute("SELECT * FROM mapping WHERE id=?", (mapping_id,))
        if not cur.fetchone():
            conn.close()
            return {"error": "Mapping not found"}

        # Validate printers exist (if not "None")
        def validate_printer(name):
            if name and name != "None":
                cur.execute("SELECT * FROM printers WHERE name=?", (name,))
                return cur.fetchone() is not None
            return True

        for printer_name in [a4_primary, a4_secondary, bar_primary, bar_secondary]:
            if not validate_printer(printer_name):
                conn.close()
                return {"error": f"Printer '{printer_name}' does not exist"}

        # Validate no duplicates for Primary/Secondary
        if a4_primary != "None" and a4_primary == a4_secondary:
            conn.close()
            return {"error": "A4 Primary and Secondary cannot be the same"}

        if bar_primary != "None" and bar_primary == bar_secondary:
            conn.close()
            return {"error": "Barcode Primary and Secondary cannot be the same"}

        # Update mapping
        cur.execute("""
            UPDATE mapping
            SET a4Primary=?, a4Secondary=?, barPrimary=?, barSecondary=?
            WHERE id=?
        """, (a4_primary, a4_secondary, bar_primary, bar_secondary, mapping_id))

        conn.commit()
        conn.close()

        return {"message": "Mapping updated successfully"}
    except Exception as e:
        return {"error": str(e)}

# ---------------- PRINTERS
@app.get("/printers")
def get_printers():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM printers")
    rows = cur.fetchall()

    conn.close()
    result = []

    for row in rows:
        printer = dict(row)

        # 🔹 Check live status (IP + USB)
        is_live = check_printer(printer["ip"], printer["name"])

        printer["status"] = "Live" if is_live else "Offline"

        result.append(printer)

    return result


@app.post("/printers")
def add_printer(data: Printer):
    name = data.name.strip()
    ip = data.ip.strip()

    if not name or not ip:
        return {"error": "Printer name and IP are required"}

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM printers WHERE ip=?", (ip,))
    if cur.fetchone():
        conn.close()
        return {"error": "Printer already exists with this IP"}

    cur.execute("SELECT * FROM printers WHERE name=?", (name,))
    if cur.fetchone():
        conn.close()
        return {"error": "Printer already exists with this name"}

    if data.category not in ["A4", "Barcode"]:
        conn.close()
        return {"error": "Invalid category"}

    cur.execute(
        "INSERT INTO printers (name, ip, category, status, language) VALUES (?, ?, ?, ?, ?)",
        (name, ip, data.category, data.status, data.language)
    )

    conn.commit()
    printer_id = cur.lastrowid
    conn.close()

    return {"message": "Printer Added", "id": printer_id}
@app.put("/printers/{printer_id}")
def update_printer_status(printer_id: int, data: Printer):
    """Update printer details with transactional cascading updates."""
    name = data.name.strip()
    ip = data.ip.strip()

    if not name or not ip:
        return {"error": "Printer name and IP are required"}

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM printers WHERE id=?", (printer_id,))
        existing = cur.fetchone()
        if not existing:
            conn.close()
            return {"error": "Printer not found"}

        cur.execute(
            "SELECT * FROM printers WHERE ip=? AND id<>?",
            (ip, printer_id)
        )
        if cur.fetchone():
            conn.close()
            return {"error": "Printer already exists with this IP"}

        cur.execute(
            "SELECT * FROM printers WHERE name=? AND id<>?",
            (name, printer_id)
        )
        if cur.fetchone():
            conn.close()
            return {"error": "Printer already exists with this name"}

        if data.category not in ["A4", "Barcode"]:
            conn.close()
            return {"error": "Invalid category"}

        # Update printer
        cur.execute(
            """
            UPDATE printers
            SET name=?, ip=?, category=?, status=?, language=?
            WHERE id=?
            """,
            (
                name,
                ip,
                data.category,
                data.status,
                data.language,
                printer_id
            )
        )

        # Cascade name change to mappings (atomic transaction)
        old_name = existing["name"]
        if old_name != name:
            cur.execute("UPDATE mapping SET a4Primary=? WHERE a4Primary=?", (name, old_name))
            cur.execute("UPDATE mapping SET a4Secondary=? WHERE a4Secondary=?", (name, old_name))
            cur.execute("UPDATE mapping SET barPrimary=? WHERE barPrimary=?", (name, old_name))
            cur.execute("UPDATE mapping SET barSecondary=? WHERE barSecondary=?", (name, old_name))

        conn.commit()
        conn.close()

        return {"message": "Printer updated successfully"}

    except Exception as e:
        if conn:
            conn.rollback()
            conn.close()
        print(f"[PRINTER UPDATE] Error: {e}")
        return {"error": str(e)}

@app.delete("/printers/{printer_id}")
def delete_printer(printer_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM printers WHERE id=?", (printer_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        return {"error": "Printer not found"}

    cur.execute(
        "DELETE FROM printers WHERE id=?",
        (printer_id,)
    )

    printer_name = existing["name"]
    cur.execute("UPDATE mapping SET a4Primary='None' WHERE a4Primary=?", (printer_name,))
    cur.execute("UPDATE mapping SET a4Secondary='None' WHERE a4Secondary=?", (printer_name,))
    cur.execute("UPDATE mapping SET barPrimary='None' WHERE barPrimary=?", (printer_name,))
    cur.execute("UPDATE mapping SET barSecondary='None' WHERE barSecondary=?", (printer_name,))

    conn.commit()
    conn.close()

    return {"message": "Printer Deleted"}

# ---------------- LOCATIONS
@app.get("/locations")
def get_locations():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM locations")
    rows = cur.fetchall()

    conn.close()

    return [row["name"] for row in rows]


@app.post("/locations")
def add_location(data: Location):
    name = data.name.strip()
    if not name:
        return {"error": "Location name is required"}

    conn = get_connection()
    cur = conn.cursor()

    # Prevent duplicate location
    cur.execute("SELECT * FROM locations WHERE name=?", (name,))
    if cur.fetchone():
        conn.close()
        return {"error": "Location already exists"}

    # Insert location
    cur.execute(
        "INSERT INTO locations (name) VALUES (?)",
        (name,)
    )

    # Prevent duplicate mapping
    cur.execute(
        "SELECT * FROM mapping WHERE location=?",
        (name,)
    )
    if not cur.fetchone():
        cur.execute(
            """
            INSERT INTO mapping (
                location,
                a4Primary,
                a4Secondary,
                barPrimary,
                barSecondary
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (name, "None", "None", "None", "None")
        )

    conn.commit()
    conn.close()

    return {"message": "Location Added with Mapping"}

@app.put("/locations/{old_name}")
def update_location(old_name: str, data: Location):
    old_name = old_name.strip()
    new_name = data.name.strip()

    if not new_name:
        return {"error": "Location name is required"}

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM locations WHERE name=?", (old_name,))
    if not cur.fetchone():
        conn.close()
        return {"error": "Location not found"}

    cur.execute(
        "SELECT * FROM locations WHERE name=? AND name<>?",
        (new_name, old_name)
    )
    if cur.fetchone():
        conn.close()
        return {"error": "Location already exists"}

    # Update locations table
    cur.execute(
        "UPDATE locations SET name=? WHERE name=?",
        (new_name, old_name)
    )

    # ALSO update mapping table
    cur.execute(
        "UPDATE mapping SET location=? WHERE location=?",
        (new_name, old_name)
    )

    conn.commit()
    conn.close()

    return {"message": "Location Updated"}


@app.delete("/locations/{name}")
def delete_location(name: str):
    name = name.strip()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM locations WHERE name=?", (name,))
    if not cur.fetchone():
        conn.close()
        return {"error": "Location not found"}

    # Delete mapping FIRST
    cur.execute("DELETE FROM mapping WHERE location=?", (name,))

    # Then delete location
    cur.execute("DELETE FROM locations WHERE name=?", (name,))

    conn.commit()
    conn.close()

    return {"message": "Location Deleted"}

# ---------------- CATEGORIES
@app.get("/categories")
def get_categories():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM categories")
    rows = cur.fetchall()

    conn.close()

    return [row["name"] for row in rows]


@app.post("/categories")
def add_category(data: Category):
    name = data.name.strip()
    if not name:
        return {"error": "Category name is required"}

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM categories WHERE name=?", (name,))
    if cur.fetchone():
        conn.close()
        return {"error": "Category already exists"}

    cur.execute(
        "INSERT INTO categories (name) VALUES (?)",
        (name,)
    )

    conn.commit()
    conn.close()

    return {"message": "Category Added"}

@app.put("/categories/{old_name}")
def update_category(old_name: str, data: Category):
    old_name = old_name.strip()
    new_name = data.name.strip()

    if not new_name:
        return {"error": "Category name is required"}

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM categories WHERE name=?", (old_name,))
    if not cur.fetchone():
        conn.close()
        return {"error": "Category not found"}

    cur.execute(
        "SELECT * FROM categories WHERE name=? AND name<>?",
        (new_name, old_name)
    )
    if cur.fetchone():
        conn.close()
        return {"error": "Category already exists"}

    cur.execute(
        "UPDATE categories SET name=? WHERE name=?",
        (new_name, old_name)
    )

    cur.execute(
        "UPDATE printers SET category=? WHERE category=?",
        (new_name, old_name)
    )

    conn.commit()
    conn.close()

    return {"message": "Category Updated"}


@app.delete("/categories/{name}")
def delete_category(name: str):
    name = name.strip()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM categories WHERE name=?", (name,))
    if not cur.fetchone():
        conn.close()
        return {"error": "Category not found"}

    cur.execute("SELECT COUNT(*) FROM printers WHERE category=?", (name,))
    if cur.fetchone()[0] > 0:
        conn.close()
        return {"error": "Cannot delete category while printers are using it"}

    cur.execute(
        "DELETE FROM categories WHERE name=?",
        (name,)
    )

    conn.commit()
    conn.close()

    return {"message": "Category Deleted"}

# ---------------- DASHBOARD
@app.get("/dashboard")
def dashboard():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM printers")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM printers WHERE status='Live'")
    live = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM printers WHERE status='Offline'")
    offline = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM printers WHERE status='Maintenance'")
    maintenance = cur.fetchone()[0]

    conn.close()

    # Job stats
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM print_jobs")
    total_jobs = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM print_jobs WHERE status='Completed'")
    completed_jobs = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM print_jobs WHERE status='Failed'")
    failed_jobs = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM print_jobs WHERE COALESCE(retry_count, 0) > 0")
    retried_jobs = cur.fetchone()[0]

    # Printer-level analytics: jobs per printer
    # COALESCE(retry_count,0) handles NULLs; TRIM() guards whitespace-only names
    cur.execute("""
        SELECT
            printer,
            COUNT(*) as job_count,
            SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN status='Failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN COALESCE(retry_count, 0) > 0 THEN 1 ELSE 0 END) as retried,
            ROUND(
                100.0 * SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0)
            , 1) as success_rate
        FROM print_jobs
        WHERE
            printer IS NOT NULL
            AND TRIM(printer) != ''
            AND printer NOT IN ('Pending', 'None')
        GROUP BY printer
        ORDER BY job_count DESC
    """)
    printer_stats = [dict(row) for row in cur.fetchall()]

    conn.close()

    return {
        "total": total,
        "live": live,
        "offline": offline,
        "maintenance": maintenance,
        "jobs": {
            "total": total_jobs,
            "completed": completed_jobs,
            "failed": failed_jobs,
            "retried": retried_jobs
        },
        "printer_stats": printer_stats
    }


@app.post("/print-job")
def print_job(data: dict):
    """Queue a print job for async processing."""
    try:
        location = data.get("location")
        category = data.get("category")
        patient_name = data.get("patient_name")
        age = data.get("age")
        gender = data.get("gender")
        patient_id = data.get("patient_id")
        tube_type = data.get("tube_type")
        visit_id = data.get("visit_id")
        datetime_str = data.get("datetime")

        if category not in ["A4", "Barcode"]:
            return {"error": "Invalid category"}

        if not location:
            return {"error": "Location is required"}

        if not datetime_str:
            datetime_str = utcnow()

        if category == "Barcode":
            required_fields = [
                patient_name,
                age,
                gender,
                tube_type,
                datetime_str
            ]

            if not all(required_fields):
                return {"error": "All barcode fields are required"}

            if not patient_id:
                patient_id = generate_patient_id()

        conn = get_connection()
        cur = conn.cursor()

        # Check for duplicate patient_id (if barcode job)
        if category == "Barcode" and patient_id:
            cur.execute(
                "SELECT id FROM print_jobs WHERE patient_id=? AND status NOT IN ('Failed', 'Cancelled')",
                (patient_id,)
            )
            if cur.fetchone():
                conn.close()
                return {
                    "error": f"Patient ID {patient_id} already has an active print job",
                    "patient_id": patient_id
                }

        # 1. Get mapping
        cur.execute("SELECT * FROM mapping WHERE location=?", (location,))
        mapping = cur.fetchone()

        if not mapping:
            conn.close()
            return {"error": "No mapping found for location"}

        # 2. Save job with initial status
        now = utcnow()

        cur.execute("""
            INSERT INTO print_jobs 
            (location, category, printer, status, type, time, patient_name, age, gender, patient_id, tube_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            location,
            category,
            "Pending",
            "Queued",
            "None",
            now,
            patient_name,
            age,
            gender,
            patient_id,
            tube_type
        ))

        conn.commit()
        job_id = cur.lastrowid  
        conn.close()

        # 3. Build payload
        payload = build_print_payload({
            "location": location,
            "category": category,
            "patient_name": patient_name,
            "age": age,
            "gender": gender,
            "patient_id": patient_id,
            "tube_type": tube_type,
            "visit_id": visit_id,
            "datetime": datetime_str,
        })

        # 4. Queue for background processing
        print_queue.put({
            "job_id": job_id,
            "location": location,
            "category": category,
            "payload": payload,
        })

        print(f"[API] Job {job_id} queued for printing")

        return {
            "job_id": job_id,
            "location": location,
            "category": category,
            "patient_id": patient_id,
            "status": "Queued",
            "message": "Job queued for processing"
        }

    except Exception as e:
        print(f"[API] Print job error: {e}")
        return {"error": str(e)}


@app.get("/print-jobs")
def get_print_jobs(
    status: str = None,
    retried: bool = False,
    limit: int = 200,
    offset: int = 0
):
    """
    Backend-level filtering with pagination.
    ?status=Completed|Failed|Queued|Printing|Retrying
    ?retried=true  — only jobs that had retries
    ?limit=N       — page size (default 200, max 1000)
    ?offset=N      — skip first N rows for pagination
    Returns: { jobs: [...], total: N, limit: N, offset: N }
    """
    limit = min(max(limit, 1), 1000)
    offset = max(offset, 0)

    # Validate status value if provided
    if status and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status '{status}'. Valid values: {sorted(VALID_STATUSES)}")

    conn = get_connection()
    cur = conn.cursor()

    conditions = []
    params = []

    if status:
        conditions.append("status = ?")
        params.append(status)

    if retried:
        conditions.append("COALESCE(retry_count, 0) > 0")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Total count for pagination metadata
    cur.execute(f"SELECT COUNT(*) FROM print_jobs {where}", params)
    total = cur.fetchone()[0]

    params_page = params + [limit, offset]
    cur.execute(f"SELECT * FROM print_jobs {where} ORDER BY id DESC LIMIT ? OFFSET ?", params_page)
    rows = cur.fetchall()
    conn.close()

    return {
        "jobs": [dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.get("/print-logs")
def get_print_logs(limit: int = 200, offset: int = 0):
    limit = min(max(limit, 1), 1000)
    offset = max(offset, 0)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM print_logs")
    total = cur.fetchone()[0]
    cur.execute("SELECT * FROM print_logs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = cur.fetchall()
    conn.close()
    return {"logs": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

@app.get("/print-logs/{job_id}")
def get_job_logs(job_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM print_logs WHERE job_id=? ORDER BY id ASC",
        (job_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.delete("/print-jobs")
def clear_print_jobs():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM print_jobs")

    conn.commit()
    conn.close()

    return {"message": "All print jobs cleared"}

@app.get("/active-printer/{location}/{category}")
def get_active_printer(location: str, category: str):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM mapping WHERE location=?", (location,))
    mapping = cur.fetchone()

    if not mapping:
        return {"printer": "None", "type": "None"}

    if category == "A4":
        primary = mapping["a4Primary"]
        secondary = mapping["a4Secondary"]
    else:
        primary = mapping["barPrimary"]
        secondary = mapping["barSecondary"]

    # Check primary
    cur.execute("SELECT * FROM printers WHERE name=?", (primary,))
    p1 = cur.fetchone()

    printer_ip = None

    if p1:
        printer_ip = p1["ip"]

    if p1 and p1["status"] == "Live":
        result = {"printer": primary, "type": "Primary"}
    else:
        result = {"printer": secondary, "type": "Failover"}

    conn.close()

    return result


import time

def auto_check():
    """Background worker to periodically check printer status."""
    last_check = 0
    check_interval = 10  # Check every 10 seconds (reduced from 5)
    
    while True:
        try:
            current_time = time.time()
            if current_time - last_check >= check_interval:
                check_printers()
                last_check = current_time
        except Exception as e:
            print(f"[AUTO_CHECK] Error: {e}")
        
        time.sleep(1)  # Small sleep to prevent busy-waiting

threading.Thread(target=auto_check, daemon=True).start()
threading.Thread(target=process_queue, daemon=True).start()

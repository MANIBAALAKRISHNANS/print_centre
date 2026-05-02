from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import init_db, get_connection
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from datetime import datetime
from services.barcode_service import build_print_payload, generate_patient_id
from services.routing_service import print_with_failover

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
^PW600
^LL280
^CI28

^CF0,28

^FO20,20^FD{patient_name} / {age}Y / {gender}^FS
^FO580,20^FB200,1,0,R^FD{visit_id}^FS

^BY2,2,60
^FO20,70
^BCN,70,Y,N,N
^FD{patient_id}^FS

^CF0,24
^FO20,160^FD{datetime_str}^FS

^CF0,26
^FO20,200^FD{tube_type}^FS

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

def send_to_printer(ip, data):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        s.connect((ip, 9100))
        s.sendall(data)
        s.close()
    except Exception as e:
        print("IP Print Error:", e)
        raise e


def print_a4_ip(printer_ip, patient_name, location):
  
    text = f"""
Patient: {patient_name}
Location: {location}
"""

    # Basic PCL format (works for most printers)
    pcl = f"\x1B%-12345X@PJL JOB\n{text}\n\x1B%-12345X"

    send_to_printer(printer_ip, pcl.encode("utf-8"))

def print_a4_file(file_path, printer_name, job_id):
    try:
        if win32api is None or win32print is None:
            raise RuntimeError("pywin32 is required for Windows spooler printing")

        win32print.SetDefaultPrinter(printer_name)

        win32api.ShellExecute(
            0,
            "print",
            file_path,
            None,
            ".",
            0
        )

        print("A4 File Sent")

        # ✅ WAIT LITTLE (simulate print time)
        import time
        time.sleep(3)

        # ✅ UPDATE STATUS → Completed
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "UPDATE print_jobs SET status=? WHERE id=?",
            ("Completed", job_id)
        )

        conn.commit()
        conn.close()

    except Exception as e:
        print("A4 Print Error:", e)
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "UPDATE print_jobs SET status=? WHERE id=?",
            ("Failed", job_id)
        )

        conn.commit()
        conn.close()
def process_queue():
    while True:
        job = print_queue.get()

        if not job:
            continue

        try:
            printer_ip = job["printer_ip"]
            category = job["category"]
            patient_name = job["patient_name"]
            age = job["age"]
            gender = job["gender"]
            patient_id = job["patient_id"]
            tube_type = job["tube_type"]
            visit_id = job.get("visit_id")
            datetime_str = job.get("datetime")
            location = job["location"]
            job_id = job["job_id"]
            file_path = job.get("file_path")
            printer_name = job["printer_name"]

            print(f"Processing job {job_id}")

            if category == "Barcode":
                print_barcode(
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
                )

            elif category == "A4":
                if file_path:
                    print_a4_file(file_path, printer_name, job_id)
                else:
                    print("No file provided for A4 job")

                    conn = get_connection()
                    cur = conn.cursor()

                    cur.execute(
                        "UPDATE print_jobs SET status=? WHERE id=?",
                        ("Failed", job_id)
                    )

                    conn.commit()
                    conn.close()


        except Exception as e:
            print("Queue Error:", e)

        print_queue.task_done()
def check_printer(ip):
    if not ip:
        return False

    try:
        with socket.create_connection((ip, 9100), timeout=0.75):
            return True
    except Exception:
        return False

@app.get("/check-printers")
def check_printers():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, ip FROM printers")
    printers = [dict(row) for row in cur.fetchall()]
    conn.close()

    def status_for_printer(printer):
        is_live = check_printer(printer["ip"])
        status = "Live" if is_live else "Offline"
        return (status, printer["id"])

    with ThreadPoolExecutor(max_workers=16) as executor:
        updates = list(executor.map(status_for_printer, printers))

    conn = get_connection()
    cur = conn.cursor()

    if updates:
        cur.executemany(
            "UPDATE printers SET status=? WHERE id=?",
            updates
        )

    conn.commit()
    conn.close()

    return {
        "message": "Printer status updated",
        "printers": [
            {"id": printer["id"], "status": status}
            for printer, (status, _) in zip(printers, updates)
        ]
    }

@app.get("/")
def home():
    return {"message": "Backend Running"}

# ---------------- MAPPING
@app.get("/mapping")
def get_mapping():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM mapping")
    rows = cur.fetchall()

    conn.close()

    return [dict(row) for row in rows]


@app.post("/mapping")
def add_mapping(data: dict):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO mapping
        (location, a4Primary, a4Secondary, barPrimary, barSecondary)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            data["location"],
            data["a4Primary"],
            data["a4Secondary"],
            data["barPrimary"],
            data["barSecondary"],
        )
    )

    conn.commit()
    conn.close()

    return {"message": "Mapping Added"}

@app.put("/mapping/{mapping_id}")
def update_mapping(mapping_id: int, data: dict):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE mapping
        SET location=?, a4Primary=?, a4Secondary=?, barPrimary=?, barSecondary=?
        WHERE id=?
    """, (
        data["location"],
        data["a4Primary"],
        data["a4Secondary"],
        data["barPrimary"],
        data["barSecondary"],
        mapping_id
    ))

    conn.commit()
    conn.close()

    return {"message": "Mapping Updated"}


@app.delete("/mapping/{mapping_id}")
def delete_mapping(mapping_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM mapping WHERE id=?", (mapping_id,))

    conn.commit()
    conn.close()

    return {"message": "Mapping Deleted"}

# ---------------- PRINTERS
@app.get("/printers")
def get_printers():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM printers")
    rows = cur.fetchall()

    conn.close()
    return [dict(row) for row in rows]


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
    name = data.name.strip()
    ip = data.ip.strip()

    if not name or not ip:
        return {"error": "Printer name and IP are required"}

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

    old_name = existing["name"]
    if old_name != name:
        cur.execute("UPDATE mapping SET a4Primary=? WHERE a4Primary=?", (name, old_name))
        cur.execute("UPDATE mapping SET a4Secondary=? WHERE a4Secondary=?", (name, old_name))
        cur.execute("UPDATE mapping SET barPrimary=? WHERE barPrimary=?", (name, old_name))
        cur.execute("UPDATE mapping SET barSecondary=? WHERE barSecondary=?", (name, old_name))

    conn.commit()
    conn.close()

    return {"message": "Printer Updated"}

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

    return {
        "total": total,
        "live": live,
        "offline": offline,
        "maintenance": maintenance
    }


@app.post("/print-job")
def print_job(data: dict):
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
            datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

        # 1. Get mapping
        cur.execute("SELECT * FROM mapping WHERE location=?", (location,))
        mapping = cur.fetchone()

        if not mapping:
            conn.close()
            return {"error": "No mapping found"}

        # 2. Select printers
        if category == "A4":
            primary = mapping["a4Primary"]
            secondary = mapping["a4Secondary"]
        else:
            primary = mapping["barPrimary"]
            secondary = mapping["barSecondary"]

        # 3. Failover logic
        if not primary or primary == "None":
            selected = secondary
            used = "Failover"
        else:
            cur.execute("SELECT * FROM printers WHERE name=?", (primary,))
            p1 = cur.fetchone()

            if p1 and p1["status"] == "Live":
                selected = primary
                used = "Primary"
            else:
                selected = secondary
                used = "Failover"

        # 4. Final safety
        
        if not selected or selected == "None":
            selected = "No Printer Available"
            used = "None"
        if selected == "No Printer Available":
            conn.close()
            return {"error": "No printer available"}

        status = "Queued"

        # 6. Save job
        now = datetime.now().strftime("%I:%M %p")

        cur.execute("""
            INSERT INTO print_jobs 
            (location, category, printer, status, type, time, patient_name, age, gender, patient_id, tube_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            location,
            category,
            selected,
            status,
            used,
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

        try:
            final_printer, final_type = print_with_failover(
                job_id,
                location,
                category,
                payload
            )
            selected = final_printer["name"]
            used = final_type
            status = "Completed"
        except Exception as e:
            print("Print Error:", e)
            status = "Failed"

        return {
            "job_id": job_id,
            "location": location,
            "category": category,
            "printer_used": selected,
            "type": used,
            "status": status,
            "patient_id": patient_id,
        }

    except Exception as e:
        return {"error": str(e)}


@app.get("/print-jobs")
def get_print_jobs():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM print_jobs ORDER BY id DESC")
    rows = cur.fetchall()

    conn.close()

    return [dict(row) for row in rows]

@app.get("/print-logs")
def get_print_logs():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM print_logs ORDER BY id DESC")
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
    while True:
        try:
            check_printers()
        except:
            pass
        time.sleep(5)   # every 5 seconds

threading.Thread(target=auto_check, daemon=True).start()
threading.Thread(target=process_queue, daemon=True).start()

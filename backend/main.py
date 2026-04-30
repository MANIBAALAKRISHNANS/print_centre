from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import init_db, get_connection
import subprocess
import socket
import threading
from queue import Queue
from datetime import datetime

print_queue = Queue()
import win32api
import win32print

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
def print_barcode(printer_ip, patient_name, age, gender, patient_id, tube_type, location, job_id):
    try:
        zpl = f"""
^XA
^PW400
^LH0,0

^CF0,28

^FO20,20^FDName:^FS
^FO150,20^FD{patient_name}^FS

^FO20,60^FDAge/Gender:^FS
^FO150,60^FD{age}/{gender}^FS

^FO20,100^FDPatient ID:^FS
^FO150,100^FD{patient_id}^FS

^FO20,140^FDTube:^FS
^FO150,140^FD{tube_type}^FS

^FO20,180^FDDate:^FS
^FO150,180^FD{datetime.now().strftime('%d/%m/%Y %H:%M')}^FS

^FO20,230
^BY2,2,80
^BCN,80,Y,N,N
^FD{patient_id}^FS

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
                    job_id
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
    try:
        result = subprocess.run(
            ["ping", "-n", "1", ip],
            stdout=subprocess.DEVNULL
        )
        return result.returncode == 0
    except:
        return False
@app.get("/check-printers")
def check_printers():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM printers")
    printers = cur.fetchall()

    for p in printers:
        ip = p["ip"]

        is_live = check_printer(ip)

        status = "Live" if is_live else "Offline"

        cur.execute(
            "UPDATE printers SET status=? WHERE id=?",
            (status, p["id"])
        )

    conn.commit()
    conn.close()

    return {"message": "Printer status updated"}

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
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM printers WHERE ip=?", (data.ip,))
    if cur.fetchone():
        conn.close()
        return {"error": "Printer already exists with this IP"}

    if data.category not in ["A4", "Barcode"]:
        return {"error": "Invalid category"}

    cur.execute(
        "INSERT INTO printers (name, ip, category, status, language) VALUES (?, ?, ?, ?, ?)",
        (data.name, data.ip, data.category, data.status, data.language)
    )

    conn.commit()
    conn.close()

    return {"message": "Printer Added"}
@app.put("/printers/{printer_id}")
def update_printer_status(printer_id: int, data: Printer):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE printers
        SET name=?, ip=?, category=?, status=?, language=?
        WHERE id=?
        """,
        (
            data.name,
            data.ip,
            data.category,
            data.status,
            data.language,
            printer_id
        )
    )

    conn.commit()
    conn.close()

    return {"message": "Printer Updated"}

@app.delete("/printers/{printer_id}")
def delete_printer(printer_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM printers WHERE id=?",
        (printer_id,)
    )

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
    conn = get_connection()
    cur = conn.cursor()

    # Prevent duplicate location
    cur.execute("SELECT * FROM locations WHERE name=?", (data.name,))
    if cur.fetchone():
        conn.close()
        return {"message": "Location already exists"}

    # Insert location
    cur.execute(
        "INSERT INTO locations (name) VALUES (?)",
        (data.name,)
    )

    # Prevent duplicate mapping
    cur.execute(
        "SELECT * FROM mapping WHERE location=?",
        (data.name,)
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
            (data.name, "None", "None", "None", "None")
        )

    conn.commit()
    conn.close()

    return {"message": "Location Added with Mapping"}

@app.put("/locations/{old_name}")
def update_location(old_name: str, data: Location):
    conn = get_connection()
    cur = conn.cursor()

    # Update locations table
    cur.execute(
        "UPDATE locations SET name=? WHERE name=?",
        (data.name, old_name)
    )

    # ALSO update mapping table
    cur.execute(
        "UPDATE mapping SET location=? WHERE location=?",
        (data.name, old_name)
    )

    conn.commit()
    conn.close()

    return {"message": "Location Updated"}


@app.delete("/locations/{name}")
def delete_location(name: str):
    conn = get_connection()
    cur = conn.cursor()

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
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO categories (name) VALUES (?)",
        (data.name,)
    )

    conn.commit()
    conn.close()

    return {"message": "Category Added"}

@app.put("/categories/{old_name}")
def update_category(old_name: str, data: Category):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "UPDATE categories SET name=? WHERE name=?",
        (data.name, old_name)
    )

    conn.commit()
    conn.close()

    return {"message": "Category Updated"}


@app.delete("/categories/{name}")
def delete_category(name: str):
    conn = get_connection()
    cur = conn.cursor()

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
        if category == "Barcode":
            if not patient_name or not patient_id:
                return {"error": "Patient name and ID required"}
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
            used = "Secondary"
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
            return {"error": "No printer available"}

        status = "Printing"
        



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
     # 5. Printing logic (FIXED)
        try:
            conn = get_connection()     # ⭐ ADD
            cur = conn.cursor() 
            cur.execute("SELECT * FROM printers WHERE name=?", (selected,))
            p = cur.fetchone()
            conn.close()

            printer_ip = None
            if p:
                printer_ip = p["ip"]

            if printer_ip and check_printer(printer_ip):

                job_data = {
                    "printer_ip": printer_ip,
                    "category": category,
                    "patient_name": patient_name,
                    "age": age,
                    "gender": gender,
                    "patient_id": patient_id,
                    "tube_type": tube_type,
                    "location": location,
                    "job_id": job_id,
                    "printer_name": selected
                }

                
                if category == "A4":
                    job_data["file_path"] = data.get("file_path")

                print_queue.put(job_data)

                print(f"Job {job_id} added to queue")

                status = "Printing"
            else:
                status = "Failed"
                conn = get_connection()
                cur = conn.cursor()

                cur.execute(
                    "UPDATE print_jobs SET status=? WHERE id=?",
                    ("Failed", job_id)
                )

                conn.commit()
                conn.close()

        except Exception as e:
            print("Print Error:", e)
            status = "Failed"
            conn = get_connection()
            cur = conn.cursor()

            cur.execute(
                "UPDATE print_jobs SET status=? WHERE id=?",
                ("Failed", job_id)
            )

            conn.commit()
            conn.close()

        return {
            "location": location,
            "category": category,
            "printer_used": selected,
            "type": used,
            "status": status   
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
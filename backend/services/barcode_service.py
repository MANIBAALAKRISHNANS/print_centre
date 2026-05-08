from uuid import uuid4
from datetime import datetime
from database import get_connection, get_cursor, get_placeholder

def patient_id_exists(patient_id):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT 1 FROM print_jobs WHERE patient_id={placeholder} LIMIT 1", (patient_id,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def generate_patient_id():
    while True:
        patient_id = f"PC{uuid4().hex[:10].upper()}"
        if not patient_id_exists(patient_id):
            return patient_id

def zpl_escape(value):
    return str(value or "").replace("^", "").replace("~", "")

def generate_barcode_label(data):
    patient_name = zpl_escape(data.get("patient_name", ""))[:20]
    age          = zpl_escape(data.get("age", ""))
    gender       = zpl_escape(data.get("gender", ""))
    patient_id   = zpl_escape(data.get("patient_id", "")) or "UNKNOWN"
    tube_type    = zpl_escape(data.get("tube_type", ""))[:20]
    datetime_str = zpl_escape(data.get("datetime", ""))
    test_name    = zpl_escape(data.get("test_name", ""))[:30]

    patient_id = patient_id.replace("\n", "").replace("\r", "").strip()

    LEFT_X   = 65
    RIGHT_W  = 355
    FONT_SM  = 18
    FONT_LG  = 24

    barcode_height = 55
    module_width   = 2
    estimated = (len(patient_id) * 11 + 35) * module_width
    if estimated > RIGHT_W:
        module_width = 1
        estimated   = (len(patient_id) * 11 + 35) * module_width
    estimated  = min(estimated, RIGHT_W)
    barcode_x  = LEFT_X + (RIGHT_W - estimated) // 2 + 20

    test_name_zpl = ""
    if test_name:
        test_name_zpl = f"""
^CF0,{FONT_SM}
^FO{LEFT_X},172^FD{test_name}^FS"""

    return f"""^XA
^LH0,0
^PW508
^LL406
^CI28
^MD15
^PR3

^CF0,{FONT_SM}
^FO{LEFT_X},26^FD{patient_name}  {age}Y / {gender}^FS

^CF0,{FONT_LG}
^FO{LEFT_X},22^FB{RIGHT_W},1,0,R^FD{patient_id}^FS

^BY{module_width},3,{barcode_height}
^FO{barcode_x},54
^BCN,{barcode_height},N,N,N
^FD{patient_id}^FS

^CF0,{FONT_LG}
^FO{LEFT_X},116^FB{RIGHT_W},1,0,C^FD{patient_id}^FS

^CF0,{FONT_SM}
^FO{LEFT_X},144^FD{datetime_str}^FS

^CF0,{FONT_SM}
^FO{LEFT_X},144^FB{RIGHT_W},1,0,R^FD{tube_type}^FS{test_name_zpl}

^XZ"""


def build_print_payload(job):
    if not job.get("datetime"):
        job["datetime"] = datetime.now().strftime("%d/%m/%Y  %H:%M:%S")

    if job.get("category") == "Barcode":
        return generate_barcode_label(job).encode("utf-8")

    text = f"""Patient: {job.get("patient_name", "")}
Location: {job.get("location", "")}
Patient ID: {job.get("patient_id", "")}
"""
    return f"\x1B%-12345X@PJL JOB\n{text}\n\x1B%-12345X".encode("utf-8")
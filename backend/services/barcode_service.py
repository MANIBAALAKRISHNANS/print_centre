from uuid import uuid4

from database import get_connection


def patient_id_exists(patient_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM print_jobs WHERE patient_id=? LIMIT 1", (patient_id,))
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
    patient_name = zpl_escape(data.get("patient_name"))[:24]
    age = zpl_escape(data.get("age"))
    gender = zpl_escape(data.get("gender"))
    patient_id = zpl_escape(data.get("patient_id"))
    tube_type = zpl_escape(data.get("tube_type"))[:32]
    visit_id = zpl_escape(data.get("visit_id"))
    datetime_str = zpl_escape(data.get("datetime"))

    return f"""^XA
^PW600
^LL280
^CI28
^CF0,28
^FO20,20^FD{patient_name} / {age}Y / {gender}^FS
^FO420,20^FB160,1,0,R^FD{visit_id}^FS
^BY2,2,60
^FO20,70
^BCN,70,Y,N,N
^FD{patient_id}^FS
^CF0,24
^FO20,160^FD{datetime_str}^FS
^CF0,26
^FO20,200^FD{tube_type}^FS
^XZ"""


def build_print_payload(job):
    if job.get("category") == "Barcode":
        return generate_barcode_label(job).encode("utf-8")

    text = f"""Patient: {job.get("patient_name", "")}
Location: {job.get("location", "")}
Patient ID: {job.get("patient_id", "")}
"""
    return f"\x1B%-12345X@PJL JOB\n{text}\n\x1B%-12345X".encode("utf-8")

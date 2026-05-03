from database import get_connection, utcnow, JobStatus
from services.printer_service import check_printer, send_to_printer
from services.document_service import process_document

def fetch_mapping(location):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mapping WHERE location=?", (location,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def fetch_printer(name):
    if not name or name == "None":
        return None

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM printers WHERE name=?", (name,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def mapping_candidates(mapping, category):
    if category == "A4":
        return [
            (mapping.get("a4Primary"), "Primary"),
            (mapping.get("a4Secondary"), "Failover"),
        ]

    return [
        (mapping.get("barPrimary"), "Primary"),
        (mapping.get("barSecondary"), "Failover"),
    ]

def select_printer(location, category):
    mapping = fetch_mapping(location)
    if not mapping:
        raise ValueError("No mapping found for this location")

    for printer_name, route_type in mapping_candidates(mapping, category):
        printer = fetch_printer(printer_name)
        if not printer:
            continue
        if printer.get("status") == "Live" and check_printer(printer.get("ip")):
            return printer, route_type

    raise ValueError("No live printer available")

def log_print_event(job_id, printer, status, message):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO print_logs (job_id, printer, status, message, time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            job_id,
            printer,
            status,
            message,
            utcnow(),
        ),
    )
    conn.commit()
    conn.close()

def mark_job(job_id, status, printer=None, route_type=None):
    conn = get_connection()
    cur = conn.cursor()

    fields = ["status=?"]
    params = [status]

    if printer is not None:
        fields.append("printer=?")
        params.append(printer)

    if route_type is not None:
        fields.append("type=?")
        params.append(route_type)

    params.append(job_id)
    cur.execute(f"UPDATE print_jobs SET {', '.join(fields)} WHERE id=?", params)
    conn.commit()
    conn.close()

def get_job_retry(job_id):
    conn = get_connection()
    cur = conn.cursor()
    # Check if retry_count column exists safely
    try:
        cur.execute("SELECT retry_count FROM print_jobs WHERE id=?", (job_id,))
        row = cur.fetchone()
        count = row["retry_count"] if row and "retry_count" in row.keys() else 0
    except Exception:
        count = 0
    finally:
        conn.close()
    return count

def mark_job_retry(job_id, retry_count):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE print_jobs SET retry_count=? WHERE id=?", (retry_count, job_id))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

def print_with_failover(job_id, location, category, payload):
    mapping = fetch_mapping(location)
    if not mapping:
        raise ValueError("No mapping found for this location")

    last_error = None

    for printer_name, route_type in mapping_candidates(mapping, category):
        printer = fetch_printer(printer_name)
        if not printer:
            continue

        converted_file_path = None
        try:
            mark_job(job_id, "Printing", printer["name"], route_type)
            log_print_event(job_id, printer["name"], "Printing", "Trying printer")
            
            print(f"[PRINT] Job {job_id} -> {printer['name']} -> {category}")
            print(f"[FORMAT] Using {printer.get('language', 'AUTO')}")

            final_payload = payload
            if category == "A4":
                file_path = payload
                if os.path.exists(file_path):
                    final_payload = process_document(file_path, printer)

            success = send_to_printer(
                printer.get("ip"),
                final_payload,
                printer.get("name")
            )

            if success:
                mark_job(job_id, "Completed", printer["name"], route_type)
                log_print_event(job_id, printer["name"], "Completed", "Print success")
                
                # Cleanup on success (MANDATORY)
                if category == "A4" and payload and os.path.exists(payload):
                    try: os.remove(payload)
                    except: pass
                    
                return printer, route_type
            else:
                raise RuntimeError("Print failed (IP + USB)")
                
        except Exception as exc:
            last_error = exc
            print(f"[ERROR] Printer {printer['name']} failed at IP {printer.get('ip')}")
            log_print_event(job_id, printer.get("name"), "Failed", str(exc))
            
            # Cleanup intermediate on failure, leave original for next failover/retry
            pass

    # If all failovers failed, handle retry logic
    retry_count = get_job_retry(job_id)
    if retry_count < 3:
        mark_job_retry(job_id, retry_count + 1)
        log_print_event(job_id, "System", "Retrying", f"Retry attempt {retry_count + 1}")
        raise Exception("RETRY")
    else:
        mark_job(job_id, "Failed")
        # Final cleanup on complete failure (MANDATORY)
        if category == "A4" and payload and os.path.exists(payload):
            try: os.remove(payload)
            except: pass
        raise Exception("FINAL_FAIL")

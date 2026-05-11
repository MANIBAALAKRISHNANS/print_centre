from database import (
    get_connection, get_cursor, get_placeholder, get_row_value, 
    utcnow, JobStatus, safe_delete
)
from services.printer_service import check_printer, send_to_printer
from services.document_service import process_document
from services.utils import is_usb_trusted
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger("RoutingService")

def fetch_mapping(location_id):
    """STRICT: Fetch mapping only by external_id."""
    if not location_id:
        return None
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        cur.execute(f"SELECT * FROM mapping WHERE external_id={placeholder}", (str(location_id),))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def fetch_printer(name):
    if not name or name == "None":
        return None
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        cur.execute(f"SELECT * FROM printers WHERE name={placeholder}", (name,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def _mget(row, key):
    """Case-insensitive dict get — handles SQLite (camelCase) and PostgreSQL (lowercase)."""
    return row.get(key) or row.get(key.lower()) or row.get(key.upper())

def mapping_candidates(mapping, category):
    if category == "A4":
        return [
            (_mget(mapping, "a4Primary"), "Primary"),
            (_mget(mapping, "a4Secondary"), "Failover"),
        ]
    return [
        (_mget(mapping, "barPrimary"), "Primary"),
        (_mget(mapping, "barSecondary"), "Failover"),
    ]

def log_print_event(job_id, printer, status, message):
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        cur.execute(f"INSERT INTO print_logs (job_id, printer, status, message, time) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                    (job_id, printer, status, message, utcnow()))
        conn.commit()
    finally:
        conn.close()

def mark_job(job_id, status, printer=None, route_type=None):
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        fields = [f"status={placeholder}"]
        params = [status]
        if printer is not None:
            fields.append(f"printer={placeholder}")
            params.append(printer)
        if route_type is not None:
            fields.append(f"type={placeholder}")
            params.append(route_type)
        params.append(job_id)
        cur.execute(f"UPDATE print_jobs SET {', '.join(fields)} WHERE id={placeholder}", params)
        conn.commit()
    finally:
        conn.close()

def get_job_retry(job_id):
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        cur.execute(f"SELECT retry_count FROM print_jobs WHERE id={placeholder}", (job_id,))
        row = cur.fetchone()
        return get_row_value(row, "retry_count", 0) or 0
    finally:
        conn.close()

def mark_job_retry(job_id, retry_count):
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        cur.execute(f"UPDATE print_jobs SET retry_count={placeholder} WHERE id={placeholder}", (retry_count, job_id))
        conn.commit()
    finally:
        conn.close()

def _update_job_file_path(job_id, file_path):
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        cur.execute(f"UPDATE print_jobs SET file_path={placeholder} WHERE id={placeholder}", (file_path, job_id))
        conn.commit()
    finally:
        conn.close()

def print_with_failover(job_id, location_id, category, payload):
    """
    STRICT: Identity-First routing.
    payload is bytes (barcode) or file_path (A4, to be converted to bytes).
    """
    mapping = fetch_mapping(location_id)
    if not mapping:
        raise ValueError("No printer mapping configured")

    is_terminal = False
    is_assigned_to_agent = False
    
    try:
        for printer_name, route_type in mapping_candidates(mapping, category):
            printer = fetch_printer(printer_name)
            if not printer: continue

            try:
                mark_job(job_id, "Printing", printer["name"], route_type)
                log_print_event(job_id, printer["name"], "Printing", "Attempting print")
                
                # Unified binary payload
                binary_payload = payload
                if category == "A4":
                    # Convert file path to bytes
                    binary_payload = process_document(payload, printer)

                # 🔹 HYBRID ROUTING: IP vs AGENT (USB)
                if printer.get("ip"):
                    # IP printers need actual bytes. If payload is still a file path
                    # (barcode saved to disk by process_queue), read the file content.
                    if isinstance(binary_payload, str) and os.path.isfile(binary_payload):
                        with open(binary_payload, "rb") as _f:
                            binary_payload = _f.read()
                    success = send_to_printer(printer["ip"], binary_payload, printer["name"])
                    if success:
                        mark_job(job_id, "Completed", printer["name"], route_type)
                        log_print_event(job_id, printer["name"], "Completed", "Success")
                        is_terminal = True
                        return printer, route_type
                    else:
                        raise RuntimeError("Printer unreachable via IP")
                else:
                    # 🔹 USB Printer: Assign to Agent
                    if not is_usb_trusted(printer):
                        log_print_event(job_id, printer["name"], "Failed", "Printer Offline or Stale")
                        raise RuntimeError(f"Printer '{printer['name']}' is Offline or Stale")

                    # For A4 jobs the backend has already converted the document to
                    # PS/PCL/Raster bytes.  The agent downloads by file_path from DB,
                    # so save the converted bytes to a file and update the DB record.
                    # Without this step the agent would receive raw PDF/DOCX and
                    # send it verbatim to the USB port — which most printers cannot print.
                    if category == "A4" and isinstance(binary_payload, bytes):
                        lang = (printer.get("language") or "PS").upper()
                        ext_map = {"PS": ".ps", "PCL": ".pcl", "RASTER": ".raster"}
                        ext = ext_map.get(lang, ".ps")
                        base = os.path.splitext(payload)[0] if isinstance(payload, str) else f"uploads/job_{job_id}"
                        converted_path = f"{base}_converted{ext}"
                        with open(converted_path, "wb") as _cf:
                            _cf.write(binary_payload)
                        _update_job_file_path(job_id, converted_path)
                        # Original uploaded file is no longer needed; agent will
                        # download the converted file via the updated file_path.
                        safe_delete(payload)

                    mark_job(job_id, JobStatus.PENDING_AGENT, printer["name"], route_type)
                    log_print_event(job_id, printer["name"], "Assigned to Agent", "Waiting for local agent pickup")
                    is_assigned_to_agent = True
                    return printer, route_type
                    
            except Exception as exc:
                log_print_event(job_id, printer["name"], "Failed", str(exc))

        # Retry/Fail logic
        retry_count = get_job_retry(job_id)
        if retry_count < 3:
            mark_job_retry(job_id, retry_count + 1)
            mark_job(job_id, JobStatus.RETRYING)
            log_print_event(job_id, "System", "Retrying", f"Retry attempt {retry_count + 1}")
            raise Exception("RETRY")
        else:
            mark_job(job_id, "Failed")
            is_terminal = True
            raise Exception("FINAL_FAIL")
            
    except Exception as e:
        if "RETRY" not in str(e):
            is_terminal = True
        raise
    finally:
        # 🔹 CLEANUP: Only if terminal (Success via IP or Final Failure)
        if is_terminal and not is_assigned_to_agent:
            safe_delete(payload)

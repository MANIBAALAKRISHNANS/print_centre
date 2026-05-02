from datetime import datetime

from database import get_connection
from services.printer_service import check_printer, send_to_printer


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
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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


def print_with_failover(job_id, location, category, payload):
    mapping = fetch_mapping(location)
    if not mapping:
        raise ValueError("No mapping found for this location")

    last_error = None

    for printer_name, route_type in mapping_candidates(mapping, category):
        printer = fetch_printer(printer_name)
        if not printer:
            continue

        try:
            mark_job(job_id, "Printing", printer["name"], route_type)
            log_print_event(job_id, printer["name"], "Printing", "Trying printer")

            success = send_to_printer(
                printer.get("ip"),
                payload,
                printer.get("name")
            )

            if success:
                mark_job(job_id, "Completed", printer["name"], route_type)
                log_print_event(job_id, printer["name"], "Completed", "Print success")
                return printer, route_type
            else:
                raise RuntimeError("Print failed (IP + USB)")
        except Exception as exc:
            last_error = exc
            log_print_event(job_id, printer.get("name"), "Failed", str(exc))

    mark_job(job_id, "Failed")
    raise RuntimeError(f"All printers failed: {last_error}")

import json
import logging
from datetime import datetime, timezone
from database import get_connection, get_cursor, get_placeholder

logger = logging.getLogger("Audit")

def log_audit(
    actor: str,
    actor_type: str,  # 'user' or 'agent'
    action: str,
    resource_type: str = None,
    resource_id: str = None,
    patient_id: str = None,
    ip_address: str = None,
    status: str = "SUCCESS",
    details: dict = None
):
    """
    HIPAA Compliant Audit Logger.
    Records system activity for compliance auditing.
    """
    try:
        conn = get_connection()
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        cur.execute(f"""
            INSERT INTO audit_log 
            (timestamp, actor, actor_type, action, resource_type, resource_id, patient_id, ip_address, status, details)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        """, (
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            actor, actor_type, action, resource_type,
            str(resource_id) if resource_id else None,
            patient_id, ip_address, status,
            json.dumps(details) if details else None
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        # ⚠️ CRITICAL: Audit log must never crash the application.
        # Fallback to file logging if database is unavailable.
        logger.error(f"AUDIT LOG DB WRITE FAILED: {e}")
        audit_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor, "actor_type": actor_type, "action": action,
            "resource": resource_type, "id": resource_id, "patient": patient_id,
            "ip": ip_address, "status": status, "details": details
        }
        logger.warning(f"AUDIT_FALLBACK: {json.dumps(audit_payload)}")


import logging
from datetime import datetime, timezone, timedelta
from database import get_connection, get_cursor, get_placeholder, get_row_value, JobStatus, utcnow
from services.routing_service import log_print_event

logger = logging.getLogger("Recovery")

STUCK_JOB_TIMEOUT_MINUTES = 10  # Jobs stuck in printing state longer than this

def recover_stuck_jobs():
    """
    Finds jobs stuck in active states (Printing, Agent Printing) and requeues or fails them.
    Ensures that a crashed agent or server doesn't leave jobs in limbo forever.
    """
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    try:
        # Use standard timestamp string for cross-dialect compatibility
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STUCK_JOB_TIMEOUT_MINUTES)).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Find stuck jobs
        cur.execute(f"""
            SELECT id, status, retry_count, printer, location_id, locked_by
            FROM print_jobs
            WHERE status IN ({placeholder}, {placeholder})
            AND locked_at IS NOT NULL
            AND locked_at < {placeholder}
        """, (JobStatus.PRINTING, JobStatus.AGENT_PRINTING, cutoff))
        
        stuck = cur.fetchall()
        
        recovered = 0
        for job in stuck:
            jid = get_row_value(job, 'id')
            retries = get_row_value(job, 'retry_count', 0) or 0
            status = get_row_value(job, 'status')
            printer = get_row_value(job, 'printer')
            
            if retries < 3:
                # Requeue for retry
                cur.execute(f"""
                    UPDATE print_jobs 
                    SET status={placeholder}, locked_at=NULL, locked_by=NULL,
                        retry_count=retry_count+1
                    WHERE id={placeholder}
                """, (JobStatus.QUEUED, jid))
                
                log_print_event(jid, printer, "Retrying", f"Auto-recovered stuck job (retry {retries+1})")
                logger.warning(f"[RECOVERY] Job {jid} was stuck in {status} — requeued (retry {retries+1})")
            else:
                # Max retries exceeded — mark as failed
                cur.execute(f"""
                    UPDATE print_jobs
                    SET status={placeholder}, locked_at=NULL, locked_by=NULL
                    WHERE id={placeholder}
                """, (JobStatus.FAILED, jid))
                
                log_print_event(jid, printer, "Failed", "Auto-failed: stuck job exceeded max retries")
                logger.error(f"[RECOVERY] Job {jid} permanently failed after {retries} retries")
            
            recovered += 1
        
        conn.commit()
        if recovered:
            logger.info(f"[RECOVERY] Successfully processed {recovered} stuck jobs")
        return recovered
    except Exception as e:
        logger.error(f"[RECOVERY ERROR] {e}")
        return 0
    finally:
        conn.close()

def check_database_integrity():
    """
    Runs integrity checks. Skips for Postgres as it's handled at engine level.
    """
    from config import settings
    if settings.DB_TYPE != "sqlite":
        return

    conn = get_connection()
    cur = get_cursor(conn)
    try:
        cur.execute("PRAGMA integrity_check")
        row = cur.fetchone()
        res = row[0] if row else "unknown"
        
        if res == "ok":
            logger.info("[INTEGRITY] Database integrity check passed.")
        else:
            logger.critical(f"[INTEGRITY] DATABASE CORRUPTION DETECTED: {res}")
    except Exception as e:
        logger.error(f"[INTEGRITY ERROR] Failed to run check: {e}")
    finally:
        conn.close()


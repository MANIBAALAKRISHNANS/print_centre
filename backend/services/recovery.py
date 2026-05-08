import logging
from datetime import datetime, timezone, timedelta
from database import get_connection, JobStatus, utcnow
from services.routing_service import log_print_event

logger = logging.getLogger("Recovery")

STUCK_JOB_TIMEOUT_MINUTES = 10  # Jobs stuck in printing state longer than this

def recover_stuck_jobs():
    """
    Finds jobs stuck in active states (Printing, Agent Printing) and requeues or fails them.
    Ensures that a crashed agent or server doesn't leave jobs in limbo forever.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Use timestamp comparison for stuck jobs
        cutoff_timestamp = datetime.now(timezone.utc).timestamp() - (STUCK_JOB_TIMEOUT_MINUTES * 60)
        
        # Find stuck jobs
        cur.execute("""
            SELECT id, status, retry_count, printer, location_id, locked_by
            FROM print_jobs
            WHERE status IN (?, ?)
            AND locked_at IS NOT NULL
            AND CAST(locked_at AS REAL) < ?
        """, (JobStatus.PRINTING, JobStatus.AGENT_PRINTING, cutoff_timestamp))
        
        stuck = cur.fetchall()
        
        recovered = 0
        for job in stuck:
            jid = job['id']
            retries = job['retry_count'] or 0
            
            if retries < 3:
                # Requeue for retry
                cur.execute("""
                    UPDATE print_jobs 
                    SET status=?, locked_at=NULL, locked_by=NULL,
                        retry_count=retry_count+1
                    WHERE id=?
                """, (JobStatus.QUEUED, jid))
                
                log_print_event(jid, job['printer'], "Retrying", f"Auto-recovered stuck job (retry {retries+1})")
                logger.warning(f"[RECOVERY] Job {jid} was stuck in {job['status']} — requeued (retry {retries+1})")
            else:
                # Max retries exceeded — mark as failed
                cur.execute("""
                    UPDATE print_jobs
                    SET status=?, locked_at=NULL, locked_by=NULL
                    WHERE id=?
                """, (JobStatus.FAILED, jid))
                
                log_print_event(jid, job['printer'], "Failed", "Auto-failed: stuck job exceeded max retries")
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
    Runs SQLite PRAGMA integrity_check and logs results.
    Identifies silent corruption early.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # PRAGMA integrity_check can take time but doesn't block readers in WAL mode
        cur.execute("PRAGMA integrity_check")
        results = [r[0] for r in cur.fetchall()]
        
        if results == ["ok"]:
            logger.info("[INTEGRITY] Database integrity check passed.")
        else:
            logger.critical(f"[INTEGRITY] DATABASE CORRUPTION DETECTED: {results}")
            # In a real environment, this would trigger an SMTP alert or PagerDuty event
    except Exception as e:
        logger.error(f"[INTEGRITY ERROR] Failed to run check: {e}")
    finally:
        conn.close()

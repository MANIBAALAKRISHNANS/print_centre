import sqlite3
import os
import sys

# Add backend to path so we can import services
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from services.barcode_service import build_print_payload

def fix_stuck_jobs():
    conn = sqlite3.connect('backend/printcenter.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    os.makedirs('uploads', exist_ok=True)
    
    # Check both Pending Agent and Agent Printing status
    cur.execute('SELECT * FROM print_jobs WHERE category="Barcode" AND status IN ("Pending Agent", "Agent Printing") AND (file_path IS NULL OR file_path="")')
    jobs = cur.fetchall()
    print(f"Found {len(jobs)} stuck barcode jobs")
    
    for job in jobs:
        try:
            # Convert Row to dict for build_print_payload
            job_dict = dict(job)
            # Add missing fields if any
            job_dict["datetime"] = job_dict.get("time", "")
            
            payload = build_print_payload(job_dict)
            path = f"uploads/barcode_{job['id']}.zpl"
            with open(path, 'wb') as f:
                f.write(payload)
            
            # Reset status to Pending Agent so the agent can pick it up again cleanly
            cur.execute('UPDATE print_jobs SET file_path=?, status="Pending Agent", locked_at=NULL, locked_by=NULL WHERE id=?', (path, job['id']))
            conn.commit()
            print(f"Fixed job {job['id']} -> {path} (Reset to Pending Agent)")
        except Exception as e:
            print(f"Failed to fix job {job['id']}: {e}")
            
    conn.close()

if __name__ == "__main__":
    fix_stuck_jobs()

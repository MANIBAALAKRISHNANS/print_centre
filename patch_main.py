import os
import re

file_path = r"c:\Users\Asus\OneDrive\Desktop\Printercentre\backend\main.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update imports
old_imports = "from fastapi import FastAPI\nfrom fastapi.middleware.cors import CORSMiddleware"
new_imports = "import os\nimport shutil\nfrom fastapi import FastAPI, UploadFile, File, Form, HTTPException\nfrom fastapi.middleware.cors import CORSMiddleware"
content = content.replace(old_imports, new_imports)

# 2. Add /print-a4-file endpoint and remove old print_a4_ip / print_a4_file
pattern = r"def print_a4_ip.*?def process_queue"

new_endpoint = '''@app.post("/print-a4-file")
async def print_a4_file_api(
    location: str = Form(...),
    file: UploadFile = File(...)
):
    """API for uploading and printing A4 documents with validation."""
    if not file.filename.lower().endswith((".pdf", ".doc", ".docx", ".txt")):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF, DOC, DOCX, TXT allowed.")

    os.makedirs("uploads", exist_ok=True)
    file_path = os.path.join("uploads", file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO print_jobs (location, category, status, file_path, file_type, time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (location, "A4", "Pending", file_path, file.content_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    job_id = cur.lastrowid
    conn.close()

    print_queue.put({
        "job_id": job_id,
        "location": location,
        "category": "A4",
        "payload": file_path
    })

    return {"message": "A4 Print Job Queued", "job_id": job_id}

def process_queue'''

content = re.sub(pattern, new_endpoint, content, flags=re.DOTALL)

# 3. Update process_queue exception handling
old_queue_except = '''            except Exception as routing_err:
                print(f"[QUEUE] Job {job_id} failed: {routing_err}")
                mark_job(job_id, "Failed")
                log_print_event(job_id, "Queue", "Failed", str(routing_err))'''

new_queue_except = '''            except Exception as routing_err:
                err_msg = str(routing_err)
                if "Retry" in err_msg:
                    print(f"[QUEUE] Retrying job {job_id}: {err_msg}")
                    import time
                    time.sleep(2)  # Wait briefly before putting back
                    print_queue.put(job)
                else:
                    print(f"[QUEUE] Job {job_id} failed: {err_msg}")
                    mark_job(job_id, "Failed")
                    log_print_event(job_id, "Queue", "Failed", err_msg)'''

content = content.replace(old_queue_except, new_queue_except)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated main.py successfully!")

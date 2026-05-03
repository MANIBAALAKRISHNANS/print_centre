# Hospital Printing System Upgrade Walkthrough

I have implemented the corrected document printing architecture exactly as requested. The new pipeline successfully handles file uploads, format conversions, robust fallback, cleanup, and routing without breaking the existing barcode printing functionality.

## Core Architecture Changes

```mermaid
flowchart TD
    A[Upload File POST /print-a4-file] --> B{Validate File Type}
    B -->|Valid (.pdf, .doc, .txt)| C[Save to uploads/ & Queue]
    B -->|Invalid| D[Return 400 Error]
    
    C --> E[process_queue Worker]
    E --> F[Routing Service]
    F --> G{printer.language}
    
    G -->|PS| H[Convert to PS]
    G -->|PCL| I[Convert to PCL]
    G -->|AUTO| H
    G -->|RAW| J[Convert to Raster]
    
    H & I & J --> K{Send via IP}
    K -->|Success| L[Delete Temp & Source Files]
    K -->|Fail| M{Send via USB}
    
    M -->|Success| L
    M -->|Fail| N{Failover Secondary}
    
    N -->|Try Backup Printer| G
    N -->|All Fail| O{Retry Count < 3}
    
    O -->|Yes| P[Re-Queue Job]
    O -->|No| Q[Mark Failed & Cleanup]
```

## Key Improvements Applied

> [!NOTE]
> **Deterministic Format Selection**
> I completely removed the PJL auto-detection. The system now strictly relies on the database `language` field:
> 1. `PS` -> PostScript
> 2. `PCL` -> PCL
> 3. `AUTO` -> defaults to `PS`
> 4. If conversion fails -> falls back to raster (`tiffg4` raster format that many systems can handle).

> [!TIP]
> **Error Handling & Retries**
> - **LibreOffice Timeouts**: I wrapped the DOC to PDF LibreOffice `subprocess` calls in a 30-second timeout with `check=True`.
> - **Queue Retries**: The `routing_service.py` tracks the retry count in the `print_jobs` table. If all printers fail, it will retry the job up to 3 times by returning it to the queue with a sleep backoff before a total failure.

> [!IMPORTANT]
> **File Cleanup (No Disk Leaks)**
> I added strict file cleanup routines inside `routing_service.py`.
> - When a job prints successfully, the converted binary file AND the original uploaded file are immediately deleted from the server.
> - If a job fails on one printer but failover is active, only the intermediate file is deleted.
> - If a job fails completely (after 3 retries), the uploaded file is purged.

## Code File Summaries

- **`database.py`**: Added `ALTER TABLE print_jobs` to add `file_path`, `file_type`, `retry_count`, and `pages`.
- **`services/document_service.py`**: The brand new file conversion hub utilizing `subprocess` for `gs` (Ghostscript) and `soffice` (LibreOffice).
- **`services/routing_service.py`**: Intercepts A4 jobs, triggers the conversion, loops over primary/secondary printers, handles the cleanup upon completion or full failure, and tracks retry attempts.
- **`services/printer_service.py`**: Renamed generic print jobs from "ZPL Job" to "Print Job", natively accepting raw bytes stream.
- **`main.py`**: Removed the old `win32api` local system prints. Added `/print-a4-file` to validate files and accept uploads via `UploadFile`. Modified queue exceptions to handle the retry pushes.

## How to Test

1. Ensure **Ghostscript** (`gswin64c.exe` or `gs`) and **LibreOffice** (`soffice`) are installed on the server and added to the `PATH`.
2. Start the FastAPI server (`uvicorn main:app --reload`).
3. Set a printer to `AUTO` or `PS` in the UI/database.
4. Upload a valid `.pdf` or `.docx` file to `POST /print-a4-file` with the correct `location` field via Postman or the frontend.
5. The backend will log the conversion process and send the binary format over port 9100.
6. Verify that the `uploads/` folder is empty after success.

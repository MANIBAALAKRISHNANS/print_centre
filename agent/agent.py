import time
import requests
import os
import logging
import threading

# 🔹 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PrintAgent")

# 🔹 Configuration
SERVER_URL = os.environ.get("SERVER_URL", "http://127.0.0.1:8000")
AGENT_ID = os.environ.get("AGENT_ID", "local_pc_1")
TOKEN = os.environ.get("AGENT_TOKEN", "hospital_agent_token_2026") # Secure Token
LOCATION_ID = os.environ.get("AGENT_LOCATION_ID", "95600d98-504e-4ff4-865d-6726b19dc0bc") # 🔹 NEW: Explicit location mapping
POLL_INTERVAL = 5 
HEARTBEAT_INTERVAL = 15 # 🔹 Reduced interval for better monitoring

try:
    import win32print
except ImportError:
    win32print = None

def check_printer_status(printer_name):
    """Strict three-layer hardware detection — NO assumptions.

    Layer 1 — Physical presence (EnumPrinters):
        The printer must appear in the system's enumerated printer list.
    Layer 2 — Handle reachability (OpenPrinter):
        If the OS cannot open a handle, the printer is definitely offline.
    Layer 3 — Status flags (GetPrinter level 2):
        Hardware flags must be clean (0x00).
    """
    if not win32print:
        return "Offline"

    # ── Layer 1: Physical presence ──────────────────────────────────────────
    try:
        enumerated = {p[2].lower() for p in win32print.EnumPrinters(2)}
    except Exception as e:
        logger.error(f"[HARDWARE VALIDATION FAIL] EnumPrinters failed: {e}")
        return "Offline"

    if printer_name.lower() not in enumerated:
        logger.warning(f"[HARDWARE VALIDATION FAIL] '{printer_name}' not found in EnumPrinters list")
        return "Offline"

    # ── Layer 2: Handle reachability ────────────────────────────────────────
    try:
        handle = win32print.OpenPrinter(printer_name)
    except Exception as e:
        logger.error(f"[HARDWARE VALIDATION FAIL] OpenPrinter failed for '{printer_name}': {e}")
        return "Offline"

    # ── Layer 3: Status flag & Attribute inspection ──────────────────────────
    try:
        info = win32print.GetPrinter(handle, 2)
        status = info.get("Status", 0)
        attributes = info.get("Attributes", 0)
        port = info.get("pPortName", "Unknown")
        
        # 🔹 DEBUG: Log raw details to diagnose "ghost" online states
        logger.info(f"[HARDWARE DEBUG] '{printer_name}' | Status: 0x{status:08X} | Attr: 0x{attributes:08X} | Port: {port}")

        # 1. Attribute Check: PRINTER_ATTRIBUTE_WORK_OFFLINE (0x400)
        # This is the most reliable way to detect "Use Printer Offline" or 
        # unplugged state in many Windows drivers.
        if attributes & 0x00000400:
            logger.warning(f"[HARDWARE VALIDATION FAIL] '{printer_name}' is set to WORK_OFFLINE (Attr: 0x{attributes:08X})")
            return "Offline"

        # 2. Status Bitmask Check
        # 0x00000080 = PRINTER_STATUS_OFFLINE
        # 0x00000001 = PRINTER_STATUS_PAUSED
        # 0x00000002 = PRINTER_STATUS_ERROR
        # 0x00000008 = PRINTER_STATUS_PAPER_JAM
        # 0x00000010 = PRINTER_STATUS_PAPER_OUT
        # 0x00001000 = PRINTER_STATUS_NOT_AVAILABLE
        # 0x00004000 = PRINTER_STATUS_OUT_OF_MEMORY
        
        if status & 0x00000080:
            logger.warning(f"[HARDWARE VALIDATION FAIL] '{printer_name}' status bit shows OFFLINE (0x{status:08X})")
            return "Offline"
            
        if status & 0x00001000:
            logger.warning(f"[HARDWARE VALIDATION FAIL] '{printer_name}' status bit shows NOT_AVAILABLE (0x{status:08X})")
            return "Offline"

        if status & (0x00000002 | 0x00000008 | 0x00000010 | 0x00004000):
            logger.warning(f"[HARDWARE VALIDATION FAIL] '{printer_name}' has ERROR/JAM/PAPER-OUT/MEM-FAIL (0x{status:08X})")
            return "Error"

        # 3. Final Fallback: If status is anything but 0 (Ready) or 0x20000 (Normal during some operations), be cautious.
        # But for now, if status is 0 and Attr is not Offline, we are good.
        if status == 0:
            return "Online"
        
        # If we reach here, there's some non-zero status we haven't explicitly handled
        logger.info(f"[HARDWARE INFO] '{printer_name}' has non-zero status 0x{status:08X}, but not explicitly Offline.")
        return "Online" 
    finally:
        win32print.ClosePrinter(handle)

def _get_usb_port(printer_name):
    """Fetch the physical port name (e.g., USB001) for a Windows printer."""
    if not win32print:
        return None
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            info = win32print.GetPrinter(handle, 2)
            port = info.get("pPortName")
            return port
        finally:
            win32print.ClosePrinter(handle)
    except Exception as e:
        logger.error(f"[USB PORT] Failed to get port for '{printer_name}': {e}")
        return None

def print_direct(port_name, data):
    """Write raw bytes directly to a hardware port, bypassing the Windows driver."""
    try:
        device_path = f"\\\\.\\{port_name}"
        logger.info(f"[DIRECT PRINT] Opening {device_path} for raw write ({len(data)} bytes)")
        with open(device_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        logger.error(f"[DIRECT PRINT] Failed to write to {port_name}: {e}")
        return False

def print_raw(printer_name, data):
    """Send raw data to a local USB printer via Spooler (Fallback)."""
    if not win32print:
        logger.error("[PRINT_RAW] win32print not available")
        return False
    try:
        handle = win32print.OpenPrinter(printer_name)
        job = win32print.StartDocPrinter(handle, 1, ("Agent Job", None, "RAW"))
        win32print.StartPagePrinter(handle)
        win32print.WritePrinter(handle, data)
        win32print.EndPagePrinter(handle)
        win32print.EndDocPrinter(handle)
        win32print.ClosePrinter(handle)
        return True
    except Exception as e:
        logger.error(f"[PRINT_RAW] Local print error on '{printer_name}': {e}")
        return False

def status_reporting_loop():
    """🔹 Periodically report local printer status to backend"""
    logger.info("Status reporting loop started")
    mapped_printers = []
    last_config_sync = 0
    
    while True:
        try:
            # 1. Sync Config every 5 mins
            if time.time() - last_config_sync > 300:
                try:
                    res = requests.get(
                        f"{SERVER_URL}/agent/config",
                        params={"agent_id": AGENT_ID, "token": TOKEN, "location_id": LOCATION_ID},
                        timeout=10
                    )
                    if res.status_code == 200:
                        mapped_printers = res.json().get("printers", [])
                        logger.info(f"Synced config. Mapped USB printers: {mapped_printers}")
                        last_config_sync = time.time()
                    elif res.status_code == 401:
                        logger.error("Config sync failed: Unauthorized")
                except Exception as e:
                    logger.warning(f"Failed to sync config with server: {e}")

            if not win32print:
                time.sleep(60)
                continue
                
            # 2. Enum local printers
            printers = win32print.EnumPrinters(2)
            local_printers = {p[2]: p for p in printers}
            
            # 3. Report for all mapped printers
            for p_name in mapped_printers:
                status = "Offline"
                if p_name in local_printers:
                    status = check_printer_status(p_name)
                else:
                    logger.warning(f"⚠️  Mapped printer '{p_name}' NOT FOUND on this PC!")

                # Always send status to refresh last_updated on server
                try:
                    logger.info(f"Reporting Status: '{p_name}' -> {status}")
                    requests.post(
                        f"{SERVER_URL}/agent/printer-status",
                        params={"agent_id": AGENT_ID, "token": TOKEN},
                        json={"printer_name": p_name, "status": status},
                        timeout=5
                    )
                except Exception as e:
                    logger.warning(f"Failed to report status for '{p_name}': {e}")
                    
        except Exception as e:
            logger.error(f"Status reporting loop error: {e}")
            
        time.sleep(15)

def heartbeat_loop():
    """Background heartbeat loop"""
    while True:
        try:
            requests.post(
                f"{SERVER_URL}/agent/heartbeat",
                params={"agent_id": AGENT_ID, "token": TOKEN, "location_id": LOCATION_ID},
                timeout=5
            )
        except: pass
        time.sleep(HEARTBEAT_INTERVAL)

def agent_loop():
    logger.info(f"Agent {AGENT_ID} started. Polling {SERVER_URL}")
    
    # Start Heartbeat & Status Threads
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    threading.Thread(target=status_reporting_loop, daemon=True).start()
    
    while True:
        try:
            # 1. Poll for jobs (Ordered by Priority)
            response = requests.get(
                f"{SERVER_URL}/agent/jobs",
                params={"agent_id": AGENT_ID, "token": TOKEN, "location_id": LOCATION_ID},
                timeout=10
            )
            
            if response.status_code == 200:
                jobs = response.json()
                for job in jobs:
                    jid = job['id']
                    prio = job['priority']
                    retries = job.get('retry_count', 0)
                    
                    logger.info(f"[JOB START] ID: {jid} | Prio: {prio} | Retry: {retries}")
                    
                    # 2. Robust Binary Fetch (Handling Partial Downloads with Retries)
                    content = None
                    for attempt in range(3):
                        try:
                            with requests.get(
                                f"{SERVER_URL}/agent/job/{jid}/file",
                                params={"agent_id": AGENT_ID, "token": TOKEN},
                                stream=True,
                                timeout=60
                            ) as r:
                                r.raise_for_status()
                                
                                # 🔹 Download Integrity Metadata
                                expected_size = r.headers.get('Content-Length')
                                if expected_size:
                                    expected_size = int(expected_size)
                                    
                                temp_content = bytearray()
                                for chunk in r.iter_content(chunk_size=1024*1024): # 1MB chunks
                                    if chunk:
                                        temp_content.extend(chunk)
                                
                                # ── INTEGRITY CHECKS ─────────────────────────────────────
                                if len(temp_content) == 0:
                                    raise ValueError("REJECTED: Empty file received from server")
                                    
                                if expected_size and len(temp_content) != expected_size:
                                    raise ValueError(f"REJECTED: Partial download (Expected: {expected_size}, Got: {len(temp_content)})")

                                content = temp_content
                                logger.info(f"[DOWNLOAD OK] ID: {jid} | Size: {len(content)} bytes")
                                break # Success!
                        except Exception as e:
                            logger.warning(f"[DOWNLOAD ATTEMPT {attempt+1}/3 FAIL] ID: {jid} | Error: {e}")
                            if attempt < 2:
                                time.sleep(2)
                            else:
                                raise # Exhausted retries

                    try:
                        # ── SAFE ZPL DEBUG LOGGING ────────────────────────────────
                        # We use a nested try/except to ensure terminal encoding 
                        # errors don't crash the agent.
                        try:
                            decoded_content = content.decode('utf-8', errors='replace')
                            logger.info(f"[ZPL DEBUG] (ID: {jid})\n{decoded_content}")
                        except Exception as log_err:
                            logger.info(f"[BINARY DATA] (ID: {jid}) - Non-text or encoding issue: {log_err}")
                                
                        # ── FORCE FRESH STATUS BEFORE PRINT ──────────────────────────
                        current_status = check_printer_status(job['printer'])
                        # ── QUICK PRE-PRINT CHECK ──────────────────────────
                        current_status = check_printer_status(job['printer'])
                        if current_status != "Online":
                            logger.error(f"[VALIDATION FAIL] Aborting Job {jid}: Printer is {current_status}")
                            requests.post(
                                f"{SERVER_URL}/agent/fail",
                                params={"job_id": jid, "agent_id": AGENT_ID, "token": TOKEN, "error": f"Printer is {current_status}"},
                                timeout=5
                            )
                            continue

                        # ── PRINT & CONFIRM IMMEDIATELY ────────────────────
                        # 🔹 Bypassing Driver Rendering for USB/COM Ports
                        printed = False
                        port_name = _get_usb_port(job['printer'])
                        if port_name and (port_name.upper().startswith("USB") or port_name.upper().startswith("COM")):
                            if print_direct(port_name, bytes(content)):
                                logger.info(f"[JOB SUCCESS] ID: {jid} via direct port {port_name}")
                                printed = True
                            else:
                                logger.warning(f"[JOB RETRY] Direct write failed for {port_name}, falling back to spooler")

                        if not printed:
                            if print_raw(job['printer'], bytes(content)):
                                logger.info(f"[JOB SUCCESS] ID: {jid} via spooler fallback")
                                printed = True

                        if printed:
                            conf_res = requests.post(
                                f"{SERVER_URL}/agent/confirm",
                                params={"job_id": jid, "agent_id": AGENT_ID, "token": TOKEN},
                                timeout=15
                            )
                            if conf_res.status_code == 200:
                                logger.info(f"[CONFIRM OK] ID: {jid}")
                            else:
                                try:
                                    err_msg = conf_res.json().get("message", "Unknown error")
                                except:
                                    err_msg = conf_res.text
                                logger.error(f"[CONFIRM FAIL] ID: {jid} | Status: {conf_res.status_code} | Error: {err_msg}")
                        else:
                            requests.post(
                                f"{SERVER_URL}/agent/fail",
                                params={"job_id": jid, "agent_id": AGENT_ID, "token": TOKEN, "error": "Hardware failure"},
                                timeout=5
                            )
                            logger.error(f"[JOB FAILURE] ID: {jid}")
                                
                    except Exception as download_err:
                        logger.error(f"[DOWNLOAD ERROR] Job {jid}: {download_err}")
                        # Leave job as 'Agent Printing' - lease will expire and reclaim naturally
                        
            elif response.status_code == 401:
                logger.error("Authentication failed. Check TOKEN.")
                time.sleep(30)
                
        except Exception as e:
            logger.error(f"Polling error: {e}")
            
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    agent_loop()

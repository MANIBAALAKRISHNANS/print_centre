import socket
import platform
import logging
import time
import requests
import os
import threading

_OS = platform.system()
_WIN32_AVAILABLE = False

if _OS == "Windows":
    try:
        import win32print
        _WIN32_AVAILABLE = True
    except ImportError:
        logging.warning("win32print not available — USB printing disabled")
elif _OS == "Darwin":
    try:
        from agent_macos import (
            check_printer_status as _macos_check,
            print_raw as _macos_print_raw,
            list_local_printers as _macos_list,
            _get_usb_port as _macos_get_port,
            print_direct as _macos_print_direct
        )
    except ImportError:
        logging.error("agent_macos.py missing or incomplete — macOS printing will fail")
else:
    logging.error(f"Unsupported OS: {_OS}")
from agent_config import load_config, save_config

# 🔹 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PrintAgent")

# 🔹 Configuration
# First try config file, then environment variable, then default localhost
_config = load_config()
SERVER_URL = _config.get("server_url") or os.environ.get("SERVER_URL", "http://127.0.0.1:8000")

def ensure_registered():
    config = load_config()
    # Update global SERVER_URL if it's found in the config (case where it's saved after setup)
    global SERVER_URL
    if config.get("server_url"):
        SERVER_URL = config["server_url"]
    
    # 1. Already registered
    if config.get("agent_id") and config.get("token"):
        logger.info(f"[AGENT] Loaded credentials for {config['agent_id']} connecting to {SERVER_URL}")
        return config["agent_id"], config["token"], config.get("location_id", "")
    
    # 2. Check for pending activation code written by setup tool
    pending_code = config.get("pending_activation_code")
    if not pending_code:
        logger.critical("[AGENT] No credentials and no pending_activation_code found.")
        logger.critical("[AGENT] Run: python agent_setup.py --code YOUR_ACTIVATION_CODE")
        logger.critical("[AGENT] Then restart the service.")
        raise SystemExit(1)
    
    logger.info(f"[AGENT] Found pending activation code — attempting registration...")
    hostname = socket.gethostname()
    server_url = config.get("server_url", SERVER_URL)
    
    try:
        res = requests.post(
            f"{server_url}/agent/register", 
            json={"activation_code": pending_code, "hostname": hostname}, 
            timeout=15
        )
        if res.status_code == 200:
            data = res.json()
            
            # Save new credentials and CLEAR the pending code
            new_config = {
                "agent_id": data["agent_id"],
                "token": data["token"],
                "location_id": data["location_id"],
                "server_url": server_url
            }
            save_config(new_config)
            
            logger.info(f"[AGENT] Registered successfully as {data['agent_id']}")
            return data["agent_id"], data["token"], data["location_id"]
        else:
            logger.critical(f"[AGENT] Registration failed: {res.status_code} {res.text}")
            raise SystemExit(1)
    except requests.RequestException as e:
        logger.critical(f"[AGENT] Cannot reach server at {server_url}: {e}")
        raise SystemExit(1)

AGENT_ID, TOKEN, LOCATION_ID = ensure_registered()
POLL_INTERVAL = 5 
HEARTBEAT_INTERVAL = 15 # 🔹 Reduced interval for better monitoring

# ── OS DISPATCH WRAPPERS ──────────────────────────────────────────────────

def check_printer_status(printer_name: str) -> str:
    """Dispatches printer status check based on OS."""
    if _OS == "Darwin":
        return _macos_check(printer_name)
    
    # Existing Windows logic
    if not _WIN32_AVAILABLE:
        return "Offline"

    # ── Layer 1: Physical presence (win32print) ──────────────────────────
    try:
        enumerated = {p[2].lower() for p in win32print.EnumPrinters(2)}
    except Exception as e:
        logger.error(f"[HARDWARE VALIDATION FAIL] EnumPrinters failed: {e}")
        return "Offline"

    if printer_name.lower() not in enumerated:
        logger.warning(f"[HARDWARE VALIDATION FAIL] '{printer_name}' not found in EnumPrinters list")
        return "Offline"

    # ── Layer 2: WMI Validation (More reliable for Offline/Disconnected) ──
    try:
        import pythoncom
        from wmi import WMI
        # Initialize COM for the current thread (Mandatory for background threads)
        pythoncom.CoInitialize()
        try:
            c = WMI()
            wmi_printers = c.Win32_Printer(Name=printer_name)
            if wmi_printers:
                wp = wmi_printers[0]
                if getattr(wp, "WorkOffline", False):
                    logger.warning(f"[HARDWARE VALIDATION FAIL] WMI reports '{printer_name}' is WorkOffline")
                    return "Offline"
                
                p_status = getattr(wp, "PrinterStatus", 0)
                if p_status in [1, 2, 7]:
                    logger.warning(f"[HARDWARE VALIDATION FAIL] WMI reports '{printer_name}' PrinterStatus: {p_status}")
                    return "Offline"
            # Cleanup COM objects before return/finally
            if 'wp' in locals(): del wp
            del wmi_printers
            del c
            import gc
            gc.collect()
        finally:
            pythoncom.CoUninitialize()
    except ImportError:
        logger.debug("[WMI DEBUG] wmi or pythoncom module not installed. Skipping WMI check.")
    except Exception as e:
        logger.debug(f"[WMI DEBUG] WMI check failed: {e}")

    # ── Layer 3: Handle & Attribute inspection (win32print) ────────────────
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            info = win32print.GetPrinter(handle, 2)
            status = info.get("Status", 0)
            attributes = info.get("Attributes", 0)
            
            # 🔹 DEBUG: Log raw details to diagnose "ghost" online states
            logger.info(f"[HARDWARE DEBUG] '{printer_name}' | Status: 0x{status:08X} | Attr: 0x{attributes:08X}")

            if attributes & 0x00000400: # PRINTER_ATTRIBUTE_WORK_OFFLINE
                logger.warning(f"[HARDWARE VALIDATION FAIL] '{printer_name}' has WORK_OFFLINE attribute")
                return "Offline"
            
            if status & 0x00000080: # PRINTER_STATUS_OFFLINE
                return "Offline"
                
            if status & 0x00001000: # PRINTER_STATUS_NOT_AVAILABLE
                return "Offline"

            if status & (0x00000002 | 0x00000008 | 0x00000010 | 0x00004000):
                return "Error"

            return "Online" 
        finally:
            win32print.ClosePrinter(handle)
    except Exception as e:
        logger.error(f"[HARDWARE VALIDATION FAIL] win32print handle check failed: {e}")
        return "Offline"

def _get_usb_port(printer_name: str):
    """Dispatches port retrieval based on OS."""
    if _OS == "Darwin":
        return _macos_get_port(printer_name)
    
    # Existing Windows logic
    if not _WIN32_AVAILABLE:
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

def print_direct(port_name: str, data: bytes) -> bool:
    """Dispatches direct port printing based on OS."""
    if _OS == "Darwin":
        return _macos_print_direct(port_name, data)
        
    # Existing Windows logic
    try:
        device_path = f"\\\\.\\{port_name}"
        logger.info(f"[DIRECT PRINT] Opening {device_path} for raw write ({len(data)} bytes)")
        with open(device_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        logger.error(f"[DIRECT PRINT] Failed to write to {port_name}: {e}")
        return False

def print_raw(printer_name: str, data: bytes) -> bool:
    """Dispatches raw spooler printing based on OS."""
    if _OS == "Darwin":
        return _macos_print_raw(printer_name, data)
        
    # Existing Windows logic
    if not _WIN32_AVAILABLE:
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
            if _OS == "Darwin":
                local_printers = {p: {} for p in _macos_list()}
            else:
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
    hostname = socket.gethostname()
    while True:
        try:
            requests.post(
                f"{SERVER_URL}/agent/heartbeat",
                params={"agent_id": AGENT_ID, "token": TOKEN, "location_id": LOCATION_ID, "hostname": hostname},
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
                        # Added: 1s sleep allows printer hardware to settle before the final status check
                        time.sleep(1)
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
                                logger.info(f"[POST-PRINT CHECK] Direct write done. Waiting 1s for hardware settle...")
                                time.sleep(1)
                                post_status = check_printer_status(job['printer'])
                                if post_status != "Error":
                                    logger.info(f"[JOB SUCCESS] ID: {jid} via direct port {port_name} | post_status={post_status}")
                                    printed = True
                                else:
                                    logger.error(f"[POST-PRINT CHECK FAIL] ID: {jid} | Hardware error after direct write")
                                    # Fall through to spooler fallback attempt
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

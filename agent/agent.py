import socket
import platform
import time
import os
import threading
import logging
import json
from logging.handlers import RotatingFileHandler

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_OS = platform.system()
_WIN32_AVAILABLE = False

if _OS == "Windows":
    try:
        import win32print
        _WIN32_AVAILABLE = True
    except ImportError:
        logging.warning("win32print not available - USB printing disabled on Windows")
elif _OS == "Darwin":
    try:
        from agent_macos import (
            check_printer_status as _macos_check,
            print_raw as _macos_print_raw,
            list_local_printers as _macos_list,
            _get_usb_port as _macos_get_port,
            print_direct as _macos_print_direct,
        )
    except ImportError:
        logging.error("agent_macos.py missing - macOS printing will fail")
else:
    logging.error(f"Unsupported OS: {_OS}")

from agent_config import load_config, save_config

# ── Logging: rotating file + console ─────────────────────────────────────────
import sys

if _OS == "Windows":
    _LOG_DIR = r"C:\PrintHubAgent"
elif _OS == "Darwin":
    _LOG_DIR = os.path.expanduser("~/Library/Logs/PrintHubAgent")
else:
    _LOG_DIR = os.path.expanduser("~/.printhub/logs")

os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_FILE = os.path.join(_LOG_DIR, "agent.log")

_handler_file = RotatingFileHandler(_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
_handler_file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

# On Windows the default console stream uses cp1252 which cannot encode Unicode symbols.
# Reconfigure stdout to UTF-8 (Python 3.7+); fall back to errors='replace' if unsupported.
if _OS == "Windows" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
_handler_console = logging.StreamHandler(sys.stdout)
_handler_console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[_handler_file, _handler_console])
logger = logging.getLogger("PrintAgent")

# ── Config & HTTP session ─────────────────────────────────────────────────────
_config = load_config()
SERVER_URL = _config.get("server_url") or os.environ.get("SERVER_URL", "http://127.0.0.1:8000")
_TLS_VERIFY = _config.get("tls_verify", True)

_retry_adapter = HTTPAdapter(
    max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
)
_session = requests.Session()
_session.mount("http://", _retry_adapter)
_session.mount("https://", _retry_adapter)

# ── Global state ──────────────────────────────────────────────────────────────
POLL_INTERVAL  = 30   # safety-net fallback poll (WebSocket handles real-time)
HEARTBEAT_INTERVAL = 15

# Event set by WebSocket when server pushes job_available — wakes the poll loop immediately
_job_trigger = threading.Event()
_ws_connected = threading.Event()  # signals that WS is currently alive


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REGISTRATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_registered():
    config = load_config()
    global SERVER_URL, _TLS_VERIFY
    if config.get("server_url"):
        SERVER_URL = config["server_url"]
    _TLS_VERIFY = config.get("tls_verify", True)

    if config.get("agent_id") and config.get("token"):
        logger.info(f"[AGENT] Credentials loaded for {config['agent_id']} -> {SERVER_URL}")
        return config["agent_id"], config["token"], config.get("location_id", "")

    pending_code = config.get("pending_activation_code")
    if not pending_code:
        logger.critical("[AGENT] No credentials and no pending_activation_code.")
        logger.critical("[AGENT] Run: python agent_setup.py --code YOUR_CODE --server SERVER_URL")
        raise SystemExit(1)

    logger.info("[AGENT] Attempting registration with activation code...")
    hostname = socket.gethostname()
    server_url = config.get("server_url", SERVER_URL)

    for attempt in range(5):
        try:
            res = _session.post(
                f"{server_url}/agent/register",
                json={"activation_code": pending_code, "hostname": hostname},
                timeout=15,
                verify=_TLS_VERIFY,
            )
            if res.status_code == 200:
                data = res.json()
                save_config({
                    "agent_id": data["agent_id"],
                    "token": data["token"],
                    "location_id": data["location_id"],
                    "server_url": server_url,
                    "tls_verify": _TLS_VERIFY,
                })
                logger.info(f"[AGENT] Registered as {data['agent_id']}")
                return data["agent_id"], data["token"], data["location_id"]
            else:
                logger.error(f"[AGENT] Registration failed ({res.status_code}): {res.text}")
                if res.status_code in (400, 403, 404):
                    raise SystemExit(1)  # bad code — no point retrying
        except requests.exceptions.SSLError:
            logger.critical("[AGENT] TLS error - re-run setup with --no-verify for self-signed certs")
            raise SystemExit(1)
        except SystemExit:
            raise
        except Exception as e:
            logger.warning(f"[AGENT] Registration attempt {attempt+1}/5 failed: {e}")
        time.sleep(2 ** attempt)

    logger.critical("[AGENT] Exhausted registration retries.")
    raise SystemExit(1)


AGENT_ID, TOKEN, LOCATION_ID = ensure_registered()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REAL-TIME WEBSOCKET CLIENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AgentWebSocket:
    """
    Persistent WebSocket connection to the server.
    Runs in its own daemon thread. On `job_available` message, wakes the
    main poll loop immediately so jobs execute in ~milliseconds instead of
    waiting up to POLL_INTERVAL seconds.
    Auto-reconnects with exponential backoff (1 s → 60 s cap).
    """

    def __init__(self, server_url: str, agent_id: str, token: str):
        ws_url = server_url.replace("https://", "wss://").replace("http://", "ws://")
        self._url = f"{ws_url}/ws/agent?agent_id={agent_id}&token={token}"
        self._stop = threading.Event()
        self._ws = None

    def start(self):
        t = threading.Thread(target=self._run, daemon=True, name="AgentWS")
        t.start()

    def stop(self):
        self._stop.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    def _run(self):
        import websocket as _ws_lib  # websocket-client

        backoff = 1
        while not self._stop.is_set():
            try:
                ws = _ws_lib.WebSocketApp(
                    self._url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws = ws
                ws.run_forever(
                    ping_interval=30,
                    ping_timeout=10,
                    sslopt={"cert_reqs": 0} if not _TLS_VERIFY else {},
                )
            except Exception as e:
                logger.debug(f"[WS] Connection error: {e}")

            _ws_connected.clear()
            if not self._stop.is_set():
                logger.info(f"[WS] Reconnecting in {backoff}s...")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def _on_open(self, ws):
        global _ws_connected
        _ws_connected.set()
        logger.info("[WS] Connected to server")

    def _on_message(self, ws, raw):
        try:
            msg = json.loads(raw)
            mtype = msg.get("type")
            if mtype == "job_available":
                logger.info("[WS] Server pushed job_available - waking poll loop")
                _job_trigger.set()
            elif mtype == "ping":
                ws.send(json.dumps({"type": "pong"}))
        except Exception as e:
            logger.debug(f"[WS] Message parse error: {e}")

    def _on_error(self, ws, error):
        logger.warning(f"[WS] Error: {error}")

    def _on_close(self, ws, code, msg):
        _ws_connected.clear()
        logger.info(f"[WS] Closed (code={code})")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OS DISPATCH WRAPPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_printer_status(printer_name: str) -> str:
    if _OS == "Darwin":
        return _macos_check(printer_name)
    if not _WIN32_AVAILABLE:
        return "Offline"

    # Layer 1 — physical presence
    try:
        enumerated = {p[2].lower() for p in win32print.EnumPrinters(2)}
    except Exception as e:
        logger.error(f"[HARDWARE] EnumPrinters failed: {e}")
        return "Offline"
    if printer_name.lower() not in enumerated:
        return "Offline"

    # Layer 2 — WMI validation
    try:
        import pythoncom
        from wmi import WMI
        pythoncom.CoInitialize()
        try:
            c = WMI()
            wmi_printers = c.Win32_Printer(Name=printer_name)
            if wmi_printers:
                wp = wmi_printers[0]
                if getattr(wp, "WorkOffline", False):
                    return "Offline"
                if getattr(wp, "PrinterStatus", 0) in [1, 2, 7]:
                    return "Offline"
            del wmi_printers, c
            import gc; gc.collect()
        finally:
            pythoncom.CoUninitialize()
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"[WMI] Check failed: {e}")

    # Layer 3 — handle inspection
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            info   = win32print.GetPrinter(handle, 2)
            status = info.get("Status", 0)
            attrs  = info.get("Attributes", 0)
            logger.info(f"[HARDWARE] '{printer_name}' status=0x{status:08X} attrs=0x{attrs:08X}")
            if attrs  & 0x00000400: return "Offline"   # WORK_OFFLINE
            if status & 0x00000080: return "Offline"   # PRINTER_STATUS_OFFLINE
            if status & 0x00001000: return "Offline"   # NOT_AVAILABLE
            if status & 0x00004016: return "Error"
            return "Online"
        finally:
            win32print.ClosePrinter(handle)
    except Exception as e:
        logger.error(f"[HARDWARE] Handle check failed: {e}")
        return "Offline"


def _get_usb_port(printer_name: str):
    if _OS == "Darwin":
        return _macos_get_port(printer_name)
    if not _WIN32_AVAILABLE:
        return None
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            return win32print.GetPrinter(handle, 2).get("pPortName")
        finally:
            win32print.ClosePrinter(handle)
    except Exception as e:
        logger.error(f"[USB PORT] {printer_name}: {e}")
        return None


def print_direct(port_name: str, data: bytes) -> bool:
    if _OS == "Darwin":
        return _macos_print_direct(port_name, data)
    try:
        with open(f"\\\\.\\{port_name}", "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        logger.error(f"[DIRECT] Write to {port_name} failed: {e}")
        return False


def print_raw(printer_name: str, data: bytes) -> bool:
    if _OS == "Darwin":
        return _macos_print_raw(printer_name, data)
    if not _WIN32_AVAILABLE:
        logger.error("[PRINT_RAW] win32print unavailable")
        return False
    try:
        handle = win32print.OpenPrinter(printer_name)
        win32print.StartDocPrinter(handle, 1, ("Agent Job", None, "RAW"))
        win32print.StartPagePrinter(handle)
        win32print.WritePrinter(handle, data)
        win32print.EndPagePrinter(handle)
        win32print.EndDocPrinter(handle)
        win32print.ClosePrinter(handle)
        return True
    except Exception as e:
        logger.error(f"[PRINT_RAW] '{printer_name}': {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKGROUND LOOPS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def heartbeat_loop():
    hostname = socket.gethostname()
    _consec_errors = 0
    while True:
        try:
            _session.post(
                f"{SERVER_URL}/agent/heartbeat",
                params={
                    "agent_id": AGENT_ID,
                    "token": TOKEN,
                    "location_id": LOCATION_ID,
                    "hostname": hostname,
                },
                timeout=5,
                verify=_TLS_VERIFY,
            )
            _consec_errors = 0
        except Exception as e:
            _consec_errors += 1
            logger.warning(f"[HEARTBEAT] Failed ({_consec_errors}): {e}")
        delay = min(HEARTBEAT_INTERVAL * (1 + _consec_errors // 3), 60)
        time.sleep(delay)


def status_reporting_loop():
    """Periodically report local USB printer status to the backend."""
    mapped_printers: list = []
    last_config_sync = 0
    _consec_errors = 0

    while True:
        try:
            # Sync printer config every 5 minutes
            if time.time() - last_config_sync > 300:
                try:
                    res = _session.get(
                        f"{SERVER_URL}/agent/config",
                        params={
                            "agent_id": AGENT_ID,
                            "token": TOKEN,
                            "location_id": LOCATION_ID,
                        },
                        timeout=10,
                        verify=_TLS_VERIFY,
                    )
                    if res.status_code == 200:
                        mapped_printers = res.json().get("printers", [])
                        logger.info(f"[STATUS] Mapped USB printers: {mapped_printers}")
                        last_config_sync = time.time()
                    elif res.status_code == 401:
                        logger.error("[STATUS] Config sync: Unauthorized")
                except Exception as e:
                    logger.warning(f"[STATUS] Config sync failed: {e}")

            # Skip reporting if no printer APIs available
            if not _WIN32_AVAILABLE and _OS != "Darwin":
                time.sleep(60)
                continue

            # Enumerate local printers
            if _OS == "Darwin":
                local_printers = set(_macos_list())
            else:
                try:
                    local_printers = {p[2] for p in win32print.EnumPrinters(2)}
                except Exception:
                    local_printers = set()

            # Report status for each mapped printer
            for p_name in mapped_printers:
                status = check_printer_status(p_name) if p_name in local_printers else "Offline"
                if p_name not in local_printers:
                    logger.warning(f"[STATUS] Mapped printer '{p_name}' not found on this machine")
                try:
                    _session.post(
                        f"{SERVER_URL}/agent/printer-status",
                        params={"agent_id": AGENT_ID, "token": TOKEN},
                        json={"printer_name": p_name, "status": status},
                        timeout=5,
                        verify=_TLS_VERIFY,
                    )
                except Exception as e:
                    logger.warning(f"[STATUS] Report failed for '{p_name}': {e}")

            _consec_errors = 0

        except Exception as e:
            _consec_errors += 1
            logger.error(f"[STATUS] Loop error: {e}")

        delay = min(15 * (1 + _consec_errors // 3), 120)
        time.sleep(delay)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# JOB PROCESSING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fetch_jobs() -> list:
    res = _session.get(
        f"{SERVER_URL}/agent/jobs",
        params={"agent_id": AGENT_ID, "token": TOKEN, "location_id": LOCATION_ID},
        timeout=10,
        verify=_TLS_VERIFY,
    )
    if res.status_code == 200:
        return res.json()
    if res.status_code == 401:
        logger.error("[POLL] Authentication failed - check agent token")
        time.sleep(30)
    return []


def _process_job(job: dict):
    jid     = job["id"]
    printer = job["printer"]
    retries = job.get("retry_count", 0)
    logger.info(f"[JOB] START id={jid} printer={printer} retry={retries}")

    # Download with 3-attempt integrity check
    content = None
    for attempt in range(3):
        try:
            with _session.get(
                f"{SERVER_URL}/agent/job/{jid}/file",
                params={"agent_id": AGENT_ID, "token": TOKEN},
                stream=True,
                timeout=60,
                verify=_TLS_VERIFY,
            ) as r:
                r.raise_for_status()
                expected = int(r.headers["Content-Length"]) if "Content-Length" in r.headers else None
                buf = bytearray()
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        buf.extend(chunk)
                if len(buf) == 0:
                    raise ValueError("Empty file received")
                if expected and len(buf) != expected:
                    raise ValueError(f"Partial download ({len(buf)}/{expected} bytes)")
                content = buf
                logger.info(f"[JOB] Downloaded {len(content)} bytes for id={jid}")
                break
        except Exception as e:
            logger.warning(f"[JOB] Download attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(2)
            else:
                logger.error(f"[JOB] Download exhausted retries for id={jid}")
                return  # leave lease to expire naturally

    try:
        try:
            logger.info(f"[ZPL] id={jid}\n{content.decode('utf-8', errors='replace')}")
        except Exception:
            pass

        # Pre-print status check (double-checked with 1 s settle)
        time.sleep(1)
        if check_printer_status(printer) != "Online":
            status = check_printer_status(printer)
            logger.error(f"[JOB] ABORT id={jid}: printer {printer} is {status}")
            _session.post(
                f"{SERVER_URL}/agent/fail",
                params={"job_id": jid, "agent_id": AGENT_ID, "token": TOKEN,
                        "error": f"Printer is {status}"},
                timeout=5, verify=_TLS_VERIFY,
            )
            return

        # Print: direct USB port first, spooler fallback
        printed = False
        port = _get_usb_port(printer)
        if port and (port.upper().startswith("USB") or port.upper().startswith("COM")):
            if print_direct(port, bytes(content)):
                time.sleep(1)
                if check_printer_status(printer) != "Error":
                    logger.info(f"[JOB] SUCCESS id={jid} via direct port {port}")
                    printed = True
                else:
                    logger.warning(f"[JOB] Post-print error on {port}, trying spooler")

        if not printed:
            if print_raw(printer, bytes(content)):
                logger.info(f"[JOB] SUCCESS id={jid} via spooler")
                printed = True

        if printed:
            conf = _session.post(
                f"{SERVER_URL}/agent/confirm",
                params={"job_id": jid, "agent_id": AGENT_ID, "token": TOKEN},
                timeout=15, verify=_TLS_VERIFY,
            )
            if conf.status_code == 200:
                logger.info(f"[JOB] CONFIRMED id={jid}")
            else:
                try:
                    err = conf.json().get("message", conf.text)
                except Exception:
                    err = conf.text
                logger.error(f"[JOB] CONFIRM FAILED id={jid}: {conf.status_code} {err}")
        else:
            _session.post(
                f"{SERVER_URL}/agent/fail",
                params={"job_id": jid, "agent_id": AGENT_ID, "token": TOKEN,
                        "error": "Hardware failure"},
                timeout=5, verify=_TLS_VERIFY,
            )
            logger.error(f"[JOB] FAILED id={jid}")

    except Exception as e:
        logger.error(f"[JOB] Unexpected error for id={jid}: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN AGENT LOOP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def agent_loop():
    logger.info(f"[AGENT] {AGENT_ID} starting - server: {SERVER_URL}")

    # Start background threads
    threading.Thread(target=heartbeat_loop, daemon=True, name="Heartbeat").start()
    threading.Thread(target=status_reporting_loop, daemon=True, name="StatusReport").start()

    # Start real-time WebSocket client
    _ws = AgentWebSocket(SERVER_URL, AGENT_ID, TOKEN)
    _ws.start()

    _consec_errors = 0
    while True:
        try:
            jobs = _fetch_jobs()
            if jobs:
                _consec_errors = 0
                for job in jobs:
                    _process_job(job)
            else:
                _consec_errors = 0

        except Exception as e:
            _consec_errors += 1
            logger.error(f"[AGENT] Poll error: {e}")

        # Wait for WebSocket push or fall back to safety-net poll interval.
        # _job_trigger.wait() returns True immediately if the event is already set.
        delay = min(POLL_INTERVAL * (1 + _consec_errors // 5), 120)
        _job_trigger.wait(timeout=delay)
        _job_trigger.clear()


if __name__ == "__main__":
    agent_loop()

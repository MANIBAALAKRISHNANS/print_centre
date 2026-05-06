import socket
import time
import logging

logger = logging.getLogger("PrinterService")

try:
    import win32print
except ImportError:
    win32print = None

# Win32 printer status flag constants
_PRINTER_STATUS_OFFLINE   = 0x00000080
_PRINTER_STATUS_ERROR     = 0x00000002
_PRINTER_STATUS_PAPER_JAM = 0x00000008
_PRINTER_STATUS_PAPER_OUT = 0x00000010
_PRINTER_STATUS_ERROR_MASK = (
    _PRINTER_STATUS_ERROR |
    _PRINTER_STATUS_PAPER_JAM |
    _PRINTER_STATUS_PAPER_OUT
)


def _verify_usb_hardware_status(printer_name: str) -> bool:
    """Re-open the printer handle and inspect hardware status flags.

    Returns True only if the printer reports status == 0 (ready).
    Returns False if Offline, Error, Paper-Out, or Jammed.
    This is the authoritative post-print hardware verification step.
    """
    if win32print is None:
        logger.error("[USB VERIFY] win32print not available — cannot verify hardware status")
        return False
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            info = win32print.GetPrinter(handle, 2)
            status = info.get("Status", 0)
        finally:
            win32print.ClosePrinter(handle)

        if status & _PRINTER_STATUS_OFFLINE:
            logger.error(f"[USB VERIFY] '{printer_name}' is OFFLINE (flag 0x{status:08X}) — reporting failure")
            return False
        if status & _PRINTER_STATUS_ERROR_MASK:
            logger.error(f"[USB VERIFY] '{printer_name}' has ERROR/JAM/PAPER-OUT (flag 0x{status:08X}) — reporting failure")
            return False
        # Transient non-zero flags (Zebra busy/processing after print) are NOT errors.
        # Only the offline/error masks above indicate real hardware faults.
        logger.info(f"[USB VERIFY] '{printer_name}' hardware status OK (flag 0x{status:08X})")
        return True
    except Exception as e:
        logger.error(f"[USB VERIFY] Could not re-open '{printer_name}' after print: {e} — reporting failure")
        return False


def _get_usb_port(printer_name):
    """Fetch the physical port name (e.g., USB001) for a Windows printer."""
    if win32print is None:
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


def _send_direct_to_port(port_name, data):
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


def check_printer(ip, timeout=2):
    if not ip:
        return False

    try:
        with socket.create_connection((ip, 9100), timeout=timeout):
            return True
    except Exception:
        return False


def send_to_printer(printer_ip, data, printer_name=None, port=9100, timeout=5):
    # Ensure bytes
    if isinstance(data, str):
        data = data.encode("utf-8")

    # -------------------------------
    # STEP 1: TRY IP PRINT
    # -------------------------------
    if printer_ip:
        try:
            with socket.create_connection((printer_ip, port), timeout=timeout) as sock:
                sock.settimeout(5) # 🔹 Timeout for data transmission
                sock.sendall(data)
                logger.info(f"Printed via IP: {printer_ip}")
                return True
        except Exception as e:
            logger.error(f"IP print failed on {printer_ip}: {e}")

    # -------------------------------
    # STEP 2: TRY USB PRINT
    # -------------------------------
    try:
        if win32print is None:
            raise Exception("win32print not available")

        printers = win32print.EnumPrinters(2)

        for p in printers:
            system_name = p[2]

            # Match printer name exactly
            if printer_name and printer_name.lower() == system_name.lower():
                # 🔹 Bypassing Driver Rendering for USB/COM Ports
                port_name = _get_usb_port(system_name)
                if port_name and (port_name.upper().startswith("USB") or port_name.upper().startswith("COM")):
                    if _send_direct_to_port(port_name, data):
                        logger.info(f"[USB PRINT] Direct port write success on {port_name}")
                        time.sleep(2)
                        return _verify_usb_hardware_status(system_name)
                    else:
                        logger.warning(f"[USB PRINT] Direct write failed for {port_name}, falling back to spooler")

                # ── Fallback: Standard Windows Spooler (RAW mode) ──
                logger.info(f"[USB PRINT] Sending data to '{system_name}' via Windows spooler fallback")
                handle = win32print.OpenPrinter(system_name)
                job = win32print.StartDocPrinter(
                    handle, 1, ("Print Job", None, "RAW")
                )
                win32print.StartPagePrinter(handle)
                win32print.WritePrinter(handle, data)
                win32print.EndPagePrinter(handle)
                win32print.EndDocPrinter(handle)
                win32print.ClosePrinter(handle)

                logger.info(f"[USB PRINT] Spooler accepted job for '{system_name}'. Waiting 1s before hardware verification...")
                time.sleep(2)

                hardware_ok = _verify_usb_hardware_status(system_name)
                if not hardware_ok:
                    logger.error(f"[USB PRINT] HARDWARE VERIFICATION FAILED for '{system_name}'")
                    return False

                logger.info(f"[USB PRINT] Hardware verification passed for '{system_name}'")
                return True

        raise Exception("Matching USB printer not found")

    except Exception as e:
        logger.error(f"USB print failed: {e}")

    # -------------------------------
    # FINAL FAILURE
    # -------------------------------
    return False
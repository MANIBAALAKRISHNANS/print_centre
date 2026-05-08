import subprocess
import logging
import os
import tempfile

logger = logging.getLogger("PrintAgentMacOS")

def check_printer_status(printer_name: str) -> str:
    """
    Check the hardware status of a printer using macOS CUPS 'lpstat' utility.
    
    Returns:
        "Online" if idle or ready.
        "Offline" if disabled, stopped, or not available.
        "Error" if an explicit error is detected.
    """
    try:
        # lpstat -p returns status like: "printer PRINTER_NAME is idle. enabled since..."
        res = subprocess.run(
            ["lpstat", "-p", printer_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if res.returncode != 0:
            return "Offline"
            
        status_line = res.stdout.lower()
        
        if "error" in status_line:
            return "Error"
        if any(word in status_line for word in ["disabled", "stopped", "not available", "paused"]):
            return "Offline"
        if "idle" in status_line or "ready" in status_line or "enabled" in status_line:
            return "Online"
            
        return "Offline"
        
    except subprocess.TimeoutExpired:
        logger.error(f"Status check timed out for {printer_name}")
        return "Offline"
    except Exception as e:
        logger.error(f"Error checking status for {printer_name}: {e}")
        return "Offline"

def list_local_printers() -> list:
    """
    Lists all local printers registered in macOS CUPS.
    
    Returns:
        A list of printer names (strings).
    """
    try:
        res = subprocess.run(["lpstat", "-p"], capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            return []
            
        printers = []
        for line in res.stdout.splitlines():
            # Lines look like: "printer Zebra_ZD230 is idle. enabled since..."
            if line.startswith("printer "):
                parts = line.split()
                if len(parts) >= 2:
                    printers.append(parts[1])
        return printers
    except Exception as e:
        logger.error(f"Error listing printers: {e}")
        return []

def print_raw(printer_name: str, data: bytes) -> bool:
    """
    Sends raw bytes directly to a macOS CUPS printer using the 'lp -o raw' command.
    Bypasses the printer driver to allow direct ZPL/EPL commands.
    
    Returns:
        True if the job was successfully accepted by the spooler.
    """
    temp_path = None
    try:
        # Create a temporary binary file
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(data)
            temp_path = f.name
            
        # Send to CUPS via lp command
        # -o raw tells CUPS not to filter or interpret the data
        res = subprocess.run(
            ["lp", "-d", printer_name, "-o", "raw", temp_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if res.returncode == 0:
            logger.info(f"Raw job sent to {printer_name} successfully")
            return True
        else:
            logger.error(f"Failed to send raw job to {printer_name}: {res.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Error in print_raw for {printer_name}: {e}")
        return False
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

def _get_usb_port(printer_name: str):
    """
    Not applicable on macOS. CUPS abstracts the USB port via printer names.
    Returns None to stay compatible with common agent logic.
    """
    return None

def print_direct(port_name, data: bytes) -> bool:
    """
    Not applicable on macOS. Use print_raw(printer_name, data) instead.
    Always returns False as macOS requires spooler-based raw writing.
    """
    return False

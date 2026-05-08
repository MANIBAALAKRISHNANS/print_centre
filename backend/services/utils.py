from datetime import datetime, timezone

STALE_THRESHOLD_SECONDS = 45

def is_usb_stale(last_updated_str: str) -> bool:
    if not last_updated_str:
        return True
    try:
        dt = datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age > STALE_THRESHOLD_SECONDS
    except Exception:
        return True

def is_usb_trusted(printer: dict) -> bool:
    if printer.get("status") != "Online":
        return False
    if is_usb_stale(printer.get("last_updated")):
        return False
    source = str(printer.get("last_update_source") or "")
    return source.startswith("Agent")

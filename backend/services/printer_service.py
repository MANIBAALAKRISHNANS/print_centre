import socket

try:
    import win32print
except ImportError:
    win32print = None


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
                sock.sendall(data)
                print("✅ Printed via IP:", printer_ip)
                return True
        except Exception as e:
            print("❌ IP print failed:", e)

    # -------------------------------
    # STEP 2: TRY USB PRINT
    # -------------------------------
    try:
        if win32print is None:
            raise Exception("win32print not available")

        printers = win32print.EnumPrinters(2)

        for p in printers:
            system_name = p[2]

            # Match printer name
            if printer_name and printer_name.lower() in system_name.lower():
                handle = win32print.OpenPrinter(system_name)

                job = win32print.StartDocPrinter(
                    handle, 1, ("Print Job", None, "RAW")
                )

                win32print.StartPagePrinter(handle)
                win32print.WritePrinter(handle, data)
                win32print.EndPagePrinter(handle)

                win32print.EndDocPrinter(handle)
                win32print.ClosePrinter(handle)

                print("✅ Printed via USB:", system_name)
                return True

        raise Exception("Matching USB printer not found")

    except Exception as e:
        print("❌ USB print failed:", e)

    # -------------------------------
    # FINAL FAILURE
    # -------------------------------
    return False

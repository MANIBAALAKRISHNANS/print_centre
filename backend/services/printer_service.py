import socket


def check_printer(ip, timeout=2):
    if not ip:
        return False

    try:
        with socket.create_connection((ip, 9100), timeout=timeout):
            return True
    except Exception:
        return False


def send_to_printer(printer_ip, data, port=9100, timeout=5):
    if isinstance(data, str):
        data = data.encode("utf-8")

    with socket.create_connection((printer_ip, port), timeout=timeout) as sock:
        sock.sendall(data)

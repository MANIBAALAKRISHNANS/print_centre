import wmi
import pythoncom
import gc

def run_check():
    # Inside this function, all WMI objects are local
    c = wmi.WMI()
    printers = c.Win32_Printer()
    for printer in printers:
        print(f"Name: {printer.Name}")
        print(f"  Status: {printer.Status}")
        print(f"  PrinterStatus: {printer.PrinterStatus}")
        print(f"  WorkOffline: {printer.WorkOffline}")
        print(f"  Availability: {printer.Availability}")
        print(f"  DetectedErrorState: {printer.DetectedErrorState}")
        print("-" * 20)

def check_printers():
    pythoncom.CoInitialize()
    try:
        run_check()
        # After run_check() returns, its local variables (c, printers, printer) 
        # are eligible for garbage collection.
        gc.collect() 
    finally:
        # Now it should be safe to uninitialize
        pythoncom.CoUninitialize()

if __name__ == "__main__":
    try:
        check_printers()
    except Exception as e:
        print(f"Error: {e}")

import os
import subprocess

def process_document(file_path: str, printer: dict) -> str:
    """
    Convert document to the appropriate format based on printer capabilities.
    Returns the path to the converted file.
    Hierarchy:
    1. If printer.language == 'PS' -> use PS
    2. If printer.language == 'PCL' -> use PCL
    3. If printer.language == 'AUTO' -> use PS
    4. If conversion fails -> fallback to raster
    """
    file_ext = os.path.splitext(file_path)[1].lower()
    
    # 1. Base conversion: DOC/DOCX to PDF, TXT to PDF or raw
    pdf_path = file_path
    if file_ext in [".doc", ".docx"]:
        pdf_path = convert_doc_to_pdf(file_path)
    elif file_ext == ".txt":
        pdf_path = convert_txt_to_pdf(file_path)

    # 2. Target format based on printer
    target_lang = printer.get("language", "AUTO").upper()
    if target_lang == "AUTO":
        target_lang = "PS" # Preferred default
        
    converted_path = None
    
    try:
        if target_lang == "PS":
            converted_path = convert_pdf_to_ps(pdf_path)
        elif target_lang == "PCL":
            converted_path = convert_pdf_to_pcl(pdf_path)
        else:
            # RAW or unsupported
            converted_path = convert_pdf_to_raster(pdf_path)
    except Exception as e:
        print(f"[DOCUMENT SERVICE] Conversion to {target_lang} failed: {e}. Falling back to raster.")
        converted_path = convert_pdf_to_raster(pdf_path)
        
    return converted_path

def convert_doc_to_pdf(doc_path: str) -> str:
    """Convert DOC/DOCX to PDF using LibreOffice headless."""
    output_dir = os.path.dirname(doc_path)
    print(f"[DOCUMENT SERVICE] Converting {doc_path} to PDF using LibreOffice...")
    try:
        # LibreOffice must be in PATH or specify full path
        cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", output_dir, doc_path]
        subprocess.run(cmd, timeout=30, check=True)
        pdf_path = os.path.splitext(doc_path)[0] + ".pdf"
        if os.path.exists(pdf_path):
            return pdf_path
        raise FileNotFoundError("LibreOffice completed but PDF was not found.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("LibreOffice conversion timed out.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"LibreOffice conversion failed: {e}")

def convert_txt_to_pdf(txt_path: str) -> str:
    """Convert TXT to PDF using simple enscript+ps2pdf or similar if available, or just fallback."""
    # Note: Implementing a basic fallback. Ghostscript can sometimes handle txt, 
    # but for true robustness a python library like reportlab or fpdf is better.
    # We will assume LibreOffice can also convert txt to pdf
    return convert_doc_to_pdf(txt_path)

def convert_pdf_to_ps(pdf_path: str) -> str:
    """Convert PDF to PostScript using Ghostscript."""
    ps_path = os.path.splitext(pdf_path)[0] + ".ps"
    print(f"[DOCUMENT SERVICE] Converting {pdf_path} to PS using Ghostscript...")
    try:
        # Windows GS executable: gswin64c or gswin32c or gs
        gs_cmd = "gswin64c" if os.name == 'nt' else "gs"
        
        # Test if gswin64c exists, if not try gs
        try:
            subprocess.run([gs_cmd, "--version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            gs_cmd = "gs" # fallback
            
        cmd = [
            gs_cmd,
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            "-sDEVICE=ps2write",
            f"-sOutputFile={ps_path}",
            pdf_path
        ]
        subprocess.run(cmd, timeout=60, check=True)
        return ps_path
    except Exception as e:
        raise RuntimeError(f"Ghostscript PS conversion failed: {e}")

def convert_pdf_to_pcl(pdf_path: str) -> str:
    """Convert PDF to PCL using Ghostscript."""
    pcl_path = os.path.splitext(pdf_path)[0] + ".pcl"
    print(f"[DOCUMENT SERVICE] Converting {pdf_path} to PCL using Ghostscript...")
    try:
        gs_cmd = "gswin64c" if os.name == 'nt' else "gs"
        
        try:
            subprocess.run([gs_cmd, "--version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            gs_cmd = "gs"
            
        cmd = [
            gs_cmd,
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            "-sDEVICE=ljet4", # Generic PCL
            f"-sOutputFile={pcl_path}",
            pdf_path
        ]
        subprocess.run(cmd, timeout=60, check=True)
        return pcl_path
    except Exception as e:
        raise RuntimeError(f"Ghostscript PCL conversion failed: {e}")

def convert_pdf_to_raster(pdf_path: str) -> str:
    """Convert PDF to raw raster (images) and then to a printable format."""
    # This is a fallback. We could use pdf2image, but let's use Ghostscript's cups/raster 
    # or direct image format (e.g. pcx or tiff) that printers might accept if raw.
    # Or simply print it as an image.
    print(f"[DOCUMENT SERVICE] Converting {pdf_path} to raster fallback...")
    
    raster_path = os.path.splitext(pdf_path)[0] + ".raster"
    
    try:
        gs_cmd = "gswin64c" if os.name == 'nt' else "gs"
        try:
            subprocess.run([gs_cmd, "--version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            gs_cmd = "gs"
            
        # Using tiffg4 as a common raster format that many systems can pipe to printers
        cmd = [
            gs_cmd,
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            "-sDEVICE=tiffg4",
            f"-sOutputFile={raster_path}",
            pdf_path
        ]
        subprocess.run(cmd, timeout=60, check=True)
        return raster_path
    except Exception as e:
        raise RuntimeError(f"Raster conversion failed: {e}")

import os
import subprocess
import logging

logger = logging.getLogger("DocumentService")

def process_document(file_path: str, printer: dict) -> bytes:
    """
    Convert document and return raw bytes. Clean up all temporary files.
    """
    file_ext = os.path.splitext(file_path)[1].lower()
    temp_files = []
    
    try:
        # 1. Base conversion: DOC/DOCX/TXT to PDF
        pdf_path = file_path
        if file_ext in [".doc", ".docx"]:
            logger.info(f"Converting DOC to PDF: {file_path}")
            pdf_path = convert_doc_to_pdf(file_path)
            temp_files.append(pdf_path)
        elif file_ext == ".txt":
            logger.info(f"Processing TXT: {file_path}")
            with open(file_path, "rb") as f:
                data = f.read()
            return data

        # 2. Target format based on printer
        target_lang = printer.get("language", "AUTO").upper()
        if target_lang == "AUTO":
            target_lang = "PS"
            
        converted_path = None
        try:
            logger.info(f"Converting PDF to {target_lang}")
            if target_lang == "PS":
                converted_path = convert_pdf_to_ps(pdf_path)
            elif target_lang == "PCL":
                converted_path = convert_pdf_to_pcl(pdf_path)
            else:
                converted_path = convert_pdf_to_raster(pdf_path)
        except Exception as e:
            logger.warning(f"Primary ({target_lang}) failed: {e}. Falling back to Raster.")
            converted_path = convert_pdf_to_raster(pdf_path)
            
        temp_files.append(converted_path)
        
        # Read final binary
        with open(converted_path, "rb") as f:
            data = f.read()
            
        return data
        
    except Exception as e:
        logger.error(f"Critical conversion failure: {e}")
        raise
        
    finally:
        # 🔹 COMPREHENSIVE CLEANUP (Hospital-Grade Safety)
        # Clean all intermediate temp files (pdf, ps, pcl, raster)
        for f in temp_files:
            if f and f != file_path and os.path.exists(f):
                try: os.remove(f)
                except: pass

def convert_doc_to_pdf(doc_path: str) -> str:
    output_dir = os.path.dirname(doc_path)
    cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", output_dir, doc_path]
    subprocess.run(cmd, timeout=120, check=True)
    pdf_path = os.path.splitext(doc_path)[0] + ".pdf"
    return pdf_path

def convert_txt_to_pdf(txt_path: str) -> str:
    return convert_doc_to_pdf(txt_path)

def convert_pdf_to_ps(pdf_path: str) -> str:
    ps_path = os.path.splitext(pdf_path)[0] + ".ps"
    gs_cmd = "gswin64c" if os.name == 'nt' else "gs"
    cmd = [gs_cmd, "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=ps2write", f"-sOutputFile={ps_path}", pdf_path]
    subprocess.run(cmd, timeout=120, check=True)
    return ps_path

def convert_pdf_to_pcl(pdf_path: str) -> str:
    pcl_path = os.path.splitext(pdf_path)[0] + ".pcl"
    gs_cmd = "gswin64c" if os.name == 'nt' else "gs"
    cmd = [gs_cmd, "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=ljet4", f"-sOutputFile={pcl_path}", pdf_path]
    subprocess.run(cmd, timeout=120, check=True)
    return pcl_path

def convert_pdf_to_raster(pdf_path: str) -> str:
    raster_path = os.path.splitext(pdf_path)[0] + ".raster"
    gs_cmd = "gswin64c" if os.name == 'nt' else "gs"
    cmd = [gs_cmd, "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=tiffg4", f"-sOutputFile={raster_path}", pdf_path]
    subprocess.run(cmd, timeout=120, check=True)
    return raster_path

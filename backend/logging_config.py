import logging
import logging.handlers
import json
import os
from datetime import datetime, timezone
from config import settings

class JSONFormatter(logging.Formatter):
    """Produces structured JSON logs for easy parsing by log aggregators (ELK, Datadog)."""
    def format(self, record):
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        
        # Attach additional structured data if provided
        if hasattr(record, "details"):
            log_data["details"] = record.details
            
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_data)

def setup_logging(log_dir: str = "./logs", json_format: bool = True):
    """
    Configures a production-ready logging system with rotation.
    """
    os.makedirs(log_dir, exist_ok=True)
    
    # 1. Main JSON Rotating Log (10MB per file, 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "printhub.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5
    )
    file_handler.setFormatter(JSONFormatter() if json_format else logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    
    # 2. Critical Error Log (5MB per file, 3 backups)
    error_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "printhub_errors.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter() if json_format else logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    
    # 3. Standard Output (Human-readable for console/dev)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [] # Clear existing handlers
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    
    # Only use console handler in non-production or explicitly requested
    if settings.environment == "development":
        root_logger.addHandler(console_handler)
    
    logging.getLogger("uvicorn.access").disabled = True # We use our own middleware for request logs
    
    print(f"[*] Logging initialized: {log_dir}")

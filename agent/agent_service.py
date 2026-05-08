import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import os
import logging
import threading
from logging.handlers import RotatingFileHandler

# Import the actual agent logic
# Ensure we can find agent.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent import agent_loop

class PrintHubAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "PrintHubAgent"
    _svc_display_name_ = "PrintHub USB Print Agent"
    _svc_description_ = "Broker between hospital workstation USB printers and the PrintHub server."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        
        # Setup logging
        log_dir = r"C:\PrintHubAgent"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        log_file = os.path.join(log_dir, "agent_service.log")
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("AgentService")

    def SvcStop(self):
        self.logger.info("Service stopping...")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        self.logger.info("Service starting...")
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        
        try:
            # Run the agent loop in a daemon thread
            agent_thread = threading.Thread(target=agent_loop, daemon=True)
            agent_thread.start()
            
            # 🔹 CRITICAL: Wait 30s to see if agent thread dies early (e.g. registration fail)
            agent_thread.join(timeout=30)
            if not agent_thread.is_alive():
                self.logger.critical("[SERVICE] Agent thread died on startup. Check agent_config.json and activation code.")
                win32event.SetEvent(self.stop_event)
                return

            # Wait for the stop event
            win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
        except Exception as e:
            self.logger.critical(f"[SERVICE] Fatal error: {e}", exc_info=True)
        
        self.logger.info("Service stopped.")

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PrintHubAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PrintHubAgentService)

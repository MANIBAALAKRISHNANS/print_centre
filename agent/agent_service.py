import win32serviceutil
import win32service
import win32event
import servicemanager
import sys
import os
import threading

# Ensure agent.py is importable from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import agent_loop, logger as agent_logger


class PrintHubAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "PrintHubAgent"
    _svc_display_name_ = "PrintHub USB Print Agent"
    _svc_description_ = "Routes USB print jobs from hospital workstations to the PrintHub server."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        # Reuse the logger already configured by agent.py (avoids basicConfig no-op conflict)
        self.logger = agent_logger

    def SvcStop(self):
        self.logger.info("[SERVICE] Stop signal received from SCM")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        # Report RUNNING immediately so SCM doesn't time out
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        self.logger.info("[SERVICE] PrintHubAgent started")
        servicemanager.LogInfoMsg("PrintHubAgent service started")

        try:
            # Run the agent loop in a daemon thread; service stays alive via WaitForSingleObject
            t = threading.Thread(target=agent_loop, daemon=True, name="AgentLoop")
            t.start()
            # Block until SCM sends a stop request
            win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
        except Exception as e:
            self.logger.critical(f"[SERVICE] Fatal: {e}", exc_info=True)

        self.logger.info("[SERVICE] PrintHubAgent stopped")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PrintHubAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PrintHubAgentService)

"""
Continuous Robust Supervisor & Watchdog for AlphaNSE Trading Platform.

Ensures 24/7 continuous operation:
1. Spawns and supervises the FastAPI Server & WebSocket Engine on port 8000.
2. Spawns and supervises the Continuous Session Monitor (logging telemetry & verification).
3. Automatically detects crashes, unhandled errors, or hangs, and restarts components immediately.
4. Performs regular health checks against http://localhost:8000/api/health.
5. Logs supervisor events to QA/logs/live_metrics/supervisor.log.
"""

import os
import sys
import time
import signal
import subprocess
import requests
from datetime import datetime

# Setup project directories
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
QA_DIR = os.path.join(PROJECT_ROOT, "QA")
LOG_DIR = os.path.join(QA_DIR, "logs", "live_metrics")
os.makedirs(LOG_DIR, exist_ok=True)
SUPERVISOR_LOG = os.path.join(LOG_DIR, "supervisor.log")
SERVER_LOG_FILE = os.path.join(LOG_DIR, "server_uvicorn.log")
LOGGER_LOG_FILE = os.path.join(LOG_DIR, "session_logger_out.log")

SERVER_URL = "http://127.0.0.1:8000"
HEALTH_CHECK_INTERVAL = 25  # seconds
MAX_CONSECUTIVE_HEALTH_FAILURES = 5

def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [SUPERVISOR] {msg}"
    print(formatted, flush=True)
    try:
        with open(SUPERVISOR_LOG, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

class ContinuousSupervisor:
    def __init__(self):
        self.server_proc = None
        self.logger_proc = None
        self.server_log_f = None
        self.logger_log_f = None
        self.consecutive_health_fails = 0
        self.should_run = True
        self.python_bin = sys.executable

        # Signal handlers
        signal.signal(signal.SIGINT, self.handle_exit)
        signal.signal(signal.SIGTERM, self.handle_exit)

    def handle_exit(self, signum, frame):
        log(f"Received stop signal ({signum}). Initiating graceful shutdown...")
        self.should_run = False
        self.stop_all()
        sys.exit(0)

    def start_server(self):
        """Start or restart the FastAPI & WebSocket server."""
        if self.server_proc and self.server_proc.poll() is None:
            return

        cmd = [
            self.python_bin, "-m", "uvicorn",
            "QA.server.api:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--log-level", "info"
        ]
        log(f"Launching FastAPI Server: {' '.join(cmd)}")
        try:
            self.server_log_f = open(SERVER_LOG_FILE, "a", encoding="utf-8", errors="replace")
            self.server_proc = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                stdout=self.server_log_f,
                stderr=subprocess.STDOUT
            )
            log(f"FastAPI Server started with PID {self.server_proc.pid}")
        except Exception as e:
            log(f"ERROR: Failed to launch FastAPI server: {e}")

    def start_logger(self):
        """Start or restart the background continuous session logger."""
        if self.logger_proc and self.logger_proc.poll() is None:
            return

        logger_script = os.path.join(QA_DIR, "monitoring", "continuous_session_logger.py")
        cmd = [self.python_bin, logger_script]
        log(f"Launching Session Logger: {' '.join(cmd)}")
        try:
            self.logger_log_f = open(LOGGER_LOG_FILE, "a", encoding="utf-8", errors="replace")
            self.logger_proc = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                stdout=self.logger_log_f,
                stderr=subprocess.STDOUT
            )
            log(f"Session Logger started with PID {self.logger_proc.pid}")
        except Exception as e:
            log(f"ERROR: Failed to launch Session Logger: {e}")

    def check_health(self) -> bool:
        """Query /api/health to confirm server responsiveness."""
        try:
            r = requests.get(f"{SERVER_URL}/api/health", timeout=15)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        return False

    def stop_process(self, proc, name: str):
        if proc and proc.poll() is None:
            log(f"Terminating {name} (PID {proc.pid})...")
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def stop_all(self):
        log("Stopping all child processes...")
        self.stop_process(self.logger_proc, "Session Logger")
        self.stop_process(self.server_proc, "FastAPI Server")
        log("All child processes stopped.")

    def run(self):
        log("=" * 70)
        log("AlphaNSE 24/7 Continuous Trading Supervisor Started")
        log(f"Working Directory: {PROJECT_ROOT}")
        log(f"Target Server: {SERVER_URL}")
        log("=" * 70)

        # Initial launch
        self.start_server()
        time.sleep(4)  # Allow server to bind port
        self.start_logger()

        last_health_check = 0.0

        while self.should_run:
            now = time.time()

            # 1. Check if server process died
            if self.server_proc:
                code = self.server_proc.poll()
                if code is not None:
                    log(f"WARNING: FastAPI Server exited unexpectedly with code {code}. Auto-restarting in 3s...")
                    time.sleep(3)
                    self.start_server()

            # 2. Check if logger process died
            if self.logger_proc:
                code = self.logger_proc.poll()
                if code is not None:
                    log(f"WARNING: Session Logger exited with code {code}. Auto-restarting in 3s...")
                    time.sleep(3)
                    self.start_logger()

            # 3. Periodic HTTP Health Check
            if now - last_health_check >= HEALTH_CHECK_INTERVAL:
                last_health_check = now
                healthy = self.check_health()
                if healthy:
                    self.consecutive_health_fails = 0
                else:
                    self.consecutive_health_fails += 1
                    log(f"WARNING: Health check failed ({self.consecutive_health_fails}/{MAX_CONSECUTIVE_HEALTH_FAILURES})")
                    if self.consecutive_health_fails >= MAX_CONSECUTIVE_HEALTH_FAILURES:
                        log("CRITICAL: Server unresponsive for multiple checks. Forcing server restart...")
                        self.stop_process(self.server_proc, "FastAPI Server")
                        time.sleep(3)
                        self.start_server()
                        self.consecutive_health_fails = 0

            time.sleep(2)

if __name__ == "__main__":
    supervisor = ContinuousSupervisor()
    supervisor.run()

import subprocess
import os
import sys
import socket
import threading
import time
import argparse
from datetime import datetime
import schedule
from pystray import MenuItem as item, Icon
from PIL import Image
import win32event
import win32api
import win32com.client
from winerror import ERROR_ALREADY_EXISTS
import base64
from io import BytesIO

# --- Configuration (Hardcoded) ---
# All settings are now inside the script.
TARGET_HOST = "tmgposapi.themall.co.th"
INTERVAL_MINUTES = 15
LOG_FOLDER = "C:\\Latency\\latency test"

# --- Base64 Encoded Icon (Self-Contained) ---
# This avoids needing a separate .ico file.
ICON_B64 = b'iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAACYSURBVHja7cExAQAAAMKg9U9tCF8gAAAAAAAAAAAAAECvA0AAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBAgQIAAAQIECBBfA2s5AAGZCIyGAAAAAElFTkSuQmCC'

# --- Single Instance Lock using a Mutex ---
class SingleInstance:
    def __init__(self, name):
        self.mutex_name = name
        self.mutex = win32event.CreateMutex(None, 1, self.mutex_name)
        self.last_error = win32api.GetLastError()

    def is_running(self):
        return self.last_error == ERROR_ALREADY_EXISTS

    def __del__(self):
        if self.mutex:
            win32api.CloseHandle(self.mutex)

# --- Startup Installation Logic ---
def install_startup():
    """Creates a shortcut in the user's Startup folder."""
    # Get the real path of the executable.
    exe_path = os.path.realpath(sys.executable)
    
    startup_folder = os.path.join(os.getenv('APPDATA'), 'Microsoft\\Windows\\Start Menu\\Programs\\Startup')
    shortcut_path = os.path.join(startup_folder, "API Connection Monitor.lnk")
    
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.Targetpath = exe_path
    shortcut.WorkingDirectory = os.path.dirname(exe_path)
    shortcut.IconLocation = exe_path
    shortcut.save()
    print(f"Success! Shortcut created in Startup folder.")
    print("The API Monitor will now start automatically on login.")

# --- Core Diagnostic Function ---
def run_diagnostics():
    print(f"[{datetime.now()}] Running diagnostics for {TARGET_HOST}...")
    computer_name = socket.gethostname()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_name = f"{computer_name}_{timestamp}.txt"
    
    os.makedirs(LOG_FOLDER, exist_ok=True)
    full_path = os.path.join(LOG_FOLDER, file_name)

    script_content = f"""
@echo off
(
    ECHO COMPREHENSIVE NETWORK DIAGNOSTIC REPORT
    ECHO =================================================
    ECHO Report generated on: %date% at %time%
    ECHO Target Host: {TARGET_HOST}
    ECHO.
    ECHO.
    ECHO ===== 1. TRACEROUTE TO VIEW NETWORK PATH =====
    ECHO.
    tracert {TARGET_HOST}
    ECHO.
    ECHO.
    ECHO ===== 2. DNS LATENCY & RESOLUTION TEST =====
    ECHO.
    powershell -ExecutionPolicy Bypass -Command "Measure-Command {{Resolve-DnsName {TARGET_HOST} -Type A -ErrorAction SilentlyContinue}}"
    ECHO.
    ECHO.
    ECHO ===== 3. CURL API CONNECTION TIMING =====
    ECHO.
    curl -o nul -s -w "DNS Lookup:      %%{{time_namelookup}}s\\nTCP Connection:  %%{{time_connect}}s\\nSSL Handshake:   %%{{time_appconnect}}s\\nTTFB:              %%{{time_starttransfer}}s\\nTotal Time:      %%{{time_total}}s\\n" https://{TARGET_HOST}
) > "{full_path}" 2>&1
"""
    try:
        subprocess.run(script_content, shell=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        print(f"[{datetime.now()}] Diagnostics complete. Log saved to {full_path}")
    except Exception as e:
        print(f"[{datetime.now()}] A critical error occurred during diagnostics: {e}")

# --- Scheduler Setup ---
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- System Tray Application Setup ---
def setup_tray_app():
    # Load icon from embedded base64 data
    icon_data = base64.b64decode(ICON_B64)
    icon_image = Image.open(BytesIO(icon_data))

    def on_run_now(icon, item):
        print("Manual diagnostic run triggered.")
        threading.Thread(target=run_diagnostics, daemon=True).start()

    def on_open_logs(icon, item):
        os.startfile(LOG_FOLDER)

    def on_exit(icon, item):
        icon.stop()

    menu = (
        item('Run Diagnostics Now', on_run_now),
        item('Open Logs Folder', on_open_logs),
        item('Exit', on_exit)
    )
    icon = Icon("API_Monitor", icon_image, "API Connection Monitor", menu)
    icon.run()

# --- Main Application Execution ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="API Connection Monitor")
    parser.add_argument('--install', action='store_true', help='Install the application to run on startup.')
    args = parser.parse_args()

    # If the --install flag is used, run the installer and exit.
    if args.install:
        install_startup()
        sys.exit(0)

    # Ensure only one instance of the main application is running.
    instance_name = "Global\\API_Monitor_Mutex_3B6A8D_v2"
    instance = SingleInstance(instance_name)
    if instance.is_running():
        print("Another instance is already running. Exiting.")
        sys.exit(1)

    print(f"Monitoring {TARGET_HOST} every {INTERVAL_MINUTES} minutes.")
    print(f"Logs will be saved to: {LOG_FOLDER}")

    schedule.every(INTERVAL_MINUTES).minutes.do(run_diagnostics)
    
    # Start the scheduler in a background thread.
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Run diagnostics once on startup after a short delay to let the system settle.
    threading.Timer(10.0, run_diagnostics).start()

    # Run the system tray application on the main thread.
    setup_tray_app()

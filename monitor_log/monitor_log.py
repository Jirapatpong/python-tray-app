import pystray
from PIL import Image, ImageDraw
import psutil
import logging
import threading
import time
import os
import subprocess
import sys

# ================= CONFIGURATION =================
TARGET_PROCESSES = ["msedge.exe", "notepad.exe"]
LOG_FILE_NAME = "kiosk_monitor_log.txt"
CHECK_INTERVAL = 5
# =================================================

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

LOG_FILE_PATH = os.path.join(application_path, LOG_FILE_NAME)

logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

running = True
process_status = {proc: False for proc in TARGET_PROCESSES}

def create_icon():
    width = 64
    height = 64
    color1 = "green"
    color2 = "blue"
    image = Image.new('RGB', (width, height), color1)
    dc = ImageDraw.Draw(image)
    dc.rectangle((width // 2, 0, width, height // 2), fill=color2)
    dc.rectangle((0, height // 2, width // 2, height), fill=color2)
    return image

def get_recent_crash_log(proc_name):
    """
    ฟังก์ชันนี้จะไปดึงข้อมูลจาก Event Viewer (Application Log) 
    หา Error ที่เกี่ยวข้องกับ process_name ในช่วง 2 นาทีล่าสุด
    """
    try:
        # คำสั่ง PowerShell เพื่อดึง Crash Log ล่าสุดแบบละเอียด
        ps_command = f"""
        Get-EventLog -LogName Application -EntryType Error -After (Get-Date).AddMinutes(-2) | 
        Where-Object {{ $_.Message -like "*{proc_name}*" }} | 
        Select-Object -First 1 | 
        Format-List TimeGenerated, EventID, Message, Source
        """
        
        # รันคำสั่งและดึงผลลัพธ์
        result = subprocess.run(["powershell", "-Command", ps_command], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if result.stdout.strip():
            return f"\n[CRASH DETAILS DETECTED FROM WINDOWS EVENT LOG]:\n{result.stdout}"
        else:
            return " (No specific crash event found in Windows Logs - maybe forced closed or clean exit)"
            
    except Exception as e:
        return f" (Failed to fetch details: {e})"

def monitor_loop(icon):
    global running
    logging.info("--- Monitor Started (Detailed Mode) ---")
    
    while running:
        current_running_processes = []
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] in TARGET_PROCESSES:
                    current_running_processes.append(proc.info['name'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        for target in TARGET_PROCESSES:
            is_now_running = target in current_running_processes
            
            if is_now_running != process_status[target]:
                if is_now_running:
                    logging.info(f"Process STARTED: {target}")
                else:
                    # กรณีที่โปรแกรมดับ -> ให้ไปขุด Log ทันที
                    msg = f"Process STOPPED/CRASHED: {target}"
                    
                    # เรียกฟังก์ชันดึงรายละเอียด
                    crash_details = get_recent_crash_log(target)
                    
                    # บันทึกลง Log ไฟล์เดียว
                    logging.warning(f"{msg}{crash_details}")
                    logging.info("-" * 50) # ขีดเส้นคั่นให้อ่านง่าย
                
                process_status[target] = is_now_running
        
        time.sleep(CHECK_INTERVAL)

def open_log_file(icon, item):
    if os.path.exists(LOG_FILE_PATH):
        subprocess.Popen(['notepad.exe', LOG_FILE_PATH])

def exit_action(icon, item):
    global running
    running = False
    logging.info("--- Monitor Stopped by User ---")
    icon.stop()

if __name__ == "__main__":
    monitor_thread = threading.Thread(target=monitor_loop, args=(None,))
    image = create_icon()
    menu = (
        pystray.MenuItem('Open Log File', open_log_file),
        pystray.MenuItem('Exit', exit_action)
    )
    icon = pystray.Icon("KioskMonitor", image, "Kiosk Monitor Tool", menu)
    
    monitor_thread = threading.Thread(target=monitor_loop, args=(icon,))
    monitor_thread.start()
    icon.run()

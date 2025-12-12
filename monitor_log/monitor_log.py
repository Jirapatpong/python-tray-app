import pystray
from PIL import Image, ImageDraw
import psutil
import logging
import threading
import time
import os
import subprocess
import sys
import json
import tkinter as tk
from tkinter import messagebox

# ================= CONFIGURATION =================
DEFAULT_PROCESSES = ["msedge.exe", "notepad.exe"]
LOG_FILE_NAME = "kiosk_monitor_log.txt"
CONFIG_FILE_NAME = "monitor_config.json"
CHECK_INTERVAL = 5
# =================================================

# Setup Paths
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

LOG_FILE_PATH = os.path.join(application_path, LOG_FILE_NAME)
CONFIG_FILE_PATH = os.path.join(application_path, CONFIG_FILE_NAME)

# Setup Logging
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Global Variables
running = True
target_processes = []
process_status = {}
management_window = None # ตัวแปรเก็บสถานะหน้าต่าง GUI

# --- Config Management ---
def load_config():
    global target_processes, process_status
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'r') as f:
                data = json.load(f)
                target_processes = data.get("processes", DEFAULT_PROCESSES)
        except Exception as e:
            logging.error(f"Error loading config: {e}")
            target_processes = DEFAULT_PROCESSES
    else:
        target_processes = DEFAULT_PROCESSES
    
    process_status = {proc: False for proc in target_processes}

def save_config():
    try:
        data = {"processes": target_processes}
        with open(CONFIG_FILE_PATH, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving config: {e}")

# --- Core Functions ---
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
    try:
        ps_command = f"""
        Get-EventLog -LogName Application -EntryType Error -After (Get-Date).AddMinutes(-2) | 
        Where-Object {{ $_.Message -like "*{proc_name}*" }} | 
        Select-Object -First 1 | 
        Format-List TimeGenerated, EventID, Message, Source
        """
        result = subprocess.run(["powershell", "-Command", ps_command], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.stdout.strip():
            return f"\n[CRASH DETAILS DETECTED FROM WINDOWS EVENT LOG]:\n{result.stdout}"
        else:
            return " (No specific crash event found in Windows Logs)"
    except Exception as e:
        return f" (Failed to fetch details: {e})"

def monitor_loop(icon):
    global running, target_processes, process_status
    logging.info("--- Monitor Started (GUI Fixed Version) ---")
    
    while running:
        current_targets = target_processes.copy()
        for t in current_targets:
            if t not in process_status:
                process_status[t] = False
        
        running_procs_now = []
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] in current_targets:
                    running_procs_now.append(proc.info['name'])
            except:
                pass

        for target in current_targets:
            is_now_running = target in running_procs_now
            prev_status = process_status.get(target, False)

            if is_now_running != prev_status:
                if is_now_running:
                    logging.info(f"Process STARTED: {target}")
                else:
                    msg = f"Process STOPPED/CRASHED: {target}"
                    crash_details = get_recent_crash_log(target)
                    logging.warning(f"{msg}{crash_details}")
                    logging.info("-" * 50)
                process_status[target] = is_now_running
        
        time.sleep(CHECK_INTERVAL)

# --- GUI Management ---
def open_management_window(icon, item):
    global management_window

    # เช็คก่อนว่ามีหน้าต่างเปิดอยู่ไหม ถ้ามีให้เด้งขึ้นมาเลย (ไม่สร้างใหม่)
    if management_window is not None:
        try:
            management_window.lift()
            management_window.focus_force()
            return
        except tk.TclError:
            # ถ้าหน้าต่างเคยถูกทำลายไปแล้วแต่ตัวแปรยังค้าง ให้เคลียร์ทิ้งแล้วสร้างใหม่
            management_window = None

    def on_closing():
        global management_window
        management_window.destroy()
        management_window = None # รีเซ็ตค่าเพื่อให้เปิดใหม่ได้ครั้งหน้า

    def add_proc():
        new_proc = entry.get().strip()
        if new_proc and new_proc not in target_processes:
            target_processes.append(new_proc)
            listbox.insert(tk.END, new_proc)
            entry.delete(0, tk.END)
            save_config()

    def remove_proc():
        try:
            selection = listbox.curselection()
            if selection:
                proc_to_remove = listbox.get(selection[0])
                target_processes.remove(proc_to_remove)
                listbox.delete(selection[0])
                save_config()
        except Exception as e:
            pass

    # Setup Window
    management_window = tk.Tk()
    management_window.title("Monitor Manager")
    management_window.geometry("300x350")
    management_window.attributes('-topmost', True)
    
    # กำหนดให้กด X แล้วเรียกฟังก์ชัน on_closing
    management_window.protocol("WM_DELETE_WINDOW", on_closing)
    
    lbl = tk.Label(management_window, text="Monitored Processes (.exe):")
    lbl.pack(pady=5)

    listbox = tk.Listbox(management_window)
    listbox.pack(fill=tk.BOTH, expand=True, padx=10)

    for p in target_processes:
        listbox.insert(tk.END, p)

    frame_entry = tk.Frame(management_window)
    frame_entry.pack(fill=tk.X, padx=10, pady=5)
    
    entry = tk.Entry(frame_entry)
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    btn_add = tk.Button(frame_entry, text="Add", command=add_proc)
    btn_add.pack(side=tk.RIGHT, padx=5)

    btn_del = tk.Button(management_window, text="Remove Selected", command=remove_proc, bg="#ffdddd")
    btn_del.pack(fill=tk.X, padx=10, pady=10)

    management_window.mainloop()

def open_log_file(icon, item):
    if os.path.exists(LOG_FILE_PATH):
        subprocess.Popen(['notepad.exe', LOG_FILE_PATH])

def exit_action(icon, item):
    global running
    running = False
    icon.stop()
    # ปิด GUI ด้วยถ้าเปิดค้างอยู่
    if management_window:
        try:
            management_window.destroy()
        except:
            pass
    os._exit(0) # Force kill process

# --- Main Execution ---
if __name__ == "__main__":
    load_config()
    
    monitor_thread = threading.Thread(target=monitor_loop, args=(None,))
    
    image = create_icon()
    menu = (
        pystray.MenuItem('Manage Processes', open_management_window),
        pystray.MenuItem('Open Log File', open_log_file),
        pystray.MenuItem('Exit', exit_action)
    )
    icon = pystray.Icon("KioskMonitor", image, "Kiosk Monitor Tool", menu)
    
    monitor_thread = threading.Thread(target=monitor_loop, args=(icon,))
    monitor_thread.start()
    
    icon.run()

# This code has been verified to have correct indentation.
# VERSION: 1.0.3-Fix (Robust Zip Monitor + Prefix Filter)
import subprocess
import threading
import os
import sys
import time
import queue
import zipfile
import shutil
import configparser
import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from tkinter import filedialog, messagebox
from pyaxmlparser import APK

# --- Image Generation for UI ---
def create_android_icon(color):
    """Generates a simple Android robot icon."""
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.arc((12, 10, 52, 50), 180, 0, fill=color, width=8)
    draw.ellipse((22, 24, 28, 30), fill='white')
    draw.ellipse((36, 24, 42, 30), fill='white')
    draw.line((20, 12, 16, 6), fill=color, width=3)
    draw.line((44, 12, 48, 6), fill=color, width=3)
    draw.rectangle((12, 32, 52, 54), fill=color, outline=color, width=1)
    return image

# --- Handler for the Zip file monitoring service ---
class ZipFileHandler(FileSystemEventHandler):
    def __init__(self, app_instance):
        self.app = app_instance

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.zip'):
            filename = os.path.basename(event.src_path)
            
            # --- [FIX 2] Filtering Logic ---
            # ถ้ามีค่า Prefix ใน Config และชื่อไฟล์ไม่ได้ขึ้นต้นด้วย Prefix นั้น -> ให้ข้ามเลย
            if self.app.zip_filename_prefix and not filename.startswith(self.app.zip_filename_prefix):
                # print(f"Ignored: {filename} (Does not match prefix '{self.app.zip_filename_prefix}')")
                return
            # -------------------------------

            if event.src_path in self.app.processing_files:
                return
            
            print(f"New zip file detected: {event.src_path}")
            self.app.master.after(0, self.app._add_zip_to_monitor, event.src_path)

# --- Handler for the APK file monitoring service ---
class ApkFileHandler(FileSystemEventHandler):
    def __init__(self, app_instance):
        self.app = app_instance

    def process_event(self, event):
        if not event.is_directory and event.src_path.endswith('.apk'):
            if event.src_path in self.app.apk_file_map: return
            if event.src_path in self.app.apk_processing_files: return
            
            print(f"New APK file event ({event.event_type}): {event.src_path}")
            self.app.master.after(0, self.app._add_apk_to_monitor, event.src_path)

    def on_created(self, event): self.process_event(event)
    def on_modified(self, event): self.process_event(event)

class App:
    def __init__(self, master, lock_file_path):
        import tkinter as tk
        from tkinter import ttk, scrolledtext
        from PIL import ImageTk

        self.master = master
        self.tray_icon = None
        self.is_running = True
        self.is_disconnecting = False
        self.api_process = None
        self.last_search_term = ""
        self.last_search_pos = "1.0"
        self.api_status = "Offline"
        self.lock_file_path = lock_file_path
        self.known_devices = set()

        self.notification_window = None
        self.notification_timer = None
        
        # --- Variables ---
        self.log_filepath = None
        self.log_dir = None 
        self.current_log_date = None
        self.zip_monitor_path = None
        self.zip_filename_prefix = "" # [FIX 2] ตัวแปรเก็บ Prefix
        self.apk_monitor_path = None
        self.zip_file_observer = None
        self.apk_file_observer = None
        
        # --- Zip Monitor ---
        self.zip_processed_count = 0
        self.zip_file_map = {}
        self.processing_files = set()
        
        # --- APK Monitor ---
        self.apk_processed_count = 0
        self.apk_file_map = {}
        self.apk_processing_files = set()
        
        if getattr(sys, 'frozen', False):
            self.base_path = os.path.dirname(sys.executable)
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))

        master.title("HHT Android Connect")

        app_width = 560
        app_height = 360
        screen_width = master.winfo_screenwidth()
        screen_height = master.winfo_screenheight()
        x_pos = screen_width - app_width - 20
        y_pos = screen_height - app_height - 80
        master.geometry(f"{app_width}x{app_height}+{x_pos}+{y_pos}")
        master.resizable(False, False)

        # --- Color Palette ---
        self.COLOR_BG = "#E0E5EC"
        self.COLOR_SHADOW_LIGHT = "#FFFFFF"
        self.COLOR_SHADOW_DARK = "#A3B1C6"
        self.COLOR_TEXT = "#5A6677"
        self.COLOR_ACCENT = "#FF6B6B"
        self.COLOR_SUCCESS = "#2EC574"
        self.COLOR_DANGER = "#FF4757"
        self.COLOR_3D_BG_ACTIVE = "#3D4450"
        self.COLOR_3D_BG_INACTIVE = "#C8D0DA"
        self.COLOR_WARNING = "#F59E0B"

        master.configure(background=self.COLOR_BG)
        self.icon_image = create_android_icon(self.COLOR_TEXT)
        master.iconphoto(True, ImageTk.PhotoImage(self.icon_image))

        # --- Style ---
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('.', font=('Segoe UI', 9), background=self.COLOR_BG, foreground=self.COLOR_TEXT, borderwidth=0)
        self.style.configure('TFrame', background=self.COLOR_BG)
        self.style.configure('Treeview', background=self.COLOR_BG, fieldbackground=self.COLOR_BG, foreground=self.COLOR_TEXT, rowheight=30, font=('Consolas', 10))
        self.style.map('Treeview', background=[('selected', self.COLOR_SHADOW_DARK)], foreground=[('selected', self.COLOR_SHADOW_LIGHT)])
        self.style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'), background=self.COLOR_BG, relief='flat')
        self.style.map('Treeview.Heading', background=[('active', self.COLOR_BG)])
        self.style.configure('TEntry', fieldbackground=self.COLOR_BG, foreground=self.COLOR_TEXT, insertcolor=self.COLOR_TEXT, relief='flat', borderwidth=0)
        self.style.configure('Tab.TButton', font=('Segoe UI', 10, 'bold'), padding=(15, 5), relief='raised', borderwidth=2)
        self.style.map('Tab.TButton', background=[('selected', self.COLOR_3D_BG_ACTIVE), ('!selected', self.COLOR_3D_BG_INACTIVE)], foreground=[('selected', 'white'), ('!selected', self.COLOR_TEXT)])
        self.style.configure('Raised.TButton', font=('Segoe UI', 9, 'bold'), padding=(10, 5), relief='raised', background=self.COLOR_3D_BG_ACTIVE, foreground='white', borderwidth=2)
        self.style.map('Raised.TButton', background=[('active', self.COLOR_SHADOW_DARK)])

        self.ADB_PATH = self.get_adb_path()
        if not self.check_adb():
            messagebox.showerror("ADB Error", "Android Debug Bridge (ADB) not found.")
            master.quit()
            return
        self.start_adb_server()
        self.connected_device = None

        self.create_widgets()
        self.refresh_devices()
        self.update_tray_status()

        self.monitor_thread = threading.Thread(target=self.device_monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.start_api_exe()
        self._setup_log_file()
        self._periodic_log_save()
        self._start_monitoring_services()
        self._scan_existing_apk_files()

    def show_notification(self, message, is_connected):
        import tkinter as tk
        if self.notification_timer: self.master.after_cancel(self.notification_timer)
        color = self.COLOR_SUCCESS if is_connected else self.COLOR_DANGER
        if self.notification_window and self.notification_window.winfo_exists():
            self.notification_window.winfo_children()[0].config(text=message, bg=color)
            self.notification_window.config(bg=color)
        else:
            self.notification_window = tk.Toplevel(self.master)
            self.notification_window.overrideredirect(True)
            self.notification_window.attributes("-topmost", True)
            self.notification_window.config(bg=color)
            tk.Label(self.notification_window, text=message, fg="white", bg=color, font=('Segoe UI', 10), justify='left', padx=20, pady=10).pack()
            self.notification_window.update_idletasks()
            x = self.master.winfo_screenwidth() - self.notification_window.winfo_width() - 20
            y = self.master.winfo_screenheight() - self.notification_window.winfo_height() - 60
            self.notification_window.geometry(f'+{x}+{y}')
        self.notification_timer = self.master.after(3000, self.hide_notification)

    def hide_notification(self):
        if self.notification_window and self.notification_window.winfo_exists():
            self.notification_window.destroy()
        self.notification_window = None; self.notification_timer = None

    def create_widgets(self):
        import tkinter as tk
        from tkinter import ttk, scrolledtext

        self.master.grid_rowconfigure(2, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        header_frame = tk.Frame(self.master, bg=self.COLOR_BG)
        header_frame.grid(row=0, column=0, sticky='ew', padx=20, pady=(15, 5))
        tk.Label(header_frame, text="HHT Android Connect", font=('Segoe UI', 16, 'bold'), bg=self.COLOR_BG, fg=self.COLOR_TEXT).pack(side='left')
        
        tab_container = tk.Frame(self.master, bg=self.COLOR_BG)
        tab_container.grid(row=1, column=0, sticky='ew', padx=20)
        self.device_tab_btn = ttk.Button(tab_container, text="Device Status", style='Tab.TButton', command=lambda: self.switch_tab('device'))
        self.device_tab_btn.pack(side='left')
        self.api_tab_btn = ttk.Button(tab_container, text="API Log", style='Tab.TButton', command=lambda: self.switch_tab('api'))
        self.api_tab_btn.pack(side='left', padx=1)
        self.zip_tab_btn = ttk.Button(tab_container, text="Zip Monitor", style='Tab.TButton', command=lambda: self.switch_tab('zip'))
        self.zip_tab_btn.pack(side='left', padx=1)
        self.apk_tab_btn = ttk.Button(tab_container, text="APK Monitor", style='Tab.TButton', command=lambda: self.switch_tab('apk'))
        self.apk_tab_btn.pack(side='left', padx=1)
        
        shadow_dark = tk.Frame(self.master, bg=self.COLOR_SHADOW_DARK)
        shadow_dark.grid(row=2, column=0, sticky='nsew', padx=(22, 18), pady=(0, 18))
        shadow_light = tk.Frame(shadow_dark, bg=self.COLOR_SHADOW_LIGHT)
        shadow_light.pack(fill='both', expand=True, padx=(2, 0), pady=(2, 0))
        self.content_frame = tk.Frame(shadow_light, bg=self.COLOR_BG, padx=15, pady=15)
        self.content_frame.pack(fill='both', expand=True, padx=(0, 2), pady=(0, 2))
        self.content_frame.grid_rowconfigure(0, weight=1); self.content_frame.grid_columnconfigure(0, weight=1)
        
        # Frame 1: Device
        self.device_frame = tk.Frame(self.content_frame, bg=self.COLOR_BG)
        self.device_frame.grid(row=0, column=0, sticky='nsew')
        self.device_frame.grid_rowconfigure(0, weight=1); self.device_frame.grid_columnconfigure(0, weight=1)
        self.device_tree = ttk.Treeview(self.device_frame, columns=('device_id', 'status'), show='headings')
        self.device_tree.heading('device_id', text='DEVICE ID', anchor='w'); self.device_tree.column('device_id', width=250)
        self.device_tree.heading('status', text='STATUS', anchor='w'); self.device_tree.column('status', anchor='center', width=100)
        self.device_tree.grid(row=0, column=0, sticky='nsew', pady=(0, 10))
        self.device_tree.tag_configure('connected', foreground=self.COLOR_SUCCESS, font=('Segoe UI', 9, 'bold'))
        self.device_tree.tag_configure('disconnected', foreground=self.COLOR_TEXT)
        bf = tk.Frame(self.device_frame, bg=self.COLOR_BG); bf.grid(row=1, column=0, sticky='ew')
        self.refresh_button = self.create_neumorphic_button(bf, text="Refresh", command=self.refresh_devices)
        self.refresh_button.pack(side='left', padx=(0, 10))
        self.disconnect_button = self.create_neumorphic_button(bf, text="Disconnect", command=self.disconnect_device)
        self.disconnect_button.pack(side='left'); self.disconnect_button.config(state='disabled')
        self.connect_button = self.create_neumorphic_button(bf, text="Connect", command=self.connect_device, is_accent=True)
        self.connect_button.pack(side='right')

        # Frame 2: API
        self.api_frame = tk.Frame(self.content_frame, bg=self.COLOR_BG)
        self.api_frame.grid(row=0, column=0, sticky='nsew')
        self.api_frame.grid_rowconfigure(1, weight=1); self.api_frame.grid_columnconfigure(0, weight=1)
        ah = tk.Frame(self.api_frame, bg=self.COLOR_BG); ah.grid(row=0, column=0, sticky='ew', pady=(0, 10)); ah.grid_columnconfigure(1, weight=1)
        self.api_status_dot = tk.Canvas(ah, width=10, height=10, bg=self.COLOR_BG, highlightthickness=0); self.api_status_dot.grid(row=0, column=0, sticky='w', pady=4)
        self.api_status_label = tk.Label(ah, text="API Status:", font=('Segoe UI', 9), bg=self.COLOR_BG, fg=self.COLOR_TEXT); self.api_status_label.grid(row=0, column=1, sticky='w', padx=5)
        self.search_entry = self.create_neumorphic_entry(ah); self.search_entry.grid(row=0, column=2, sticky='e', padx=(0, 5))
        ttk.Button(ah, text="Search", style='Raised.TButton', command=self.search_api_logs).grid(row=0, column=3, sticky='e', padx=(0, 5))
        self.refresh_api_button = ttk.Button(ah, text="Restart API", style='Raised.TButton', command=self.refresh_api_exe); self.refresh_api_button.grid(row=0, column=4, sticky='e', padx=(0,5))
        lf = tk.Frame(self.api_frame, bg=self.COLOR_SHADOW_DARK, bd=0); lf.grid(row=1, column=0, sticky='nsew')
        self.api_log_text = scrolledtext.ScrolledText(lf, wrap=tk.WORD, state='disabled', bg=self.COLOR_BG, fg=self.COLOR_TEXT, font=('Consolas', 8), relief='flat', bd=2, highlightthickness=0)
        self.api_log_text.pack(fill='both', expand=True, padx=2, pady=2)
        self.api_log_text.tag_config('search', background=self.COLOR_ACCENT, foreground='white')
        self.api_log_text.tag_config('current_search', background=self.COLOR_WARNING, foreground='black')

        # Frame 3: Zip
        self.zip_frame = tk.Frame(self.content_frame, bg=self.COLOR_BG)
        self.zip_frame.grid(row=0, column=0, sticky='nsew')
        self.zip_frame.grid_rowconfigure(1, weight=1); self.zip_frame.grid_columnconfigure(0, weight=1)
        zh = tk.Frame(self.zip_frame, bg=self.COLOR_BG); zh.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.zip_count_label = tk.Label(zh, text="Total Files Processed: 0", font=('Segoe UI', 9, 'bold'), bg=self.COLOR_BG, fg=self.COLOR_TEXT); self.zip_count_label.pack(side='left')
        self.zip_tree = ttk.Treeview(self.zip_frame, columns=('filename', 'status'), show='headings')
        self.zip_tree.heading('filename', text='FILENAME', anchor='w'); self.zip_tree.column('filename', width=350)
        self.zip_tree.heading('status', text='STATUS', anchor='w'); self.zip_tree.column('status', width=100)
        self.zip_tree.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        self.zip_tree.tag_configure('pending', foreground=self.COLOR_TEXT)
        self.zip_tree.tag_configure('processing', foreground=self.COLOR_WARNING, font=('Segoe UI', 9, 'bold'))
        self.zip_tree.tag_configure('done', foreground=self.COLOR_SUCCESS, font=('Segoe UI', 9, 'bold'))
        self.zip_tree.tag_configure('error', foreground=self.COLOR_DANGER, font=('Segoe UI', 9, 'bold'))
        
        # Frame 4: APK
        self.apk_frame = tk.Frame(self.content_frame, bg=self.COLOR_BG)
        self.apk_frame.grid(row=0, column=0, sticky='nsew')
        self.apk_frame.grid_rowconfigure(1, weight=1); self.apk_frame.grid_columnconfigure(0, weight=1)
        ah = tk.Frame(self.apk_frame, bg=self.COLOR_BG); ah.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.apk_count_label = tk.Label(ah, text="Total APKs Processed: 0", font=('Segoe UI', 9, 'bold'), bg=self.COLOR_BG, fg=self.COLOR_TEXT); self.apk_count_label.pack(side='left')
        self.apk_tree = ttk.Treeview(self.apk_frame, columns=('filename', 'status'), show='headings')
        self.apk_tree.heading('filename', text='FILENAME', anchor='w'); self.apk_tree.column('filename', width=350)
        self.apk_tree.heading('status', text='STATUS', anchor='w'); self.apk_tree.column('status', width=100)
        self.apk_tree.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        self.apk_tree.tag_configure('pending', foreground=self.COLOR_TEXT)
        self.apk_tree.tag_configure('processing', foreground=self.COLOR_WARNING, font=('Segoe UI', 9, 'bold'))
        self.apk_tree.tag_configure('done', foreground=self.COLOR_SUCCESS, font=('Segoe UI', 9, 'bold'))
        self.apk_tree.tag_configure('error', foreground=self.COLOR_DANGER, font=('Segoe UI', 9, 'bold'))
        self.apk_tree.tag_configure('skipped', foreground=self.COLOR_TEXT, font=('Segoe UI', 9, 'italic'))

        self.switch_tab('device')

    def _setup_log_file(self):
        try:
            self.log_dir = os.path.join(self.base_path, "log"); os.makedirs(self.log_dir, exist_ok=True)
            self._cleanup_old_logs()
            self.current_log_date = time.strftime("%Y-%m-%d")
            filename = f"api_log_{self.current_log_date}.txt"
            self.log_filepath = os.path.join(self.log_dir, filename)
            self._load_log_for_today()
        except Exception: pass

    def _cleanup_old_logs(self):
        if not self.log_dir: return
        try:
            cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
            for f in os.listdir(self.log_dir):
                if f.startswith("api_log_") and f.endswith(".txt"):
                    try:
                        d = datetime.datetime.strptime(f.replace("api_log_", "").replace(".txt", ""), "%Y-%m-%d")
                        if d < cutoff: os.remove(os.path.join(self.log_dir, f))
                    except: pass
        except: pass
            
    def _load_log_for_today(self):
        if self.log_filepath and os.path.exists(self.log_filepath):
            try:
                with open(self.log_filepath, 'r', encoding='utf-8') as f: c = f.read()
                if c:
                    self.api_log_text.config(state='normal')
                    self.api_log_text.insert('1.0', c)
                    self.api_log_text.see('end')
                    self.api_log_text.config(state='disabled')
            except: pass

    def _auto_save_log(self):
        if not self.log_filepath: return
        try:
            c = self.api_log_text.get("1.0", "end-1c")
            td = time.strftime("%Y-%m-%d")
            if td != self.current_log_date:
                if c.strip():
                    fc = self._format_sql_log(c)
                    with open(self.log_filepath, 'w', encoding='utf-8') as f: f.write(fc)
                self.current_log_date = td
                self.log_filepath = os.path.join(self.log_dir, f"api_log_{td}.txt")
                self.api_log_text.config(state='normal'); self.api_log_text.delete('1.0', 'end'); self.api_log_text.config(state='disabled')
            else:
                if c.strip():
                    fc = self._format_sql_log(c)
                    with open(self.log_filepath, 'w', encoding='utf-8') as f: f.write(fc)
        except: pass

    def _periodic_log_save(self):
        if self.is_running: self._auto_save_log(); self.master.after(30000, self._periodic_log_save)

    def _format_sql_log(self, raw): return raw # Kept simple as per backup

    def create_neumorphic_button(self, parent, text, command, is_accent=False):
        import tkinter as tk
        fg = 'white' if is_accent else self.COLOR_TEXT; bg = self.COLOR_ACCENT if is_accent else self.COLOR_BG
        return tk.Button(parent, text=text, command=command, font=('Segoe UI', 9, 'bold'), bg=bg, fg=fg, activebackground=self.COLOR_SHADOW_DARK if not is_accent else self.COLOR_ACCENT, activeforeground=self.COLOR_SHADOW_LIGHT if not is_accent else 'white', relief='flat', bd=0, highlightthickness=1, highlightbackground=self.COLOR_SHADOW_DARK, padx=10, pady=4)

    def create_neumorphic_entry(self, parent):
        import tkinter as tk
        from tkinter import ttk
        f = tk.Frame(parent, bg=self.COLOR_SHADOW_DARK, padx=2, pady=2)
        ttk.Entry(f, font=('Segoe UI', 9), style='TEntry', width=18).pack()
        return f

    def switch_tab(self, tab_name):
        self.device_tab_btn.state(['!selected']); self.api_tab_btn.state(['!selected'])
        self.zip_tab_btn.state(['!selected']); self.apk_tab_btn.state(['!selected'])
        self.device_frame.grid_remove(); self.api_frame.grid_remove()
        self.zip_frame.grid_remove(); self.apk_frame.grid_remove()
        if tab_name == 'device': self.device_frame.grid(); self.device_tab_btn.state(['selected'])
        elif tab_name == 'api': self.api_frame.grid(); self.api_tab_btn.state(['selected'])
        elif tab_name == 'zip': self.zip_frame.grid(); self.zip_tab_btn.state(['selected'])
        elif tab_name == 'apk': self.apk_frame.grid(); self.apk_tab_btn.state(['selected'])

    def set_api_status(self, status):
        self.api_status = status
        if status == "Online": self.api_status_dot.config(bg=self.COLOR_SUCCESS); self.api_status_label.config(text="API Status: Online", fg=self.COLOR_SUCCESS)
        else: self.api_status_dot.config(bg=self.COLOR_DANGER); self.api_status_label.config(text="API Status: Offline", fg=self.COLOR_DANGER)
        self.update_tray_status()

    def search_api_logs(self):
        import tkinter as tk
        term = self.search_entry.winfo_children()[0].get()
        self.api_log_text.config(state='normal')
        if term != self.last_search_term:
            self.last_search_term = term; self.last_search_pos = "1.0"
            self.api_log_text.tag_remove('search', '1.0', tk.END); self.api_log_text.tag_remove('current_search', '1.0', tk.END)
        if term:
            start = self.api_log_text.search(term, self.last_search_pos, stopindex=tk.END, nocase=True)
            if not start: self.last_search_pos = "1.0"; self.api_log_text.tag_remove('current_search', '1.0', tk.END); start = self.api_log_text.search(term, self.last_search_pos, stopindex=tk.END, nocase=True)
            if start:
                end = f"{start}+{len(term)}c"
                self.api_log_text.tag_add('search', start, end); self.api_log_text.tag_remove('current_search', '1.0', tk.END); self.api_log_text.tag_add('current_search', start, end); self.api_log_text.see(start); self.last_search_pos = end
        self.api_log_text.config(state='disabled')

    def start_api_exe(self):
        self.api_log_queue = queue.Queue()
        p = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "api.exe")
        if not os.path.exists(p): self.log_to_api_tab("Error: api.exe not found."); self.set_api_status("Offline"); return
        try:
            self.api_process = subprocess.Popen([p], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8', errors='replace')
            threading.Thread(target=self.read_api_output, daemon=True).start()
            self.master.after(100, self.process_api_log_queue)
        except Exception as e: self.log_to_api_tab(f"Failed to start api: {e}"); self.set_api_status("Offline")

    def refresh_api_exe(self):
        if self.api_process: self.api_process.terminate(); self.api_process = None
        self.api_log_text.config(state='normal'); self.api_log_text.delete('1.0', 'end'); self.api_log_text.config(state='disabled'); self.set_api_status("Offline"); self.start_api_exe()

    def read_api_output(self):
        for line in iter(self.api_process.stdout.readline, ''): self.api_log_queue.put(line)
        self.api_process.stdout.close(); self.master.after(0, self.set_api_status, "Offline")

    def process_api_log_queue(self):
        import tkinter as tk
        try:
            while True: self.log_to_api_tab(self.api_log_queue.get_nowait())
        except queue.Empty: pass
        finally:
            if self.is_running: self.master.after(100, self.process_api_log_queue)

    def log_to_api_tab(self, msg):
        import tkinter as tk
        self.api_log_text.config(state='normal'); self.api_log_text.insert(tk.END, msg); self.api_log_text.see(tk.END); self.api_log_text.config(state='disabled')
        if "fiber" in msg.lower() and self.api_status != "Online": self.set_api_status("Online")

    def hide_window(self): self.master.withdraw()
    def show_window(self, icon=None, item=None): self.master.deiconify(); self.master.lift(); self.master.focus_force()

    def update_tray_status(self):
        if not self.tray_icon: return
        ds = f"Device: {self.connected_device}" if self.connected_device else "Device: Disconnected"
        as_ = f"API: {self.api_status}"
        self.tray_icon.title = f"HHT Connect: {'Connected' if self.connected_device else 'Disconnected'}"
        if self.connected_device: self.tray_icon.icon = create_android_icon(self.COLOR_SUCCESS)
        else: self.tray_icon.icon = create_android_icon(self.COLOR_TEXT)

    def device_monitor_loop(self):
        while self.is_running:
            try:
                res = subprocess.run([self.ADB_PATH, "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                curr = set(self.parse_device_list(res.stdout))
                if self.connected_device and self.connected_device not in curr:
                    if not self.is_disconnecting: self.is_disconnecting = True; self.master.after(0, self.handle_auto_disconnect)
                if not self.connected_device:
                    new = curr - self.known_devices
                    if new: threading.Thread(target=self._connect_device, args=(new.pop(),), daemon=True).start()
                self.known_devices = curr
            except: pass
            time.sleep(3)

    def handle_auto_disconnect(self):
        did = self.connected_device; self.connected_device = None; self.disconnect_button.config(state='disabled')
        self.refresh_devices(); self.update_tray_status(); self.is_disconnecting = False
        self.show_notification(f"Disconnected:\n{did}", False); self.master.after(0, self._clear_apk_monitor)
        
    def _update_device_tree(self, devs):
        import tkinter as tk
        for i in self.device_tree.get_children(): self.device_tree.delete(i)
        if devs:
            for d in sorted(list(devs)):
                s = "Connected" if d == self.connected_device else "Available"
                self.device_tree.insert('', tk.END, values=(d, s), tags=('connected' if s == "Connected" else 'disconnected',))
        else: self.device_tree.insert('', tk.END, values=('No devices found.', ''), tags=())

    def _refresh_devices(self):
        try:
            res = subprocess.run([self.ADB_PATH, "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            devs = self.parse_device_list(res.stdout); all_ = set(devs)
            if self.connected_device: all_.add(self.connected_device)
            self.master.after(0, self._update_device_tree, all_)
        except: pass
        finally: self.master.after(0, self.refresh_button.config, {'state': 'normal'})

    def _connect_device(self, did):
        from tkinter import messagebox
        try:
            res = subprocess.run([self.ADB_PATH, "-s", did, "reverse", "tcp:8000", "tcp:8000"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if self.connected_device is None and res.returncode == 0:
                self.connected_device = did; self.is_disconnecting = False
                self.master.after(0, self.show_notification, f"Connected:\n{did}", True)
                self.master.after(0, self.disconnect_button.config, {'state': 'normal'})
                self.master.after(0, self.refresh_devices); self.master.after(0, self.update_tray_status)
                self.master.after(0, self._clear_apk_monitor); self.master.after(100, self._scan_existing_apk_files)
            elif res.returncode != 0: self.master.after(0, lambda: messagebox.showerror("Error", f"Failed:\n{res.stderr}"))
        except: pass
        finally: self.master.after(0, self.connect_button.config, {'state': 'normal'})

    def _disconnect_device(self):
        if not self.connected_device: return
        try:
            res = subprocess.run([self.ADB_PATH, "-s", self.connected_device, "reverse", "--remove", "tcp:8000"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if res.returncode == 0:
                did = self.connected_device; self.connected_device = None; self.disconnect_button.config(state='disabled')
                self.refresh_devices(); self.update_tray_status(); self.show_notification(f"Disconnected:\n{did}", False); self._clear_apk_monitor()
        except: pass
        finally: self.disconnect_button.config(state='normal')

    def get_adb_path(self):
        if getattr(sys, 'frozen', False): b = sys._MEIPASS
        else: b = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(b, "adb", "adb.exe"); return p if os.path.exists(p) else "adb"

    def check_adb(self):
        try: subprocess.run([self.ADB_PATH, "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW); return True
        except: return False

    def start_adb_server(self):
        try: subprocess.run([self.ADB_PATH, "start-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        except: pass

    def refresh_devices(self): self.refresh_button.config(state='normal'); threading.Thread(target=self._refresh_devices, daemon=True).start()

    def parse_device_list(self, out):
        d = []
        for l in out.strip().split('\n')[1:]:
            if l.strip():
                p = l.split('\t')
                if len(p) >= 2 and p[1] == 'device': d.append(p[0])
        return d

    def connect_device(self):
        from tkinter import messagebox
        s = self.device_tree.focus()
        if not s: messagebox.showwarning("Select", "Select a device"); return
        d = self.device_tree.item(s)['values'][0]
        if self.connected_device: messagebox.showwarning("Warn", "Disconnect first"); return
        threading.Thread(target=self._connect_device, args=(d,), daemon=True).start()

    def disconnect_device(self): threading.Thread(target=self._disconnect_device, daemon=True).start()

    # --- Config ---
    def _load_configs(self):
        from tkinter import messagebox
        p = os.path.join(self.base_path, "configs", "config.ini")
        c = configparser.ConfigParser()
        if not os.path.exists(p): messagebox.showerror("Error", "Config not found"); return False
        try:
            c.read(p)
            self.zip_monitor_path = c['SETTING']['DEFAULT_PRICE_TAG_PATH']
            self.apk_monitor_path = c['APK_INSTALLER']['MONITOR_PATH']
            
            # --- [FIX 2] Read Prefix ---
            try:
                self.zip_filename_prefix = c['SETTING']['ZIP_FILENAME_PREFIX']
                print(f"Zip Prefix Filter: '{self.zip_filename_prefix}'")
            except KeyError:
                self.zip_filename_prefix = "" # Default to ALL files if not set
            # ---------------------------

            return True
        except: return False

    def _start_monitoring_services(self):
        if self._load_configs():
            if self.zip_monitor_path and os.path.exists(self.zip_monitor_path):
                self.zip_file_observer = Observer()
                self.zip_file_observer.schedule(ZipFileHandler(self), self.zip_monitor_path, recursive=False)
                self.zip_file_observer.start()
            if self.apk_monitor_path and os.path.exists(self.apk_monitor_path):
                self.apk_file_observer = Observer()
                self.apk_file_observer.schedule(ApkFileHandler(self), self.apk_monitor_path, recursive=False)
                self.apk_file_observer.start()

    def _scan_existing_apk_files(self):
        if not self.apk_monitor_path or not os.path.exists(self.apk_monitor_path): return
        try:
            for f in os.listdir(self.apk_monitor_path):
                if f.endswith(".apk"):
                    fp = os.path.join(self.apk_monitor_path, f)
                    if fp not in self.apk_file_map and fp not in self.apk_processing_files: self._add_apk_to_monitor(fp)
        except: pass

    # --- Zip Logic (Fixed) ---
    def _add_zip_to_monitor(self, fp):
        import tkinter as tk
        if fp in self.processing_files: return
        self.processing_files.add(fp)
        iid = self.zip_tree.insert('', tk.END, values=(os.path.basename(fp), 'Pending'), tags=('pending',))
        self.zip_file_map[fp] = iid
        threading.Thread(target=self.process_zip_file, args=(fp,), daemon=True).start()

    def _update_zip_status(self, iid, s):
        try:
            fn = self.zip_tree.item(iid, 'values')[0]
            tag = 'error'
            if s == "Done": tag = 'done'; self.zip_processed_count += 1; self.zip_count_label.config(text=f"Total Files Processed: {self.zip_processed_count}")
            elif s == "Processing": tag = 'processing'
            self.zip_tree.item(iid, values=(fn, s), tags=(tag,))
        except: pass

    def _remove_from_processing_list(self, fp):
        if fp in self.processing_files: self.processing_files.remove(fp)

    def process_zip_file(self, zip_path):
        iid = self.zip_file_map.get(zip_path)
        if not iid: return
        self.master.after(0, self._update_zip_status, iid, "Processing")
        
        # --- [FIX 1] Robust Retry Logic (Wait for file to be ready) ---
        # วนลูปรอสูงสุด 20 วินาที (20 x 1s) เพื่อให้แน่ใจว่าไฟล์เขียนเสร็จ
        for i in range(20): 
            try:
                # ลองเปิดไฟล์แบบ Read ถ้าเปิดได้แสดงว่าไฟล์ไม่ถูก Lock และมีอยู่จริง
                with open(zip_path, 'rb'): pass 
                time.sleep(1) # รออีกนิดเพื่อความชัวร์ (Network latency)
                break 
            except: 
                # ถ้า Error (PermissionDenied/FileNotFound) ให้รอ 1 วินาทีแล้วลองใหม่
                time.sleep(1) 
        else: 
            # ถ้าครบ 20 รอบแล้วยังเปิดไม่ได้
            print(f"Timeout: File {zip_path} is locked or incomplete.")
            self.master.after(0, self._update_zip_status, iid, "Error: Locked")
            self.master.after(0, self._remove_from_processing_list, zip_path)
            return
        # -----------------------------------------------------------

        tmp = os.path.join(self.base_path, "tmp", f"extract_{os.path.basename(zip_path)}")
        orig = os.path.basename(zip_path)
        d = os.path.dirname(zip_path)
        
        try:
            parts = orig.replace('.zip', '').split('-')
            new_zp = zip_path
            
            if len(parts) == 5:
                # Rename Logic
                new_name = f"{parts[0]}-{parts[1]}-{parts[2]}-{parts[3]}-{time.strftime('%y%m%d')}-{parts[4]}.zip"
                new_zp = os.path.join(d, new_name)
            
            os.makedirs(tmp, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as z: z.extractall(tmp)
            os.remove(zip_path)

            with zipfile.ZipFile(new_zp, 'w', zipfile.ZIP_DEFLATED) as z:
                for root, dirs, files in os.walk(tmp):
                    for dr in dirs:
                        p = os.path.join(root, dr); arc = os.path.relpath(p, tmp).replace(os.sep, '/') + '/'
                        zi = zipfile.ZipInfo(arc); zi.create_system = 3; zi.external_attr = (0o755 << 16) | 0x10
                        z.writestr(zi, "")
                    for f in files:
                        p = os.path.join(root, f); arc = os.path.relpath(p, tmp).replace(os.sep, '/')
                        zi = zipfile.ZipInfo.from_file(p, arc); zi.create_system = 3; zi.external_attr = (0o644 << 16)
                        with open(p, "rb") as src: z.writestr(zi, src.read())
            
            self.master.after(0, self._update_zip_status, iid, "Done")

        except Exception as e:
            print(f"Zip Process Error: {e}")
            self.master.after(0, self._update_zip_status, iid, "Error")
        
        finally:
            if os.path.exists(tmp): shutil.rmtree(tmp)
            self.master.after(0, self._remove_from_processing_list, zip_path)

    # --- APK Logic ---
    def _clear_apk_monitor(self):
        try:
            for i in self.apk_tree.get_children(): self.apk_tree.delete(i)
        except: pass
        self.apk_processed_count = 0; self.apk_file_map.clear(); self.apk_processing_files.clear()
        try: self.apk_count_label.config(text="Total APKs Processed: 0")
        except: pass

    def _add_apk_to_monitor(self, fp):
        import tkinter as tk
        fn = os.path.basename(fp)
        if fp in self.apk_file_map: return
        self.apk_processing_files.add(fp)
        iid = self.apk_tree.insert('', tk.END, values=(fn, 'Pending'), tags=('pending',))
        self.apk_file_map[fp] = iid
        threading.Thread(target=self._run_apk_install, args=(fp, iid), daemon=True).start()

    def _get_device_version(self, pkg):
        if not self.connected_device: return 0
        try:
            res = subprocess.run([self.ADB_PATH, "-s", self.connected_device, "shell", "dumpsys", "package", pkg], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            for l in res.stdout.splitlines():
                if "versionCode=" in l: return int(l.strip().split('versionCode=')[1].split(' ')[0])
            return 0
        except: return 0

    def _run_apk_install(self, fp, iid):
        self.master.after(0, self._update_apk_status, iid, "Checking...")
        for _ in range(5):
            try:
                with open(fp, 'rb'): pass; break
            except: time.sleep(1)
        else: self.master.after(0, self._update_apk_status, iid, "Error: File locked"); return

        try: apk = APK(fp); pkg = apk.package; ver = int(apk.version_code)
        except: self.master.after(0, self._update_apk_status, iid, "Error: Invalid APK"); return
            
        w = 0
        while not self.connected_device and self.is_running and w < 10: self.master.after(0, self._update_apk_status, iid, "Waiting..."); time.sleep(1); w+=1
        if not self.connected_device: self.master.after(0, self._update_apk_status, iid, "Error: No device"); return
            
        dv = self._get_device_version(pkg)
        msg = ""
        if dv == 0: msg = "Installing..."
        elif ver > dv: msg = "Upgrading..."
        else: self.master.after(0, self._update_apk_status, iid, f"Skipped (v{dv})"); return
                
        self.master.after(0, self._update_apk_status, iid, msg)
        try:
            res = subprocess.run([self.ADB_PATH, "-s", self.connected_device, "install", "-r", fp], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if "Success" in res.stdout: self.master.after(0, self._update_apk_status, iid, "Success")
            else: self.master.after(0, self._update_apk_status, iid, "Error: Install Fail")
        except Exception as e: self.master.after(0, self._update_apk_status, iid, f"Error: {e}")
        finally: self.master.after(0, self._remove_from_apk_processing_list, fp)
            
    def _update_apk_status(self, iid, msg):
        try:
            if not self.apk_tree.exists(iid): return
            fn = self.apk_tree.item(iid, 'values')[0]
            tag = 'error'
            if "Success" in msg: tag='done'; self.apk_processed_count+=1; self.apk_count_label.config(text=f"Total APKs Processed: {self.apk_processed_count}")
            elif "Skipped" in msg: tag='skipped'
            elif "Installing" in msg or "Upgrading" in msg or "Waiting" in msg: tag='processing'
            self.apk_tree.item(iid, values=(fn, msg), tags=(tag,))
        except: pass
            
    def _remove_from_apk_processing_list(self, fp):
        if fp in self.apk_processing_files: self.apk_processing_files.remove(fp)

    def on_app_quit(self):
        self.is_running = False; self._auto_save_log()
        if self.tray_icon: self.tray_icon.stop()
        if self.api_process: self.api_process.terminate()
        if self.connected_device:
            try: subprocess.run([self.ADB_PATH, "-s", self.connected_device, "reverse", "--remove", "tcp:8000"], creationflags=subprocess.CREATE_NO_WINDOW)
            except: pass
        try: os.remove(self.lock_file_path)
        except: pass
        self.master.destroy()

if __name__ == "__main__":
    import tkinter as tk
    from tkinter import messagebox
    from PIL import Image
    import pystray
    import ctypes
    import psutil

    td = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp')
    lf = os.path.join(td, 'hht_android_connect.lock')
    if os.path.exists(lf):
        try:
            with open(lf, 'r') as f: pid = int(f.read().strip())
            if psutil.pid_exists(pid): messagebox.showinfo("Running", "App already running."); sys.exit()
        except: pass
    with open(lf, 'w') as f: f.write(str(os.getpid()))

    def is_admin():
        try: return ctypes.windll.shell32.IsUserAnAdmin()
        except: return False

    if is_admin():
        try:
            root = tk.Tk()
            app = App(root, lock_file_path=lf) 
            root.protocol('WM_DELETE_WINDOW', app.hide_window)
            m = pystray.Menu(pystray.MenuItem('Show', app.show_window, default=True), pystray.MenuItem('Quit', app.on_app_quit))
            icon = pystray.Icon("HHT", app.icon_image, "HHT Connect", m)
            app.tray_icon = icon
            threading.Thread(target=icon.run, daemon=True).start()
            root.mainloop()
        except Exception as e:
            if os.path.exists(lf): os.remove(lf)
            messagebox.showerror("Error", f"{e}")
    else:
        if os.path.exists(lf): os.remove(lf)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)

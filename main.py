# This code has been verified to have correct indentation.
# VERSION: 1.0.5 (Final Robust: Safe Zone Processing + Compact UI + Filter)
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
import ctypes
from ctypes import wintypes
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from tkinter import filedialog, messagebox
from pyaxmlparser import APK

# --- Image Generation for UI ---
def create_android_icon(color):
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
            
            # --- FEATURE: Prefix Filter ---
            # ถ้า Config ระบุ Prefix ไว้ แล้วไฟล์ไม่ตรงเงื่อนไข -> ข้ามทันที
            if self.app.zip_filename_prefix and not filename.startswith(self.app.zip_filename_prefix):
                return
            # ------------------------------

            if event.src_path in self.app.processing_files: return
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
            self.app.master.after(0, self.app._add_apk_to_monitor, event.src_path)
    def on_created(self, event): self.process_event(event)
    def on_modified(self, event): self.process_event(event)

class App:
    
    APP_VERSION = "1.0.5" 

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
        
        # Configs & Paths
        self.log_filepath = None
        self.log_dir = None
        self.current_log_date = None
        self.zip_monitor_path = None
        self.zip_filename_prefix = "" # Loaded from config
        self.apk_monitor_path = None
        
        self.zip_file_observer = None
        self.apk_file_observer = None
        
        self.zip_processed_count = 0
        self.zip_file_map = {}
        self.processing_files = set()
        
        self.apk_processed_count = 0
        self.apk_file_map = {}
        self.apk_processing_files = set()
        
        # Stream Variables
        self.scrcpy_process = None
        self.stream_window_id = None
        self._source_aspect = None  
        self._stream_resize_bind_id = None
        self.current_tab = "device"
        
        if getattr(sys, 'frozen', False):
            self.base_path = os.path.dirname(sys.executable)
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))

        master.title(f"HHT Connect - v{self.APP_VERSION}")

        # --- UI: Compact Size ---
        app_width = 600  
        app_height = 520 
        screen_width = master.winfo_screenwidth()
        screen_height = master.winfo_screenheight()
        x_pos = screen_width - app_width - 20
        y_pos = screen_height - app_height - 80
        master.geometry(f"{app_width}x{app_height}+{x_pos}+{y_pos}")
        master.resizable(False, False)

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
        self.COLOR_SIDEBAR_BG = "#3D4450"
        self.COLOR_SIDEBAR_BTN_INACTIVE = "#3D4450"
        self.COLOR_SIDEBAR_BTN_ACTIVE = "#E0E5EC"
        self.COLOR_SIDEBAR_TEXT_INACTIVE = "#C8D0DA"
        self.COLOR_SIDEBAR_TEXT_ACTIVE = "#3D4450"

        master.configure(background=self.COLOR_BG)
        self.icon_image = create_android_icon(self.COLOR_TEXT)
        master.iconphoto(True, ImageTk.PhotoImage(self.icon_image))

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('.', font=('Segoe UI', 9), background=self.COLOR_BG, foreground=self.COLOR_TEXT, borderwidth=0)
        self.style.configure('TFrame', background=self.COLOR_BG)
        # Compact Treeview Row
        self.style.configure('Treeview', background=self.COLOR_BG, fieldbackground=self.COLOR_BG, foreground=self.COLOR_TEXT, rowheight=26, font=('Consolas', 10))
        self.style.map('Treeview', background=[('selected', self.COLOR_SHADOW_DARK)], foreground=[('selected', self.COLOR_SHADOW_LIGHT)])
        self.style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'), background=self.COLOR_BG, relief='flat')
        self.style.map('Treeview.Heading', background=[('active', self.COLOR_BG)])
        self.style.configure('TEntry', fieldbackground=self.COLOR_BG, foreground=self.COLOR_TEXT, insertcolor=self.COLOR_TEXT, relief='flat', borderwidth=0)
        self.style.configure('Raised.TButton', font=('Segoe UI', 9, 'bold'), padding=(10, 5), relief='raised', background=self.COLOR_3D_BG_ACTIVE, foreground='white', borderwidth=2)
        self.style.map('Raised.TButton', background=[('active', self.COLOR_SHADOW_DARK)])

        self.ADB_PATH = self.get_adb_path()
        self.SCRCPY_PATH = self.get_scrcpy_path()
        
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
        
        self.switch_tab('device')

    # ... (Notifications & Helper Methods) ...
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

    def create_side_button(self, parent, text, command):
        import tkinter as tk
        return tk.Button(parent, text=text, command=command, font=('Segoe UI', 10, 'bold'), bg=self.COLOR_SIDEBAR_BTN_INACTIVE, fg=self.COLOR_SIDEBAR_TEXT_INACTIVE, activebackground=self.COLOR_SIDEBAR_BTN_ACTIVE, activeforeground=self.COLOR_SIDEBAR_TEXT_ACTIVE, relief='flat', bd=0, anchor='w', padx=15, pady=12)

    def create_neumorphic_button(self, parent, text, command, is_accent=False):
        import tkinter as tk
        return tk.Button(parent, text=text, command=command, font=('Segoe UI', 9, 'bold'), bg=self.COLOR_ACCENT if is_accent else self.COLOR_BG, fg='white' if is_accent else self.COLOR_TEXT, activebackground=self.COLOR_SHADOW_DARK if not is_accent else self.COLOR_ACCENT, activeforeground=self.COLOR_SHADOW_LIGHT if not is_accent else 'white', relief='flat', bd=0, highlightthickness=1, highlightbackground=self.COLOR_SHADOW_DARK, padx=10, pady=4)

    def create_neumorphic_entry(self, parent):
        import tkinter as tk
        from tkinter import ttk
        f = tk.Frame(parent, bg=self.COLOR_SHADOW_DARK, padx=2, pady=2)
        ttk.Entry(f, font=('Segoe UI', 9), style='TEntry', width=18).pack()
        return f

    def create_widgets(self):
        import tkinter as tk
        from tkinter import ttk, scrolledtext

        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(1, weight=1)
        
        # Sidebar
        sidebar = tk.Frame(self.master, bg=self.COLOR_SIDEBAR_BG, width=170)
        sidebar.grid(row=0, column=0, sticky='nsw')
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="HHT CONNECT", font=('Segoe UI', 14, 'bold'), bg=self.COLOR_SIDEBAR_BG, fg=self.COLOR_BG, anchor='w', padx=15, pady=15).pack(fill='x')
        self.side_btn_device = self.create_side_button(sidebar, "Device Status", lambda: self.switch_tab('device'))
        self.side_btn_device.pack(fill='x')
        self.side_btn_api = self.create_side_button(sidebar, "API Log", lambda: self.switch_tab('api'))
        self.side_btn_api.pack(fill='x')
        self.side_btn_zip = self.create_side_button(sidebar, "Zip Monitor", lambda: self.switch_tab('zip'))
        self.side_btn_zip.pack(fill='x')
        self.side_btn_apk = self.create_side_button(sidebar, "APK Monitor", lambda: self.switch_tab('apk'))
        self.side_btn_apk.pack(fill='x')
        self.side_btn_stream = self.create_side_button(sidebar, "Stream Screen", lambda: self.switch_tab('stream'))
        self.side_btn_stream.pack(fill='x')
        self.all_side_buttons = [self.side_btn_device, self.side_btn_api, self.side_btn_zip, self.side_btn_apk, self.side_btn_stream]

        # Content Area
        self.content_area = tk.Frame(self.master, bg=self.COLOR_BG, width=430)
        self.content_area.grid(row=0, column=1, sticky='nsew')
        pad_cfg = {'padx': 15, 'pady': 15}

        # Device Frame
        self.device_frame = tk.Frame(self.content_area, bg=self.COLOR_BG, **pad_cfg)
        self.device_frame.place(relwidth=1, relheight=1)
        self.device_frame.grid_rowconfigure(0, weight=1)
        self.device_frame.grid_columnconfigure(0, weight=1)
        self.device_tree = ttk.Treeview(self.device_frame, columns=('device_id', 'status'), show='headings')
        self.device_tree.heading('device_id', text='DEVICE ID', anchor='w'); self.device_tree.column('device_id', width=240)
        self.device_tree.heading('status', text='STATUS', anchor='w'); self.device_tree.column('status', anchor='center', width=100)
        self.device_tree.grid(row=0, column=0, sticky='nsew', pady=(0, 10))
        self.device_tree.tag_configure('connected', foreground=self.COLOR_SUCCESS, font=('Segoe UI', 9, 'bold'))
        self.device_tree.tag_configure('disconnected', foreground=self.COLOR_TEXT)
        bf = tk.Frame(self.device_frame, bg=self.COLOR_BG)
        bf.grid(row=1, column=0, sticky='ew')
        self.refresh_button = self.create_neumorphic_button(bf, "Refresh", self.refresh_devices)
        self.refresh_button.pack(side='left', padx=(0, 10))
        self.disconnect_button = self.create_neumorphic_button(bf, "Disconnect", self.disconnect_device)
        self.disconnect_button.pack(side='left')
        self.disconnect_button.config(state='disabled')
        self.connect_button = self.create_neumorphic_button(bf, "Connect", self.connect_device, True)
        self.connect_button.pack(side='right')

        # API Frame
        self.api_frame = tk.Frame(self.content_area, bg=self.COLOR_BG, **pad_cfg)
        self.api_frame.place(relwidth=1, relheight=1)
        self.api_frame.grid_rowconfigure(1, weight=1); self.api_frame.grid_columnconfigure(0, weight=1)
        ah = tk.Frame(self.api_frame, bg=self.COLOR_BG); ah.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        ah.grid_columnconfigure(1, weight=1)
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

        # Zip Frame
        self.zip_frame = tk.Frame(self.content_area, bg=self.COLOR_BG, **pad_cfg)
        self.zip_frame.place(relwidth=1, relheight=1)
        self.zip_frame.grid_rowconfigure(1, weight=1); self.zip_frame.grid_columnconfigure(0, weight=1)
        zh = tk.Frame(self.zip_frame, bg=self.COLOR_BG); zh.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.zip_count_label = tk.Label(zh, text="Total Files Processed: 0", font=('Segoe UI', 9, 'bold'), bg=self.COLOR_BG, fg=self.COLOR_TEXT); self.zip_count_label.pack(side='left')
        self.zip_tree = ttk.Treeview(self.zip_frame, columns=('filename', 'status'), show='headings')
        self.zip_tree.heading('filename', text='FILENAME', anchor='w'); self.zip_tree.column('filename', width=240)
        self.zip_tree.heading('status', text='STATUS', anchor='w'); self.zip_tree.column('status', width=100)
        self.zip_tree.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        self.zip_tree.tag_configure('pending', foreground=self.COLOR_TEXT)
        self.zip_tree.tag_configure('processing', foreground=self.COLOR_WARNING, font=('Segoe UI', 9, 'bold'))
        self.zip_tree.tag_configure('done', foreground=self.COLOR_SUCCESS, font=('Segoe UI', 9, 'bold'))
        self.zip_tree.tag_configure('error', foreground=self.COLOR_DANGER, font=('Segoe UI', 9, 'bold'))

        # APK Frame
        self.apk_frame = tk.Frame(self.content_area, bg=self.COLOR_BG, **pad_cfg)
        self.apk_frame.place(relwidth=1, relheight=1)
        self.apk_frame.grid_rowconfigure(1, weight=1); self.apk_frame.grid_columnconfigure(0, weight=1)
        ah = tk.Frame(self.apk_frame, bg=self.COLOR_BG); ah.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.apk_count_label = tk.Label(ah, text="Total APKs Processed: 0", font=('Segoe UI', 9, 'bold'), bg=self.COLOR_BG, fg=self.COLOR_TEXT); self.apk_count_label.pack(side='left')
        self.apk_tree = ttk.Treeview(self.apk_frame, columns=('filename', 'status'), show='headings')
        self.apk_tree.heading('filename', text='FILENAME', anchor='w'); self.apk_tree.column('filename', width=240)
        self.apk_tree.heading('status', text='STATUS', anchor='w'); self.apk_tree.column('status', width=100)
        self.apk_tree.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        self.apk_tree.tag_configure('pending', foreground=self.COLOR_TEXT)
        self.apk_tree.tag_configure('processing', foreground=self.COLOR_WARNING, font=('Segoe UI', 9, 'bold'))
        self.apk_tree.tag_configure('done', foreground=self.COLOR_SUCCESS, font=('Segoe UI', 9, 'bold'))
        self.apk_tree.tag_configure('error', foreground=self.COLOR_DANGER, font=('Segoe UI', 9, 'bold'))
        self.apk_tree.tag_configure('skipped', foreground=self.COLOR_TEXT, font=('Segoe UI', 9, 'italic'))

        # Stream Frame (Embedded)
        self.stream_frame = tk.Frame(self.content_area, bg=self.COLOR_BG, **pad_cfg)
        self.stream_frame.place(relwidth=1, relheight=1)
        self.stream_frame.grid_rowconfigure(0, weight=0) 
        self.stream_frame.grid_rowconfigure(1, weight=1) 
        self.stream_frame.grid_rowconfigure(2, weight=0) 
        self.stream_frame.grid_columnconfigure(0, weight=1) 
        
        tk.Label(self.stream_frame, text="Device Screen Stream", font=('Segoe UI', 12, 'bold'), bg=self.COLOR_BG, fg=self.COLOR_TEXT).grid(row=0, column=0, pady=(0, 10))
        self.stream_embed_frame = tk.Frame(self.stream_frame, bg=self.COLOR_BG) # Match App BG
        self.stream_embed_frame.grid(row=1, column=0, sticky='nsew', pady=5)
        self.stream_start_btn = ttk.Button(self.stream_frame, text="Start Stream", style='Raised.TButton', command=self._start_stream)
        self.stream_start_btn.grid(row=2, column=0, pady=(5,5))
        self.stream_status_label = tk.Label(self.stream_frame, text="Click 'Start Stream' to begin.", font=('Segoe UI', 9), bg=self.COLOR_BG, fg=self.COLOR_TEXT)
        self.stream_status_label.grid(row=3, column=0, pady=(0, 10))

    def switch_tab(self, tab_name):
        self.current_tab = tab_name
        if tab_name != "stream": self._stop_stream()
        for btn in self.all_side_buttons: btn.config(bg=self.COLOR_SIDEBAR_BTN_INACTIVE, fg=self.COLOR_SIDEBAR_TEXT_INACTIVE)
        if tab_name == 'device': self.device_frame.tkraise(); self.side_btn_device.config(bg=self.COLOR_SIDEBAR_BTN_ACTIVE, fg=self.COLOR_SIDEBAR_TEXT_ACTIVE)
        elif tab_name == 'api': self.api_frame.tkraise(); self.side_btn_api.config(bg=self.COLOR_SIDEBAR_BTN_ACTIVE, fg=self.COLOR_SIDEBAR_TEXT_ACTIVE)
        elif tab_name == 'zip': self.zip_frame.tkraise(); self.side_btn_zip.config(bg=self.COLOR_SIDEBAR_BTN_ACTIVE, fg=self.COLOR_SIDEBAR_TEXT_ACTIVE)
        elif tab_name == 'apk': self.apk_frame.tkraise(); self.side_btn_apk.config(bg=self.COLOR_SIDEBAR_BTN_ACTIVE, fg=self.COLOR_SIDEBAR_TEXT_ACTIVE)
        elif tab_name == 'stream': self.stream_frame.tkraise(); self.side_btn_stream.config(bg=self.COLOR_SIDEBAR_BTN_ACTIVE, fg=self.COLOR_SIDEBAR_TEXT_ACTIVE)

    # --- NEW: Screen Streaming Methods ---
    def _start_stream(self):
        from tkinter import messagebox
        if not self.connected_device:
            self.stream_status_label.config(text="Error: No device connected.")
            return
        if self.scrcpy_process: return
        if not os.path.exists(self.SCRCPY_PATH):
            messagebox.showerror("Stream Error", "scrcpy.exe not found.")
            self.stream_status_label.config(text="Error: scrcpy.exe not found.")
            return

        self.stream_status_label.config(text="Starting stream...")
        self.stream_start_btn.config(state='disabled')
        self.master.update_idletasks()
        
        target_height = self.stream_embed_frame.winfo_height()
        if target_height < 200: target_height = 600 

        env = os.environ.copy(); env['ADB'] = self.ADB_PATH

        self.scrcpy_process = subprocess.Popen([
            self.SCRCPY_PATH, "-s", self.connected_device,
            "--window-title=HHT_STREAM",
            "--window-x=0", "--window-y=0", "--window-borderless"
        ], creationflags=subprocess.CREATE_NO_WINDOW, env=env)

        self.stream_window_id = None
        if self._stream_resize_bind_id:
            try: self.stream_embed_frame.unbind("<Configure>", self._stream_resize_bind_id)
            except: pass
        self._stream_resize_bind_id = self.stream_embed_frame.bind("<Configure>", lambda e: self._resize_stream_to_fit())
        threading.Thread(target=self._embed_stream_window, daemon=True).start()

    def _embed_stream_window(self):
        import ctypes
        try:
            hwnd = 0; retries = 20
            while hwnd == 0 and retries > 0 and self.is_running and self.current_tab == 'stream':
                hwnd = ctypes.windll.user32.FindWindowW(None, "HHT_STREAM")
                if hwnd == 0: retries -= 1; time.sleep(0.5)
            if hwnd == 0: self._stop_stream(); return

            self.stream_window_id = hwnd
            frame_id = self.stream_embed_frame.winfo_id()
            
            # Calculate Aspect Ratio from Original Window
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = max(1, rect.right - rect.left); h = max(1, rect.bottom - rect.top)
            self._source_aspect = w / h
            
            # Embed
            ctypes.windll.user32.SetParent(hwnd, frame_id)
            
            # Initial Resize
            self._resize_stream_to_fit()
            
            if self.is_running:
                self.stream_status_label.config(text=f"Streaming: {self.connected_device}")
                self.stream_start_btn.config(state='normal', text="Stop Stream", command=self._stop_stream)
        except: self._stop_stream()

    def _resize_stream_to_fit(self, event=None):
        import ctypes
        if not self.stream_window_id or not self._source_aspect: return
        self.master.update_idletasks()
        fw = max(1, self.stream_embed_frame.winfo_width())
        fh = max(1, self.stream_embed_frame.winfo_height())
        
        nh = fh
        nw = int(nh * self._source_aspect)
        if nw > fw:
            nw = fw
            nh = int(nw / self._source_aspect)
        
        x = (fw - nw) // 2; y = (fh - nh) // 2
        try: ctypes.windll.user32.MoveWindow(self.stream_window_id, x, y, nw, nh, True)
        except: pass

    def _stop_stream(self):
        if self.scrcpy_process: self.scrcpy_process.terminate(); self.scrcpy_process = None
        if self.is_running:
            try: self.stream_status_label.config(text="Click 'Start Stream' to begin."); self.stream_start_btn.config(state='normal', text="Start Stream", command=self._start_stream)
            except: pass

    # --- Config & Monitoring ---
    def _load_configs(self):
        config_path = os.path.join(self.base_path, "configs", "config.ini")
        config = configparser.ConfigParser()
        if not os.path.exists(config_path): messagebox.showerror("Config Error", "Config not found"); return False
        try:
            config.read(config_path)
            self.zip_monitor_path = config['SETTING']['DEFAULT_PRICE_TAG_PATH']
            self.apk_monitor_path = config['APK_INSTALLER']['MONITOR_PATH']
            
            # --- FEATURE: Prefix ---
            try: self.zip_filename_prefix = config['SETTING']['ZIP_FILENAME_PREFIX']
            except KeyError: self.zip_filename_prefix = ""
            return True
        except: return False

    # ... (Other Methods: Log, ADB, etc. - Standard) ...
    def set_api_status(self, status):
        self.api_status = status
        if status == "Online": self.api_status_dot.config(bg=self.COLOR_SUCCESS); self.api_status_label.config(text="API Status: Online", fg=self.COLOR_SUCCESS)
        else: self.api_status_dot.config(bg=self.COLOR_DANGER); self.api_status_label.config(text="API Status: Offline", fg=self.COLOR_DANGER)
        self.update_tray_status()
    def search_api_logs(self):
        import tkinter as tk
        search_term = self.search_entry.winfo_children()[0].get()
        self.api_log_text.config(state='normal')
        if search_term != self.last_search_term:
            self.last_search_term = search_term
            self.api_log_text.tag_remove('search', '1.0', tk.END); self.api_log_text.tag_remove('current_search', '1.0', tk.END)
        if search_term:
            start_pos = self.api_log_text.search(search_term, self.last_search_pos, stopindex=tk.END, nocase=True)
            if not start_pos:
                self.last_search_pos = "1.0"
                self.api_log_text.tag_remove('current_search', '1.0', tk.END)
                start_pos = self.api_log_text.search(search_term, self.last_search_pos, stopindex=tk.END, nocase=True)
            if start_pos:
                end_pos = f"{start_pos}+{len(search_term)}c"
                self.api_log_text.tag_add('search', start_pos, end_pos)
                self.api_log_text.tag_remove('current_search', '1.0', tk.END)
                self.api_log_text.tag_add('current_search', start_pos, end_pos)
                self.api_log_text.see(start_pos)
                self.last_search_pos = end_pos
        self.api_log_text.config(state='disabled')
    def start_api_exe(self):
        self.api_log_queue = queue.Queue()
        api_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "api.exe")
        if not os.path.exists(api_path): self.log_to_api_tab("Error: api.exe not found."); self.set_api_status("Offline"); return
        try:
            self.api_process = subprocess.Popen([api_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8', errors='replace')
            threading.Thread(target=self.read_api_output, daemon=True).start()
            self.master.after(100, self.process_api_log_queue)
        except Exception as e: self.log_to_api_tab(f"Failed to start api: {e}"); self.set_api_status("Offline")
    def refresh_api_exe(self):
        if self.api_process: self.api_process.terminate(); self.api_process = None
        self.api_log_text.config(state='normal'); self.api_log_text.delete('1.0', 'end'); self.api_log_text.config(state='disabled')
        self.set_api_status("Offline"); self.start_api_exe()
    def read_api_output(self):
        for line in iter(self.api_process.stdout.readline, ''): self.api_log_queue.put(line)
        self.api_process.stdout.close(); self.master.after(0, self.set_api_status, "Offline")
    def process_api_log_queue(self):
        import tkinter as tk
        try:
            while True:
                line = self.api_log_queue.get_nowait()
                self.log_to_api_tab(line)
        except queue.Empty: pass
        finally:
            if self.is_running: self.master.after(100, self.process_api_log_queue)
    def log_to_api_tab(self, message):
        import tkinter as tk
        self.api_log_text.config(state='normal'); self.api_log_text.insert(tk.END, message); self.api_log_text.see(tk.END); self.api_log_text.config(state='disabled')
        if "fiber" in message.lower() and self.api_status != "Online": self.set_api_status("Online")
    def _setup_log_file(self):
        try:
            self.log_dir = os.path.join(self.base_path, "log"); os.makedirs(self.log_dir, exist_ok=True)
            threading.Thread(target=self._cleanup_old_logs, daemon=True).start()
            self.current_log_date = time.strftime("%Y-%m-%d")
            filename = f"api_log_{self.current_log_date}.txt"
            self.log_filepath = os.path.join(self.log_dir, filename)
            self._load_log_for_today()
        except: pass
    def _cleanup_old_logs(self):
        if not self.log_dir: return
        try:
            cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
            for f in os.listdir(self.log_dir):
                if f.startswith("api_log_") and f.endswith(".txt"):
                    try:
                        fd = datetime.datetime.strptime(f.replace("api_log_", "").replace(".txt", ""), "%Y-%m-%d")
                        if fd < cutoff: os.remove(os.path.join(self.log_dir, f))
                    except: pass
        except: pass
    def _load_log_for_today(self):
        if self.log_filepath and os.path.exists(self.log_filepath):
            try:
                with open(self.log_filepath, 'r', encoding='utf-8') as f: c = f.read()
                if c: self.api_log_text.config(state='normal'); self.api_log_text.insert('1.0', c); self.api_log_text.see('end'); self.api_log_text.config(state='disabled')
            except: pass
    def _auto_save_log(self):
        if not self.log_filepath: return
        try: c = self.api_log_text.get("1.0", "end-1c"); threading.Thread(target=self._save_log_to_file_worker, args=(c,), daemon=True).start()
        except: pass
    def _clear_api_log_widget(self):
        try: self.api_log_text.config(state='normal'); self.api_log_text.delete('1.0', 'end'); self.api_log_text.config(state='disabled')
        except: pass
    def _save_log_to_file_worker(self, content):
        try:
            td = time.strftime("%Y-%m-%d")
            if td != self.current_log_date:
                if content.strip():
                    fc = self._format_sql_log(content)
                    with open(self.log_filepath, 'w', encoding='utf-8') as f: f.write(fc)
                self.current_log_date = td; self.log_filepath = os.path.join(self.log_dir, f"api_log_{td}.txt")
                self.master.after(0, self._clear_api_log_widget)
            else:
                if content.strip():
                    fc = self._format_sql_log(content)
                    with open(self.log_filepath, 'w', encoding='utf-8') as f: f.write(fc)
        except: pass
    def _periodic_log_save(self):
        if self.is_running: self._auto_save_log(); self.master.after(30000, self._periodic_log_save)
    def _format_sql_log(self, raw): return raw
    def hide_window(self): self._stop_stream(); self.master.withdraw()
    def show_window(self, icon=None, item=None): self.master.deiconify(); self.master.lift(); self.master.focus_force()
    def get_adb_path(self):
        if getattr(sys, 'frozen', False): base = sys._MEIPASS
        else: base = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(base, "adb", "adb.exe"); return p if os.path.exists(p) else "adb"
    def get_scrcpy_path(self):
        if getattr(sys, 'frozen', False): base = sys._MEIPASS
        else: base = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(base, "scrcpy", "scrcpy.exe"); return p if os.path.exists(p) else "scrcpy.exe"
    def check_adb(self):
        try: subprocess.run([self.ADB_PATH, "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW); return True
        except: return False
    def start_adb_server(self):
        try: subprocess.run([self.ADB_PATH, "start-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        except: pass
    def refresh_devices(self): threading.Thread(target=self._refresh_devices_worker, daemon=True).start()
    def _refresh_devices_worker(self):
        try:
            res = subprocess.run([self.ADB_PATH, "devices"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            devs = []
            for line in res.stdout.splitlines()[1:]:
                if line.strip():
                    p = line.split('\t')
                    if len(p) >= 2 and p[1] == 'device': devs.append(p[0])
            self.master.after(0, self._update_device_ui, devs)
        except: pass
    def _update_device_ui(self, devs):
        for i in self.device_tree.get_children(): self.device_tree.delete(i)
        all_devs = set(devs)
        if self.connected_device: all_devs.add(self.connected_device)
        for d in sorted(list(all_devs)):
            status = "Connected" if d == self.connected_device else "Available"
            tag = "connected" if status == "Connected" else "disconnected"
            self.device_tree.insert('', 'end', values=(d, status), tags=(tag,))
    def parse_device_list(self, out): return [] 
    def connect_device(self):
        sel = self.device_tree.focus()
        if not sel: messagebox.showwarning("Select", "Select a device"); return
        dev = self.device_tree.item(sel)['values'][0]
        if self.connected_device == dev: messagebox.showinfo("Info", "Connected"); return
        if self.connected_device: messagebox.showwarning("Warn", "Disconnect first"); return
        threading.Thread(target=self._connect_worker, args=(dev,), daemon=True).start()
    def _connect_worker(self, dev):
        try:
            res = subprocess.run([self.ADB_PATH, "-s", dev, "reverse", "tcp:8000", "tcp:8000"], creationflags=subprocess.CREATE_NO_WINDOW)
            if res.returncode == 0:
                self.connected_device = dev; self.is_disconnecting = False
                self.master.after(0, self.show_notification, f"Connected: {dev}", True)
                self.master.after(0, self.refresh_devices); self.master.after(0, self.update_tray_status)
                self.master.after(0, self._clear_apk_monitor); self.master.after(100, self._scan_existing_apk_files)
                self.master.after(0, self.disconnect_button.config, {'state':'normal'})
            else: self.master.after(0, lambda: messagebox.showerror("Error", "Failed"))
        except: pass
        finally: self.master.after(0, self.connect_button.config, {'state':'normal'})
    def disconnect_device(self):
        if not self.connected_device: return
        threading.Thread(target=self._disconnect_worker, daemon=True).start()
    def _disconnect_worker(self):
        try:
            subprocess.run([self.ADB_PATH, "-s", self.connected_device, "reverse", "--remove", "tcp:8000"], creationflags=subprocess.CREATE_NO_WINDOW)
            dev = self.connected_device; self.connected_device = None
            self.master.after(0, self.refresh_devices); self.master.after(0, self.update_tray_status)
            self.master.after(0, self.show_notification, f"Disconnected: {dev}", False)
            self.master.after(0, self._clear_apk_monitor)
            self._stop_stream()
            self.master.after(0, self.disconnect_button.config, {'state':'disabled'})
        except: pass
    def _start_monitoring_services(self):
        if self._load_configs():
            if self.zip_monitor_path and os.path.exists(self.zip_monitor_path):
                self.zip_file_observer = Observer(); self.zip_file_observer.schedule(ZipFileHandler(self), self.zip_monitor_path, recursive=False); self.zip_file_observer.start()
            if self.apk_monitor_path and os.path.exists(self.apk_monitor_path):
                self.apk_file_observer = Observer(); self.apk_file_observer.schedule(ApkFileHandler(self), self.apk_monitor_path, recursive=False); self.apk_file_observer.start()
    def _scan_existing_apk_files(self):
        if not self.apk_monitor_path or not os.path.exists(self.apk_monitor_path): return
        try:
            for f in os.listdir(self.apk_monitor_path):
                if f.endswith(".apk"):
                    fp = os.path.join(self.apk_monitor_path, f)
                    if fp not in self.apk_file_map and fp not in self.apk_processing_files: self._add_apk_to_monitor(fp)
        except: pass
    def _clear_apk_monitor(self):
        try:
            for i in self.apk_tree.get_children(): self.apk_tree.delete(i)
        except: pass
        self.apk_processed_count=0; self.apk_file_map.clear(); self.apk_processing_files.clear()
        try: self.apk_count_label.config(text="Total APKs Processed: 0")
        except: pass
    def _add_apk_to_monitor(self, fp):
        import tkinter as tk
        if fp in self.apk_file_map: return
        self.apk_processing_files.add(fp)
        iid = self.apk_tree.insert('', 'end', values=(os.path.basename(fp), 'Pending'), tags=('pending',))
        self.apk_file_map[fp] = iid
        threading.Thread(target=self._run_apk_install, args=(fp, iid), daemon=True).start()
    def _run_apk_install(self, fp, iid):
        self.master.after(0, self._update_apk_status, iid, "Checking...")
        for _ in range(5):
            try: 
                with open(fp, 'rb'): pass
                break
            except: time.sleep(1)
        else: self.master.after(0, self._update_apk_status, iid, "Error: File locked"); return
        try: apk = APK(fp); pkg = apk.package; ver = int(apk.version_code)
        except: self.master.after(0, self._update_apk_status, iid, "Error: Invalid APK"); return
        wait = 0
        while not self.connected_device and self.is_running and wait < 10:
            self.master.after(0, self._update_apk_status, iid, "Waiting for device..."); time.sleep(1); wait+=1
        if not self.connected_device: self.master.after(0, self._update_apk_status, iid, "Error: No device"); return
        dev_ver = 0
        try:
            res = subprocess.run([self.ADB_PATH, "-s", self.connected_device, "shell", "dumpsys", "package", pkg], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            for l in res.stdout.splitlines():
                if "versionCode=" in l: dev_ver = int(l.strip().split("versionCode=")[1].split(" ")[0]); break
        except: pass
        msg = ""
        if dev_ver == 0: msg = "Installing..."
        elif ver > dev_ver: msg = "Upgrading..."
        else: self.master.after(0, self._update_apk_status, iid, f"Skipped (v{dev_ver} installed)"); return
        self.master.after(0, self._update_apk_status, iid, msg)
        try:
            res = subprocess.run([self.ADB_PATH, "-s", self.connected_device, "install", "-r", fp], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if "Success" in res.stdout: self.master.after(0, self._update_apk_status, iid, "Success")
            else: self.master.after(0, self._update_apk_status, iid, "Error: Install Failed")
        except Exception as e: self.master.after(0, self._update_apk_status, iid, f"Error: {e}")
        finally: self.master.after(0, self._remove_from_apk_processing_list, fp)
    def _update_apk_status(self, iid, msg):
        try:
            if not self.apk_tree.exists(iid): return
            fn = self.apk_tree.item(iid, 'values')[0]
            tag = 'error'
            if 'Success' in msg: tag='done'
            elif 'Skipped' in msg: tag='skipped'
            elif 'Installing' in msg or 'Upgrading' in msg or 'Waiting' in msg: tag='processing'
            self.apk_tree.item(iid, values=(fn, msg), tags=(tag,))
        except: pass
    def _remove_from_apk_processing_list(self, fp): 
        if fp in self.apk_processing_files: self.apk_processing_files.remove(fp)

    # --- Zip Methods (SAFE ZONE & ISOLATION LOGIC) ---
    def _add_zip_to_monitor(self, fp):
        import tkinter as tk
        if fp in self.processing_files: return
        self.processing_files.add(fp)
        iid = self.zip_tree.insert('', 'end', values=(os.path.basename(fp), 'Pending'), tags=('pending',))
        self.zip_file_map[fp] = iid
        threading.Thread(target=self.process_zip_file, args=(fp,), daemon=True).start()

    def process_zip_file(self, zip_path):
        iid = self.zip_file_map.get(zip_path)
        if not iid: return
        self.master.after(0, self._update_zip_status, iid, "Processing")
        
        # --- Robustness: Wait for file ready ---
        for i in range(20): 
            try:
                with open(zip_path, 'rb'): pass 
                time.sleep(1) 
                break 
            except: time.sleep(1) 
        else: 
            self.master.after(0, self._update_zip_status, iid, "Error: Locked")
            self.master.after(0, self._remove_from_processing_list, zip_path)
            return

        original_dir = os.path.dirname(zip_path)
        filename = os.path.basename(zip_path)
        
        # --- ISOLATION: Create Safe Zone ---
        safe_zone_dir = os.path.join(original_dir, "HHT_Temp_Processing")
        os.makedirs(safe_zone_dir, exist_ok=True)
        safe_zip_path = os.path.join(safe_zone_dir, filename)

        try:
            # 1. Move to Safe Zone (Atomic Move)
            shutil.move(zip_path, safe_zip_path)

            # 2. Process in Safe Zone
            extract_dir = os.path.join(safe_zone_dir, f"extract_{filename}")
            
            parts = filename.replace('.zip', '').split('-')
            final_filename = filename 
            if len(parts) == 5:
                final_filename = f"{parts[0]}-{parts[1]}-{parts[2]}-{parts[3]}-{time.strftime('%y%m%d')}-{parts[4]}.zip"
            
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(safe_zip_path, 'r') as z: z.extractall(extract_dir)
            os.remove(safe_zip_path)

            new_zip_in_safe_zone = os.path.join(safe_zone_dir, final_filename)
            with zipfile.ZipFile(new_zip_in_safe_zone, 'w', zipfile.ZIP_DEFLATED) as z:
                for root, dirs, files in os.walk(extract_dir):
                    for dr in dirs:
                        p = os.path.join(root, dr); arc = os.path.relpath(p, extract_dir).replace(os.sep, '/') + '/'
                        zi = zipfile.ZipInfo(arc); zi.create_system = 3; zi.external_attr = (0o755 << 16) | 0x10
                        z.writestr(zi, "")
                    for f in files:
                        p = os.path.join(root, f); arc = os.path.relpath(p, extract_dir).replace(os.sep, '/')
                        zi = zipfile.ZipInfo.from_file(p, arc); zi.create_system = 3; zi.external_attr = (0o644 << 16)
                        with open(p, "rb") as src: z.writestr(zi, src.read())

            # 3. Move Back to Original Dir (Finished)
            final_dest_path = os.path.join(original_dir, final_filename)
            if os.path.exists(final_dest_path): os.remove(final_dest_path)
            shutil.move(new_zip_in_safe_zone, final_dest_path)
            
            self.master.after(0, self._update_zip_status, iid, "Done")

        except Exception as e:
            print(f"Zip Process Error: {e}")
            self.master.after(0, self._update_zip_status, iid, "Error")
        
        finally:
            if 'extract_dir' in locals() and os.path.exists(extract_dir): shutil.rmtree(extract_dir)
            self.master.after(0, self._remove_from_processing_list, zip_path)

    def _update_zip_status(self, iid, s):
        try:
            if not self.zip_tree.exists(iid): return
            fn = self.zip_tree.item(iid, 'values')[0]
            tag = 'error'
            if s == 'Done': tag='done'
            elif s == 'Processing': tag='processing'
            self.zip_tree.item(iid, values=(fn, s), tags=(tag,))
        except: pass
    def _remove_from_processing_list(self, fp):
        if fp in self.processing_files: self.processing_files.remove(fp)

    def update_tray_status(self):
        if not self.tray_icon: return
        t = f"HHT Connect v{self.APP_VERSION}\n"
        if self.connected_device: t += f"Device: {self.connected_device}\n"
        else: t += "Device: Disconnected\n"
        t += f"API: {self.api_status}"
        self.tray_icon.title = t

    def device_monitor_loop(self):
        while self.is_running:
            if self.connected_device:
                res = subprocess.run([self.ADB_PATH, "devices"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                found = False
                for line in res.stdout.splitlines():
                    if self.connected_device in line and "device" in line: found = True; break
                if not found:
                    self.master.after(0, self.show_notification, f"Lost connection: {self.connected_device}", False)
                    self.connected_device = None
                    self.master.after(0, self.disconnect_button.config, {'state':'disabled'})
                    self.master.after(0, self.refresh_devices)
                    self._stop_stream()
            time.sleep(3)

    # --- Exit ---
    def on_app_quit(self):
        self.is_running = False
        try:
            c = self.api_log_text.get("1.0", "end-1c")
            threading.Thread(target=self._save_log_to_file_worker, args=(c,), daemon=True).start()
        except: pass
        self._stop_stream()
        if self.tray_icon: self.tray_icon.stop()
        if self.api_process: self.api_process.terminate()
        if self.connected_device:
            subprocess.run([self.ADB_PATH, "-s", self.connected_device, "reverse", "--remove", "tcp:8000"], creationflags=subprocess.CREATE_NO_WINDOW)
        try: subprocess.run([self.ADB_PATH, "kill-server"], creationflags=subprocess.CREATE_NO_WINDOW)
        except: pass
        if os.path.exists(self.lock_file_path):
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
    
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except: pass

    temp_dir = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp')
    lock_file = os.path.join(temp_dir, 'hht_android_connect.lock')

    if os.path.exists(lock_file):
        try:
            with open(lock_file, 'r') as f: pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                messagebox.showinfo("Already Running", "App is already running.")
                sys.exit()
        except: pass

    with open(lock_file, 'w') as f: f.write(str(os.getpid()))

    try:
        root = tk.Tk()
        app = App(root, lock_file_path=lock_file) 
        root.protocol('WM_DELETE_WINDOW', app.hide_window)
        menu = pystray.Menu(pystray.MenuItem('Show', app.show_window, default=True), pystray.MenuItem('Quit', app.on_app_quit))
        icon = pystray.Icon("HHT", app.icon_image, "HHT Connect", menu)
        app.tray_icon = icon
        threading.Thread(target=icon.run, daemon=True).start()
        root.mainloop()
    except Exception as e:
        if os.path.exists(lock_file): os.remove(lock_file)
        messagebox.showerror("Application Error", f"An unexpected error occurred: {e}")

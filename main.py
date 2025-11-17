# This code has been verified to have correct indentation.
import subprocess
import threading
import os
import sys
import time
import queue
import zipfile
import shutil
import configparser # Using configparser for .ini files
import datetime # For log date management
import ctypes # For screen streaming (embedding window)
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
            if event.src_path in self.app.processing_files:
                print(f"Ignoring self-generated file event: {event.src_path}")
                return
            print(f"New zip file detected: {event.src_path}")
            self.app.master.after(0, self.app._add_zip_to_monitor, event.src_path)

# --- Handler for the APK file monitoring service ---
class ApkFileHandler(FileSystemEventHandler):
    def __init__(self, app_instance):
        self.app = app_instance

    def process_event(self, event):
        """Helper to process both create and modify events."""
        if not event.is_directory and event.src_path.endswith('.apk'):
            
            # Check 1: Have we *ever* seen this file this session?
            if event.src_path in self.app.apk_file_map:
                print(f"Ignoring duplicate event for already processed file: {event.src_path}")
                return
            
            # Check 2: Is this file *currently* in the queue?
            if event.src_path in self.app.apk_processing_files:
                print(f"Ignoring duplicate event for file in queue: {event.src_path}")
                return
            
            print(f"New APK file event ({event.event_type}): {event.src_path}")
            self.app.master.after(0, self.app._add_apk_to_monitor, event.src_path)

    def on_created(self, event):
        self.process_event(event)
        
    def on_modified(self, event):
        # This catches files that are "pasted" or slowly copied
        self.process_event(event)

class App:
    
    APP_VERSION = "1.0.0" # <--- ตั้งค่าเวอร์ชันตรงนี้

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
        
        # --- Variables for auto-save log & file monitoring ---
        self.log_filepath = None
        self.log_dir = None # Store log directory
        self.current_log_date = None # Track current log date
        self.zip_monitor_path = None
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
        
        # --- NEW: Screen streaming variables ---
        self.scrcpy_process = None
        self.stream_window_id = None
        self.current_tab = "device" # Track current tab
        
        if getattr(sys, 'frozen', False):
            self.base_path = os.path.dirname(sys.executable)
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))

        master.title(f"HHT Android Connect - v{self.APP_VERSION}") # <-- Added version to title

        # --- NEW: Updated window size for vertical layout ---
        app_width = 560 # Slimmer width (170 + 390)
        app_height = 680 # Slimmer height
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
        self.COLOR_SIDEBAR_BG = "#3D4450" # Dark sidebar
        self.COLOR_SIDEBAR_BTN_INACTIVE = "#3D4450"
        self.COLOR_SIDEBAR_BTN_ACTIVE = "#E0E5EC"
        self.COLOR_SIDEBAR_TEXT_INACTIVE = "#C8D0DA"
        self.COLOR_SIDEBAR_TEXT_ACTIVE = "#3D4450"

        master.configure(background=self.COLOR_BG)

        self.icon_image = create_android_icon(self.COLOR_TEXT)
        icon_photo = ImageTk.PhotoImage(self.icon_image)
        master.iconphoto(True, icon_photo)

        # --- Style Configuration ---
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('.', font=('Segoe UI', 9), background=self.COLOR_BG, foreground=self.COLOR_TEXT, borderwidth=0)
        self.style.configure('TFrame', background=self.COLOR_BG)
        self.style.configure('Treeview',
                             background=self.COLOR_BG,
                             fieldbackground=self.COLOR_BG,
                             foreground=self.COLOR_TEXT,
                             rowheight=30,
                             font=('Consolas', 10))
        self.style.map('Treeview', background=[('selected', self.COLOR_SHADOW_DARK)], foreground=[('selected', self.COLOR_SHADOW_LIGHT)])
        self.style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'), background=self.COLOR_BG, relief='flat')
        self.style.map('Treeview.Heading', background=[('active', self.COLOR_BG)])
        self.style.configure('TEntry', fieldbackground=self.COLOR_BG, foreground=self.COLOR_TEXT, insertcolor=self.COLOR_TEXT, relief='flat', borderwidth=0)
        
        self.style.configure('Raised.TButton', font=('Segoe UI', 9, 'bold'), padding=(10, 5), relief='raised',
                             background=self.COLOR_3D_BG_ACTIVE, foreground='white', borderwidth=2)
        self.style.map('Raised.TButton', background=[('active', self.COLOR_SHADOW_DARK)])

        # --- Initialization Steps ---
        self.ADB_PATH = self.get_adb_path()
        self.SCRCPY_PATH = self.get_scrcpy_path() # New path
        
        if not self.check_adb():
            messagebox.showerror("ADB Error", "Android Debug Bridge (ADB) not found.")
            master.quit()
            return
            
        self.start_adb_server()
        self.connected_device = None

        self.create_widgets() # Build the NEW UI
        self.refresh_devices()
        self.update_tray_status()

        self.monitor_thread = threading.Thread(target=self.device_monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.start_api_exe()
        self._setup_log_file()
        self._periodic_log_save()
        self._start_monitoring_services()
        self._scan_existing_apk_files()
        
        self.switch_tab('device') # Start on the first tab

    # --- Custom Notification Methods ---
    def show_notification(self, message, is_connected):
        import tkinter as tk
        if self.notification_timer:
            self.master.after_cancel(self.notification_timer)

        color = self.COLOR_SUCCESS if is_connected else self.COLOR_DANGER
        
        if self.notification_window and self.notification_window.winfo_exists():
            label = self.notification_window.winfo_children()[0]
            label.config(text=message, bg=color)
            self.notification_window.config(bg=color)
        else:
            self.notification_window = tk.Toplevel(self.master)
            win = self.notification_window
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.config(bg=color)
            
            label = tk.Label(win, text=message, fg="white", bg=color, font=('Segoe UI', 10), justify='left', padx=20, pady=10)
            label.pack()

            win.update_idletasks()
            width = win.winfo_width()
            height = win.winfo_height()
            screen_width = self.master.winfo_screenwidth()
            screen_height = self.master.winfo_screenheight()
            x = screen_width - width - 20
            y = screen_height - height - 60
            win.geometry(f'{width}x{height}+{x}+{y}')
        
        self.notification_timer = self.master.after(3000, self.hide_notification)

    def hide_notification(self):
        if self.notification_window and self.notification_window.winfo_exists():
            self.notification_window.destroy()
        self.notification_window = None
        self.notification_timer = None

    # --- NEW: create_side_button ---
    def create_side_button(self, parent, text, command):
        """Creates a new button for the sidebar."""
        import tkinter as tk
        button = tk.Button(parent, text=text, command=command,
                           font=('Segoe UI', 10, 'bold'),
                           bg=self.COLOR_SIDEBAR_BTN_INACTIVE,
                           fg=self.COLOR_SIDEBAR_TEXT_INACTIVE,
                           activebackground=self.COLOR_SIDEBAR_BTN_ACTIVE,
                           activeforeground=self.COLOR_SIDEBAR_TEXT_ACTIVE,
                           relief='flat', bd=0, anchor='w',
                           padx=15, pady=15) # Slimmer padding
        return button

    # --- NEW: create_widgets (Complete Redesign) ---
    def create_widgets(self):
        import tkinter as tk
        from tkinter import ttk, scrolledtext

        # --- Main Layout (Sidebar + Content) ---
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(1, weight=1)
        
        # --- 1. Sidebar ---
        sidebar_frame = tk.Frame(self.master, bg=self.COLOR_SIDEBAR_BG, width=170) # Slimmer sidebar
        sidebar_frame.grid(row=0, column=0, sticky='nsw')
        sidebar_frame.pack_propagate(False) # Prevent shrinking
        
        header_label = tk.Label(sidebar_frame, text="HHT CONNECT", font=('Segoe UI', 14, 'bold'),
                                bg=self.COLOR_SIDEBAR_BG, fg=self.COLOR_BG,
                                anchor='w', padx=15, pady=20)
        header_label.pack(fill='x')
        
        self.side_btn_device = self.create_side_button(sidebar_frame, "Device Status", lambda: self.switch_tab('device'))
        self.side_btn_device.pack(fill='x')
        
        self.side_btn_api = self.create_side_button(sidebar_frame, "API Log", lambda: self.switch_tab('api'))
        self.side_btn_api.pack(fill='x')

        self.side_btn_zip = self.create_side_button(sidebar_frame, "Zip Monitor", lambda: self.switch_tab('zip'))
        self.side_btn_zip.pack(fill='x')

        self.side_btn_apk = self.create_side_button(sidebar_frame, "APK Monitor", lambda: self.switch_tab('apk'))
        self.side_btn_apk.pack(fill='x')
        
        self.side_btn_stream = self.create_side_button(sidebar_frame, "Stream Screen", lambda: self.switch_tab('stream'))
        self.side_btn_stream.pack(fill='x')

        # List of all buttons for easy management
        self.all_side_buttons = [self.side_btn_device, self.side_btn_api, self.side_btn_zip, self.side_btn_apk, self.side_btn_stream]

        # --- 2. Main Content Area ---
        # This frame holds all the "pages" stacked on top of each other
        self.content_area = tk.Frame(self.master, bg=self.COLOR_BG, width=390) # Slimmer content
        self.content_area.grid(row=0, column=1, sticky='nsew')
        
        # --- Page 1: Device Status ---
        self.device_frame = tk.Frame(self.content_area, bg=self.COLOR_BG, padx=20, pady=20)
        self.device_frame.place(relwidth=1, relheight=1) # Use .place to stack frames
        self.device_frame.grid_rowconfigure(0, weight=1)
        self.device_frame.grid_columnconfigure(0, weight=1)
        
        self.device_tree = ttk.Treeview(self.device_frame, columns=('device_id', 'status'), show='headings')
        self.device_tree.heading('device_id', text='DEVICE ID', anchor='w')
        self.device_tree.heading('status', text='STATUS', anchor='w')
        self.device_tree.column('device_id', anchor='w', width=240) # Resized
        self.device_tree.column('status', anchor='center', width=100) # Resized
        self.device_tree.grid(row=0, column=0, sticky='nsew', pady=(0, 10))
        self.device_tree.tag_configure('connected', foreground=self.COLOR_SUCCESS, font=('Segoe UI', 9, 'bold'))
        self.device_tree.tag_configure('disconnected', foreground=self.COLOR_TEXT)
        buttons_frame = tk.Frame(self.device_frame, bg=self.COLOR_BG)
        buttons_frame.grid(row=1, column=0, sticky='ew')
        self.refresh_button = self.create_neumorphic_button(buttons_frame, text="Refresh", command=self.refresh_devices)
        self.refresh_button.pack(side='left', padx=(0, 10))
        self.disconnect_button = self.create_neumorphic_button(buttons_frame, text="Disconnect", command=self.disconnect_device)
        self.disconnect_button.pack(side='left')
        self.disconnect_button.config(state='disabled')
        self.connect_button = self.create_neumorphic_button(buttons_frame, text="Connect", command=self.connect_device, is_accent=True)
        self.connect_button.pack(side='right')

        # --- Page 2: API Log ---
        self.api_frame = tk.Frame(self.content_area, bg=self.COLOR_BG, padx=20, pady=20)
        self.api_frame.place(relwidth=1, relheight=1)
        self.api_frame.grid_rowconfigure(1, weight=1)
        self.api_frame.grid_columnconfigure(0, weight=1)
        api_header_frame = tk.Frame(self.api_frame, bg=self.COLOR_BG)
        api_header_frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        api_header_frame.grid_columnconfigure(1, weight=1)
        self.api_status_dot = tk.Canvas(api_header_frame, width=10, height=10, bg=self.COLOR_BG, highlightthickness=0)
        self.api_status_dot.grid(row=0, column=0, sticky='w', pady=4)
        self.api_status_label = tk.Label(api_header_frame, text="API Status:", font=('Segoe UI', 9), bg=self.COLOR_BG, fg=self.COLOR_TEXT)
        self.api_status_label.grid(row=0, column=1, sticky='w', padx=5)
        self.search_entry = self.create_neumorphic_entry(api_header_frame)
        self.search_entry.grid(row=0, column=2, sticky='e', padx=(0, 5))
        search_button = ttk.Button(api_header_frame, text="Search", style='Raised.TButton', command=self.search_api_logs)
        search_button.grid(row=0, column=3, sticky='e', padx=(0, 5))
        self.refresh_api_button = ttk.Button(api_header_frame, text="Restart API", style='Raised.TButton', command=self.refresh_api_exe)
        self.refresh_api_button.grid(row=0, column=4, sticky='e', padx=(0,5))
        log_frame = tk.Frame(self.api_frame, bg=self.COLOR_SHADOW_DARK, bd=0)
        log_frame.grid(row=1, column=0, sticky='nsew')
        self.api_log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', bg=self.COLOR_BG, fg=self.COLOR_TEXT, font=('Consolas', 8), relief='flat', bd=2, highlightthickness=0)
        self.api_log_text.pack(fill='both', expand=True, padx=2, pady=2)
        self.api_log_text.tag_config('search', background=self.COLOR_ACCENT, foreground='white')
        self.api_log_text.tag_config('current_search', background=self.COLOR_WARNING, foreground='black')

        # --- Page 3: Zip Monitor ---
        self.zip_frame = tk.Frame(self.content_area, bg=self.COLOR_BG, padx=20, pady=20)
        self.zip_frame.place(relwidth=1, relheight=1)
        self.zip_frame.grid_rowconfigure(1, weight=1)
        self.zip_frame.grid_columnconfigure(0, weight=1)
        zip_header_frame = tk.Frame(self.zip_frame, bg=self.COLOR_BG)
        zip_header_frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.zip_count_label = tk.Label(zip_header_frame, text="Total Files Processed: 0", font=('Segoe UI', 9, 'bold'), bg=self.COLOR_BG, fg=self.COLOR_TEXT)
        self.zip_count_label.pack(side='left')
        clear_zip_btn = ttk.Button(zip_header_frame, text="Clear List", style='Raised.TButton', command=self._clear_zip_monitor)
        clear_zip_btn.pack(side='right')
        self.zip_tree = ttk.Treeview(self.zip_frame, columns=('filename', 'status'), show='headings')
        self.zip_tree.heading('filename', text='FILENAME', anchor='w')
        self.zip_tree.heading('status', text='STATUS', anchor='w')
        self.zip_tree.column('filename', anchor='w', width=240) # Resized
        self.zip_tree.column('status', anchor='w', width=100) # Resized
        self.zip_tree.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        self.zip_tree.tag_configure('pending', foreground=self.COLOR_TEXT)
        self.zip_tree.tag_configure('processing', foreground=self.COLOR_WARNING, font=('Segoe UI', 9, 'bold'))
        self.zip_tree.tag_configure('done', foreground=self.COLOR_SUCCESS, font=('Segoe UI', 9, 'bold'))
        self.zip_tree.tag_configure('error', foreground=self.COLOR_DANGER, font=('Segoe UI', 9, 'bold'))
        
        # --- Page 4: APK Monitor ---
        self.apk_frame = tk.Frame(self.content_area, bg=self.COLOR_BG, padx=20, pady=20)
        self.apk_frame.place(relwidth=1, relheight=1)
        self.apk_frame.grid_rowconfigure(1, weight=1)
        self.apk_frame.grid_columnconfigure(0, weight=1)
        apk_header_frame = tk.Frame(self.apk_frame, bg=self.COLOR_BG)
        apk_header_frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.apk_count_label = tk.Label(apk_header_frame, text="Total APKs Processed: 0", font=('Segoe UI', 9, 'bold'), bg=self.COLOR_BG, fg=self.COLOR_TEXT)
        self.apk_count_label.pack(side='left')
        clear_apk_btn = ttk.Button(apk_header_frame, text="Clear List", style='Raised.TButton', command=self._clear_apk_monitor)
        clear_apk_btn.pack(side='right')
        self.apk_tree = ttk.Treeview(self.apk_frame, columns=('filename', 'status'), show='headings')
        self.apk_tree.heading('filename', text='FILENAME', anchor='w')
        self.apk_tree.heading('status', text='STATUS', anchor='w')
        self.apk_tree.column('filename', anchor='w', width=240) # Resized
        self.apk_tree.column('status', anchor='w', width=100) # Resized
        self.apk_tree.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        self.apk_tree.tag_configure('pending', foreground=self.COLOR_TEXT)
        self.apk_tree.tag_configure('processing', foreground=self.COLOR_WARNING, font=('Segoe UI', 9, 'bold'))
        self.apk_tree.tag_configure('done', foreground=self.COLOR_SUCCESS, font=('Segoe UI', 9, 'bold'))
        self.apk_tree.tag_configure('error', foreground=self.COLOR_DANGER, font=('Segoe UI', 9, 'bold'))
        self.apk_tree.tag_configure('skipped', foreground=self.COLOR_TEXT, font=('Segoe UI', 9, 'italic'))

        # --- Page 5: Stream Screen ---
        self.stream_frame = tk.Frame(self.content_area, bg=self.COLOR_BG, padx=20, pady=20)
        self.stream_frame.place(relwidth=1, relheight=1)
        
        stream_header = tk.Label(self.stream_frame, text="Device Screen Stream", font=('Segoe UI', 12, 'bold'), bg=self.COLOR_BG, fg=self.COLOR_TEXT)
        stream_header.pack(pady=(0, 10))
        
        # This frame will hold the embedded scrcpy window
        self.stream_embed_frame = tk.Frame(self.stream_frame, bg="black", width=350, height=580) # Resized
        self.stream_embed_frame.pack(expand=True, pady=10)
        
        self.stream_status_label = tk.Label(self.stream_frame, text="Click 'Stream Screen' to begin. Requires a connected device.", font=('Segoe UI', 9), bg=self.COLOR_BG, fg=self.COLOR_TEXT)
        self.stream_status_label.pack(pady=(10, 0))

    # --- Log File Methods ---
    def _setup_log_file(self):
        """Creates log dir, cleans old logs, and sets path for today's log."""
        try:
            self.log_dir = os.path.join(self.base_path, "log")
            os.makedirs(self.log_dir, exist_ok=True)
            
            # Run cleanup
            self._cleanup_old_logs()

            # Set path for today
            self.current_log_date = time.strftime("%Y-%m-%d")
            filename = f"api_log_{self.current_log_date}.txt"
            self.log_filepath = os.path.join(self.log_dir, filename)
            print(f"Logging API output to: {self.log_filepath}")
            
            # Load any existing content from today's log
            self._load_log_for_today()
            
        except Exception as e:
            print(f"Error setting up log file: {e}")

    def _cleanup_old_logs(self):
        """Deletes log files older than 7 days."""
        if not self.log_dir:
            return
        
        print("Cleaning up old logs...")
        try:
            cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
            for filename in os.listdir(self.log_dir):
                if filename.startswith("api_log_") and filename.endswith(".txt"):
                    try:
                        date_str = filename.replace("api_log_", "").replace(".txt", "")
                        file_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                        if file_date < cutoff:
                            filepath_to_delete = os.path.join(self.log_dir, filename)
                            os.remove(filepath_to_delete)
                            print(f"Deleted old log: {filename}")
                    except ValueError:
                        # Ignore files with non-date names
                        print(f"Skipping file with unexpected name: {filename}")
        except Exception as e:
            print(f"Error during log cleanup: {e}")
            
    def _load_log_for_today(self):
        """Loads existing log content from today's file into the widget."""
        if self.log_filepath and os.path.exists(self.log_filepath):
            try:
                with open(self.log_filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                if content:
                    self.api_log_text.config(state='normal')
                    self.api_log_text.insert('1.0', content)
                    self.api_log_text.see('end')
                    self.api_log_text.config(state='disabled')
                    print(f"Loaded existing log from {self.log_filepath}")
            except Exception as e:
                print(f"Error loading existing log: {e}")

    def _auto_save_log(self):
        """Saves the current log, handling daily rollover."""
        if not self.log_filepath:
            return
        
        try:
            content = self.api_log_text.get("1.0", "end-1c")
            today_date_str = time.strftime("%Y-%m-%d")
            
            # Check for date change (midnight rollover)
            if today_date_str != self.current_log_date:
                print(f"Date changed. Saving final log for {self.current_log_date}")
                # 1. Save yesterday's content to yesterday's file one last time
                if content.strip():
                    formatted_content = self._format_sql_log(content)
                    with open(self.log_filepath, 'w', encoding='utf-8') as f:
                        f.write(formatted_content)
                
                # 2. Update path to today's file
                self.current_log_date = today_date_str
                filename = f"api_log_{self.current_log_date}.txt"
                self.log_filepath = os.path.join(self.log_dir, filename)
                
                # 3. Clear the log widget for the new day
                self.api_log_text.config(state='normal')
                self.api_log_text.delete('1.0', 'end')
                self.api_log_text.config(state='disabled')
                print(f"Rolled over to new log file: {self.log_filepath}")
                
            else:
                # No date change, just overwrite today's file with current widget content
                if content.strip():
                    formatted_content = self._format_sql_log(content)
                    with open(self.log_filepath, 'w', encoding='utf-8') as f:
                        f.write(formatted_content)
                        
        except Exception as e:
            print(f"Error during auto-save: {e}")

    def _periodic_log_save(self):
        """Calls the auto-save method and reschedules itself."""
        if self.is_running:
            self._auto_save_log()
            # Reschedule to run again after 30 seconds (30000 ms)
            self.master.after(30000, self._periodic_log_save)

    def _format_sql_log(self, raw_content):
        formatted_lines = []
        sql_keywords = [
            ' FROM ', ' WHERE ', ' INSERT INTO ', ' UPDATE ', ' SET ', ' VALUES ',
            ' LEFT JOIN ', ' INNER JOIN ', ' GROUP BY ', ' ORDER BY ', ' DELETE FROM '
        ]
        for line in raw_content.splitlines():
            if 'SELECT ' in line or 'INSERT INTO ' in line or 'UPDATE ' in line or 'DELETE FROM ' in line:
                formatted_lines.append("--- SQL Query ---")
                for keyword in sql_keywords:
                    line = line.replace(keyword, f'\n  {keyword.strip()} ')
                formatted_lines.append(line)
                formatted_lines.append("-" * 17 + "\n")
            else:
                formatted_lines.append(line)
        return "\n".join(formatted_lines)

    # --- UI Helper Methods ---
    def create_neumorphic_button(self, parent, text, command, is_accent=False):
        import tkinter as tk
        fg_color = 'white' if is_accent else self.COLOR_TEXT
        bg_color = self.COLOR_ACCENT if is_accent else self.COLOR_BG
        button = tk.Button(parent, text=text, command=command, font=('Segoe UI', 9, 'bold'),
                           bg=bg_color, fg=fg_color,
                           activebackground=self.COLOR_SHADOW_DARK if not is_accent else self.COLOR_ACCENT,
                           activeforeground=self.COLOR_SHADOW_LIGHT if not is_accent else 'white',
                           relief='flat', bd=0, highlightthickness=1,
                           highlightbackground=self.COLOR_SHADOW_DARK, padx=10, pady=4)
        return button

    def create_neumorphic_entry(self, parent):
        import tkinter as tk
        from tkinter import ttk
        entry_frame = tk.Frame(parent, bg=self.COLOR_SHADOW_DARK, padx=2, pady=2)
        entry = ttk.Entry(entry_frame, font=('Segoe UI', 9), style='TEntry', width=18)
        entry.pack()
        return entry_frame

    def switch_tab(self, tab_name):
        print(f"Switching to tab: {tab_name}")
        self.current_tab = tab_name
        
        # Stop stream if we navigate away
        if tab_name != "stream":
            self._stop_stream()
            
        # Reset all button styles
        for btn in self.all_side_buttons:
            btn.config(bg=self.COLOR_SIDEBAR_BTN_INACTIVE, fg=self.COLOR_SIDEBAR_TEXT_INACTIVE)
            
        # Raise the correct frame and highlight the button
        if tab_name == 'device':
            self.device_frame.tkraise()
            self.side_btn_device.config(bg=self.COLOR_SIDEBAR_BTN_ACTIVE, fg=self.COLOR_SIDEBAR_TEXT_ACTIVE)
        elif tab_name == 'api':
            self.api_frame.tkraise()
            self.side_btn_api.config(bg=self.COLOR_SIDEBAR_BTN_ACTIVE, fg=self.COLOR_SIDEBAR_TEXT_ACTIVE)
        elif tab_name == 'zip':
            self.zip_frame.tkraise()
            self.side_btn_zip.config(bg=self.COLOR_SIDEBAR_BTN_ACTIVE, fg=self.COLOR_SIDEBAR_TEXT_ACTIVE)
        elif tab_name == 'apk':
            self.apk_frame.tkraise()
            self.side_btn_apk.config(bg=self.COLOR_SIDEBAR_BTN_ACTIVE, fg=self.COLOR_SIDEBAR_TEXT_ACTIVE)
        elif tab_name == 'stream':
            self.stream_frame.tkraise()
            self.side_btn_stream.config(bg=self.COLOR_SIDEBAR_BTN_ACTIVE, fg=self.COLOR_SIDEBAR_TEXT_ACTIVE)
            # Start the stream
            self._start_stream()

    # --- API Process Methods ---
    def set_api_status(self, status):
        self.api_status = status
        if status == "Online":
            self.api_status_dot.config(bg=self.COLOR_SUCCESS)
            self.api_status_label.config(text="API Status: Online", fg=self.COLOR_SUCCESS)
        else:
            self.api_status_dot.config(bg=self.COLOR_DANGER)
            self.api_status_label.config(text="API Status: Offline", fg=self.COLOR_DANGER)
        self.update_tray_status()

    def search_api_logs(self):
        import tkinter as tk
        search_term = self.search_entry.winfo_children()[0].get()
        self.api_log_text.config(state='normal')
        if search_term != self.last_search_term:
            self.last_search_term = search_term
            self.last_search_pos = "1.0"
            self.api_log_text.tag_remove('search', '1.0', tk.END)
            self.api_log_text.tag_remove('current_search', '1.0', tk.END)
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
        if not os.path.exists(api_path):
            self.log_to_api_tab("Error: api.exe not found in the application directory.")
            self.set_api_status("Offline")
            return
        try:
            self.api_process = subprocess.Popen([api_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8', errors='replace')
            threading.Thread(target=self.read_api_output, daemon=True).start()
            self.master.after(100, self.process_api_log_queue)
        except Exception as e:
            self.log_to_api_tab(f"Failed to start api.exe: {e}")
            self.set_api_status("Offline")

    def refresh_api_exe(self):
        if self.api_process:
            self.api_process.terminate()
            self.api_process = None
        self.api_log_text.config(state='normal')
        self.api_log_text.delete('1.0', 'end')
        self.api_log_text.config(state='disabled')
        self.set_api_status("Offline")
        self.start_api_exe()

    def read_api_output(self):
        for line in iter(self.api_process.stdout.readline, ''):
            self.api_log_queue.put(line)
        self.api_process.stdout.close()
        self.master.after(0, self.set_api_status, "Offline")

    def process_api_log_queue(self):
        import tkinter as tk
        try:
            while True:
                line = self.api_log_queue.get_nowait()
                self.log_to_api_tab(line)
        except queue.Empty:
            pass
        finally:
            if self.is_running:
                self.master.after(100, self.process_api_log_queue)

    def log_to_api_tab(self, message):
        import tkinter as tk
        self.api_log_text.config(state='normal')
        self.api_log_text.insert(tk.END, message)
        self.api_log_text.see(tk.END)
        self.api_log_text.config(state='disabled')
        if "fiber" in message.lower() and self.api_status != "Online":
            self.set_api_status("Online")

    # --- Window and Tray Methods ---
    def hide_window(self):
        self._stop_stream() # Stop stream when hiding
        self.master.withdraw()

    def show_window(self, icon=None, item=None):
        self.master.deiconify()
        self.master.lift()
        self.master.focus_force()
        # Restart stream if that was the last active tab
        if self.current_tab == 'stream':
            self._start_stream()

    def update_tray_status(self):
        if not self.tray_icon: return
        device_status_text = f"Device: {self.connected_device}" if self.connected_device else f"Device: Disconnected"
        api_status_text = f"API: Online" if self.api_status == "Online" else f"API: Offline"
        self.tray_icon.menu = self.create_tray_menu(device_status_text, api_status_text)
        if self.connected_device:
            self.tray_icon.icon = create_android_icon(self.COLOR_SUCCESS)
            self.tray_icon.title = f"HHT Android Connect: Connected"
        else:
            self.tray_icon.icon = create_android_icon(self.COLOR_TEXT)
            self.tray_icon.title = "HHT Android Connect: Disconnected"

    def create_tray_menu(self, device_status, api_status):
        import pystray
        return pystray.Menu(
            pystray.MenuItem('Show', self.show_window, default=True),
            pystray.MenuItem(device_status, None, enabled=False),
            pystray.MenuItem(api_status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', self.on_app_quit)
        )

    # --- Device Monitoring and Connection Methods ---
    def device_monitor_loop(self):
        while self.is_running:
            try:
                result = subprocess.run([self.ADB_PATH, "devices"], 
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                        text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                
                current_devices = set(self.parse_device_list(result.stdout))

                if self.connected_device and self.connected_device not in current_devices:
                    if not self.is_disconnecting:
                        self.is_disconnecting = True
                        self.master.after(0, self.handle_auto_disconnect)
                
                if not self.connected_device:
                    newly_connected = current_devices - self.known_devices
                    if newly_connected:
                        device_to_connect = newly_connected.pop()
                        threading.Thread(target=self._connect_device, args=(device_to_connect,), daemon=True).start()
                
                self.known_devices = current_devices
            except Exception as e:
                print(f"Error in device monitor loop: {e}")
            
            time.sleep(3)

    def handle_auto_disconnect(self):
        device_id = self.connected_device
        if device_id:
            self.connected_device = None
            self.disconnect_button.config(state='disabled')
            self.refresh_devices()
            self.update_tray_status()
            self.is_disconnecting = False
            self.show_notification(f"Device Disconnected:\n{device_id}", is_connected=False)
            
            # --- Clear APK list on disconnect ---
            self.master.after(0, self._clear_apk_monitor)
            # --- Stop stream on disconnect ---
            self._stop_stream()
        
    def _update_device_tree(self, all_known_devices):
        import tkinter as tk
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        
        if all_known_devices:
            for device_id in sorted(list(all_known_devices)):
                status = "Connected" if device_id == self.connected_device else "Available"
                tag = "connected" if status == "Connected" else "disconnected"
                self.device_tree.insert('', tk.END, values=(device_id, status), tags=(tag,))
        else:
            self.device_tree.insert('', tk.END, values=('No devices found.', ''), tags=())

    def _refresh_devices(self):
        from tkinter import messagebox
        try:
            result = subprocess.run([self.ADB_PATH, "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            output = result.stdout
            devices = self.parse_device_list(output)
            all_known_devices = set(devices)
            if self.connected_device:
                all_known_devices.add(self.connected_device)
            
            self.master.after(0, self._update_device_tree, all_known_devices)
        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror("Error", f"An error occurred while refreshing devices:\n{e}"))
        finally:
            self.master.after(0, self.refresh_button.config, {'state': 'normal'})

    def _connect_device(self, device_id):
        from tkinter import messagebox
        try:
            result = subprocess.run([self.ADB_PATH, "-s", device_id, "reverse", "tcp:8000", "tcp:8000"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if self.connected_device is None and result.returncode == 0:
                self.connected_device = device_id
                self.is_disconnecting = False
                self.master.after(0, self.show_notification, f"Device Connected:\n{device_id}", True)
                self.master.after(0, self.disconnect_button.config, {'state': 'normal'})
                self.master.after(0, self.refresh_devices)
                self.master.after(0, self.update_tray_status)
                
                # --- Clear list, then scan for APKs ---
                self.master.after(0, self._clear_apk_monitor)
                self.master.after(100, self._scan_existing_apk_files) # Added small delay
                
            elif result.returncode != 0:
                self.master.after(0, lambda: messagebox.showerror("Error", f"Failed to connect:\n{result.stderr}"))
        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror("Error", f"An error occurred during connection:\n{e}"))
        finally:
            self.master.after(0, self.connect_button.config, {'state': 'normal'})

    def _disconnect_device(self):
        from tkinter import messagebox
        if not self.connected_device: return
        try:
            result = subprocess.run([self.ADB_PATH, "-s", self.connected_device, "reverse", "--remove", "tcp:8000"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                device_id = self.connected_device
                self.connected_device = None
                self.disconnect_button.config(state='disabled')
                self.refresh_devices()
                self.update_tray_status()
                self.show_notification(f"Device Disconnected:\n{device_id}", is_connected=False)
                
                # --- Clear APK list on disconnect ---
                self._clear_apk_monitor()
                # --- Stop stream on disconnect ---
                self._stop_stream()
                
            else:
                messagebox.showerror("Error", f"Failed to disconnect:\n{result.stderr}")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred during disconnection:\n{e}")
        finally:
            self.disconnect_button.config(state='normal')

    # --- ADB Helper Methods ---
    def get_adb_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        adb_path = os.path.join(base_path, "adb", "adb.exe")
        return adb_path if os.path.exists(adb_path) else "adb"

    def get_scrcpy_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        scrcpy_path = os.path.join(base_path, "scrcpy", "scrcpy.exe")
        return scrcpy_path if os.path.exists(scrcpy_path) else "scrcpy.exe"

    def check_adb(self):
        from tkinter import messagebox
        try:
            subprocess.run([self.ADB_PATH, "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except FileNotFoundError:
            messagebox.showerror("ADB Error", f"ADB executable not found at the expected path: {self.ADB_PATH}")
            return False
        except Exception:
            return False

    def start_adb_server(self):
        from tkinter import messagebox
        try:
            subprocess.run([self.ADB_PATH, "start-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            messagebox.showerror("Error", f"Could not start ADB server:\n{e}")
            self.master.quit()

    def refresh_devices(self):
        self.refresh_button.config(state='normal')
        threading.Thread(target=self._refresh_devices, daemon=True).start()

    def parse_device_list(self, adb_output):
        devices = []
        lines = adb_output.strip().split('\n')
        for line in lines[1:]:
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 2 and parts[1] == 'device':
                    devices.append(parts[0])
        return devices

    def connect_device(self):
        from tkinter import messagebox
        selected_item = self.device_tree.focus()
        if not selected_item:
            messagebox.showwarning("Select Device", "Please select a device to connect.")
            return
        device_details = self.device_tree.item(selected_item)
        selected_device = device_details['values'][0]

        if self.connected_device == selected_device:
            messagebox.showinfo("Already Connected", f"Device {selected_device} is already connected.")
            return
        
        # --- "FRIENDLY" CHECK ---
        if self.connected_device is not None:
            messagebox.showwarning("Device Already Connected", 
                                  f"Device {self.connected_device} is already connected.\n\n"
                                  f"Please click 'Disconnect' first before connecting a new device.")
            return
        # --- END CHECK ---
        
        threading.Thread(target=self._connect_device, args=(selected_device,), daemon=True).start()

    def disconnect_device(self):
        from tkinter import messagebox
        if not self.connected_device:
            messagebox.showwarning("No Connection", "No device is currently connected.")
            return
        threading.Thread(target=self._disconnect_device, daemon=True).start()

    # --- Config & Monitoring Service Methods ---
    def _load_configs(self):
        """Loads paths from config.ini using configparser."""
        from tkinter import messagebox
        config_path = os.path.join(self.base_path, "configs", "config.ini")
        config = configparser.ConfigParser()
        
        if not os.path.exists(config_path):
            print(f"Error: Config file not found at {config_path}")
            messagebox.showerror("Config Error", f"Configuration file not found. Please create it at:\n{config_path}")
            return False
            
        try:
            config.read(config_path)
            
            try:
                self.zip_monitor_path = config['SETTING']['DEFAULT_PRICE_TAG_PATH']
                if not os.path.exists(self.zip_monitor_path):
                    messagebox.showwarning("Config Warning", f"The Zip monitor path does not exist:\n{self.zip_monitor_path}\n\nThe Zip service will not start.")
                else:
                    print(f"Monitoring Zip Outbox path: {self.zip_monitor_path}")
            except KeyError:
                messagebox.showerror("Config Error", "DEFAULT_PRICE_TAG_PATH not found in [SETTING] section of config.ini")
                
            try:
                self.apk_monitor_path = config['APK_INSTALLER']['MONITOR_PATH']
                if not os.path.exists(self.apk_monitor_path):
                    messagebox.showwarning("Config Warning", f"The APK monitor path does not exist:\n{self.apk_monitor_path}\n\nThe APK service will not start.")
                else:
                    print(f"Monitoring APK path: {self.apk_monitor_path}")
            except KeyError:
                messagebox.showerror("Config Error", "MONITOR_PATH not found in [APK_INSTALLER] section of config.ini")
                
            return True
            
        except Exception as e:
            messagebox.showerror("Config Error", f"Error loading config.ini file: {e}")
            return False

    def _start_monitoring_services(self):
        """Initializes and starts all watchdog file observers."""
        if self._load_configs():
            if self.zip_monitor_path and os.path.exists(self.zip_monitor_path):
                zip_event_handler = ZipFileHandler(self)
                self.zip_file_observer = Observer()
                self.zip_file_observer.schedule(zip_event_handler, self.zip_monitor_path, recursive=False)
                self.zip_file_observer.start()
                print("Zip monitoring service started.")
            
            if self.apk_monitor_path and os.path.exists(self.apk_monitor_path):
                apk_event_handler = ApkFileHandler(self)
                self.apk_file_observer = Observer()
                self.apk_file_observer.schedule(apk_event_handler, self.apk_monitor_path, recursive=False)
                self.apk_file_observer.start()
                print("APK monitoring service started.")

    def _scan_existing_apk_files(self):
        """Scans the APK monitor path for existing files on startup."""
        if not self.apk_monitor_path or not os.path.exists(self.apk_monitor_path):
            return 

        print(f"Scanning for existing APKs in: {self.apk_monitor_path}")
        try:
            for filename in os.listdir(self.apk_monitor_path):
                if filename.endswith(".apk"):
                    filepath = os.path.join(self.apk_monitor_path, filename)
                    if filepath not in self.apk_file_map and filepath not in self.apk_processing_files:
                        print(f"Found existing APK: {filepath}")
                        self._add_apk_to_monitor(filepath)
        except Exception as e:
            print(f"Error scanning existing APKs: {e}")

    # --- Zip Service Methods ---
    def _clear_zip_monitor(self):
        """Clears the Zip monitor list and resets the state."""
        print("Clearing Zip Monitor...")
        try:
            for item in self.zip_tree.get_children():
                self.zip_tree.delete(item)
        except Exception as e:
            print(f"Error clearing Zip tree: {e}")
        
        self.zip_processed_count = 0
        self.zip_file_map.clear()
        self.processing_files.clear()
        
        try:
            self.zip_count_label.config(text="Total Files Processed: 0")
        except Exception as e:
            print(f"Error resetting Zip count label: {e}")

    def _add_zip_to_monitor(self, filepath):
        import tkinter as tk
        filename = os.path.basename(filepath)
        
        if filepath in self.processing_files: return
        self.processing_files.add(filepath)
        
        item_id = self.zip_tree.insert('', tk.END, values=(filename, 'Pending'), tags=('pending',))
        self.zip_file_map[filepath] = item_id
        threading.Thread(target=self.process_zip_file, args=(filepath,), daemon=True).start()

    def _update_zip_status(self, item_id, status):
        try:
            if not self.zip_tree.exists(item_id): return
            filename = self.zip_tree.item(item_id, 'values')[0]
            if status == "Processing":
                self.zip_tree.item(item_id, values=(filename, 'Processing'), tags=('processing',))
            elif status == "Done":
                self.zip_tree.item(item_id, values=(filename, 'Done'), tags=('done',))
                self.zip_processed_count += 1
                self.zip_count_label.config(text=f"Total Files Processed: {self.zip_processed_count}")
            elif status == "Error":
                self.zip_tree.item(item_id, values=(filename, 'Error'), tags=('error',))
        except Exception as e:
            print(f"Error updating zip status in UI: {e}")

    def _remove_from_processing_list(self, filepath):
        if filepath in self.processing_files:
            self.processing_files.remove(filepath)

    def process_zip_file(self, zip_path):
        item_id = self.zip_file_map.get(zip_path)
        if not item_id:
            print(f"Error: Could not find item_id for {zip_path}")
            return

        self.master.after(0, self._update_zip_status, item_id, "Processing")
        
        for _ in range(5):
            try:
                with open(zip_path, 'rb') as f: pass 
                break 
            except PermissionError: 
                time.sleep(1) 
            except FileNotFoundError:
                print(f"File {zip_path} disappeared while waiting, aborting.")
                self.master.after(0, self._remove_from_processing_list, zip_path)
                return
        else: 
            print(f"Failed to access file {zip_path} after 5 seconds, skipping.")
            self.master.after(0, self._update_zip_status, item_id, "Error")
            self.master.after(0, self._remove_from_processing_list, zip_path)
            return

        temp_extract_dir = os.path.join(self.base_path, "tmp", f"extract_{os.path.basename(zip_path)}")
        original_filename_with_ext = os.path.basename(zip_path)
        original_dir = os.path.dirname(zip_path)
        
        try:
            # --- RENAMING LOGIC ---
            filename_no_ext = original_filename_with_ext.replace('.zip', '')
            filename_parts = filename_no_ext.split('-')
            new_zip_path = zip_path
            
            if len(filename_parts) == 5: # This is the "short" name we need to fix
                part_prefix = filename_parts[0]  # PTG
                part_branch = filename_parts[1]  # 3081
                part_zero = filename_parts[2]    # 0000
                part_date = filename_parts[3]    # 251105
                part_time = filename_parts[4]    # 195912
                part_export_date = time.strftime("%y%m%d") 
                new_filename = f"{part_prefix}-{part_branch}-{part_zero}-{part_date}-{part_export_date}-{part_time}.zip"
                new_zip_path = os.path.join(original_dir, new_filename)
                print(f"Original name: {original_filename_with_ext}, New name: {new_filename}")
            
            elif len(filename_parts) == 6: # It's already in the correct format
                print(f"Filename {original_filename_with_ext} is already in the correct format.")
                new_zip_path = zip_path
            
            else: # Unknown format
                print(f"Warning: Unknown filename format '{original_filename_with_ext}'. Re-zipping with original name.")
                new_zip_path = zip_path
            # --- END RENAMING LOGIC ---

            # 1. Unzip
            os.makedirs(temp_extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)
            print(f"Unzipped '{original_filename_with_ext}'")

            # 2. Delete original
            os.remove(zip_path)
            print(f"Removed original: {zip_path}")

            # 3. Re-zip with the NEW name, adding directory entries
            with zipfile.ZipFile(new_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
                for root, dirs, files in os.walk(temp_extract_dir):
                    # Add directory entries
                    for d in dirs:
                        dir_path = os.path.join(root, d)
                        arcname = os.path.relpath(dir_path, temp_extract_dir)
                        arcname = arcname.replace(os.path.sep, '/') + '/'
                        
                        zinfo = zipfile.ZipInfo(arcname)
                        zinfo.create_system = 3 # Unix
                        zinfo.external_attr = (0o755 << 16) | 0x10 # 0x10 is directory flag
                        zinfo.compress_type = zipfile.ZIP_DEFLATED
                        zip_ref.writestr(zinfo, "")
                        
                    # Now, add all files in this directory
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_extract_dir) 
                        arcname = arcname.replace(os.path.sep, '/') 
                        
                        zinfo = zipfile.ZipInfo.from_file(file_path, arcname)
                        zinfo.create_system = 3 
                        zinfo.external_attr = (0o644 << 16) 
                        
                        with open(file_path, "rb") as source:
                            zip_ref.writestr(zinfo, source.read()) 
            
            print(f"Successfully re-packaged to: {new_zip_path}")
            self.master.after(0, self._update_zip_status, item_id, "Done")

        except Exception as e:
            print(f"Error processing zip file {zip_path}: {e}")
            self.master.after(0, self._update_zip_status, item_id, "Error")
        
        finally:
            # 4. Clean up
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
            self.master.after(0, self._remove_from_processing_list, zip_path) 
            
    # --- APK Installer Methods ---
    def _clear_apk_monitor(self):
        """Clears the APK monitor list and resets the state."""
        print("Clearing APK Monitor...")
        # Clear the visual list
        try:
            for item in self.apk_tree.get_children():
                self.apk_tree.delete(item)
        except Exception as e:
            print(f"Error clearing APK tree (window might be closing): {e}")
        
        # Reset the internal tracking
        self.apk_processed_count = 0
        self.apk_file_map.clear()
        self.apk_processing_files.clear()
        
        try:
            self.apk_count_label.config(text="Total APKs Processed: 0")
        except Exception as e:
            print(f"Error resetting APK count label (window might be closing): {e}")

    def _add_apk_to_monitor(self, filepath):
        import tkinter as tk
        filename = os.path.basename(filepath)
        
        if filepath in self.apk_file_map:
             print(f"APK {filename} is already in the processing queue or done.")
             return
        
        self.apk_processing_files.add(filepath)
        
        item_id = self.apk_tree.insert('', tk.END, values=(filename, 'Pending'), tags=('pending',))
        self.apk_file_map[filepath] = item_id # Add to *session* lock
        threading.Thread(target=self._run_apk_install, args=(filepath, item_id), daemon=True).start()
        
    def _get_device_version(self, pkg_name):
        """Queries the connected device for the version code of a package."""
        if not self.connected_device:
            return 0
            
        try:
            device_id = self.connected_device
            command = [self.ADB_PATH, "-s", device_id, "shell", "dumpsys", "package", pkg_name]
            
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.stdout:
                for line in result.stdout.splitlines():
                    if "versionCode=" in line:
                        version_str = line.strip().split('versionCode=')[1]
                        version_code = int(version_str.split(' ')[0])
                        print(f"Found device version {version_code} for {pkg_name}")
                        return version_code
            
            print(f"Package {pkg_name} not found on device.")
            return 0 # Package not found
        except Exception as e:
            print(f"Error getting device version: {e}")
            return 0

    def _run_apk_install(self, apk_path, item_id):
        self.master.after(0, self._update_apk_status, item_id, "Checking...")
        
        # 1. Wait for file to be accessible
        for _ in range(5):
            try:
                with open(apk_path, 'rb') as f: pass
                break
            except PermissionError:
                time.sleep(1)
            except FileNotFoundError:
                print(f"APK {apk_path} disappeared, aborting.")
                self.master.after(0, self._update_apk_status, item_id, "Error: File disappeared")
                self.master.after(0, self._remove_from_apk_processing_list, apk_path)
                return
        else:
            print(f"Failed to access file {apk_path} after 5 seconds, skipping.")
            self.master.after(0, self._update_apk_status, item_id, "Error: File locked")
            self.master.after(0, self._remove_from_apk_processing_list, apk_path)
            return

        # 2. Parse APK for package name and version
        try:
            apk = APK(apk_path)
            pkg_name = apk.package
            pc_version = int(apk.version_code)
            print(f"PC APK '{os.path.basename(apk_path)}' is {pkg_name} v{pc_version}")
        except Exception as e:
            print(f"Error parsing APK: {e}")
            self.master.after(0, self._update_apk_status, item_id, "Error: Invalid APK")
            self.master.after(0, self._remove_from_apk_processing_list, apk_path)
            return
            
        # 3. Wait for a device to be connected (up to 10 sec)
        wait_time = 0
        while not self.connected_device and self.is_running and wait_time < 10:
            print(f"APK Install: Waiting for device... ({wait_time}s)")
            self.master.after(0, self._update_apk_status, item_id, "Waiting for device...")
            time.sleep(1)
            wait_time += 1

        if not self.connected_device:
            print("APK Install: Timed out waiting for device.")
            self.master.after(0, self._update_apk_status, item_id, "Error: No device")
            self.master.after(0, self._remove_from_apk_processing_list, apk_path)
            return
            
        # 4. Get version from device
        device_version = self._get_device_version(pkg_name)
        
        # 5. Compare and decide
        try:
            install_needed = False
            install_reason = ""
            status_tag = ""
            
            if device_version == 0:
                install_needed = True
                install_reason = f"Installing (v{pc_version})..."
            elif pc_version > device_version:
                install_needed = True
                install_reason = f"Upgrading (v{device_version} -> v{pc_version})..."
            elif pc_version == device_version:
                status_tag = f"Skipped (v{pc_version} installed)"
            else: # pc_version < device_version
                status_tag = f"Skipped (Newer v{device_version})"
                
            if install_needed:
                self.master.after(0, self._update_apk_status, item_id, install_reason)
                device_id = self.connected_device
                command = [self.ADB_PATH, "-s", device_id, "install", "-r", apk_path]
                
                result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
                
                if "Success" in result.stdout:
                    self.master.after(0, self._update_apk_status, item_id, "Success")
                else:
                    error_message = (result.stdout or result.stderr).strip().split('\n')[-1]
                    if not error_message: error_message = "Unknown error"
                    self.master.after(0, self._update_apk_status, item_id, f"Error: {error_message}")
            elif status_tag:
                 self.master.after(0, self._update_apk_status, item_id, status_tag)
            
        except Exception as e:
            self.master.after(0, self._update_apk_status, item_id, f"Error: {e}")
        finally:
            self.master.after(0, self._remove_from_apk_processing_list, apk_path)
            
    def _update_apk_status(self, item_id, status_message):
        try:
            if not self.apk_tree.exists(item_id):
                return
                
            filename = self.apk_tree.item(item_id, 'values')[0]
            
            if "Processing" in status_message or "Installing" in status_message or "Upgrading" in status_message or "Waiting" in status_message:
                self.apk_tree.item(item_id, values=(filename, status_message), tags=('processing',))
            elif "Success" in status_message:
                self.apk_tree.item(item_id, values=(filename, 'Done'), tags=('done',))
                self.apk_processed_count += 1
                self.apk_count_label.config(text=f"Total APKs Processed: {self.apk_processed_count}")
            elif "Skipped" in status_message:
                self.apk_tree.item(item_id, values=(filename, status_message), tags=('skipped',))
            else: # Any other message is an error
                self.apk_tree.item(item_id, values=(filename, status_message), tags=('error',))
        except Exception as e:
            print(f"Error updating APK status in UI (item may be gone): {e}")
            
    def _remove_from_apk_processing_list(self, filepath):
        """Removes an APK from the processing set once done/failed."""
        if filepath in self.apk_processing_files:
            self.apk_processing_files.remove(filepath)
            
    # --- NEW: Screen Streaming Methods ---
    def _start_stream(self):
        """Starts the scrcpy stream and embeds it."""
        from tkinter import messagebox
        if not self.connected_device:
            self.stream_status_label.config(text="Error: No device connected.")
            return
        
        if self.scrcpy_process:
            print("Stream already running.")
            return
            
        if not os.path.exists(self.SCRCPY_PATH):
            print(f"scrcpy not found at: {self.SCRCPY_PATH}")
            messagebox.showerror("Stream Error", f"scrcpy.exe not found.\nPlease ensure it is in the 'scrcpy' folder.")
            self.stream_status_label.config(text="Error: scrcpy.exe not found.")
            return

        print("Starting stream...")
        self.stream_status_label.config(text="Starting stream, please wait...")
        
        # --- FIX: Set ADB environment variable for scrcpy ---
        # 1. Copy the current environment
        env = os.environ.copy()
        # 2. Tell scrcpy EXACTLY where our adb.exe is
        env['ADB'] = self.ADB_PATH
        # --- END FIX ---

        # Launch scrcpy in a new process
        # --window-title is crucial for finding the window
        self.scrcpy_process = subprocess.Popen([
            self.SCRCPY_PATH,
            "-s", self.connected_device,
            "--window-title=HHT_STREAM",
            "--max-size=580", # Resized to fit new frame
            "--window-x=0", "--window-y=0",
            "--window-borderless"
        ], creationflags=subprocess.CREATE_NO_WINDOW, env=env) # Pass the modified env
        
        # Start a thread to find and embed the window
        threading.Thread(target=self._embed_stream_window, daemon=True).start()

    def _embed_stream_window(self):
        """Worker thread to find the scrcpy window and embed it."""
        try:
            # Find the window handle (HWND) using the title we set
            hwnd = 0
            retries = 10 # Try for 5 seconds
            while hwnd == 0 and retries > 0 and self.is_running and self.current_tab == 'stream':
                hwnd = ctypes.windll.user32.FindWindowW(None, "HHT_STREAM")
                if hwnd == 0:
                    retries -= 1
                    time.sleep(0.5)
            
            if hwnd == 0:
                print("Could not find HHT_STREAM window. Aborting embed.")
                if self.is_running:
                    self.stream_status_label.config(text="Error: Could not start stream. Try reconnecting device.")
                self._stop_stream()
                return

            # Get the handle (ID) of our Tkinter frame
            frame_id = self.stream_embed_frame.winfo_id()

            # --- NEW: Get actual window size to prevent black bars ---
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            
            # Container dimensions (padx=20*2=40, width=390. 390-40=350)
            container_width = 350
            container_height = 580 # Based on frame height
            
            if width > container_width:
                height = int(height * (container_width / width))
                width = container_width
            
            if height > container_height:
                width = int(width * (container_height / height))
                height = container_height
            
            print(f"scrcpy window found. Resizing frame to: {width}x{height}")
            
            # Resize our black embed frame to match the window size
            self.stream_embed_frame.config(width=width, height=height)
            # --- END NEW ---
            
            # Re-parent the scrcpy window into our frame
            ctypes.windll.user32.SetParent(hwnd, frame_id)
            
            # Move it to the top-left corner of the frame and resize
            ctypes.windll.user32.MoveWindow(hwnd, 0, 0, width, height, True)
            
            print(f"Successfully embedded stream window {hwnd} into frame {frame_id}")
            if self.is_running:
                self.stream_status_label.config(text=f"Streaming device: {self.connected_device}")

        except Exception as e:
            print(f"Error embedding window: {e}")
            if self.is_running: # Only update label if app is not closing
                self.stream_status_label.config(text="Error: Failed to embed stream.")

    def _stop_stream(self):
        """Stops the scrcpy stream process if it's running."""
        if self.scrcpy_process:
            print("Stopping stream...")
            self.scrcpy_process.terminate()
            self.scrcpy_process = None
            if self.is_running: # Check if app is still running
                self.stream_status_label.config(text="Stream stopped.")

    # --- Application Exit Method ---
    def on_app_quit(self):
        self.is_running = False
        self._auto_save_log()
        self._stop_stream() # Stop stream on quit
        
        if self.zip_file_observer:
            self.zip_file_observer.stop()
            self.zip_file_observer.join()
            print("Zip monitoring service stopped.")

        if self.apk_file_observer:
            self.apk_file_observer.stop()
            self.apk_file_observer.join()
            print("APK monitoring service stopped.")

        if self.tray_icon: self.tray_icon.stop()
        if self.api_process: self.api_process.terminate()
        
        if self.connected_device:
            try:
                subprocess.run([self.ADB_PATH, "-s", self.connected_device, "reverse", "--remove", "tcp:8000"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception as e: print(f"Could not disconnect on exit: {e}")
        
        try:
            if os.path.exists(self.lock_file_path): os.remove(self.lock_file_path)
        except Exception as e: print(f"Could not remove lock file: {e}")

        self.master.destroy()

# --- Main Execution Block ---
if __name__ == "__main__":
    import tkinter as tk
    from tkinter import messagebox
    from PIL import Image
    import pystray
    import ctypes
    import psutil

    # --- Robust Single-Instance Check ---
    temp_dir = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp')
    lock_file = os.path.join(temp_dir, 'hht_android_connect.lock')

    if os.path.exists(lock_file):
        try:
            with open(lock_file, 'r') as f: pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                messagebox.showinfo("Already Running", "HHT Android Connect is already running in the system tray.")
                sys.exit()
            else: print("Stale lock file found. The application will start.")
        except (IOError, ValueError): print("Corrupt lock file found. The application will start.")

    with open(lock_file, 'w') as f: f.write(str(os.getpid()))

    # --- Admin Check ---
    def is_admin():
        try: return ctypes.windll.shell32.IsUserAnAdmin()
        except: return False

    # --- Launch Application ---
    if is_admin():
        try:
            root = tk.Tk()
            app = App(root, lock_file_path=lock_file) 
            root.protocol('WM_DELETE_WINDOW', app.hide_window)
            initial_menu = app.create_tray_menu("Device: Disconnected", "API: Offline")
            icon = pystray.Icon("HHTAndroidConnect", app.icon_image, "HHT Android Connect", initial_menu)
            app.tray_icon = icon
            threading.Thread(target=icon.run, daemon=True).start()
            root.mainloop()
        except Exception as e:
            if os.path.exists(lock_file): os.remove(lock_file)
            messagebox.showerror("Application Error", f"An unexpected error occurred: {e}")
    else:
        if os.path.exists(lock_file): os.remove(lock_file)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)

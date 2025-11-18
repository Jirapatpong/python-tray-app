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
    draw.rectangle((18, 30, 46, 50), fill=color)
    return image

def create_windows_icon(color):
    """Generates a simple Windows logo icon."""
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 28, 28), fill=color)
    draw.rectangle((36, 8, 56, 28), fill=color)
    draw.rectangle((8, 36, 28, 56), fill=color)
    draw.rectangle((36, 36, 56, 56), fill=color)
    return image

def create_wifi_icon(color):
    """Generates a simple Wi-Fi icon."""
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.arc((10, 10, 54, 54), 200, 340, fill=color, width=4)
    draw.arc((16, 20, 48, 52), 210, 330, fill=color, width=4)
    draw.arc((22, 30, 42, 50), 220, 320, fill=color, width=4)
    draw.ellipse((28, 40, 36, 48), fill=color)
    return image

def create_log_icon(color):
    """Generates a simple log icon."""
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 12, 48, 52), outline=color, width=3)
    draw.line((22, 22, 42, 22), fill=color, width=2)
    draw.line((22, 30, 42, 30), fill=color, width=2)
    draw.line((22, 38, 36, 38), fill=color, width=2)
    return image

# --- Python Imaging Library (PIL) imports for icon generation ---
try:
    from PIL import Image, ImageTk
except ImportError:
    print("PIL (Pillow) is required for icon generation.")
    sys.exit(1)

# --- System Tray Imports ---
try:
    import pystray
except ImportError:
    print("pystray is required for system tray functionality.")
    sys.exit(1)

# --- Tkinter GUI ---
import tkinter as tk
from tkinter import ttk

# --- Lock File for Single Instance ---
LOCK_FILE = "hht_android_connect.lock"

class APKMonitorHandler(FileSystemEventHandler):
    """Watches the APK folder for new/updated APK files."""
    def __init__(self, callback_new_apk):
        super().__init__()
        self.callback_new_apk = callback_new_apk

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".apk"):
            self.callback_new_apk(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".apk"):
            self.callback_new_apk(event.src_path)

class ApiServerLogger(threading.Thread):
    """
    Reads stdout and stderr lines from the API server process
    and pushes them to the main thread via a thread-safe queue.
    """
    def __init__(self, process, log_queue):
        super().__init__(daemon=True)
        self.process = process
        self.log_queue = log_queue

    def run(self):
        # Read from stdout
        for line in iter(self.process.stdout.readline, ''):
            if line:
                self.log_queue.put(("API", line.rstrip("\n")))

        # Read from stderr
        for line in iter(self.process.stderr.readline, ''):
            if line:
                self.log_queue.put(("API_ERR", line.rstrip("\n")))

class HHTToolTip:
    """
    A small tooltip class to show hover text on widgets
    """
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tipwindow = None
        self.id = None

        widget.bind("<Enter>", self.on_enter)
        widget.bind("<Leave>", self.on_leave)

    def on_enter(self, event=None):
        self.schedule()

    def on_leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(self.delay, self.showtip)

    def unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def showtip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify="left",
                         background="#ffffe0", relief="solid", borderwidth=1,
                         font=("Segoe UI", 9))
        label.pack(ipadx=4)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

class App:
    def __init__(self, master):
        self.master = master
        master.title("HHT Android Connect")
        master.geometry("980x640")
        master.minsize(980, 640)

        # Application flags / state
        self.is_running = True
        self.current_tab = "adb"
        self.connected_device = None
        self.api_process = None
        self.api_log_queue = queue.Queue()
        self.api_log_thread = None
        self.scrcpy_process = None
        self.tray_icon = None
        self.log_observer = None
        self.log_handler = None
        self.monitoring_thread = None
        self.monitoring_thread_stop = threading.Event()
        self._stream_resize_bind_id = None  # used if you later bind <Configure>

        # For APK monitoring
        self.apk_file_observer = None
        self.apk_processing_files = set()

        # Paths / config
        self.base_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
        self.scrcpy_folder = os.path.join(self.base_dir, "scrcpy")
        self.scrcpy_config_file = os.path.join(self.base_dir, "config.ini")
        self.ADB_PATH = os.path.join(self.scrcpy_folder, "adb.exe")
        self.SCRCPY_PATH = os.path.join(self.scrcpy_folder, "scrcpy.exe")

        self.config = configparser.ConfigParser()
        self.config.read(self.scrcpy_config_file, encoding="utf-8")

        # UI setup
        self._load_config()
        self._build_ui()
        self._create_tray_icon()
        self._start_adb_monitor()
        self._start_api_log_reader()

        self.master.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------
    # Configuration loading/saving
    # ------------------------------
    def _load_config(self):
        # Load config, or create defaults
        if "SCRCPY" not in self.config:
            self.config["SCRCPY"] = {}
        if "PATHS" not in self.config:
            self.config["PATHS"] = {}
        if "VISUAL" not in self.config:
            self.config["VISUAL"] = {}
        if "HHT" not in self.config:
            self.config["HHT"] = {}

        scrcpy_section = self.config["SCRCPY"]
        paths_section = self.config["PATHS"]
        visual_section = self.config["VISUAL"]
        hht_section = self.config["HHT"]

        # PATHS
        self.apk_folder = paths_section.get("apk_folder", os.path.join(self.base_dir, "apk"))
        self.install_log_folder = paths_section.get("install_log_folder", os.path.join(self.base_dir, "log"))
        self.api_log_file = paths_section.get("api_log_file", os.path.join(self.base_dir, "server_log.txt"))
        self.monitor_log_file = paths_section.get("monitor_log_file", os.path.join(self.base_dir, "monitor_log.txt"))

        # SCRCPY
        self.scrcpy_bit_rate = scrcpy_section.get("bit_rate", "8M")
        self.scrcpy_max_fps = scrcpy_section.get("max_fps", "30")
        self.scrcpy_record = scrcpy_section.getboolean("record", False)
        self.scrcpy_record_folder = scrcpy_section.get("record_folder", os.path.join(self.base_dir, "recordings"))

        # HHT
        self.api_script = hht_section.get("api_script", os.path.join(self.base_dir, "start_hht_api.bat"))
        self.api_port = hht_section.get("api_port", "8000")
        self.api_host = hht_section.get("api_host", "127.0.0.1")

        # VISUAL
        self.theme_bg_color = visual_section.get("theme_bg_color", "#f0f0f0")
        self.theme_accent_color = visual_section.get("theme_accent_color", "#0078d4")
        self.theme_text_color = visual_section.get("theme_text_color", "#333333")

        self.log_file_limit_days = int(paths_section.get("log_file_limit_days", "7"))

    def _save_config(self):
        self.config["PATHS"]["apk_folder"] = self.apk_folder
        self.config["PATHS"]["install_log_folder"] = self.install_log_folder
        self.config["PATHS"]["api_log_file"] = self.api_log_file
        self.config["PATHS"]["monitor_log_file"] = self.monitor_log_file
        self.config["SCRCPY"]["bit_rate"] = self.scrcpy_bit_rate
        self.config["SCRCPY"]["max_fps"] = self.scrcpy_max_fps
        self.config["SCRCPY"]["record"] = str(self.scrcpy_record)
        self.config["SCRCPY"]["record_folder"] = self.scrcpy_record_folder
        self.config["VISUAL"]["theme_bg_color"] = self.theme_bg_color
        self.config["VISUAL"]["theme_accent_color"] = self.theme_accent_color
        self.config["VISUAL"]["theme_text_color"] = self.theme_text_color
        self.config["HHT"]["api_script"] = self.api_script
        self.config["HHT"]["api_port"] = self.api_port
        self.config["HHT"]["api_host"] = self.api_host
        self.config["PATHS"]["log_file_limit_days"] = str(self.log_file_limit_days)

        with open(self.scrcpy_config_file, "w", encoding="utf-8") as f:
            self.config.write(f)

    # ------------------------------
    # UI Construction
    # ------------------------------
    def _build_ui(self):
        self.master.configure(bg=self.theme_bg_color)

        # Top header
        header_frame = tk.Frame(self.master, bg=self.theme_bg_color)
        header_frame.pack(fill="x", padx=10, pady=10)

        title_label = tk.Label(
            header_frame,
            text="HHT Android Connect",
            font=("Segoe UI", 16, "bold"),
            bg=self.theme_bg_color,
            fg=self.theme_text_color,
        )
        title_label.pack(side="left")

        # Status area
        self.status_label = tk.Label(
            header_frame, text="Ready", font=("Segoe UI", 10),
            bg=self.theme_bg_color, fg=self.theme_text_color
        )
        self.status_label.pack(side="right")

        # Notebook (tabs)
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=(0, 10))

        # Create tabs
        self.adb_tab = tk.Frame(self.notebook, bg="white")
        self.stream_tab = tk.Frame(self.notebook, bg="white")
        self.log_tab = tk.Frame(self.notebook, bg="white")

        self.notebook.add(self.adb_tab, text="ADB & APK")
        self.notebook.add(self.stream_tab, text="Screen Stream")
        self.notebook.add(self.log_tab, text="Logs & Monitor")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Build each tab
        self._build_adb_tab()
        self._build_stream_tab()
        self._build_log_tab()

    # ------------------------------
    # ADB & APK tab
    # ------------------------------
    def _build_adb_tab(self):
        # Left side: device list / connect
        left_frame = tk.Frame(self.adb_tab, bg="white")
        left_frame.pack(side="left", fill="y", padx=10, pady=10)

        device_label = tk.Label(
            left_frame, text="Connected Devices", font=("Segoe UI", 11, "bold"), bg="white"
        )
        device_label.pack(anchor="w")

        self.device_listbox = tk.Listbox(
            left_frame, height=10, width=30,
            font=("Segoe UI", 10)
        )
        self.device_listbox.pack(fill="y", pady=(5, 5))

        refresh_button = tk.Button(
            left_frame,
            text="Refresh Devices",
            command=self._refresh_devices,
            bg=self.theme_accent_color,
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=6,
            pady=3,
        )
        refresh_button.pack(fill="x", pady=(0, 5))

        connect_button = tk.Button(
            left_frame,
            text="Connect",
            command=self._connect_device,
            bg="#28a745",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=6,
            pady=3,
        )
        connect_button.pack(fill="x", pady=(0, 5))

        disconnect_button = tk.Button(
            left_frame,
            text="Disconnect",
            command=self._disconnect_device,
            bg="#dc3545",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=6,
            pady=3,
        )
        disconnect_button.pack(fill="x")

        # Right side: APK folder, API server, etc
        right_frame = tk.Frame(self.adb_tab, bg="white")
        right_frame.pack(side="right", expand=True, fill="both", padx=10, pady=10)

        path_group = tk.LabelFrame(
            right_frame,
            text="APK & Log Configuration",
            font=("Segoe UI", 10, "bold"),
            bg="white"
        )
        path_group.pack(fill="x", pady=(0, 10))

        # APK folder
        apk_label = tk.Label(path_group, text="APK Folder:", bg="white")
        apk_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.apk_folder_var = tk.StringVar(value=self.apk_folder)
        apk_entry = tk.Entry(path_group, textvariable=self.apk_folder_var, width=50)
        apk_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        apk_browse = tk.Button(
            path_group,
            text="Browse...",
            command=self._browse_apk_folder,
            bg="#e0e0e0",
            relief="flat",
        )
        apk_browse.grid(row=0, column=2, padx=5, pady=5)

        # Install log folder
        log_label = tk.Label(path_group, text="Install Log Folder:", bg="white")
        log_label.grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.install_log_var = tk.StringVar(value=self.install_log_folder)
        log_entry = tk.Entry(path_group, textvariable=self.install_log_var, width=50)
        log_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        log_browse = tk.Button(
            path_group,
            text="Browse...",
            command=self._browse_install_log_folder,
            bg="#e0e0e0",
            relief="flat",
        )
        log_browse.grid(row=1, column=2, padx=5, pady=5)

        # API server config
        api_group = tk.LabelFrame(
            right_frame,
            text="HHT API Server",
            font=("Segoe UI", 10, "bold"),
            bg="white"
        )
        api_group.pack(fill="x")

        script_label = tk.Label(api_group, text="Start Script (.bat):", bg="white")
        script_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.api_script_var = tk.StringVar(value=self.api_script)
        script_entry = tk.Entry(api_group, textvariable=self.api_script_var, width=50)
        script_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        script_browse = tk.Button(
            api_group,
            text="Browse...",
            command=self._browse_api_script,
            bg="#e0e0e0",
            relief="flat",
        )
        script_browse.grid(row=0, column=2, padx=5, pady=5)

        port_label = tk.Label(api_group, text="Port:", bg="white")
        port_label.grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.api_port_var = tk.StringVar(value=self.api_port)
        port_entry = tk.Entry(api_group, textvariable=self.api_port_var, width=10)
        port_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        host_label = tk.Label(api_group, text="Host:", bg="white")
        host_label.grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.api_host_var = tk.StringVar(value=self.api_host)
        host_entry = tk.Entry(api_group, textvariable=self.api_host_var, width=20)
        host_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        start_api_button = tk.Button(
            api_group,
            text="Start API Server",
            command=self._start_api_server,
            bg="#28a745",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )
        start_api_button.grid(row=3, column=0, padx=5, pady=8, sticky="w")

        stop_api_button = tk.Button(
            api_group,
            text="Stop API Server",
            command=self._stop_api_server,
            bg="#dc3545",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )
        stop_api_button.grid(row=3, column=1, padx=5, pady=8, sticky="w")

        save_config_button = tk.Button(
            right_frame,
            text="Save Configuration",
            command=self._save_config_changes,
            bg="#0078d4",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )
        save_config_button.pack(anchor="e", pady=(10, 0))

        # Device status line
        self.device_status_label = tk.Label(
            right_frame,
            text="No device connected.",
            bg="white",
            fg=self.theme_text_color,
            anchor="w",
        )
        self.device_status_label.pack(fill="x", pady=(10, 0))

        # APK list / install status
        apk_list_frame = tk.LabelFrame(
            right_frame,
            text="APK Install Queue & Status",
            font=("Segoe UI", 10, "bold"),
            bg="white"
        )
        apk_list_frame.pack(fill="both", expand=True, pady=(10, 0))

        columns = ("apk_name", "package_name", "version", "status")
        self.apk_tree = ttk.Treeview(
            apk_list_frame,
            columns=columns,
            show="headings",
            height=10,
        )
        for col in columns:
            self.apk_tree.heading(col, text=col.replace("_", " ").title())
        self.apk_tree.column("apk_name", width=200)
        self.apk_tree.column("package_name", width=250)
        self.apk_tree.column("version", width=80)
        self.apk_tree.column("status", width=120)

        self.apk_tree.pack(fill="both", expand=True, pady=5)

        self._load_existing_apks()

    # ------------------------------
    # Stream tab
    # ------------------------------
    def _build_stream_tab(self):
        # Left side: instructions and controls
        left_frame = tk.Frame(self.stream_tab, bg="white")
        left_frame.pack(side="left", fill="y", padx=10, pady=10)

        title = tk.Label(
            left_frame,
            text="Device Screen Stream",
            font=("Segoe UI", 12, "bold"),
            bg="white",
            fg=self.theme_text_color,
        )
        title.pack(anchor="w")

        desc = tk.Label(
            left_frame,
            text=(
                "This will mirror the connected device screen.\n"
                "Requires scrcpy in the 'scrcpy' folder.\n"
                "Stream area auto-fits the available height."
            ),
            bg="white",
            justify="left",
        )
        desc.pack(anchor="w", pady=(5, 10))

        start_stream_btn = tk.Button(
            left_frame,
            text="Start Screen Stream",
            command=self._start_stream,
            bg="#28a745",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )
        start_stream_btn.pack(fill="x", pady=(0, 5))

        stop_stream_btn = tk.Button(
            left_frame,
            text="Stop Screen Stream",
            command=self._stop_stream,
            bg="#dc3545",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )
        stop_stream_btn.pack(fill="x")

        self.stream_status_label = tk.Label(
            left_frame,
            text="Stream idle.",
            bg="white",
            fg=self.theme_text_color,
        )
        self.stream_status_label.pack(anchor="w", pady=(10, 0))

        # Right side: the embed area
        right_frame = tk.Frame(self.stream_tab, bg="#f0f0f0")
        right_frame.pack(side="right", expand=True, fill="both", padx=10, pady=10)

        # A frame that will hold the scrcpy window
        self.stream_embed_frame = tk.Frame(right_frame, bg="black")
        self.stream_embed_frame.pack(
            expand=True,
            fill="both",
            padx=20,
            pady=20
        )

        # A label for overlay text or instructions
        self.stream_overlay_label = tk.Label(
            self.stream_embed_frame,
            text="Screen stream will appear here when started.",
            bg="black",
            fg="white",
            font=("Segoe UI", 11)
        )
        self.stream_overlay_label.place(relx=0.5, rely=0.5, anchor="center")

    # ------------------------------
    # Logs tab
    # ------------------------------
    def _build_log_tab(self):
        top_frame = tk.Frame(self.log_tab, bg="white")
        top_frame.pack(fill="x", padx=10, pady=10)

        label = tk.Label(
            top_frame,
            text="API Server Logs",
            font=("Segoe UI", 12, "bold"),
            bg="white",
            fg=self.theme_text_color,
        )
        label.pack(anchor="w")

        self.api_log_text = tk.Text(
            self.log_tab,
            wrap="none",
            bg="#1e1e1e",
            fg="#ffffff",
            font=("Consolas", 9),
        )
        self.api_log_text.pack(expand=True, fill="both", padx=10, pady=(0, 10))

        # Monitor config line
        monitor_frame = tk.Frame(self.log_tab, bg="white")
        monitor_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.monitor_label = tk.Label(
            monitor_frame,
            text=f"Monitor log: {self.monitor_log_file}",
            bg="white",
            fg=self.theme_text_color,
        )
        self.monitor_label.pack(side="left")

        browse_monitor_btn = tk.Button(
            monitor_frame,
            text="Browse Monitor Log",
            command=self._browse_monitor_log_file,
            bg="#e0e0e0",
            relief="flat",
        )
        browse_monitor_btn.pack(side="right")

    # ------------------------------
    # Tab changed handler
    # ------------------------------
    def _on_tab_changed(self, event):
        tab = event.widget.tab("current")["text"]
        if tab == "ADB & APK":
            self.current_tab = "adb"
        elif tab == "Screen Stream":
            self.current_tab = "stream"
        else:
            self.current_tab = "logs"

    # ------------------------------
    # Device + ADB handling
    # ------------------------------
    def _start_adb_monitor(self):
        self._refresh_devices()
        self.master.after(5000, self._start_adb_monitor)

    def _refresh_devices(self):
        if not os.path.exists(self.ADB_PATH):
            self.device_status_label.config(text="adb.exe not found. Check 'scrcpy' folder.")
            return
        try:
            result = subprocess.run(
                [self.ADB_PATH, "devices"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            lines = result.stdout.splitlines()
            lines = lines[1:]
            devices = []
            for line in lines:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "device":
                        devices.append(parts[0])

            self.device_listbox.delete(0, tk.END)
            for d in devices:
                self.device_listbox.insert(tk.END, d)

            if devices:
                status = f"Detected devices: {', '.join(devices)}"
            else:
                status = "No devices detected. Connect your device via USB."

            self.device_status_label.config(text=status)

        except Exception as e:
            self.device_status_label.config(text=f"Error listing devices: {e}")

    def _connect_device(self):
        selection = self.device_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Device Selected", "Please select a device from the list.")
            return
        device_id = self.device_listbox.get(selection[0])
        self.connected_device = device_id
        self.device_status_label.config(text=f"Connected to device: {device_id}")
        self.status_label.config(text=f"Device: {device_id}")

    def _disconnect_device(self):
        self.connected_device = None
        self.device_status_label.config(text="No device connected.")
        self.status_label.config(text="Ready")

    # ------------------------------
    # Folder / path selection
    # ------------------------------
    def _browse_apk_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.apk_folder = folder
            self.apk_folder_var.set(folder)
            self._save_config()

    def _browse_install_log_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.install_log_folder = folder
            self.install_log_var.set(folder)
            self._save_config()

    def _browse_api_script(self):
        path = filedialog.askopenfilename(
            title="Select API start script (.bat)",
            filetypes=[("Batch Files", "*.bat"), ("All Files", "*.*")]
        )
        if path:
            self.api_script = path
            self.api_script_var.set(path)
            self._save_config()

    def _browse_monitor_log_file(self):
        path = filedialog.askopenfilename(
            title="Select monitor log file",
            filetypes=[("Log Files", "*.log *.txt"), ("All Files", "*.*")]
        )
        if path:
            self.monitor_log_file = path
            self.monitor_label.config(text=f"Monitor log: {path}")
            self._save_config()

    def _save_config_changes(self):
        self.apk_folder = self.apk_folder_var.get()
        self.install_log_folder = self.install_log_var.get()
        self.api_script = self.api_script_var.get()
        self.api_port = self.api_port_var.get()
        self.api_host = self.api_host_var.get()
        self._save_config()
        messagebox.showinfo("Configuration Saved", "Your configuration has been saved.")

    # ------------------------------
    # API server
    # ------------------------------
    def _start_api_server(self):
        if self.api_process and self.api_process.poll() is None:
            messagebox.showinfo("API Server", "API server is already running.")
            return

        if not self.api_script or not os.path.exists(self.api_script):
            messagebox.showerror("API Script Not Found", "Please configure a valid API start script (.bat).")
            return

        try:
            self.api_process = subprocess.Popen(
                [self.api_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.api_log_thread = ApiServerLogger(self.api_process, self.api_log_queue)
            self.api_log_thread.start()
            self.status_label.config(text="API Server: Running")
        except Exception as e:
            messagebox.showerror("API Server Error", f"Could not start API server:\n{e}")

    def _stop_api_server(self):
        if self.api_process and self.api_process.poll() is None:
            self.api_process.terminate()
            self.api_process = None
            self.status_label.config(text="API Server: Stopped")

    def _start_api_log_reader(self):
        while True:
            try:
                source, line = self.api_log_queue.get_nowait()
                self._append_api_log_line(source, line)
            except queue.Empty:
                break
        self.master.after(200, self._start_api_log_reader)

    def _append_api_log_line(self, source, line):
        if not line:
            return
        prefix = "[API]" if source == "API" else "[API_ERR]"
        self.api_log_text.insert(tk.END, f"{prefix} {line}\n")
        self.api_log_text.see(tk.END)

    # ------------------------------
    # APK monitoring
    # ------------------------------
    def _load_existing_apks(self):
        if not os.path.isdir(self.apk_folder):
            return

        for fname in os.listdir(self.apk_folder):
            if fname.lower().endswith(".apk"):
                full_path = os.path.join(self.apk_folder, fname)
                self._add_apk_to_tree(full_path, status="Pending")

        self._start_apk_monitor()

    def _start_apk_monitor(self):
        if self.apk_file_observer:
            self.apk_file_observer.stop()
            self.apk_file_observer.join()

        if not os.path.isdir(self.apk_folder):
            return

        event_handler = APKMonitorHandler(self._on_new_apk)
        self.apk_file_observer = Observer()
        self.apk_file_observer.schedule(event_handler, self.apk_folder, recursive=False)
        self.apk_file_observer.start()

    def _on_new_apk(self, filepath):
        if filepath in self.apk_processing_files:
            return
        self.apk_processing_files.add(filepath)
        self._add_apk_to_tree(filepath, status="Pending")
        threading.Thread(target=self._process_apk_install, args=(filepath,), daemon=True).start()

    def _add_apk_to_tree(self, filepath, status="Pending"):
        try:
            apk = APK(filepath)
            apk_name = os.path.basename(filepath)
            package_name = apk.package
            version_name = apk.version_name or ""
        except Exception:
            apk_name = os.path.basename(filepath)
            package_name = "Unknown"
            version_name = ""

        self.apk_tree.insert(
            "",
            tk.END,
            values=(apk_name, package_name, version_name, status),
            tags=(filepath,)
        )

    def _process_apk_install(self, filepath):
        if not self.connected_device:
            self._update_apk_status(filepath, "Failed (No device)")
            self._remove_from_apk_processing_list(filepath)
            return

        self._update_apk_status(filepath, "Installing...")
        self._ensure_install_log_folder()
        log_filename = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_install.log"
        log_path = os.path.join(self.install_log_folder, log_filename)

        cmd = [self.ADB_PATH, "-s", self.connected_device, "install", "-r", filepath]
        try:
            with open(log_path, "w", encoding="utf-8") as log_file:
                proc = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=log_file,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                proc.wait()

            if proc.returncode == 0:
                self._update_apk_status(filepath, f"Success (Log: {os.path.basename(log_path)})")
            else:
                self._update_apk_status(filepath, f"Failed (Log: {os.path.basename(log_path)})")
        except Exception as e:
            self._update_apk_status(filepath, f"Error: {e}")
        finally:
            self._remove_from_apk_processing_list(filepath)

    def _ensure_install_log_folder(self):
        os.makedirs(self.install_log_folder, exist_ok=True)

    def _update_apk_status(self, filepath, status):
        for item in self.apk_tree.get_children():
            tags = self.apk_tree.item(item, "tags")
            if filepath in tags:
                try:
                    values = list(self.apk_tree.item(item, "values"))
                    values[-1] = status
                    self.apk_tree.item(item, values=values)
                except Exception as e:
                    print(f"Error updating APK status in UI (item may be gone): {e}")
                break

    def _remove_from_apk_processing_list(self, filepath):
        if filepath in self.apk_processing_files:
            self.apk_processing_files.remove(filepath)

    # --- NEW: Screen Streaming Methods ---
    def _start_stream(self):
        """Starts the scrcpy stream and embeds it (auto fit height)."""
        from tkinter import messagebox
        if not self.connected_device:
            self.stream_status_label.config(text="Error: No device connected.")
            return

        if self.scrcpy_process:
            print("Stream already running.")
            return

        if not os.path.exists(self.SCRCPY_PATH):
            print(f"scrcpy not found at: {self.SCRCPY_PATH}")
            messagebox.showerror(
                "Stream Error",
                "scrcpy.exe not found.\nPlease ensure it is in the 'scrcpy' folder.",
            )
            self.stream_status_label.config(text="Error: scrcpy.exe not found.")
            return

        print("Starting stream...")
        self.stream_status_label.config(text="Starting stream, please wait...")

        # ให้ Tk คำนวณขนาด frame ล่าสุดก่อน (ใช้ความสูงของพื้นที่สีดำ)
        self.master.update_idletasks()
        frame_height = self.stream_embed_frame.winfo_height()
        if frame_height <= 0:
            frame_height = 540  # fallback เผื่อกรณียังไม่ได้วาด frame

        # Set ADB environment variable for scrcpy
        env = os.environ.copy()
        env["ADB"] = self.ADB_PATH

        # ใช้ --max-size = ความสูงของ frame → scrcpy จะ scale โดยยึดด้านยาวสุด = frame_height
        self.scrcpy_process = subprocess.Popen(
            [
                self.SCRCPY_PATH,
                "-s",
                self.connected_device,
                "--window-title=HHT_STREAM",
                "--max-size",
                str(frame_height),
                "--window-x=0",
                "--window-y=0",
                "--window-borderless",
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=env,
        )

        # Start a thread to find and embed the window
        threading.Thread(target=self._embed_stream_window, daemon=True).start()

    def _embed_stream_window(self):
        """Worker thread to find the scrcpy window and embed it."""
        try:
            # Find the window handle (HWND) using the title we set
            hwnd = 0
            retries = 10  # Try for 5 seconds
            while hwnd == 0 and retries > 0 and self.is_running and self.current_tab == "stream":
                hwnd = ctypes.windll.user32.FindWindowW(None, "HHT_STREAM")
                if hwnd == 0:
                    retries -= 1
                    time.sleep(0.5)

            if hwnd == 0:
                print("Could not find HHT_STREAM window. Aborting embed.")
                if self.is_running:
                    self.stream_status_label.config(
                        text="Error: Could not start stream. Try reconnecting device."
                    )
                self._stop_stream()
                return

            # Get the handle (ID) of our Tkinter frame
            frame_id = self.stream_embed_frame.winfo_id()

            # Get actual window size and center it
            self.master.update_idletasks()  # Ensure frame size is calculated
            frame_width = self.stream_embed_frame.winfo_width()
            frame_height = self.stream_embed_frame.winfo_height()

            # Get scrcpy window size
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            scrcpy_width = rect.right - rect.left
            scrcpy_height = rect.bottom - rect.top

            # Calculate aspect ratio to fit height
            if scrcpy_height <= 0:
                scrcpy_height = 1
            ratio = frame_height / scrcpy_height
            new_height = frame_height
            new_width = int(scrcpy_width * ratio)

            # Calculate offsets to center the window horizontally
            x_offset = (frame_width - new_width) // 2
            y_offset = (frame_height - new_height) // 2  # normally ~0

            # Re-parent the scrcpy window into our frame
            ctypes.windll.user32.SetParent(hwnd, frame_id)

            # Move it to the center of the frame and resize
            ctypes.windll.user32.MoveWindow(
                hwnd, x_offset, y_offset, new_width, new_height, True
            )

            print(f"Successfully embedded stream window {hwnd} into frame {frame_id}")
            if self.is_running:
                self.stream_status_label.config(
                    text=f"Streaming device: {self.connected_device}"
                )

        except Exception as e:
            print(f"Error embedding window: {e}")
            if self.is_running:
                self.stream_status_label.config(text="Error: Failed to embed stream.")

    def _stop_stream(self):
        """Stops the scrcpy stream process if it's running."""
        if self.scrcpy_process:
            print("Stopping stream...")
            self.scrcpy_process.terminate()
            self.scrcpy_process = None
            if self.is_running:
                try:
                    self.stream_status_label.config(text="Stream stopped.")
                except Exception:
                    pass

    # ------------------------------
    # Cleanup / Exit
    # ------------------------------
    def _on_close(self):
        self.is_running = False

        if self.apk_file_observer:
            self.apk_file_observer.stop()
            self.apk_file_observer.join()
            print("APK monitoring service stopped.")

        if self.tray_icon:
            self.tray_icon.stop()
        if self.api_process:
            self.api_process.terminate()

        if self.connected_device:
            try:
                subprocess.run(
                    [self.ADB_PATH, "-s", self.connected_device, "reverse", "--remove", "tcp:8000"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except Exception as e:
                print(f"Could not disconnect on exit: {e}")

        try:
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except Exception as e:
            print(f"Could not remove lock file: {e}")

        self.master.destroy()

    # ------------------------------
    # System Tray
    # ------------------------------
    def _create_tray_icon(self):
        try:
            android_img = create_android_icon(self.theme_accent_color)
            icon_image = android_img
            self.tray_icon = pystray.Icon(
                "hht_android_connect",
                icon_image,
                "HHT Android Connect",
                menu=pystray.Menu(
                    pystray.MenuItem(
                        "Show", self._on_tray_show
                    ),
                    pystray.MenuItem(
                        "Exit", self._on_tray_exit
                    )
                )
            )
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"Could not create system tray icon: {e}")

    def _on_tray_show(self, icon, item):
        self.master.after(0, self._restore_main_window)

    def _on_tray_exit(self, icon, item):
        self.master.after(0, self._on_close)

    def _restore_main_window(self):
        self.master.deiconify()
        self.master.lift()
        self.master.focus_force()

# ------------------------------
# Main entry
# ------------------------------
def main():
    if os.path.exists(LOCK_FILE):
        messagebox.showinfo(
            "Already Running",
            "HHT Android Connect is already running."
        )
        return

    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    main()

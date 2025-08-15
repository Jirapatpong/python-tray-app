import subprocess
import threading
import os
import sys
import time
import queue

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

class App:
    def __init__(self, master):
        import tkinter as tk
        from tkinter import ttk, messagebox
        from PIL import ImageTk

        self.master = master
        self.tray_icon = None
        self.is_running = True
        self.is_disconnecting = False
        self.api_process = None
        self.last_search_term = ""
        self.last_search_pos = "1.0"
        self.api_status = "Offline"

        master.title("HHT Android Connect")
        app_width, app_height = 750, 550
        screen_width, screen_height = master.winfo_screenwidth(), master.winfo_screenheight()
        master.geometry(f"{app_width}x{app_height}+{screen_width-app_width-40}+{screen_height-app_height-80}")
        master.configure(background='#F9F6F6')
        master.resizable(False, False)

        # --- ICON ---
        self.icon_image = create_android_icon('#B22222')
        icon_photo = ImageTk.PhotoImage(self.icon_image)
        master.iconphoto(True, icon_photo)

        # --- COLOR THEME ---
        self.COLOR_PRIMARY = "#B22222"  # Firebrick
        self.COLOR_PRIMARY_HOVER = "#9B1B1B"
        self.COLOR_SECONDARY = "#E57373"  # Soft red
        self.COLOR_BG = "#FFFFFF"
        self.COLOR_WINDOW_BG = "#F9F6F6"
        self.COLOR_TEXT = "#333333"
        self.COLOR_SELECTION = "#FFDADA"
        self.COLOR_ALT_ROW = "#FAF0F0"

        # --- STYLES ---
        self.style = ttk.Style()
        self.style.theme_use('clam')

        self.style.configure('.', background=self.COLOR_BG, foreground=self.COLOR_TEXT, font=('Segoe UI', 10))
        self.style.configure('TFrame', background=self.COLOR_BG)
        self.style.configure('Header.TLabel', font=('Segoe UI', 18, 'bold'), foreground=self.COLOR_TEXT, background=self.COLOR_WINDOW_BG)
        self.style.configure('Primary.TButton', font=('Segoe UI', 10, 'bold'), background=self.COLOR_PRIMARY, foreground='white', padding=(15, 8), relief='flat')
        self.style.map('Primary.TButton', background=[('active', self.COLOR_PRIMARY_HOVER)])
        self.style.configure('Secondary.TButton', font=('Segoe UI', 10, 'bold'), background=self.COLOR_BG, foreground=self.COLOR_TEXT, padding=(15, 8), relief='flat')
        self.style.map('Secondary.TButton', background=[('active', '#F0F0F0')])
        self.style.configure("Treeview.Heading", font=('Segoe UI', 10, 'bold'), background=self.COLOR_BG, padding=12)
        self.style.configure("Treeview", rowheight=40, font=('Consolas', 11), fieldbackground=self.COLOR_BG)
        self.style.map("Treeview", background=[('selected', self.COLOR_SELECTION)], foreground=[('selected', self.COLOR_TEXT)])
        self.style.configure('Tab.TButton', font=('Segoe UI', 10, 'bold'), background=self.COLOR_WINDOW_BG, borderwidth=0, relief='flat', padding=(15, 8))
        self.style.map('Tab.TButton', background=[('active', self.COLOR_BG)])

        self.ADB_PATH = self.get_adb_path()
        if not self.check_adb():
            messagebox.showerror("Error", "ADB not found.")
            master.quit()
            return
        self.start_adb_server()
        self.connected_device = None

        self.create_widgets()
        self.refresh_devices()
        self.update_tray_status()

        threading.Thread(target=self.device_monitor_loop, daemon=True).start()
        self.start_api_exe()

    def create_widgets(self):
        import tkinter as tk
        from tkinter import ttk, scrolledtext

        padded_frame = tk.Frame(self.master, background=self.COLOR_WINDOW_BG, padx=20, pady=20)
        padded_frame.pack(fill=tk.BOTH, expand=True)

        header_label = ttk.Label(padded_frame, text="HHT Android Connect", style='Header.TLabel')
        header_label.pack(anchor='w', pady=(0, 10), padx=10)

        # Tabs
        tab_frame = ttk.Frame(padded_frame, style='TFrame')
        tab_frame.pack(fill=tk.X, padx=10)
        self.device_tab_button = ttk.Button(tab_frame, text="Device Status", style='Tab.TButton', command=lambda: self.switch_tab('device'))
        self.device_tab_button.pack(side=tk.LEFT, padx=(0, 5))
        self.api_tab_button = ttk.Button(tab_frame, text="API Log", style='Tab.TButton', command=lambda: self.switch_tab('api'))
        self.api_tab_button.pack(side=tk.LEFT)

        # Content area
        self.content_frame = tk.Canvas(padded_frame, bg=self.COLOR_BG, highlightthickness=0)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.device_frame = ttk.Frame(self.content_frame, style='TFrame', padding=20)
        self.api_frame = ttk.Frame(self.content_frame, style='TFrame', padding=20)

        # Device buttons
        buttons_frame = ttk.Frame(self.device_frame, padding=(0, 20, 0, 0))
        buttons_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.refresh_button = ttk.Button(buttons_frame, text="Refresh Devices", command=self.refresh_devices, style='Secondary.TButton')
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 10))
        self.connect_button = ttk.Button(buttons_frame, text="Connect Selected", command=self.connect_device, style='Primary.TButton')
        self.connect_button.pack(side=tk.LEFT, padx=(0, 10))
        self.disconnect_button = ttk.Button(buttons_frame, text="Disconnect", command=self.disconnect_device, style='Secondary.TButton')
        self.disconnect_button.pack(side=tk.LEFT)
        self.disconnect_button.config(state='disabled')

        # Device Tree
        tree_frame = ttk.Frame(self.device_frame, padding=(0, 10, 0, 0))
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.device_tree = ttk.Treeview(tree_frame, columns=('device_id', 'status'), show='headings')
        self.device_tree.heading('device_id', text='DEVICE ID', anchor='w')
        self.device_tree.heading('status', text='STATUS', anchor='w')
        self.device_tree.column('device_id', anchor='w', width=400)
        self.device_tree.column('status', anchor='w', width=150)
        self.device_tree.tag_configure('connected', foreground="#20C997", font=('Segoe UI', 10, 'bold'))
        self.device_tree.tag_configure('disconnected', foreground="#DC3545", font=('Segoe UI', 10, 'bold'))
        self.device_tree.pack(fill=tk.BOTH, expand=True)
        self.device_tree.tag_configure('alt', background=self.COLOR_ALT_ROW)

        # API Status
        api_status_frame = ttk.Frame(self.api_frame, style='TFrame', padding=(0, 0, 0, 10))
        api_status_frame.pack(fill=tk.X)
        self.api_status_dot = tk.Canvas(api_status_frame, width=10, height=10, bg='red', highlightthickness=0)
        self.api_status_dot.pack(side=tk.LEFT, padx=(0, 5))
        self.api_status_label = ttk.Label(api_status_frame, text="API Status: Offline", font=('Segoe UI', 10, 'bold'), foreground='red')
        self.api_status_label.pack(side=tk.LEFT)
        self.refresh_api_button = ttk.Button(api_status_frame, text="Refresh API", command=self.refresh_api_exe, style='Secondary.TButton')
        self.refresh_api_button.pack(side=tk.RIGHT)

        # API Search & Log
        search_frame = ttk.Frame(self.api_frame, style='TFrame', padding=(0, 0, 0, 10))
        search_frame.pack(fill=tk.X)
        self.search_entry = ttk.Entry(search_frame, font=('Segoe UI', 10))
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        search_button = ttk.Button(search_frame, text="Search", command=self.search_api_logs, style='Secondary.TButton')
        search_button.pack(side=tk.LEFT)
        self.api_log_text = scrolledtext.ScrolledText(self.api_frame, wrap=tk.WORD, state='disabled', bg='#2B2B2B', fg='#EAEAEA', font=('Consolas', 10), relief='flat', borderwidth=0)
        self.api_log_text.pack(fill=tk.BOTH, expand=True)
        self.api_log_text.tag_config('search', background='yellow', foreground='black')
        self.api_log_text.tag_config('current_search', background='#FFA500', foreground='black')

        self.switch_tab('device')

    # --- rest of your methods unchanged (device handling, ADB, API process, tray icon, etc.) ---
    # copy-paste them from your working main.py

if __name__ == "__main__":
    import tkinter as tk
    from PIL import Image
    import pystray

    root = tk.Tk()
    app = App(root)
    app.icon_image.save('app_icon.ico')
    root.protocol('WM_DELETE_WINDOW', app.hide_window)
    initial_menu = app.create_tray_menu("🔴 Device: Disconnected", "🔴 API: Offline")
    icon = pystray.Icon("HHTAndroidConnect", create_android_icon('#B22222'), "HHT Android Connect", initial_menu)
    app.tray_icon = icon
    threading.Thread(target=icon.run, daemon=True).start()
    root.mainloop()

# This code has been verified to have correct indentation.
import subprocess
import threading
import os
import sys
import time
import queue

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

class App:
    def __init__(self, master, lock_file_path):
        import tkinter as tk
        from tkinter import ttk, messagebox, scrolledtext
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
        self.known_devices = set() # Set to track devices between scans

        master.title("HHT Android Connect")

        app_width = 560
        app_height = 360
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

        master.configure(background=self.COLOR_BG)

        self.icon_image = create_android_icon(self.COLOR_TEXT)
        icon_photo = ImageTk.PhotoImage(self.icon_image)
        master.iconphoto(True, icon_photo)

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
        
        self.style.configure('Tab.TButton', font=('Segoe UI', 10, 'bold'), padding=(15, 5), relief='raised', borderwidth=2)
        self.style.map('Tab.TButton',
                       background=[('selected', self.COLOR_3D_BG_ACTIVE), ('!selected', self.COLOR_3D_BG_INACTIVE)],
                       foreground=[('selected', 'white'), ('!selected', self.COLOR_TEXT)])

        self.style.configure('Raised.TButton', font=('Segoe UI', 9, 'bold'), padding=(10, 5), relief='raised',
                             background=self.COLOR_3D_BG_ACTIVE, foreground='white', borderwidth=2)
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

    def create_widgets(self):
        import tkinter as tk
        from tkinter import ttk, scrolledtext

        self.master.grid_rowconfigure(2, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        header_frame = tk.Frame(self.master, bg=self.COLOR_BG)
        header_frame.grid(row=0, column=0, sticky='ew', padx=20, pady=(15, 5))
        header_label = tk.Label(header_frame, text="HHT Android Connect", font=('Segoe UI', 16, 'bold'), bg=self.COLOR_BG, fg=self.COLOR_TEXT)
        header_label.pack(side='left')
        tab_container = tk.Frame(self.master, bg=self.COLOR_BG)
        tab_container.grid(row=1, column=0, sticky='ew', padx=20)
        self.device_tab_btn = ttk.Button(tab_container, text="Device Status", style='Tab.TButton', command=lambda: self.switch_tab('device'))
        self.device_tab_btn.pack(side='left')
        self.api_tab_btn = ttk.Button(tab_container, text="API Log", style='Tab.TButton', command=lambda: self.switch_tab('api'))
        self.api_tab_btn.pack(side='left', padx=1)
        shadow_dark = tk.Frame(self.master, bg=self.COLOR_SHADOW_DARK)
        shadow_dark.grid(row=2, column=0, sticky='nsew', padx=(22, 18), pady=(0, 18))
        shadow_light = tk.Frame(shadow_dark, bg=self.COLOR_SHADOW_LIGHT)
        shadow_light.pack(fill='both', expand=True, padx=(2, 0), pady=(2, 0))
        self.content_frame = tk.Frame(shadow_light, bg=self.COLOR_BG, padx=15, pady=15)
        self.content_frame.pack(fill='both', expand=True, padx=(0, 2), pady=(0, 2))
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.device_frame = tk.Frame(self.content_frame, bg=self.COLOR_BG)
        self.device_frame.grid(row=0, column=0, sticky='nsew')
        self.api_frame = tk.Frame(self.content_frame, bg=self.COLOR_BG)
        self.api_frame.grid(row=0, column=0, sticky='nsew')
        self.device_frame.grid_rowconfigure(0, weight=1)
        self.device_frame.grid_columnconfigure(0, weight=1)
        self.device_tree = ttk.Treeview(self.device_frame, columns=('device_id', 'status'), show='headings')
        self.device_tree.heading('device_id', text='DEVICE ID', anchor='w')
        self.device_tree.heading('status', text='STATUS', anchor='w')
        self.device_tree.column('device_id', anchor='w', width=250)
        self.device_tree.column('status', anchor='center', width=100)
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
        save_log_button = ttk.Button(api_header_frame, text="Save Log", style='Raised.TButton', command=self.save_api_log)
        save_log_button.grid(row=0, column=4, sticky='e', padx=(0, 5))
        self.refresh_api_button = ttk.Button(api_header_frame, text="Restart API", style='Raised.TButton', command=self.refresh_api_exe)
        self.refresh_api_button.grid(row=0, column=5, sticky='e')

        log_frame = tk.Frame(self.api_frame, bg=self.COLOR_SHADOW_DARK, bd=0)
        log_frame.grid(row=1, column=0, sticky='nsew')
        self.api_log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', bg=self.COLOR_BG, fg=self.COLOR_TEXT, font=('Consolas', 8), relief='flat', bd=2, highlightthickness=0)
        self.api_log_text.pack(fill='both', expand=True, padx=2, pady=2)
        self.api_log_text.tag_config('search', background=self.COLOR_ACCENT, foreground='white')
        self.api_log_text.tag_config('current_search', background='#F59E0B', foreground='black')
        self.switch_tab('device')

    def save_api_log(self):
        from tkinter import messagebox
        try:
            raw_log_content = self.api_log_text.get("1.0", "end-1c")

            if not raw_log_content.strip():
                messagebox.showinfo("Log Empty", "The API log is empty. Nothing to save.")
                return

            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))
            
            log_dir = os.path.join(base_path, "log")
            os.makedirs(log_dir, exist_ok=True)

            timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"api_log_{timestamp}.txt"
            filepath = os.path.join(log_dir, filename)

            formatted_content = self._format_sql_log(raw_content)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(formatted_content)
            
            messagebox.showinfo("Success", f"Log saved successfully to:\n{filepath}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save log file.\n\nError: {e}")

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
        self.device_tab_btn.state(['!selected'])
        self.api_tab_btn.state(['!selected'])
        if tab_name == 'device':
            self.api_frame.grid_remove()
            self.device_frame.grid()
            self.device_tab_btn.state(['selected'])
        else:
            self.device_frame.grid_remove()
            self.api_frame.grid()
            self.api_tab_btn.state(['selected'])

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

    def hide_window(self):
        self.master.withdraw()

    def show_window(self, icon=None, item=None):
        self.master.deiconify()
        self.master.lift()
        self.master.focus_force()

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

    # --- MODIFIED: This loop now handles auto-connect and auto-disconnect ---
    def device_monitor_loop(self):
        """Periodically checks for device changes and handles connections."""
        while self.is_running:
            try:
                result = subprocess.run([self.ADB_PATH, "devices"], 
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                        text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                
                current_devices = set(self.parse_device_list(result.stdout))

                # 1. Handle Auto-Disconnection
                if self.connected_device and self.connected_device not in current_devices:
                    if not self.is_disconnecting:
                        self.is_disconnecting = True
                        self.master.after(0, self.handle_auto_disconnect)
                
                # 2. Handle Auto-Connection
                if not self.connected_device:
                    newly_connected = current_devices - self.known_devices
                    if newly_connected:
                        device_to_connect = newly_connected.pop()
                        # Use a thread for the connection logic to not block the monitor
                        threading.Thread(target=self._connect_device, args=(device_to_connect,)).start()
                
                # 3. Update the set of known devices for the next cycle
                self.known_devices = current_devices

            except Exception as e:
                print(f"Error in device monitor loop: {e}")
            
            time.sleep(3) # Check for changes every 3 seconds

    def handle_auto_disconnect(self):
        from tkinter import messagebox
        if self.connected_device:
            messagebox.showinfo("Disconnected", f"Device {self.connected_device} has been disconnected.")
        self.connected_device = None
        self.disconnect_button.config(state='disabled')
        self.refresh_devices()
        self.update_tray_status()
        self.is_disconnecting = False

    def _refresh_devices(self):
        import tkinter as tk
        from tkinter import messagebox
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        try:
            result = subprocess.run([self.ADB_PATH, "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            output = result.stdout
            devices = self.parse_device_list(output)
            all_known_devices = set(devices)
            if self.connected_device:
                all_known_devices.add(self.connected_device)
            if all_known_devices:
                for device_id in sorted(list(all_known_devices)):
                    status = "Connected" if device_id == self.connected_device else "Available"
                    tag = "connected" if status == "Connected" else "disconnected"
                    self.device_tree.insert('', tk.END, values=(device_id, status), tags=(tag,))
            else:
                self.device_tree.insert('', tk.END, values=('No devices found.', ''), tags=())
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while refreshing devices:\n{e}")
        finally:
            self.refresh_button.config(state='normal')

    def _connect_device(self, device_id):
        from tkinter import messagebox
        try:
            # Prevent trying to connect to the same device again if a race condition occurs
            if self.connected_device is not None:
                return

            result = subprocess.run([self.ADB_PATH, "-s", device_id, "reverse", "tcp:8000", "tcp:8000"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            # Double-check another thread didn't connect while this was running
            if self.connected_device is None and result.returncode == 0:
                self.connected_device = device_id
                self.is_disconnecting = False
                # Schedule UI updates on the main thread
                self.master.after(0, lambda: messagebox.showinfo("Success", f"Automatically connected to device {device_id}"))
                self.master.after(0, self.disconnect_button.config, {'state': 'normal'})
                self.master.after(0, self.refresh_devices)
                self.master.after(0, self.update_tray_status)
            elif result.returncode != 0:
                # Schedule error message on the main thread
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
                messagebox.showinfo("Success", f"Successfully disconnected from device {self.connected_device}")
                self.connected_device = None
                self.disconnect_button.config(state='disabled')
                self.refresh_devices()
                self.update_tray_status()
            else:
                messagebox.showerror("Error", f"Failed to disconnect:\n{result.stderr}")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred during disconnection:\n{e}")
        finally:
            self.disconnect_button.config(state='normal')

    def get_adb_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        adb_path = os.path.join(base_path, "adb", "adb.exe")
        return adb_path if os.path.exists(adb_path) else "adb"

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
        threading.Thread(target=self._refresh_devices).start()

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
        threading.Thread(target=self._connect_device, args=(selected_device,)).start()

    def disconnect_device(self):
        from tkinter import messagebox
        if not self.connected_device:
            messagebox.showwarning("No Connection", "No device is currently connected.")
            return
        threading.Thread(target=self._disconnect_device).start()

    def on_app_quit(self):
        self.is_running = False
        if self.tray_icon:
            self.tray_icon.stop()
        if self.api_process:
            self.api_process.terminate()
        if self.connected_device:
            try:
                subprocess.run([self.ADB_PATH, "-s", self.connected_device, "reverse", "--remove", "tcp:8000"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception as e:
                print(f"Could not disconnect on exit: {e}")
        
        try:
            if os.path.exists(self.lock_file_path):
                os.remove(self.lock_file_path)
        except Exception as e:
            print(f"Could not remove lock file: {e}")

        self.master.destroy()


if __name__ == "__main__":
    import tkinter as tk
    from tkinter import messagebox
    from PIL import Image
    import pystray
    import ctypes

    temp_dir = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp')
    lock_file = os.path.join(temp_dir, 'hht_android_connect.lock')

    if os.path.exists(lock_file):
        messagebox.showinfo("Already Running", "HHT Android Connect is already running in the system tray.")
        sys.exit()
    else:
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))

    def is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

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
            if os.path.exists(lock_file):
                os.remove(lock_file)
            messagebox.showerror("Application Error", f"An unexpected error occurred: {e}")
    else:
        if os.path.exists(lock_file):
            os.remove(lock_file)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)

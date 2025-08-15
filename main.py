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
    def __init__(self, master):
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
        
        # Define color constants as instance variables
        self.COLOR_PRIMARY = "#10B981"  # Emerald Green
        self.COLOR_PRIMARY_LIGHT = "#34D399"
        self.COLOR_SECONDARY = "#3B82F6"  # Blue
        self.COLOR_SECONDARY_LIGHT = "#60A5FA"
        self.COLOR_BG = "#FFFFFF"  # White background for cards
        self.COLOR_WINDOW_BG = "#F8FAFC"  # Slate background
        self.COLOR_DARK_TEXT = "#1F2937"  # Gray-800
        self.COLOR_SUBTEXT = "#6B7280"  # Gray-500
        self.COLOR_SUCCESS = "#10B981"  # Green for success
        self.COLOR_ERROR = "#EF4444"  # Red for error
        self.COLOR_SHADOW = "#E2E8F0"  # Slate-200
        
        master.title("HHT Android Connect")
        
        app_width = 800
        app_height = 600
        screen_width = master.winfo_screenwidth()
        screen_height = master.winfo_screenheight()
        x_pos = (screen_width - app_width) // 2
        y_pos = (screen_height - app_height) // 2
        master.geometry(f"{app_width}x{app_height}+{x_pos}+{y_pos}")

        master.configure(background=self.COLOR_WINDOW_BG)
        
        self.icon_image = create_android_icon(self.COLOR_SUCCESS)
        icon_photo = ImageTk.PhotoImage(self.icon_image)
        master.iconphoto(True, icon_photo)
        
        master.resizable(False, False)

        # --- Style Configuration ---
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.style.configure('.', background=self.COLOR_BG, foreground=self.COLOR_DARK_TEXT, font=('Inter', 11), borderwidth=0, relief='flat')
        self.style.configure('TFrame', background=self.COLOR_BG)
        self.style.configure('Card.TFrame', background=self.COLOR_BG)
        self.style.configure('TLabel', background=self.COLOR_BG, foreground=self.COLOR_DARK_TEXT)
        self.style.configure('Header.TLabel', font=('Inter', 20, 'bold'), foreground=self.COLOR_DARK_TEXT, background=self.COLOR_WINDOW_BG)
        
        self.style.configure('Primary.TButton', font=('Inter', 11, 'bold'), background=self.COLOR_PRIMARY, foreground='white', padding=(20, 10), borderwidth=0, relief='flat')
        self.style.map('Primary.TButton', background=[('active', self.COLOR_PRIMARY_LIGHT)])
        self.style.configure('Secondary.TButton', font=('Inter', 11, 'bold'), background=self.COLOR_BG, foreground=self.COLOR_SECONDARY, padding=(20, 10), borderwidth=1, bordercolor=self.COLOR_SECONDARY)
        self.style.map('Secondary.TButton', bordercolor=[('active', self.COLOR_SECONDARY_LIGHT)], background=[('active', '#F1F5F9')])

        self.style.configure("Treeview.Heading", font=('Inter', 11, 'bold'), background=self.COLOR_BG, foreground=self.COLOR_DARK_TEXT, padding=12, relief='flat')
        self.style.configure("Treeview", rowheight=50, font=('Inter', 11), fieldbackground=self.COLOR_BG, borderwidth=0, relief='flat')
        self.style.map("Treeview", background=[('selected', '#E6F3FF')], foreground=[('selected', self.COLOR_DARK_TEXT)])
        
        self.ADB_PATH = self.get_adb_path()
        if not self.check_adb():
            messagebox.showerror("Error", "ADB not found.", parent=master)
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

        padded_frame = tk.Frame(self.master, background=self.COLOR_WINDOW_BG, padx=24, pady=24)
        padded_frame.pack(fill=tk.BOTH, expand=True)

        header_frame = tk.Frame(padded_frame, background=self.COLOR_WINDOW_BG)
        header_frame.pack(fill=tk.X, pady=(0, 16))
        header_label = ttk.Label(header_frame, text="HHT Android Connect", style='Header.TLabel')
        header_label.pack(side=tk.LEFT)
        
        # --- Tab Navigation ---
        tab_container = tk.Frame(padded_frame, bg=self.COLOR_WINDOW_BG)
        tab_container.pack(fill=tk.X, pady=(0, 16))
        
        self.device_tab_button = ttk.Button(tab_container, text="Device Status", command=lambda: self.switch_tab('device'), style='Secondary.TButton')
        self.device_tab_button.pack(side=tk.LEFT, padx=(0, 8))
        self.api_tab_button = ttk.Button(tab_container, text="API Log", command=lambda: self.switch_tab('api'), style='Secondary.TButton')
        self.api_tab_button.pack(side=tk.LEFT)
        
        # --- Main Content Card ---
        shadow = tk.Canvas(padded_frame, bg=self.COLOR_WINDOW_BG, highlightthickness=0)
        shadow.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.content_frame = tk.Canvas(shadow, bg=self.COLOR_BG, highlightthickness=0)
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        shadow.bind("<Configure>", lambda e: self.draw_shadow(shadow, self.content_frame))
        self.content_frame.bind("<Configure>", self.draw_rounded_card)

        self.device_frame = ttk.Frame(self.content_frame, style='TFrame', padding=24)
        self.api_frame = ttk.Frame(self.content_frame, style='TFrame', padding=24)
        
        # --- Device Tab ---
        buttons_frame = ttk.Frame(self.device_frame, padding=(0, 16, 0, 0))
        buttons_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.refresh_button = ttk.Button(buttons_frame, text="Refresh Devices", command=self.refresh_devices, style='Secondary.TButton')
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 8))
        self.connect_button = ttk.Button(buttons_frame, text="Connect Selected", command=self.connect_device, style='Primary.TButton')
        self.connect_button.pack(side=tk.LEFT, padx=(0, 8))
        self.disconnect_button = ttk.Button(buttons_frame, text="Disconnect", command=self.disconnect_device, style='Secondary.TButton')
        self.disconnect_button.pack(side=tk.LEFT)
        self.disconnect_button.config(state='disabled')
        tree_frame = ttk.Frame(self.device_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.device_tree = ttk.Treeview(tree_frame, columns=('device_id', 'status'), show='headings')
        self.device_tree.heading('device_id', text='Device ID', anchor='w')
        self.device_tree.heading('status', text='Status', anchor='w')
        self.device_tree.column('device_id', anchor='w', width=450)
        self.device_tree.column('status', anchor='w', width=150)
        self.device_tree.pack(fill=tk.BOTH, expand=True)
        self.device_tree.tag_configure('connected', foreground=self.COLOR_SUCCESS, font=('Inter', 11, 'bold'))
        self.device_tree.tag_configure('disconnected', foreground=self.COLOR_ERROR, font=('Inter', 11, 'bold'))
        
        # --- API Tab ---
        api_status_frame = ttk.Frame(self.api_frame, style='TFrame', padding=(0, 0, 0, 16))
        api_status_frame.pack(fill=tk.X)
        status_container = tk.Frame(api_status_frame, bg=self.COLOR_BG)
        status_container.pack(side=tk.LEFT)
        self.api_status_dot = tk.Canvas(status_container, width=12, height=12, bg=self.COLOR_ERROR, highlightthickness=0)
        self.api_status_dot.pack(side=tk.LEFT, padx=(0, 8), pady=2)
        self.api_status_label = ttk.Label(status_container, text="API Status: Offline", font=('Inter', 11, 'bold'), foreground=self.COLOR_ERROR)
        self.api_status_label.pack(side=tk.LEFT)
        
        self.refresh_api_button = ttk.Button(api_status_frame, text="Refresh API", command=self.refresh_api_exe, style='Secondary.TButton')
        self.refresh_api_button.pack(side=tk.RIGHT)

        search_frame = ttk.Frame(self.api_frame, style='TFrame', padding=(0, 0, 0, 16))
        search_frame.pack(fill=tk.X)
        self.search_entry = ttk.Entry(search_frame, font=('Inter', 11))
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        search_button = ttk.Button(search_frame, text="Search", command=self.search_api_logs, style='Secondary.TButton')
        search_button.pack(side=tk.LEFT)
        self.api_log_text = scrolledtext.ScrolledText(self.api_frame, wrap=tk.WORD, state='disabled', bg='#1F2937', fg='#F3F4F6', font=('JetBrains Mono', 10), relief='flat', borderwidth=0)
        self.api_log_text.pack(fill=tk.BOTH, expand=True)
        self.api_log_text.tag_config('search', background='#FBBF24', foreground='#1F2937')
        self.api_log_text.tag_config('current_search', background='#F59E0B', foreground='#1F2937')
        
        self.switch_tab('device')

    def draw_shadow(self, canvas, content_canvas):
        canvas.delete("shadow")
        width = content_canvas.winfo_width()
        height = content_canvas.winfo_height()
        canvas.create_oval(4, 4, 24, 24, fill=self.COLOR_SHADOW, outline="")
        canvas.create_oval(width - 20, 4, width, 24, fill=self.COLOR_SHADOW, outline="")
        canvas.create_oval(4, height - 20, 24, height, fill=self.COLOR_SHADOW, outline="")
        canvas.create_oval(width - 20, height - 20, width, height, fill=self.COLOR_SHADOW, outline="")
        canvas.create_rectangle(14, 4, width - 10, height, fill=self.COLOR_SHADOW, outline="")
        canvas.create_rectangle(4, 14, width, height - 10, fill=self.COLOR_SHADOW, outline="")
        content_canvas.place(x=2, y=2, relwidth=1, relheight=1)

    def draw_rounded_card(self, event):
        self.content_frame.delete("rounded_rect")
        width = event.width
        height = event.height
        self.content_frame.create_oval(0, 0, 24, 24, fill=self.COLOR_BG, outline="")
        self.content_frame.create_oval(width - 24, 0, width, 24, fill=self.COLOR_BG, outline="")
        self.content_frame.create_oval(0, height - 24, 24, height, fill=self.COLOR_BG, outline="")
        self.content_frame.create_oval(width - 24, height - 24, width, height, fill=self.COLOR_BG, outline="")
        self.content_frame.create_rectangle(12, 0, width - 12, height, fill=self.COLOR_BG, outline="")
        self.content_frame.create_rectangle(0, 12, width, height - 12, fill=self.COLOR_BG, outline="")

    def draw_tab(self, canvas, text, is_active):
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        
        if is_active:
            canvas.create_oval(0, 5, 20, 25, fill=self.COLOR_BG, outline="")
            canvas.create_oval(width - 20, 5, width, 25, fill=self.COLOR_BG, outline="")
            canvas.create_rectangle(10, 5, width - 10, 25, fill=self.COLOR_BG, outline="")
            canvas.create_text(width/2, 15, text=text, font=('Inter', 11, 'bold'), fill=self.COLOR_PRIMARY)
        else:
            canvas.create_text(width/2, 15, text=text, font=('Inter', 11), fill=self.COLOR_SUBTEXT)

    def switch_tab(self, tab_name):
        self.device_frame.place_forget()
        self.api_frame.place_forget()
        self.device_tab_button.configure(style='Secondary.TButton')
        self.api_tab_button.configure(style='Secondary.TButton')

        if tab_name == 'device':
            self.device_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.device_tab_button.configure(style='Primary.TButton')
        else:
            self.api_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.api_tab_button.configure(style='Primary.TButton')

    def search_api_logs(self):
        import tkinter as tk
        search_term = self.search_entry.get()
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

    def set_api_status(self, status):
        self.api_status = status
        if status == "Online":
            self.api_status_dot.config(bg=self.COLOR_SUCCESS)
            self.api_status_label.config(text="API Status: Online", foreground=self.COLOR_SUCCESS)
        else:
            self.api_status_dot.config(bg=self.COLOR_ERROR)
            self.api_status_label.config(text="API Status: Offline", foreground=self.COLOR_ERROR)
        self.update_tray_status()

    def hide_window(self):
        self.master.withdraw()

    def show_window(self, icon=None, item=None):
        self.master.deiconify()
        self.master.lift()
        self.master.focus_force()

    def update_tray_status(self):
        if not self.tray_icon: return
        
        device_status_text = f"🟢 Device: {self.connected_device}" if self.connected_device else f"🔴 Device: Disconnected"
        api_status_text = f"🟢 API: Online" if self.api_status == "Online" else f"🔴 API: Offline"
        
        self.tray_icon.menu = self.create_tray_menu(device_status_text, api_status_text)
        
        if self.connected_device:
            self.tray_icon.icon = create_android_icon(self.COLOR_SUCCESS)
            self.tray_icon.title = f"HHT Android Connect: Connected"
        else:
            self.tray_icon.icon = create_android_icon(self.COLOR_SUBTEXT)
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

    def device_monitor_loop(self):
        from tkinter import messagebox
        while self.is_running:
            if self.connected_device and not self.is_disconnecting:
                try:
                    result = subprocess.run([self.ADB_PATH, "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    if self.connected_device not in result.stdout:
                        self.is_disconnecting = True
                        self.master.after(0, self.handle_auto_disconnect)
                except Exception as e:
                    print(f"Error in monitor loop: {e}")
            time.sleep(2)

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
                    status = "Connected" if device_id == self.connected_device else "Disconnected"
                    tag = status.lower()
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
            result = subprocess.run([self.ADB_PATH, "-s", device_id, "reverse", "tcp:8000", "tcp:8000"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                self.connected_device = device_id
                self.is_disconnecting = False
                messagebox.showinfo("Success", f"Successfully connected to device {device_id}")
                self.disconnect_button.config(state='normal')
                self.refresh_devices()
                self.update_tray_status()
            else:
                messagebox.showerror("Error", f"Failed to connect:\n{result.stderr}")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred during connection:\n{e}")
        finally:
            self.connect_button.config(state='normal')

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
        try:
            subprocess.run([self.ADB_PATH, "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
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
        self.refresh_button.config(state='disabled')
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
        self.connect_button.config(state='disabled')
        threading.Thread(target=self._connect_device, args=(selected_device,)).start()

    def disconnect_device(self):
        from tkinter import messagebox
        if not self.connected_device:
            messagebox.showwarning("No Connection", "No device is currently connected.")
            return
        self.disconnect_button.config(state='disabled')
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
        self.master.destroy()

if __name__ == "__main__":
    import tkinter as tk
    from PIL import Image
    import pystray

    root = tk.Tk()
    app = App(root)

    app.icon_image.save('app_icon.ico')
    
    root.protocol('WM_DELETE_WINDOW', app.hide_window)
    
    initial_menu = app.create_tray_menu("🔴 Device: Disconnected", "🔴 API: Offline")
    icon = pystray.Icon("HHTAndroidConnect", create_android_icon('#6B7280'), "HHT Android Connect", initial_menu)
    
    app.tray_icon = icon

    threading.Thread(target=icon.run, daemon=True).start()

    root.mainloop()

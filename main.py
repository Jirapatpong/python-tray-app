import subprocess
import threading
import os
import sys
import time
import queue
# GUI imports will be moved into the main block to support headless building

# --- System Tray Icon Creation ---
def create_android_icon(color):
    """Generates a simple Android robot icon."""
    # This function requires Pillow, which will be imported later.
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Head
    draw.arc((12, 10, 52, 50), 180, 0, fill=color, width=8)
    # Eyes
    draw.ellipse((22, 24, 28, 30), fill='white')
    draw.ellipse((36, 24, 42, 30), fill='white')
    # Antennae
    draw.line((20, 12, 16, 6), fill=color, width=3)
    draw.line((44, 12, 48, 6), fill=color, width=3)
    # Body
    draw.rectangle((12, 32, 52, 54), fill=color, outline=color, width=1)

    return image

class App:
    def __init__(self, master):
        # Import GUI libraries here, inside the class context
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
        
        master.title("HHT Android Connect")
        
        app_width = 750
        app_height = 550
        screen_width = master.winfo_screenwidth()
        screen_height = master.winfo_screenheight()
        x_pos = screen_width - app_width - 40
        y_pos = screen_height - app_height - 80
        master.geometry(f"{app_width}x{app_height}+{x_pos}+{y_pos}")

        master.configure(background='#F0F2F5') # Main window background
        
        self.icon_image = create_android_icon('grey')
        icon_photo = ImageTk.PhotoImage(self.icon_image)
        master.iconphoto(True, icon_photo)
        
        master.resizable(False, False)

        # --- Style Configuration ---
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # New color palette from the image
        COLOR_PRIMARY = "#7B61FF" # Purple
        COLOR_SUCCESS = "#20C997" # Green
        COLOR_DANGER = "#DC3545"  # Red
        COLOR_BG = "#F8F9FA"      # Light background for cards
        COLOR_WINDOW_BG = "#F0F2F5" # Main window background
        COLOR_DARK_TEXT = "#343A40"
        COLOR_LIGHT_TEXT = "#6C757D"
        COLOR_SELECTION = "#D6D1FF" # Light purple for selection

        self.style.configure('.', background=COLOR_BG, foreground=COLOR_DARK_TEXT, font=('Segoe UI', 10))
        self.style.configure('TFrame', background=COLOR_BG)
        self.style.configure('TLabel', background=COLOR_BG, foreground=COLOR_DARK_TEXT)
        self.style.configure('Header.TLabel', font=('Segoe UI', 18, 'bold'), foreground=COLOR_DARK_TEXT, background=COLOR_WINDOW_BG)
        
        # Button Styles
        self.style.configure('Primary.TButton', font=('Segoe UI', 10, 'bold'), background=COLOR_PRIMARY, foreground='white', padding=(15, 8), borderwidth=0)
        self.style.map('Primary.TButton', background=[('active', '#6A52E0')])
        self.style.configure('Secondary.TButton', font=('Segoe UI', 10, 'bold'), background=COLOR_BG, foreground=COLOR_DARK_TEXT, padding=(15, 8), borderwidth=1)
        self.style.map('Secondary.TButton', bordercolor=[('active', COLOR_PRIMARY), ('!active', '#CED4DA')], background=[('active', '#E9ECEF')])

        # Treeview Style
        self.style.configure("Treeview.Heading", font=('Segoe UI', 10, 'bold'), background=COLOR_BG, padding=12, relief='flat')
        self.style.configure("Treeview", rowheight=40, font=('Consolas', 11), fieldbackground=COLOR_BG, borderwidth=0, relief='flat')
        self.style.map("Treeview", background=[('selected', COLOR_SELECTION)], foreground=[('selected', COLOR_DARK_TEXT)])
        
        # Notebook (Tabs) Style
        self.style.configure('TNotebook', background=COLOR_WINDOW_BG, borderwidth=0)
        self.style.configure('TNotebook.Tab', font=('Segoe UI', 10, 'bold'), padding=[15, 8], background=COLOR_WINDOW_BG, borderwidth=0)
        self.style.map('TNotebook.Tab', background=[('selected', COLOR_BG)], foreground=[('selected', COLOR_PRIMARY)])

        # --- ADB Setup ---
        self.ADB_PATH = self.get_adb_path()
        if not self.check_adb():
            messagebox.showerror("Error", "ADB not found.")
            master.quit()
            return
        self.start_adb_server()
        self.connected_device = None

        # --- UI Creation ---
        self.create_widgets()

        # --- Initial Load & Monitoring ---
        self.refresh_devices()
        self.update_tray_status()
        
        self.monitor_thread = threading.Thread(target=self.device_monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        self.start_api_exe()

    def create_widgets(self):
        import tkinter as tk
        from tkinter import ttk, scrolledtext

        # Main frame with padding to create space around the card
        padded_frame = tk.Frame(self.master, background='#F0F2F5', padx=20, pady=20)
        padded_frame.pack(fill=tk.BOTH, expand=True)

        header_label = ttk.Label(padded_frame, text="HHT Android Connect", style='Header.TLabel')
        header_label.pack(anchor='w', pady=(0, 10), padx=10)
        
        # --- Create Notebook for Tabs ---
        self.notebook = ttk.Notebook(padded_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # --- Tab 1: Device Status ---
        device_tab = ttk.Frame(self.notebook, style='TFrame', padding=20)
        self.notebook.add(device_tab, text='Device Status')
        
        buttons_frame = ttk.Frame(device_tab, padding=(0, 20, 0, 0))
        buttons_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.refresh_button = ttk.Button(buttons_frame, text="Refresh Devices", command=self.refresh_devices, style='Secondary.TButton')
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 10))

        self.connect_button = ttk.Button(buttons_frame, text="Connect Selected", command=self.connect_device, style='Primary.TButton')
        self.connect_button.pack(side=tk.LEFT, padx=(0, 10))

        self.disconnect_button = ttk.Button(buttons_frame, text="Disconnect", command=self.disconnect_device, style='Secondary.TButton')
        self.disconnect_button.pack(side=tk.LEFT)
        self.disconnect_button.config(state='disabled')

        tree_frame = ttk.Frame(device_tab, padding=(0, 10, 0, 0))
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.device_tree = ttk.Treeview(tree_frame, columns=('device_id', 'status'), show='headings')
        self.device_tree.heading('device_id', text='DEVICE ID', anchor='w')
        self.device_tree.heading('status', text='STATUS', anchor='w')
        self.device_tree.column('device_id', anchor='w', width=400)
        self.device_tree.column('status', anchor='w', width=150)
        self.device_tree.pack(fill=tk.BOTH, expand=True)
        self.device_tree.tag_configure('connected', foreground="#20C997", font=('Segoe UI', 10, 'bold'))
        self.device_tree.tag_configure('disconnected', foreground="#DC3545", font=('Segoe UI', 10, 'bold'))
        
        # --- Tab 2: API Log ---
        api_tab = ttk.Frame(self.notebook, style='TFrame', padding=20)
        self.notebook.add(api_tab, text='API Log')
        
        search_frame = ttk.Frame(api_tab, style='TFrame', padding=(0, 0, 0, 10))
        search_frame.pack(fill=tk.X)
        
        self.search_entry = ttk.Entry(search_frame, font=('Segoe UI', 10))
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        search_button = ttk.Button(search_frame, text="Search", command=self.search_api_logs, style='Secondary.TButton')
        search_button.pack(side=tk.LEFT)

        self.api_log_text = scrolledtext.ScrolledText(api_tab, wrap=tk.WORD, state='disabled', bg='#1E1E1E', fg='#D4D4D4', font=('Consolas', 10), relief='flat', borderwidth=0)
        self.api_log_text.pack(fill=tk.BOTH, expand=True)
        self.api_log_text.tag_config('search', background='yellow', foreground='black')
        self.api_log_text.tag_config('current_search', background='#FFA500', foreground='black') # For the current find

    def search_api_logs(self):
        import tkinter as tk
        search_term = self.search_entry.get()
        self.api_log_text.config(state='normal')
        
        # If the search term is new, reset the search position and highlights
        if search_term != self.last_search_term:
            self.last_search_term = search_term
            self.last_search_pos = "1.0"
            self.api_log_text.tag_remove('search', '1.0', tk.END)
            self.api_log_text.tag_remove('current_search', '1.0', tk.END)

        if search_term:
            # Find the next occurrence from the last position
            start_pos = self.api_log_text.search(search_term, self.last_search_pos, stopindex=tk.END, nocase=True)
            
            # If not found, loop back to the beginning
            if not start_pos:
                self.last_search_pos = "1.0"
                self.api_log_text.tag_remove('current_search', '1.0', tk.END) # Clear previous current highlight
                start_pos = self.api_log_text.search(search_term, self.last_search_pos, stopindex=tk.END, nocase=True)

            if start_pos:
                end_pos = f"{start_pos}+{len(search_term)}c"
                
                # Highlight all matches in yellow, but the current one in orange
                self.api_log_text.tag_add('search', start_pos, end_pos)
                self.api_log_text.tag_remove('current_search', '1.0', tk.END)
                self.api_log_text.tag_add('current_search', start_pos, end_pos)
                
                # Scroll to the found text
                self.api_log_text.see(start_pos)
                
                # Update the last position for the next search
                self.last_search_pos = end_pos
        
        self.api_log_text.config(state='disabled')

    def start_api_exe(self):
        self.api_log_queue = queue.Queue()
        api_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "api.exe")
        
        if not os.path.exists(api_path):
            self.log_to_api_tab("Error: api.exe not found in the application directory.")
            return

        try:
            self.api_process = subprocess.Popen(
                [api_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding='utf-8',
                errors='replace'
            )
            
            threading.Thread(target=self.read_api_output, daemon=True).start()
            self.master.after(100, self.process_api_log_queue)
            
        except Exception as e:
            self.log_to_api_tab(f"Failed to start api.exe: {e}")

    def read_api_output(self):
        for line in iter(self.api_process.stdout.readline, ''):
            self.api_log_queue.put(line)
        self.api_process.stdout.close()

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

    def hide_window(self):
        self.master.withdraw()

    def show_window(self, icon=None, item=None):
        self.master.deiconify()
        self.master.lift()
        self.master.focus_force()

    def update_tray_status(self):
        if not self.tray_icon: return
        if self.connected_device:
            self.tray_icon.icon = create_android_icon('green')
            self.tray_icon.title = f"HHT Android Connect: Connected to {self.connected_device}"
        else:
            self.tray_icon.icon = create_android_icon('grey')
            self.tray_icon.title = "HHT Android Connect: Disconnected"

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

    def quit_app(icon, item):
        app.on_app_quit()

    root.protocol('WM_DELETE_WINDOW', app.hide_window)

    menu = (pystray.MenuItem('Show', app.show_window, default=True), pystray.MenuItem('Quit', quit_app))
    icon = pystray.Icon("HHTAndroidConnect", create_android_icon('grey'), "HHT Android Connect", menu)
    
    app.tray_icon = icon

    threading.Thread(target=icon.run, daemon=True).start()

    root.mainloop()

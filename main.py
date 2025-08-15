import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import os
import sys
from PIL import Image, ImageDraw
import pystray

# --- System Tray Icon Creation ---
def create_icon_image(color):
    """Generates a simple square icon image."""
    width = 64
    height = 64
    image = Image.new('RGB', (width, height), 'white')
    dc = ImageDraw.Draw(image)
    dc.rectangle(
        (width // 4, height // 4, width * 3 // 4, height * 3 // 4),
        fill=color)
    return image

class App:
    def __init__(self, master):
        self.master = master
        self.tray_icon = None # Will be set later
        
        master.title("System Monitor")
        master.geometry("750x550")
        master.configure(background='#F0F2F5')
        
        # --- FIX 1: Make the window non-resizable ---
        master.resizable(False, False)

        # --- Style Configuration ---
        self.style = ttk.Style()
        self.style.theme_use('clam')
        # ... (rest of the styling is the same)
        COLOR_PRIMARY = "#0D6EFD"
        COLOR_SUCCESS = "#198754"
        COLOR_DANGER = "#DC3545"
        COLOR_LIGHT_GREY = "#F8F9FA"
        COLOR_GREY_BORDER = "#DEE2E6"
        COLOR_WHITE = "#FFFFFF"
        COLOR_DARK_TEXT = "#212529"
        COLOR_SECONDARY_TEXT = "#6C757D"
        self.style.configure('.', background=COLOR_WHITE, foreground=COLOR_DARK_TEXT, font=('Segoe UI', 10))
        self.style.configure('TFrame', background=COLOR_WHITE)
        self.style.configure('TLabel', background=COLOR_WHITE, foreground=COLOR_DARK_TEXT)
        self.style.configure('Header.TLabel', font=('Segoe UI', 18, 'bold'), foreground=COLOR_PRIMARY)
        self.style.configure('Tab.TButton', font=('Segoe UI', 11, 'bold'), borderwidth=0, padding=(20, 10))
        self.style.map('Tab.TButton', background=[('active', COLOR_LIGHT_GREY), ('!active', COLOR_WHITE)], foreground=[('!active', COLOR_SECONDARY_TEXT)])
        self.style.configure('ActiveTab.TButton', foreground=COLOR_PRIMARY)
        self.style.configure('Primary.TButton', font=('Segoe UI', 10, 'bold'), background=COLOR_PRIMARY, foreground=COLOR_WHITE, padding=(15, 8), borderwidth=0)
        self.style.map('Primary.TButton', background=[('active', '#0B5ED7')])
        self.style.configure('Secondary.TButton', font=('Segoe UI', 10, 'bold'), background=COLOR_LIGHT_GREY, foreground=COLOR_DARK_TEXT, padding=(15, 8), borderwidth=1, relief='solid')
        self.style.map('Secondary.TButton', background=[('active', '#E2E6EA')], bordercolor=[('!active', COLOR_GREY_BORDER)])
        self.style.configure("Treeview.Heading", font=('Segoe UI', 10, 'bold'), background=COLOR_LIGHT_GREY, padding=10)
        self.style.configure("Treeview", rowheight=40, font=('Consolas', 11), fieldbackground=COLOR_WHITE, borderwidth=0)
        self.style.map("Treeview", background=[('selected', '#E7F1FF')])

        # --- ADB Setup (Original Logic) ---
        self.ADB_PATH = self.get_adb_path()
        if not self.check_adb():
            messagebox.showerror("Error", "ADB not found. Please install ADB or place adb.exe in the same folder as the program.")
            master.quit()
            return
        self.start_adb_server()
        self.connected_device = None

        # --- UI Creation ---
        self.create_widgets()

        # --- Initial Load ---
        self.refresh_devices()
        self.update_tray_status() # Set initial tray status

    def create_widgets(self):
        # ... (UI creation is the same)
        padded_frame = tk.Frame(self.master, background='#F0F2F5', padx=20, pady=20)
        padded_frame.pack(fill=tk.BOTH, expand=True)
        main_frame = ttk.Frame(padded_frame, style='TFrame', padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        header_label = ttk.Label(main_frame, text="System Monitor", style='Header.TLabel')
        header_label.pack(anchor='w', pady=(0, 20))
        tabs_frame = ttk.Frame(main_frame)
        tabs_frame.pack(fill=tk.X)
        device_status_tab = ttk.Button(tabs_frame, text="Device Status", style='ActiveTab.TButton', state='disabled')
        device_status_tab.pack(side=tk.LEFT)
        api_connection_tab = ttk.Button(tabs_frame, text="API Connection", style='Tab.TButton', state='disabled')
        api_connection_tab.pack(side=tk.LEFT)
        underline = tk.Frame(main_frame, height=2, bg='#0D6EFD')
        underline.pack(fill=tk.X, anchor='n')
        tree_frame = ttk.Frame(main_frame, padding=(0, 20, 0, 0))
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.device_tree = ttk.Treeview(tree_frame, columns=('device_id', 'status'), show='headings')
        self.device_tree.heading('device_id', text='DEVICE ID', anchor='w')
        self.device_tree.heading('status', text='STATUS', anchor='w')
        self.device_tree.column('device_id', anchor='w', width=300)
        self.device_tree.column('status', anchor='w', width=150)
        self.device_tree.pack(fill=tk.BOTH, expand=True)
        self.device_tree.tag_configure('connected', foreground="#198754", font=('Segoe UI', 10, 'bold'))
        self.device_tree.tag_configure('disconnected', foreground="#DC3545", font=('Segoe UI', 10, 'bold'))
        buttons_frame = ttk.Frame(main_frame, padding=(0, 20, 0, 0))
        buttons_frame.pack(fill=tk.X)
        self.refresh_button = ttk.Button(buttons_frame, text="Refresh Devices", command=self.refresh_devices, style='Secondary.TButton')
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 10))
        self.connect_button = ttk.Button(buttons_frame, text="Connect Selected", command=self.connect_device, style='Primary.TButton')
        self.connect_button.pack(side=tk.LEFT, padx=(0, 10))
        self.disconnect_button = ttk.Button(buttons_frame, text="Disconnect", command=self.disconnect_device, style='Secondary.TButton')
        self.disconnect_button.pack(side=tk.LEFT)
        self.disconnect_button.config(state='disabled')

    # --- FIX 2: System Tray Helper Methods ---
    def hide_window(self):
        """Hides the main window."""
        self.master.withdraw()

    def show_window(self):
        """Shows the main window."""
        self.master.deiconify()
        self.master.lift()
        self.master.focus_force()

    def update_tray_status(self):
        """Updates the tray icon and tooltip based on connection status."""
        if not self.tray_icon:
            return
        if self.connected_device:
            self.tray_icon.icon = create_icon_image('green')
            self.tray_icon.title = f"System Monitor: Connected to {self.connected_device}"
        else:
            self.tray_icon.icon = create_icon_image('grey')
            self.tray_icon.title = "System Monitor: Disconnected"

    # ===================================================================
    # Original logic with minor changes to update the tray status
    # ===================================================================

    def _refresh_devices(self):
        # ... (same as before)
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        try:
            result = subprocess.run([self.ADB_PATH, "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            output = result.stdout
            devices = self.parse_device_list(output)
            connected_devices = []
            if self.connected_device:
                connected_devices.append(self.connected_device)
            all_known_devices = list(set(devices + connected_devices))
            if all_known_devices:
                for device_id in all_known_devices:
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
        try:
            result = subprocess.run([self.ADB_PATH, "-s", device_id, "reverse", "tcp:8000", "tcp:8000"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                self.connected_device = device_id
                messagebox.showinfo("Success", f"Successfully connected to device {device_id}")
                self.disconnect_button.config(state='normal')
                self.refresh_devices()
                self.update_tray_status() # Update tray on connect
            else:
                messagebox.showerror("Error", f"Failed to connect:\n{result.stderr}")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred during connection:\n{e}")
        finally:
            self.connect_button.config(state='normal')

    def _disconnect_device(self):
        if not self.connected_device:
            return
        try:
            result = subprocess.run([self.ADB_PATH, "-s", self.connected_device, "reverse", "--remove", "tcp:8000"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                messagebox.showinfo("Success", f"Successfully disconnected from device {self.connected_device}")
                self.connected_device = None
                self.disconnect_button.config(state='disabled')
                self.refresh_devices()
                self.update_tray_status() # Update tray on disconnect
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
        if not self.connected_device:
            messagebox.showwarning("No Connection", "No device is currently connected.")
            return
        self.disconnect_button.config(state='disabled')
        threading.Thread(target=self._disconnect_device).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.withdraw() # Start hidden

    # --- System Tray Setup ---
    def quit_app(icon, item):
        icon.stop()
        if app.connected_device:
            app._disconnect_device() # Disconnect on quit
        root.destroy()

    def show_app(icon, item):
        app.show_window()

    menu = (pystray.MenuItem('Show', show_app, default=True), pystray.MenuItem('Quit', quit_app))
    icon = pystray.Icon("SystemMonitor", create_icon_image('grey'), "System Monitor", menu)
    
    # Pass the icon object to the app
    app.tray_icon = icon

    # Run the icon in a separate thread
    threading.Thread(target=icon.run, daemon=True).start()

    root.mainloop()


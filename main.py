import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import os
import sys
import time
from PIL import Image, ImageDraw, ImageTk
import pystray

# --- System Tray Icon Creation ---
def create_android_icon(color):
    """Generates a simple Android robot icon."""
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
        self.master = master
        self.tray_icon = None 
        self.is_running = True # Flag for the monitoring thread
        self.is_disconnecting = False # Flag to prevent multiple popups
        
        master.title("HHT Android Connect")
        
        # --- Window Size and Position ---
        app_width = 480 # 20% thinner than 600
        app_height = 440 # 20% shorter than 550
        screen_width = master.winfo_screenwidth()
        screen_height = master.winfo_screenheight()
        x_pos = screen_width - app_width - 40 # Position at bottom right with margin
        y_pos = screen_height - app_height - 80
        master.geometry(f"{app_width}x{app_height}+{x_pos}+{y_pos}")

        master.configure(background='#F0F2F5')
        
        # Set the window icon
        self.icon_image = create_android_icon('grey')
        icon_photo = ImageTk.PhotoImage(self.icon_image)
        master.iconphoto(True, icon_photo)
        
        master.resizable(False, False)

        # --- Style Configuration ---
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        COLOR_PRIMARY = "#0D6EFD"
        COLOR_SUCCESS = "#198754"
        COLOR_DANGER = "#DC3545"
        COLOR_LIGHT_GREY = "#F8F9FA"
        COLOR_GREY_BORDER = "#DEE2E6"
        COLOR_WHITE = "#FFFFFF"
        COLOR_DARK_TEXT = "#212529"
        COLOR_SECONDARY_TEXT = "#6C757D"
        COLOR_SELECTION = "#8EBBFF"

        self.style.configure('.', background=COLOR_WHITE, foreground=COLOR_DARK_TEXT, font=('Segoe UI', 10))
        self.style.configure('TFrame', background=COLOR_WHITE)
        self.style.configure('TLabel', background=COLOR_WHITE, foreground=COLOR_DARK_TEXT)
        self.style.configure('Header.TLabel', font=('Segoe UI', 18, 'bold'), foreground=COLOR_PRIMARY)
        self.style.configure('Primary.TButton', font=('Segoe UI', 10, 'bold'), background=COLOR_PRIMARY, foreground=COLOR_WHITE, padding=(15, 8), borderwidth=0)
        self.style.map('Primary.TButton', background=[('active', '#0B5ED7')])
        self.style.configure('Secondary.TButton', font=('Segoe UI', 10, 'bold'), background=COLOR_LIGHT_GREY, foreground=COLOR_DARK_TEXT, padding=(15, 8), borderwidth=1, relief='solid')
        self.style.map('Secondary.TButton', background=[('active', '#E2E6EA')], bordercolor=[('!active', COLOR_GREY_BORDER)])
        self.style.configure("Treeview.Heading", font=('Segoe UI', 10, 'bold'), background=COLOR_LIGHT_GREY, padding=10)
        self.style.configure("Treeview", rowheight=40, font=('Consolas', 11), fieldbackground=COLOR_WHITE, borderwidth=0)
        self.style.map("Treeview", background=[('selected', COLOR_SELECTION)])

        # --- ADB Setup ---
        self.ADB_PATH = self.get_adb_path()
        if not self.check_adb():
            messagebox.showerror("Error", "ADB not found. Please install ADB or place adb.exe in the same folder as the program.")
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

    def create_widgets(self):
        padded_frame = tk.Frame(self.master, background='#F0F2F5', padx=20, pady=20)
        padded_frame.pack(fill=tk.BOTH, expand=True)

        main_frame = ttk.Frame(padded_frame, style='TFrame', padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        header_label = ttk.Label(main_frame, text="HHT Android Connect", style='Header.TLabel')
        header_label.pack(anchor='w', pady=(0, 20))

        underline = tk.Frame(main_frame, height=2, bg='#0D6EFD')
        underline.pack(fill=tk.X, anchor='n', pady=(0, 10))

        buttons_frame = ttk.Frame(main_frame, padding=(0, 20, 0, 0))
        buttons_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.refresh_button = ttk.Button(buttons_frame, text="Refresh Devices", command=self.refresh_devices, style='Secondary.TButton')
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 10))

        self.connect_button = ttk.Button(buttons_frame, text="Connect Selected", command=self.connect_device, style='Primary.TButton')
        self.connect_button.pack(side=tk.LEFT, padx=(0, 10))

        self.disconnect_button = ttk.Button(buttons_frame, text="Disconnect", command=self.disconnect_device, style='Secondary.TButton')
        self.disconnect_button.pack(side=tk.LEFT)
        self.disconnect_button.config(state='disabled')

        tree_frame = ttk.Frame(main_frame, padding=(0, 10, 0, 0))
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.device_tree = ttk.Treeview(tree_frame, columns=('device_id', 'status'), show='headings')
        
        self.device_tree.heading('device_id', text='DEVICE ID', anchor='w')
        self.device_tree.heading('status', text='STATUS', anchor='w')
        self.device_tree.column('device_id', anchor='w', width=200) # Adjusted width for thinner window
        self.device_tree.column('status', anchor='w', width=100)
        self.device_tree.pack(fill=tk.BOTH, expand=True)
        self.device_tree.tag_configure('connected', foreground="#198754", font=('Segoe UI', 10, 'bold'))
        self.device_tree.tag_configure('disconnected', foreground="#DC3545", font=('Segoe UI', 10, 'bold'))

    # --- System Tray Helper Methods ---
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

    # --- Background Monitoring ---
    def device_monitor_loop(self):
        """Periodically checks for device connection changes."""
        while self.is_running:
            if self.connected_device and not self.is_disconnecting:
                try:
                    result = subprocess.run([self.ADB_PATH, "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    if self.connected_device not in result.stdout:
                        self.is_disconnecting = True
                        print(f"Device {self.connected_device} disconnected physically.")
                        self.master.after(0, self.handle_auto_disconnect)
                except Exception as e:
                    print(f"Error in monitor loop: {e}")
            time.sleep(2)

    def handle_auto_disconnect(self):
        """Handles UI updates when a device is physically disconnected."""
        if self.connected_device:
            messagebox.showinfo("Disconnected", f"Device {self.connected_device} has been disconnected.")
        self.connected_device = None
        self.disconnect_button.config(state='disabled')
        self.refresh_devices()
        self.update_tray_status()
        self.is_disconnecting = False

    # --- Original Logic ---
    def _refresh_devices(self):
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
    
    def on_app_quit(self):
        """Handles cleanup when the application is fully closed."""
        self.is_running = False
        if self.tray_icon:
            self.tray_icon.stop()
        if self.connected_device:
            try:
                subprocess.run([self.ADB_PATH, "-s", self.connected_device, "reverse", "--remove", "tcp:8000"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception as e:
                print(f"Could not disconnect on exit: {e}")
        self.master.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)

    # --- Save the icon to a file to be used by PyInstaller ---
    app.icon_image.save('app_icon.ico')

    def quit_app(icon, item):
        app.on_app_quit()

    root.protocol('WM_DELETE_WINDOW', app.hide_window)

    menu = (pystray.MenuItem('Show', app.show_window, default=True), pystray.MenuItem('Quit', quit_app))
    icon = pystray.Icon("HHTAndroidConnect", create_android_icon('grey'), "HHT Android Connect", menu)
    
    app.tray_icon = icon

    threading.Thread(target=icon.run, daemon=True).start()

    root.mainloop()

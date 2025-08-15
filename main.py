# main.py
import sys
import signal
from datetime import datetime

from PIL import Image, ImageDraw
import pystray

# Simple popup window
import tkinter as tk

signal.signal(signal.SIGINT, signal.SIG_DFL)

# Keep a single window instance
_window = None

def make_default_icon(size=64):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, size-4, size-4), fill=(102, 51, 204, 255))
    draw.ellipse((size*0.55, size*0.15, size*0.85, size*0.45), fill=(255, 255, 255, 230))
    draw.ellipse((size*0.70, size*0.62, size*0.78, size*0.70), fill=(255, 255, 255, 230))
    return img

def show_popup():
    """Create (or focus) a small Tk window."""
    global _window

    now = datetime.now().strftime('%H:%M:%S')

    # If the window already exists, just update + raise it
    if _window is not None and _window.winfo_exists():
        _window.time_var.set(f"Time: {now}")
        _window.deiconify()
        _window.lift()
        _window.focus_force()
        return

    _window = tk.Tk()
    _window.title("Tray App")
    _window.geometry("320x160")
    _window.resizable(False, False)

    # Store StringVar on the window for easy updates
    _window.time_var = tk.StringVar(value=f"Time: {now}")

    title = tk.Label(_window, text="Hello from your tray app!", font=("Segoe UI", 12, "bold"))
    title.pack(pady=(18, 6))

    time_lbl = tk.Label(_window, textvariable=_window.time_var, font=("Segoe UI", 10))
    time_lbl.pack(pady=(0, 16))

    btn = tk.Button(_window, text="Close", command=_window.destroy, width=12)
    btn.pack()

    # Start the modal loop; the tray keeps running, but this blocks further clicks until closed.
    _window.mainloop()

def on_clicked_open(icon, item):
    # Update tooltip and show the popup window
    icon.title = f"Tray running - {datetime.now().strftime('%H:%M:%S')}"
    show_popup()

def on_clicked_quit(icon, item):
    icon.visible = False
    icon.stop()

def run_tray(icon_image=None):
    image = icon_image or make_default_icon(64)

    # default=True makes this the action when double-clicking the tray icon (Windows/macOS).
    menu = pystray.Menu(
        pystray.MenuItem('Open', on_clicked_open, default=True),
        pystray.MenuItem('Quit', on_clicked_quit)
    )

    icon = pystray.Icon(name="PythonTrayApp", title="Tray running", icon=image, menu=menu)
    icon.run()

if __name__ == "__main__":
    icon_img = None
    if len(sys.argv) >= 2:
        try:
            from PIL import Image
            icon_path = sys.argv[1]
            icon_img = Image.open(icon_path)
        except Exception:
            icon_img = None
    run_tray(icon_img)

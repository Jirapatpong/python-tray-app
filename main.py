# main.py
import sys
import signal
from datetime import datetime
from PIL import Image, ImageDraw
import pystray

signal.signal(signal.SIGINT, signal.SIG_DFL)

def make_default_icon(size=64):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, size-4, size-4), fill=(102, 51, 204, 255))
    draw.ellipse((size*0.55, size*0.15, size*0.85, size*0.45), fill=(255, 255, 255, 230))
    draw.ellipse((size*0.70, size*0.62, size*0.78, size*0.70), fill=(255, 255, 255, 230))
    return img

def on_clicked_open(icon, item):
    icon.title = f"Tray running - {datetime.now().strftime('%H:%M:%S')}"

def on_clicked_quit(icon, item):
    icon.visible = False
    icon.stop()

def run_tray(icon_image=None):
    image = icon_image or make_default_icon(64)
    menu = pystray.Menu(
        pystray.MenuItem('Open', on_clicked_open),
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

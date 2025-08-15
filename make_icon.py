# make_icon.py
from PIL import Image, ImageDraw

def make_default_icon(size=256):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, size-8, size-8), fill=(102, 51, 204, 255))
    draw.ellipse((size*0.58, size*0.18, size*0.88, size*0.48), fill=(255, 255, 255, 230))
    draw.ellipse((size*0.72, size*0.64, size*0.80, size*0.72), fill=(255, 255, 255, 230))
    return img

if __name__ == "__main__":
    img = make_default_icon(256)
    sizes = [(256,256), (128,128), (64,64), (48,48), (32,32), (16,16)]
    img.save("icon.ico", sizes=sizes)
    print("icon.ico created.")

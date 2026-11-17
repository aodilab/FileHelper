import os
import sys
import win32com.client
from PIL import Image, ImageDraw
from config.settings import APPLE_TOUCH_ICON_PATH, ASSETS_DIR, BASE_DIR, ICON_ICO_PATH, ICON_PNG_PATH


def _draw_transfer_folder_glyph(draw, size):
    """Draw white folder with clean polygon bidirectional transfer arrows on a canvas of `size`."""
    s = size / 256.0
    draw.rounded_rectangle([(int(48 * s), int(80 * s)), (int(208 * s), int(196 * s))], radius=int(18 * s), fill=(255, 255, 255, 255))
    draw.rounded_rectangle([(int(48 * s), int(64 * s)), (int(120 * s), int(104 * s))], radius=int(14 * s), fill=(255, 255, 255, 255))
    green = (7, 193, 96, 255)
    # Right arrow (top): shaft + triangle head
    draw.rounded_rectangle([(int(88 * s), int(117 * s)), (int(148 * s), int(129 * s))], radius=int(6 * s), fill=green)
    draw.polygon([(int(142 * s), int(105 * s)), (int(168 * s), int(123 * s)), (int(142 * s), int(141 * s))], fill=green)
    # Left arrow (bottom): shaft + triangle head
    draw.rounded_rectangle([(int(108 * s), int(153 * s)), (int(168 * s), int(165 * s))], radius=int(6 * s), fill=green)
    draw.polygon([(int(114 * s), int(141 * s)), (int(88 * s), int(159 * s)), (int(114 * s), int(177 * s))], fill=green)


def build_app_icons():
    """Generate WeChat File-Transfer style green folder icons (ICO, PNG, and full-bleed iOS touch icon)."""
    os.makedirs(ASSETS_DIR, exist_ok=True)
    size = 256

    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)
    for y in range(size):
        r = int(25 - 18 * (y / size))
        g = int(211 - 18 * (y / size))
        b = int(110 - 14 * (y / size))
        bg_draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # 1. Desktop rounded-square icon
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(8, 8), (size - 8, size - 8)], radius=56, fill=255)
    img.paste(bg, (0, 0), mask)
    _draw_transfer_folder_glyph(ImageDraw.Draw(img), size)

    img.save(ICON_PNG_PATH, "PNG")
    img.save(ICON_ICO_PATH, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

    # 2. Full-bleed opaque 180x180 square for iPhone Home Screen bookmark (iOS masks corners automatically)
    ios_img = bg.copy()
    _draw_transfer_folder_glyph(ImageDraw.Draw(ios_img), size)
    ios_img.resize((180, 180), Image.Resampling.LANCZOS).save(APPLE_TOUCH_ICON_PATH, "PNG")


def create_desktop_shortcut():
    """Create 文件传输助手.lnk on Windows Desktop pointing to the app executable or build.py."""
    if not os.path.exists(ICON_ICO_PATH) or not os.path.exists(APPLE_TOUCH_ICON_PATH):
        build_app_icons()

    desktop_dir = os.path.join(os.environ["USERPROFILE"], "Desktop")
    old_lnk = os.path.join(desktop_dir, "AppleDrop.lnk")
    if os.path.exists(old_lnk):
        try:
            os.remove(old_lnk)
        except Exception:
            pass
    shortcut_path = os.path.join(desktop_dir, "文件传输助手.lnk")
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)

    if getattr(sys, "frozen", False):
        shortcut.TargetPath = sys.executable
        shortcut.Arguments = ""
        shortcut.WorkingDirectory = os.path.dirname(os.path.abspath(sys.executable))
        shortcut.IconLocation = f"{sys.executable}, 0"
    else:
        build_py = os.path.join(BASE_DIR, "build.py")
        pythonw_path = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pythonw_path):
            pythonw_path = sys.executable
        shortcut.TargetPath = pythonw_path
        shortcut.Arguments = f'"{build_py}"'
        shortcut.WorkingDirectory = BASE_DIR
        shortcut.IconLocation = f"{ICON_ICO_PATH}, 0"

    shortcut.Description = "文件传输助手 - 局域网双向原画与剪贴板无痕传输"
    shortcut.Save()
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, 0, 0)
    except Exception:
        pass
    return shortcut_path

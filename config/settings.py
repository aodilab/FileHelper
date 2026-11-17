import os
import sys

IS_FROZEN = getattr(sys, "frozen", False)
BASE_DIR = os.path.dirname(os.path.abspath(sys.executable)) if IS_FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR) if IS_FROZEN else BASE_DIR


def _resolve_data_dir():
    if not IS_FROZEN:
        return os.path.join(BASE_DIR, "data")
    # Portable folder keeps data/ beside FileHelper.exe; Program Files installs fall back to %LOCALAPPDATA%.
    pf_roots = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    norm_base = os.path.normcase(os.path.abspath(BASE_DIR))
    in_pf = any(p and norm_base.startswith(os.path.normcase(os.path.abspath(p)) + os.sep) for p in pf_roots)
    if not in_pf:
        try:
            probe = os.path.join(BASE_DIR, ".write_probe")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("")
            os.remove(probe)
            return os.path.join(BASE_DIR, "data")
        except OSError:
            pass
    local_app = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local_app, "FileHelper", "data")


ASSETS_DIR = os.path.join(RESOURCE_DIR, "assets")
TEMPLATES_DIR = os.path.join(RESOURCE_DIR, "templates")
SCRATCH_DIR = os.path.join(BASE_DIR, "scratch")
DATA_DIR = _resolve_data_dir()

ICON_ICO_PATH = os.path.join(ASSETS_DIR, "app_icon.ico")
ICON_PNG_PATH = os.path.join(ASSETS_DIR, "app_icon.png")
APPLE_TOUCH_ICON_PATH = os.path.join(ASSETS_DIR, "apple_touch_icon.png")
MOBILE_HTML_PATH = os.path.join(TEMPLATES_DIR, "mobile_portal.html")

DEFAULT_PORT = 8899
WIN_WIDTH = 460
WIN_HEIGHT = 680
SUPERSAMPLE_SCALE = 2
STREAM_CHUNK_SIZE = 512 * 1024

VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".mkv", ".avi")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp")

MIME_OVERRIDES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
}

TOKENS = {
    "canvas_bg_hex": "#f2f2f6",
    "canvas_bg": (242, 242, 246, 255),
    "composer_bg": (247, 247, 249, 255),
    "viewer_stage_bg": (237, 237, 240),
    "viewer_bar_bg": (235, 235, 237),
    "card_bg": (255, 255, 255, 255),
    "card_border": (229, 229, 234, 255),
    "hairline": (226, 226, 232, 255),
    "space_black": (17, 17, 17, 255),
    "text_body": (60, 60, 67, 255),
    "text_secondary": (134, 134, 139, 255),
    "neutral_pill_hover": (230, 230, 236, 255),
    "link_blue": (87, 107, 149, 255),
    "link_blue_hover": (60, 80, 122, 255),
    "wx_green": (7, 193, 96, 255),
    "wx_green_hover": (6, 173, 86, 255),
    "wx_green_bubble": (149, 236, 105, 255),
    "semantic_green_text": (7, 193, 96, 255),
    "semantic_red_text": (215, 0, 21, 255),
    "editor_red_ink": (250, 81, 81, 255),
}

CODE_LINE_RULES = {
    "src": {"golden": (120, 250), "max": 350},
    "templates": {"golden": (120, 250), "max": 350},
    "config": {"golden": (50, 150), "max": 250},
    "scripts": {"golden": (50, 150), "max": 250},
    "AGENTS.md": {"golden": (50, 65), "max": 80},
}

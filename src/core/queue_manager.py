import os, io, json, time, socket, threading, urllib.request
import win32clipboard
from PIL import Image, ImageOps
from config.settings import DEFAULT_PORT, IMAGE_EXTS


def copy_image_to_clipboard(item):
    try:
        src = io.BytesIO(item["bytes"]) if item.get("bytes") else item.get("path")
        if not src: return False
        img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        out = io.BytesIO(); img.save(out, "BMP")
        win32clipboard.OpenClipboard(); win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, out.getvalue()[14:])
        win32clipboard.CloseClipboard()
        return True
    except Exception:
        try: win32clipboard.CloseClipboard()
        except Exception: pass
        return False


def _make_thumb(source):
    try:
        img = Image.open(io.BytesIO(source) if isinstance(source, bytes) else source)
        img = ImageOps.exif_transpose(img).convert("RGBA")
        img.thumbnail((720, 800), Image.Resampling.LANCZOS)
        return img
    except Exception:
        return None


def get_local_ip():
    """Detect primary LAN IPv4 address (skipping virtual TUN 198.18.x.x)."""
    for target in ("192.168.1.1", "223.5.5.5", "10.255.255.255"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith(("127.", "198.18.", "169.254.")):
                return ip
        except Exception:
            pass
        finally:
            s.close()
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip.startswith(("192.168.", "10.", "172.")):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


def format_size(bytes_val):
    """Format byte size into human-readable string."""
    if bytes_val < 1024:
        return f"{bytes_val} B"
    if bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    if bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.2f} MB"
    return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"


def check_existing_instance_and_send(files, port=DEFAULT_PORT):
    """If FileHelper is already running, forward dropped files via local HTTP IPC and exit."""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/ping",
            headers={"User-Agent": "FileHelper-CLI"},
        )
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("app") in ("FileHelper", "AppleDrop"):
                if files:
                    abs_paths = [os.path.abspath(f) for f in files]
                    payload = json.dumps({"paths": abs_paths}).encode("utf-8")
                    post_req = urllib.request.Request(
                        f"http://127.0.0.1:{port}/api/add",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(post_req, timeout=1.2):
                        pass
                return True
    except Exception:
        pass
    return False


class FileQueue:
    """Thread-safe hybrid queue: zero-copy disk paths + RAM-only text/image items (wiped on clear/exit)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.files = []
        self.next_id = 1
        self.version = 0
        self.wakeup_requested = False
        self.phone_connected = False

    def mark_phone_connected(self):
        with self.lock:
            if not self.phone_connected:
                self.phone_connected = True
                self._bump_version()

    def _bump_version(self):
        self.version += 1

    def request_wakeup(self):
        with self.lock:
            self.wakeup_requested = True
            self._bump_version()

    def consume_wakeup(self):
        with self.lock:
            if self.wakeup_requested:
                self.wakeup_requested = False
                return True
            return False

    def add_files(self, paths):
        added = 0
        with self.lock:
            for p in paths:
                if not p:
                    continue
                abs_p = os.path.abspath(p)
                if not os.path.exists(abs_p):
                    continue
                if os.path.isdir(abs_p):
                    for root, _, filenames in os.walk(abs_p):
                        for fn in filenames:
                            fp = os.path.join(root, fn)
                            if not any(f.get("path") == fp for f in self.files):
                                self._add_single_file(fp)
                                added += 1
                else:
                    if not any(f.get("path") == abs_p for f in self.files):
                        self._add_single_file(abs_p)
                        added += 1
            if added > 0:
                self._bump_version()
        return added

    def _add_single_file(self, file_path):
        size = os.path.getsize(file_path)
        name = os.path.basename(file_path)
        thumb = _make_thumb(file_path) if name.lower().endswith(IMAGE_EXTS) else None
        item = {
            "id": str(self.next_id), "kind": "file", "sender": "pc", "path": file_path,
            "name": name, "size": size, "size_str": format_size(size),
            "status": "等待发送", "progress": 0, "speed": "", "thumb": thumb, "ts": time.time(),
        }
        self.next_id += 1
        self.files.append(item)

    def add_text_item(self, text, sender="pc"):
        clean = (text or "").strip()
        if not clean: return None
        raw = clean.encode("utf-8")
        preview = clean.replace("\r", " ").replace("\n", " ")[:26]
        with self.lock:
            item = {
                "id": str(self.next_id), "kind": "text", "sender": sender, "text": clean,
                "name": preview, "size": len(raw), "size_str": f"{len(clean)} 字",
                "status": "点击复制", "progress": 100, "speed": "", "ts": time.time(),
            }
            self.next_id += 1
            self.files.append(item)
            self._bump_version()
            return dict(item)

    def add_memory_item(self, name, data_bytes, mime="image/png", sender="pc"):
        if not data_bytes: return None
        raw_b = bytes(data_bytes)
        is_img = (mime or "").startswith("image/") or (name or "").lower().endswith(IMAGE_EXTS)
        thumb = _make_thumb(raw_b) if is_img else None
        with self.lock:
            item = {
                "id": str(self.next_id), "kind": "memory", "sender": sender,
                "name": name or "剪贴板图片.png", "mime": mime, "bytes": raw_b, "thumb": thumb,
                "size": len(raw_b), "size_str": format_size(len(raw_b)),
                "status": "点击复制" if sender == "phone" else "等待发送", "progress": 0, "speed": "", "ts": time.time(),
            }
            self.next_id += 1
            self.files.append(item)
            self._bump_version()
            return {k: v for k, v in item.items() if k not in ("bytes", "thumb")}

    def get_all(self):
        with self.lock:
            return [{k: v for k, v in f.items() if k != "bytes"} for f in self.files]

    def get_by_id(self, file_id):
        with self.lock:
            for f in self.files:
                if f["id"] == str(file_id):
                    return dict(f)
            return None

    def get_next_pending(self):
        with self.lock:
            for f in self.files:
                if f.get("kind") in ("file", "memory") and f["status"] == "等待发送":
                    return dict(f)
            media = [f for f in self.files if f.get("kind") in ("file", "memory")]
            return dict(media[-1]) if media else None

    def update_status(self, file_id, status=None, progress=None, speed=None):
        with self.lock:
            for f in self.files:
                if f["id"] == str(file_id):
                    if status is not None:
                        f["status"] = status
                    if progress is not None:
                        f["progress"] = progress
                    if speed is not None:
                        f["speed"] = speed
                    self._bump_version()
                    break

    def remove(self, file_id):
        with self.lock:
            for f in self.files:
                if f["id"] == str(file_id):
                    f["bytes"] = None
                    f["text"] = ""
            self.files = [f for f in self.files if f["id"] != str(file_id)]
            self._bump_version()

    def clear_all(self):
        with self.lock:
            for f in self.files:
                f["bytes"] = None
                f["text"] = ""
            self.files.clear()
            self._bump_version()

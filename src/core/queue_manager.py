import os, io, json, time, shutil, socket, threading, urllib.request
import win32clipboard
from PIL import Image, ImageOps
from config.settings import BASE_DIR, DATA_DIR, DEFAULT_PORT, IMAGE_EXTS

HISTORY_PATH, BLOBS_DIR = os.path.join(DATA_DIR, "history.json"), os.path.join(DATA_DIR, "blobs")
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _desktop_name():
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(128)
        ctypes.windll.user32.GetUserObjectInformationW(ctypes.windll.user32.GetThreadDesktop(ctypes.windll.kernel32.GetCurrentThreadId()), 2, buf, 256, None)
        return buf.value
    except Exception: return ""


def _latest_code_mtime():
    py = (os.path.join(r, fn) for sub in ("config", "src") for r, _, fs in os.walk(os.path.join(BASE_DIR, sub)) for fn in fs if fn.endswith(".py"))
    return max((os.path.getmtime(p) for p in py if os.path.exists(p)), default=0.0)


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
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(source) if isinstance(source, bytes) else source)).convert("RGBA")
        img.thumbnail((720, 800), Image.Resampling.LANCZOS)
        return img
    except Exception: return None


def get_local_ip():
    """Detect primary LAN IPv4 address (skipping virtual TUN 198.18.x.x)."""
    for target in ("192.168.1.1", "223.5.5.5", "10.255.255.255"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 80)); ip = s.getsockname()[0]
            if ip and not ip.startswith(("127.", "198.18.", "169.254.")): return ip
        except Exception: pass
        finally: s.close()
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip.startswith(("192.168.", "10.", "172.")): return ip
    except Exception: pass
    return "127.0.0.1"


def format_size(b):
    return f"{b} B" if b < 1024 else (f"{b / 1024:.1f} KB" if b < 1048576 else (f"{b / 1048576:.2f} MB" if b < 1073741824 else f"{b / 1073741824:.2f} GB"))


def check_existing_instance_and_send(files, port=DEFAULT_PORT):
    """If FileHelper is already running, wake it via direct loopback IPC (bypassing proxy) and exit."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.04)
    rc = s.connect_ex(("127.0.0.1", port))
    s.close()
    if rc != 0: return False
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/ping", headers={"User-Agent": "FileHelper-CLI"})
        with _DIRECT_OPENER.open(req, timeout=0.3) as resp:
            info = json.loads(resp.read().decode("utf-8"))
            if info.get("app") == "FileHelper":
                if info.get("boot_ts", 0) < _latest_code_mtime() or info.get("desktop", "") != _desktop_name():
                    try: _DIRECT_OPENER.open(f"http://127.0.0.1:{port}/api/ping?quit=1", timeout=0.2).close()
                    except Exception: pass
                    time.sleep(0.12)
                    return False
                if files:
                    payload = json.dumps({"paths": [os.path.abspath(f) for f in files]}).encode("utf-8")
                    add_req = urllib.request.Request(f"http://127.0.0.1:{port}/api/add", data=payload, headers={"Content-Type": "application/json"})
                    with _DIRECT_OPENER.open(add_req, timeout=0.8): pass
                return True
    except Exception: pass
    return False


class FileQueue:
    """Thread-safe queue with local persistence across restarts; clicking Clear wipes 100% of local data."""

    def __init__(self, persist=True):
        self.lock, self.persist, self.boot_ts, self.desktop_name = threading.Lock(), persist, time.time(), _desktop_name()
        self.files, self.next_id, self.version = [], 1, 0
        self.wakeup_requested, self.quit_requested, self.phone_connected = False, False, False
        if self.persist: self._load_history()

    def _load_history(self):
        if not os.path.exists(HISTORY_PATH): return
        try: records = json.loads(open(HISTORY_PATH, "r", encoding="utf-8").read())
        except Exception: return
        deferred = []
        for rec in records if isinstance(records, list) else []:
            kind, iid = rec.get("kind"), str(rec.get("id", ""))
            if not iid: continue
            if kind == "text" and rec.get("text"):
                rec["progress"] = 100; self.files.append(rec)
            elif kind == "file" and rec.get("path") and os.path.exists(rec["path"]):
                p = rec["path"]; rec["size"] = os.path.getsize(p); rec["size_str"] = format_size(rec["size"])
                rec["thumb"] = None; rec.setdefault("progress", 0); rec.setdefault("speed", ""); self.files.append(rec)
                if p.lower().endswith(IMAGE_EXTS): deferred.append((rec, p))
            elif kind == "memory" and rec.get("blob"):
                bp = os.path.join(BLOBS_DIR, rec["blob"])
                if os.path.exists(bp):
                    raw_b = open(bp, "rb").read()
                    is_img = (rec.get("mime") or "").startswith("image/") or (rec.get("name") or "").lower().endswith(IMAGE_EXTS)
                    rec.update({"bytes": raw_b, "thumb": None, "progress": 0, "speed": ""})
                    self.files.append(rec)
                    if is_img: deferred.append((rec, raw_b))
        self.next_id = max((int(f["id"]) for f in self.files if str(f.get("id", "")).isdigit()), default=0) + 1
        if deferred:
            def _hydrate():
                for item, src in deferred:
                    th = _make_thumb(src)
                    if th is not None:
                        with self.lock: item["thumb"] = th; self._bump_version()
            threading.Thread(target=_hydrate, daemon=True).start()

    def _save_history(self):
        if not self.persist: return
        if not self.files: return shutil.rmtree(DATA_DIR, ignore_errors=True)
        try:
            os.makedirs(DATA_DIR, exist_ok=True); serial = []
            for f in self.files:
                st = "已完成" if f.get("status") in ("已复制", "已保存") or "传输中" in str(f.get("status", "")) else f.get("status", "")
                row = {k: f[k] for k in ("id", "kind", "sender", "name", "size", "size_str", "ts", "text", "path", "mime", "blob") if k in f}
                row["status"] = st; serial.append(row)
            tmp = HISTORY_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fp: json.dump(serial, fp, ensure_ascii=False)
            os.replace(tmp, HISTORY_PATH)
        except Exception: pass

    def mark_phone_connected(self):
        with self.lock:
            if not self.phone_connected: self.phone_connected = True; self._bump_version()

    def _bump_version(self): self.version += 1

    def request_wakeup(self):
        with self.lock: self.wakeup_requested = True; self._bump_version()

    def consume_wakeup(self):
        with self.lock:
            if self.wakeup_requested: self.wakeup_requested = False; return True
            return False

    def add_files(self, paths):
        added = 0
        with self.lock:
            for p in paths:
                if not p or not os.path.exists(os.path.abspath(p)): continue
                abs_p = os.path.abspath(p)
                if os.path.isdir(abs_p):
                    for root, _, filenames in os.walk(abs_p):
                        for fn in filenames:
                            fp = os.path.join(root, fn)
                            if not any(f.get("path") == fp for f in self.files): self._add_single_file(fp); added += 1
                elif not any(f.get("path") == abs_p for f in self.files): self._add_single_file(abs_p); added += 1
            if added > 0: self._save_history(); self._bump_version()
        return added

    def _add_single_file(self, file_path):
        size, name = os.path.getsize(file_path), os.path.basename(file_path)
        thumb = _make_thumb(file_path) if name.lower().endswith(IMAGE_EXTS) else None
        self.files.append({"id": str(self.next_id), "kind": "file", "sender": "pc", "path": file_path, "name": name, "size": size, "size_str": format_size(size), "status": "等待发送", "progress": 0, "speed": "", "thumb": thumb, "ts": time.time()})
        self.next_id += 1

    def add_text_item(self, text, sender="pc"):
        clean = (text or "").strip()
        if not clean: return None
        raw = clean.encode("utf-8")
        with self.lock:
            item = {"id": str(self.next_id), "kind": "text", "sender": sender, "text": clean, "name": clean.replace("\r", " ").replace("\n", " ")[:26], "size": len(raw), "size_str": f"{len(clean)} 字", "status": "点击复制", "progress": 100, "speed": "", "ts": time.time()}
            self.next_id += 1; self.files.append(item); self._save_history(); self._bump_version()
            return dict(item)

    def add_memory_item(self, name, data_bytes, mime="image/png", sender="pc"):
        if not data_bytes: return None
        raw_b = bytes(data_bytes)
        is_img = (mime or "").startswith("image/") or (name or "").lower().endswith(IMAGE_EXTS)
        with self.lock:
            iid = str(self.next_id); self.next_id += 1
            blob_name = f"{iid}.bin"
            if self.persist:
                try: os.makedirs(BLOBS_DIR, exist_ok=True); open(os.path.join(BLOBS_DIR, blob_name), "wb").write(raw_b)
                except Exception: pass
            item = {"id": iid, "kind": "memory", "sender": sender, "blob": blob_name, "name": name or "剪贴板图片.png", "mime": mime, "bytes": raw_b, "thumb": _make_thumb(raw_b) if is_img else None, "size": len(raw_b), "size_str": format_size(len(raw_b)), "status": "点击复制" if sender == "phone" else "等待发送", "progress": 0, "speed": "", "ts": time.time()}
            self.files.append(item); self._save_history(); self._bump_version()
            return {k: v for k, v in item.items() if k not in ("bytes", "thumb")}

    def get_all(self):
        with self.lock: return [{k: v for k, v in f.items() if k != "bytes"} for f in self.files]

    def get_by_id(self, file_id):
        with self.lock:
            f = next((x for x in self.files if x["id"] == str(file_id)), None)
            return dict(f) if f else None

    def get_next_pending(self):
        with self.lock:
            for f in self.files:
                if f.get("kind") in ("file", "memory") and f["status"] == "等待发送": return dict(f)
            media = [f for f in self.files if f.get("kind") in ("file", "memory")]
            return dict(media[-1]) if media else None

    def update_status(self, file_id, status=None, progress=None, speed=None):
        with self.lock:
            for f in self.files:
                if f["id"] == str(file_id):
                    if status is not None: f["status"] = status
                    if progress is not None: f["progress"] = progress
                    if speed is not None: f["speed"] = speed
                    self._bump_version(); break

    def remove(self, file_id):
        with self.lock:
            for f in self.files:
                if f["id"] == str(file_id):
                    if self.persist and f.get("blob"):
                        try: os.remove(os.path.join(BLOBS_DIR, f["blob"]))
                        except Exception: pass
                    f["bytes"] = None; f["text"] = ""
            self.files = [f for f in self.files if f["id"] != str(file_id)]
            self._save_history(); self._bump_version()

    def clear_all(self):
        with self.lock:
            for f in self.files: f["bytes"] = None; f["text"] = ""
            self.files.clear()
            if self.persist: shutil.rmtree(DATA_DIR, ignore_errors=True)
            self._bump_version()

import os, io, sys, json, time, shutil, socket, threading, urllib.request
import win32clipboard
from PIL import Image, ImageOps
from config.settings import BASE_DIR, DATA_DIR, DEFAULT_PORT, IMAGE_EXTS, IS_FROZEN

try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception: pass

HISTORY_PATH, BLOBS_DIR = os.path.join(DATA_DIR, "history.json"), os.path.join(DATA_DIR, "blobs")
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_NORM_EXE = os.path.normcase(os.path.abspath(sys.executable))


def _desktop_name():
    try:
        import ctypes; buf = ctypes.create_unicode_buffer(128)
        ctypes.windll.user32.GetUserObjectInformationW(ctypes.windll.user32.GetThreadDesktop(ctypes.windll.kernel32.GetCurrentThreadId()), 2, buf, 256, None)
        return buf.value
    except Exception: return ""

def _latest_code_mtime():
    if IS_FROZEN: return os.path.getmtime(sys.executable) if os.path.exists(sys.executable) else 0.0
    py = [os.path.join(BASE_DIR, "build.py"), *(os.path.join(r, fn) for sub in ("config", "src") for r, _, fs in os.walk(os.path.join(BASE_DIR, sub)) for fn in fs if fn.endswith(".py"))]
    return max((os.path.getmtime(p) for p in py if os.path.exists(p)), default=0.0)

def copy_image_to_clipboard(item):
    try:
        src = io.BytesIO(item["bytes"]) if item.get("bytes") else item.get("path")
        if not src: return False
        out = io.BytesIO(); ImageOps.exif_transpose(Image.open(src)).convert("RGB").save(out, "BMP")
        win32clipboard.OpenClipboard(); win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, out.getvalue()[14:]); win32clipboard.CloseClipboard()
        return True
    except Exception:
        try: win32clipboard.CloseClipboard()
        except Exception: pass
        return False

def _make_thumb(source):
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(source) if isinstance(source, bytes) else source)).convert("RGBA")
        img.thumbnail((720, 800), Image.Resampling.LANCZOS); return img
    except Exception: return None

def _is_virtual_ip(ip):
    if not ip or ip.startswith(("127.", "169.254.", "198.18.", "198.19.", "26.")): return True
    p = ip.split(".")
    return len(p) == 4 and p[0] == "100" and p[1].isdigit() and 64 <= int(p[1]) <= 127

def get_local_ip():
    """Detect physical LAN IPv4 address (skipping Clash/Sing-box TUN, Tailscale, and VMware .1 bridges)."""
    routed = []
    for target in ("223.5.5.5", "192.168.1.1", "10.255.255.255"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 80)); ip = s.getsockname()[0]
            if not _is_virtual_ip(ip):
                if ip.startswith(("192.168.", "10.")) and not ip.endswith(".1"): return ip
                routed.append(ip)
        except Exception: pass
        finally: s.close()
    try:
        cands = [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not _is_virtual_ip(ip) and ip.startswith(("192.168.", "10.", "172."))]
        if cands: return sorted(cands, key=lambda x: (0 if x.startswith("192.168.") else (1 if x.startswith("10.") else 2), x.endswith(".1"), x not in routed))[0]
    except Exception: pass
    return routed[0] if routed else "127.0.0.1"

def format_size(b):
    return f"{b} B" if b < 1024 else (f"{b / 1024:.1f} KB" if b < 1048576 else (f"{b / 1048576:.2f} MB" if b < 1073741824 else f"{b / 1073741824:.2f} GB"))


def check_existing_instance_and_send(files, port=DEFAULT_PORT):
    """If FileHelper is already running, wake it via direct loopback IPC (bypassing proxy) and exit."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(0.05)
    rc = s.connect_ex(("127.0.0.1", port)); s.close()
    if rc != 0: return False
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/ping", headers={"User-Agent": "FileHelper-CLI"})
        with _DIRECT_OPENER.open(req, timeout=0.35) as resp:
            info = json.loads(resp.read().decode("utf-8"))
            if info.get("app") == "FileHelper":
                diff_exe = IS_FROZEN and info.get("exe") and info.get("exe") != _NORM_EXE
                if diff_exe or info.get("boot_ts", 0) < _latest_code_mtime() or info.get("desktop", "") != _desktop_name():
                    try: _DIRECT_OPENER.open(f"http://127.0.0.1:{port}/api/ping?quit=1", timeout=0.25).close()
                    except Exception: pass
                    time.sleep(0.2); return False
                if files:
                    payload = json.dumps({"paths": [os.path.abspath(f) for f in files]}).encode("utf-8")
                    with _DIRECT_OPENER.open(urllib.request.Request(f"http://127.0.0.1:{port}/api/add", data=payload, headers={"Content-Type": "application/json"}), timeout=0.8): pass
                return True
    except Exception: pass
    return False


class FileQueue:
    """Thread-safe queue with local persistence across restarts; clicking Clear wipes 100% of local data."""

    def __init__(self, persist=True):
        self.lock, self.persist, self.boot_ts, self.desktop_name = threading.Lock(), persist, time.time(), _desktop_name()
        self.files, self.next_id, self.version = [], int(time.time() * 1000), 0
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
                bn = os.path.basename(str(rec["blob"])); bp = os.path.join(BLOBS_DIR, bn)
                if os.path.exists(bp):
                    sz = os.path.getsize(bp)
                    is_img = (rec.get("mime") or "").startswith("image/") or (rec.get("name") or "").lower().endswith(IMAGE_EXTS)
                    rec.update({"blob": bn, "path": bp, "size": sz, "size_str": format_size(sz), "thumb": None, "progress": 0, "speed": ""})
                    self.files.append(rec)
                    if is_img: deferred.append((rec, bp))
        self.next_id = max([int(f["id"]) for f in self.files if str(f.get("id", "")).isdigit()] + [int(time.time() * 1000)]) + 1
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
                keys = ("id", "kind", "sender", "name", "size", "size_str", "ts", "text", "mime", "blob", *(("path",) if f.get("kind") != "memory" else ()))
                serial.append({**{k: f[k] for k in keys if k in f}, "status": st})
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
        with self.lock:
            item = {"id": str(self.next_id), "kind": "text", "sender": sender, "text": clean, "name": clean.replace("\r", " ").replace("\n", " ")[:26], "size": len(clean.encode("utf-8")), "size_str": f"{len(clean)} 字", "status": "点击复制", "progress": 100, "speed": "", "ts": time.time()}
            self.next_id += 1; self.files.append(item); self._save_history(); self._bump_version()
            return dict(item)

    def alloc_blob(self):
        with self.lock: iid = str(self.next_id); self.next_id += 1
        os.makedirs(BLOBS_DIR, exist_ok=True)
        return iid, f"{iid}.bin", os.path.join(BLOBS_DIR, f"{iid}.bin")

    def commit_blob_item(self, iid, blob_name, bp, name, mime="application/octet-stream", sender="phone"):
        if not os.path.exists(bp): return None
        sz, is_img = os.path.getsize(bp), (mime or "").startswith("image/") or (name or "").lower().endswith(IMAGE_EXTS)
        thumb = _make_thumb(bp) if is_img else None
        with self.lock:
            item = {"id": iid, "kind": "memory", "sender": sender, "blob": blob_name, "path": bp, "name": name or "剪贴板图片.png", "mime": mime, "thumb": thumb, "size": sz, "size_str": format_size(sz), "status": "点击复制" if sender == "phone" else "等待发送", "progress": 0, "speed": "", "ts": time.time()}
            self.files.append(item); self._save_history(); self._bump_version()
            return {k: v for k, v in item.items() if k not in ("bytes", "thumb")}

    def add_memory_item(self, name, data_bytes, mime="image/png", sender="pc"):
        if data_bytes is None: return None
        raw_b = bytes(data_bytes)
        if self.persist:
            iid, blob_name, bp = self.alloc_blob(); open(bp, "wb").write(raw_b)
            return self.commit_blob_item(iid, blob_name, bp, name, mime=mime, sender=sender)
        is_img = (mime or "").startswith("image/") or (name or "").lower().endswith(IMAGE_EXTS)
        with self.lock:
            iid = str(self.next_id); self.next_id += 1
            item = {"id": iid, "kind": "memory", "sender": sender, "name": name or "剪贴板图片.png", "mime": mime, "bytes": raw_b, "thumb": _make_thumb(raw_b) if is_img else None, "size": len(raw_b), "size_str": format_size(len(raw_b)), "status": "点击复制" if sender == "phone" else "等待发送", "progress": 0, "speed": "", "ts": time.time()}
            self.files.append(item); self._bump_version()
            return {k: v for k, v in item.items() if k not in ("bytes", "thumb")}

    def get_all(self):
        with self.lock: return [{k: v for k, v in f.items() if k != "bytes"} for f in self.files]
    def get_by_id(self, file_id):
        with self.lock: return next((dict(x) for x in self.files if x["id"] == str(file_id)), None)
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
                        try: os.remove(os.path.join(BLOBS_DIR, os.path.basename(f["blob"])))
                        except Exception: pass
                    f["bytes"] = None; f["text"] = ""
            self.files = [f for f in self.files if f["id"] != str(file_id)]; self._save_history(); self._bump_version()
    def clear_all(self):
        with self.lock:
            for f in self.files: f["bytes"] = None; f["text"] = ""
            self.files.clear(); self.persist and shutil.rmtree(DATA_DIR, ignore_errors=True); self._bump_version()

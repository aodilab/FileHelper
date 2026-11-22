import io
import json
import os
import socket
import sys
import time
import urllib.request
import win32clipboard
from PIL import Image, ImageOps

from config.settings import BASE_DIR, DEFAULT_PORT, IS_FROZEN

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

CLIENT_TTL = 45.0
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_NORM_EXE = os.path.normcase(os.path.abspath(sys.executable))
_SENDER_LABELS = {
    "pc": "电脑",
    "ios": "iPhone",
    "ipad": "iPad",
    "android": "Android",
    "phone": "手机",
}


def default_sender_label(sender): return _SENDER_LABELS.get(str(sender or "").lower(), "手机")

def detect_ua_device(user_agent):
    ua = (user_agent or "").lower()
    if "ipad" in ua: return "ipad", "iPad"
    if "iphone" in ua or "ipod" in ua: return "ios", "iPhone"
    if "android" in ua: return "android", "Android"
    return "phone", "手机"

def format_devices_summary(devices, prefix="已连 "):
    names = [d.get("label") or default_sender_label(d.get("kind")) for d in (devices or []) if d]
    if not names: return ""
    return f"{prefix}{' · '.join(names)}" if len(names) <= 2 else f"{prefix}{names[0]} · {names[1]} 等 {len(names)} 台"


def desktop_name():
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(128)
        tid = ctypes.windll.kernel32.GetCurrentThreadId()
        hdesk = ctypes.windll.user32.GetThreadDesktop(tid)
        ctypes.windll.user32.GetUserObjectInformationW(hdesk, 2, buf, 256, None)
        return buf.value
    except Exception:
        return ""


def _latest_code_mtime():
    if IS_FROZEN:
        return os.path.getmtime(sys.executable) if os.path.exists(sys.executable) else 0.0
    py = [os.path.join(BASE_DIR, "build.py")]
    for sub in ("config", "src"):
        for r, _, fs in os.walk(os.path.join(BASE_DIR, sub)):
            for fn in fs:
                if fn.endswith(".py"):
                    py.append(os.path.join(r, fn))
    return max((os.path.getmtime(p) for p in py if os.path.exists(p)), default=0.0)


def copy_image_to_clipboard(item):
    try:
        src = io.BytesIO(item["bytes"]) if item.get("bytes") else item.get("path")
        if not src:
            return False
        out = io.BytesIO()
        ImageOps.exif_transpose(Image.open(src)).convert("RGB").save(out, "BMP")
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, out.getvalue()[14:])
        win32clipboard.CloseClipboard()
        return True
    except Exception:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
        return False


def make_thumb(source):
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(source) if isinstance(source, bytes) else source)).convert("RGBA")
        img.thumbnail((720, 800), Image.Resampling.LANCZOS)
        return img
    except Exception:
        return None


def _is_virtual_ip(ip):
    if not ip or ip.startswith(("127.", "169.254.", "198.18.", "198.19.", "26.")):
        return True
    p = ip.split(".")
    return len(p) == 4 and p[0] == "100" and p[1].isdigit() and 64 <= int(p[1]) <= 127


def get_local_ip():
    """Detect physical LAN IPv4 address (skipping Clash/Sing-box TUN, Tailscale, and VMware .1 bridges)."""
    routed = []
    for target in ("223.5.5.5", "192.168.1.1", "10.255.255.255"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 80))
            ip = s.getsockname()[0]
            if not _is_virtual_ip(ip):
                if ip.startswith(("192.168.", "10.")) and not ip.endswith(".1"):
                    return ip
                routed.append(ip)
        except Exception:
            pass
        finally:
            s.close()
    try:
        cands = [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not _is_virtual_ip(ip) and ip.startswith(("192.168.", "10.", "172."))]
        if cands:
            return sorted(cands, key=lambda x: (0 if x.startswith("192.168.") else (1 if x.startswith("10.") else 2), x.endswith(".1"), x not in routed))[0]
    except Exception:
        pass
    return routed[0] if routed else "127.0.0.1"


def format_size(b):
    if b < 1024: return f"{b} B"
    if b < 1048576: return f"{b / 1024:.1f} KB"
    if b < 1073741824: return f"{b / 1048576:.2f} MB"
    return f"{b / 1073741824:.2f} GB"


def check_existing_instance_and_send(files, port=DEFAULT_PORT):
    """If FileHelper is already running, wake it via direct loopback IPC (bypassing proxy) and exit."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.05)
    rc = s.connect_ex(("127.0.0.1", port))
    s.close()
    if rc != 0:
        return False
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/ping", headers={"User-Agent": "FileHelper-CLI"})
        with _DIRECT_OPENER.open(req, timeout=0.35) as resp:
            info = json.loads(resp.read().decode("utf-8"))
            if info.get("app") == "FileHelper":
                diff_exe = IS_FROZEN and info.get("exe") and info.get("exe") != _NORM_EXE
                if diff_exe or info.get("boot_ts", 0) < _latest_code_mtime() or info.get("desktop", "") != desktop_name():
                    try:
                        _DIRECT_OPENER.open(f"http://127.0.0.1:{port}/api/ping?quit=1", timeout=0.25).close()
                    except Exception:
                        pass
                    time.sleep(0.2)
                    return False
                if files:
                    payload = json.dumps({"paths": [os.path.abspath(f) for f in files]}).encode("utf-8")
                    add_req = urllib.request.Request(f"http://127.0.0.1:{port}/api/add", data=payload, headers={"Content-Type": "application/json"})
                    with _DIRECT_OPENER.open(add_req, timeout=0.8):
                        pass
                return True
    except Exception:
        pass
    return False


class PeerRegistry:
    """Tracks active mobile/web peers on LAN with automatic duplicate numbering and TTL expiry."""

    def __init__(self, ttl=CLIENT_TTL):
        self.ttl = ttl
        self.clients = {}
        self._sig = ()

    def active_devices(self, now=None):
        now = time.time() if now is None else now
        for k in [k for k, v in self.clients.items() if now - v["last_seen"] > self.ttl]:
            del self.clients[k]
        ordered = sorted(self.clients.values(), key=lambda c: c["joined_at"])
        counts, seen, out = {}, {}, []
        for c in ordered:
            counts[c["base_label"]] = counts.get(c["base_label"], 0) + 1
        for c in ordered:
            base = c["base_label"]
            seen[base] = seen.get(base, 0) + 1
            lbl = f"{base} {seen[base]}" if counts[base] > 1 else base
            out.append({"cid": c["cid"], "kind": c["kind"], "label": lbl})
        return out

    def _refresh_sig(self, now=None):
        devs = self.active_devices(now)
        sig = tuple((d["cid"], d["label"]) for d in devs)
        changed = sig != self._sig
        self._sig = sig
        return devs, changed

    def touch(self, cid=None, label=None, kind="phone", ip=""):
        now = time.time()
        if not cid:
            if not ip or any(c.get("ip") == ip and not k.startswith("ip:") for k, c in self.clients.items()):
                return False
            cid = f"ip:{ip}"
        base = (label or default_sender_label(kind)).strip()[:18] or default_sender_label(kind)
        joined = self.clients[cid]["joined_at"] if cid in self.clients else now
        if ip and not cid.startswith("ip:") and f"ip:{ip}" in self.clients:
            joined = min(joined, self.clients.pop(f"ip:{ip}")["joined_at"])
        self.clients[cid] = {"cid": cid, "kind": kind or "phone", "base_label": base, "ip": ip, "joined_at": joined, "last_seen": now}
        _, changed = self._refresh_sig(now)
        return changed

    def prune(self):
        if not self.clients and not self._sig:
            return False
        _, changed = self._refresh_sig()
        return changed

    def resolve_sender(self, sender, sender_id=None, sender_label=None):
        if sender == "pc":
            return "pc", "电脑"
        sid = sender_id or sender or "phone"
        live = next((d["label"] for d in self.active_devices() if d["cid"] == sid), None)
        return sid, live or sender_label or default_sender_label(sender)


def start_lan_beacon(port_fn, stop_evt, udp_port=DEFAULT_PORT):
    """UDP LAN discovery responder so the Android app finds the PC automatically even after IP changes."""
    import threading
    def _loop():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", udp_port)); sock.settimeout(0.8)
            while not stop_evt.is_set():
                try: data, addr = sock.recvfrom(256)
                except socket.timeout: continue
                except OSError: break
                if data.strip().startswith(b"FILEHELPER_DISCOVER"):
                    reply = json.dumps({"app": "FileHelper", "port": port_fn(), "host": get_local_ip(), "name": socket.gethostname()}, ensure_ascii=False).encode("utf-8")
                    try: sock.sendto(reply, addr)
                    except OSError: pass
            sock.close()
        except Exception: pass
    threading.Thread(target=_loop, daemon=True).start()

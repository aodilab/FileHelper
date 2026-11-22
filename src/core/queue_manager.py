import json, os, shutil, threading, time

from config.settings import DATA_DIR, IMAGE_EXTS
from src.core.peer_hub import (
    PeerRegistry,
    check_existing_instance_and_send,
    copy_image_to_clipboard,
    default_sender_label,
    desktop_name,
    format_size,
    get_local_ip,
    make_thumb,
)

HISTORY_PATH, BLOBS_DIR = os.path.join(DATA_DIR, "history.json"), os.path.join(DATA_DIR, "blobs")
__all__ = ["FileQueue", "HISTORY_PATH", "BLOBS_DIR", "check_existing_instance_and_send", "copy_image_to_clipboard", "format_size", "get_local_ip"]


class FileQueue:
    """Thread-safe queue with local persistence across restarts; clicking Clear wipes 100% of local data."""

    def __init__(self, persist=True):
        self.lock, self.persist = threading.Lock(), persist
        self.boot_ts, self.desktop_name = time.time(), desktop_name()
        self.files, self.next_id, self.version = [], int(time.time() * 1000), 0
        self.wakeup_requested = self.quit_requested = self.phone_connected = False
        self.peers = PeerRegistry()
        if self.persist:
            self._load_history()

    def _load_history(self):
        if not os.path.exists(HISTORY_PATH):
            return
        try:
            records = json.loads(open(HISTORY_PATH, "r", encoding="utf-8").read())
        except Exception:
            return
        deferred = []
        for rec in records if isinstance(records, list) else []:
            kind, iid = rec.get("kind"), str(rec.get("id", ""))
            if not iid:
                continue
            rec.setdefault("sender_label", default_sender_label(rec.get("sender", "pc")))
            if kind == "text" and rec.get("text"):
                rec["progress"] = 100
                self.files.append(rec)
            elif kind == "file" and rec.get("path") and os.path.exists(rec["path"]):
                p = rec["path"]
                sz = os.path.getsize(p)
                rec.update({"size": sz, "size_str": format_size(sz), "thumb": None})
                rec.setdefault("progress", 0)
                rec.setdefault("speed", "")
                self.files.append(rec)
                if p.lower().endswith(IMAGE_EXTS):
                    deferred.append((rec, p))
            elif kind == "memory" and rec.get("blob"):
                bn = os.path.basename(str(rec["blob"]))
                bp = os.path.join(BLOBS_DIR, bn)
                if os.path.exists(bp):
                    sz = os.path.getsize(bp)
                    is_img = (rec.get("mime") or "").startswith("image/") or (rec.get("name") or "").lower().endswith(IMAGE_EXTS)
                    rec.update({"blob": bn, "path": bp, "size": sz, "size_str": format_size(sz), "thumb": None, "progress": 0, "speed": ""})
                    self.files.append(rec)
                    if is_img:
                        deferred.append((rec, bp))
        self.next_id = max([int(f["id"]) for f in self.files if str(f.get("id", "")).isdigit()] + [int(time.time() * 1000)]) + 1
        if deferred:
            def _hydrate():
                for item, src in deferred:
                    th = make_thumb(src)
                    if th is not None:
                        with self.lock:
                            item["thumb"] = th
                            self._bump_version()
            threading.Thread(target=_hydrate, daemon=True).start()

    def _save_history(self):
        if not self.persist:
            return
        if not self.files:
            return shutil.rmtree(DATA_DIR, ignore_errors=True)
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            serial = []
            for f in self.files:
                st = "已完成" if f.get("status") in ("已复制", "已保存") or "传输中" in str(f.get("status", "")) else f.get("status", "")
                keys = ("id", "kind", "sender", "sender_id", "sender_label", "name", "size", "size_str", "ts", "text", "mime", "blob", *(("path",) if f.get("kind") != "memory" else ()))
                serial.append({**{k: f[k] for k in keys if k in f}, "status": st})
            tmp = HISTORY_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(serial, fp, ensure_ascii=False)
            os.replace(tmp, HISTORY_PATH)
        except Exception:
            pass

    def touch_client(self, cid=None, label=None, kind="phone", ip=""):
        with self.lock:
            changed = self.peers.touch(cid=cid, label=label, kind=kind, ip=ip)
            self.phone_connected = bool(self.peers.clients)
            if changed:
                self._bump_version()

    def prune_clients(self):
        with self.lock:
            changed = self.peers.prune()
            self.phone_connected = bool(self.peers.clients)
            if changed:
                self._bump_version()

    def get_active_devices(self):
        with self.lock:
            devs = self.peers.active_devices()
            self.phone_connected = bool(devs)
            return devs

    def mark_phone_connected(self):
        with self.lock:
            if not self.phone_connected:
                self.phone_connected = True
                self._bump_version()

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
                if not p or not os.path.exists(os.path.abspath(p)):
                    continue
                abs_p = os.path.abspath(p)
                if os.path.isdir(abs_p):
                    for root, _, filenames in os.walk(abs_p):
                        for fn in filenames:
                            fp = os.path.join(root, fn)
                            if not any(f.get("path") == fp for f in self.files):
                                self._add_single_file(fp); added += 1
                elif not any(f.get("path") == abs_p for f in self.files):
                    self._add_single_file(abs_p); added += 1
            if added > 0:
                self._save_history(); self._bump_version()
        return added

    def _add_single_file(self, file_path):
        size, name = os.path.getsize(file_path), os.path.basename(file_path)
        thumb = make_thumb(file_path) if name.lower().endswith(IMAGE_EXTS) else None
        self.files.append({"id": str(self.next_id), "kind": "file", "sender": "pc", "sender_id": "pc", "sender_label": "电脑", "path": file_path, "name": name, "size": size, "size_str": format_size(size), "status": "等待发送", "progress": 0, "speed": "", "thumb": thumb, "ts": time.time()})
        self.next_id += 1

    def add_text_item(self, text, sender="pc", sender_id=None, sender_label=None):
        clean = (text or "").strip()
        if not clean:
            return None
        with self.lock:
            sid, slbl = self.peers.resolve_sender(sender, sender_id, sender_label)
            item = {"id": str(self.next_id), "kind": "text", "sender": sender, "sender_id": sid, "sender_label": slbl, "text": clean, "name": clean.replace("\r", " ").replace("\n", " ")[:26], "size": len(clean.encode("utf-8")), "size_str": f"{len(clean)} 字", "status": "点击复制", "progress": 100, "speed": "", "ts": time.time()}
            self.next_id += 1; self.files.append(item); self._save_history(); self._bump_version()
            return dict(item)

    def alloc_blob(self):
        with self.lock:
            iid = str(self.next_id); self.next_id += 1
        os.makedirs(BLOBS_DIR, exist_ok=True)
        return iid, f"{iid}.bin", os.path.join(BLOBS_DIR, f"{iid}.bin")

    def commit_blob_item(self, iid, blob_name, bp, name, mime="application/octet-stream", sender="phone", sender_id=None, sender_label=None):
        if not os.path.exists(bp):
            return None
        sz = os.path.getsize(bp)
        is_img = (mime or "").startswith("image/") or (name or "").lower().endswith(IMAGE_EXTS)
        thumb = make_thumb(bp) if is_img else None
        with self.lock:
            sid, slbl = self.peers.resolve_sender(sender, sender_id, sender_label)
            item = {"id": iid, "kind": "memory", "sender": sender, "sender_id": sid, "sender_label": slbl, "blob": blob_name, "path": bp, "name": name or "剪贴板图片.png", "mime": mime, "thumb": thumb, "size": sz, "size_str": format_size(sz), "status": "等待发送" if sender == "pc" else "点击复制", "progress": 0, "speed": "", "ts": time.time()}
            self.files.append(item); self._save_history(); self._bump_version()
            return {k: v for k, v in item.items() if k not in ("bytes", "thumb")}

    def add_memory_item(self, name, data_bytes, mime="image/png", sender="pc", sender_id=None, sender_label=None):
        if data_bytes is None:
            return None
        raw_b = bytes(data_bytes)
        if self.persist:
            iid, blob_name, bp = self.alloc_blob(); open(bp, "wb").write(raw_b)
            return self.commit_blob_item(iid, blob_name, bp, name, mime=mime, sender=sender, sender_id=sender_id, sender_label=sender_label)
        is_img = (mime or "").startswith("image/") or (name or "").lower().endswith(IMAGE_EXTS)
        with self.lock:
            iid = str(self.next_id); self.next_id += 1
            sid, slbl = self.peers.resolve_sender(sender, sender_id, sender_label)
            item = {"id": iid, "kind": "memory", "sender": sender, "sender_id": sid, "sender_label": slbl, "name": name or "剪贴板图片.png", "mime": mime, "bytes": raw_b, "thumb": make_thumb(raw_b) if is_img else None, "size": len(raw_b), "size_str": format_size(len(raw_b)), "status": "等待发送" if sender == "pc" else "点击复制", "progress": 0, "speed": "", "ts": time.time()}
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
            self.files = [f for f in self.files if f["id"] != str(file_id)]
            self._save_history(); self._bump_version()

    def clear_all(self):
        with self.lock:
            for f in self.files: f["bytes"] = None; f["text"] = ""
            self.files.clear()
            self.persist and shutil.rmtree(DATA_DIR, ignore_errors=True)
            self._bump_version()

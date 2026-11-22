import os, io, sys, json, time, socket, mimetypes, threading, urllib.parse, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import TCPServer, ThreadingMixIn

from config.settings import APPLE_TOUCH_ICON_PATH, BASE_DIR, DEFAULT_PORT, ICON_ICO_PATH, ICON_PNG_PATH, MIME_OVERRIDES, MOBILE_HTML_PATH, STREAM_CHUNK_SIZE
from src.core.peer_hub import detect_ua_device, start_lan_beacon
from src.core.queue_manager import get_local_ip, format_size

_NORM_EXE = os.path.normcase(os.path.abspath(sys.executable))
_LOOPBACK_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


def make_handler(server_ref, file_queue, port):
    class FileHelperHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args): pass
        def _is_local(self): return self.client_address[0] in ("127.0.0.1", "::1")

        def _touch_peer(self, qs=None, data=None):
            ua_kind, ua_lbl = detect_ua_device(self.headers.get("User-Agent", ""))
            src = data if isinstance(data, dict) else {}
            qget = lambda k: (qs.get(k, [""])[0] if qs else "")
            cid = (src.get("sender_id") or src.get("cid") or qget("cid") or "").strip() or None
            kind = (src.get("sender") or src.get("kind") or qget("kind") or qget("sender") or ua_kind).strip() or ua_kind
            lbl = (src.get("sender_label") or src.get("dev") or qget("dev") or "").strip() or (ua_lbl if kind == ua_kind else "")
            if cid or not self._is_local():
                file_queue.touch_client(cid=cid, label=lbl or ua_lbl, kind=kind, ip=self.client_address[0])
            return kind, cid, lbl or ua_lbl

        def send_cors_headers(self, cache=False):
            for k, v in (("Access-Control-Allow-Origin", "*"), ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"), ("Access-Control-Allow-Headers", "Content-Type, Range"), ("Cache-Control", "private, max-age=3600" if cache else "no-store, no-cache, must-revalidate")):
                self.send_header(k, v)

        def do_OPTIONS(self): self.send_response(200); self.send_cors_headers(); self.end_headers()

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            path, length = parsed.path, max(0, int(self.headers.get("Content-Length", 0) or 0))
            if path == "/api/upload":
                if length < 0 or length > 20 * 1024**3: return self._send_json({"success": False, "error": "invalid_length"}, status=400)
                qs = urllib.parse.parse_qs(parsed.query)
                sender, cid, dev = self._touch_peer(qs=qs)
                name, mime = os.path.basename(qs.get("name", ["手机图片.png"])[0]) or "手机文件.bin", qs.get("mime", ["application/octet-stream"])[0]
                if not file_queue.persist:
                    item = file_queue.add_memory_item(name, self.rfile.read(length), mime=mime, sender=sender, sender_id=cid, sender_label=dev)
                    return self._send_json({"success": bool(item), "item": item}, status=200 if item else 400)
                iid, blob_name, bp = file_queue.alloc_blob()
                try:
                    rem = length
                    with open(bp, "wb") as fp:
                        while rem > 0:
                            chunk = self.rfile.read(min(STREAM_CHUNK_SIZE, rem))
                            if not chunk: raise ConnectionError("incomplete upload")
                            fp.write(chunk); rem -= len(chunk)
                    item = file_queue.commit_blob_item(iid, blob_name, bp, name, mime=mime, sender=sender, sender_id=cid, sender_label=dev)
                    return self._send_json({"success": bool(item), "item": item}, status=200 if item else 400)
                except Exception as e:
                    try: os.remove(bp)
                    except Exception: pass
                    return self._send_json({"success": False, "error": str(e)}, status=400)

            body = self.rfile.read(length) if 0 < length <= 4 * 1024 * 1024 else b""
            if path == "/api/add":
                if not self._is_local(): return self._send_text("Forbidden", status=403)
                try: added = file_queue.add_files(json.loads(body.decode("utf-8")).get("paths", [])); file_queue.request_wakeup(); self._send_json({"success": True, "added": added})
                except Exception as e: self._send_text(str(e), status=400)
            elif path == "/api/text":
                try:
                    data = json.loads(body.decode("utf-8")); sender, cid, dev = self._touch_peer(data=data)
                    self._send_json({"success": bool(item := file_queue.add_text_item(data.get("text", ""), sender=sender, sender_id=cid, sender_label=dev)), "item": item})
                except Exception as e: self._send_text(str(e), status=400)
            elif path == "/api/delete":
                try: file_queue.remove(json.loads(body.decode("utf-8")).get("id", "")); self._send_json({"success": True})
                except Exception as e: self._send_text(str(e), status=400)
            elif path == "/api/clear": file_queue.clear_all(); self._send_json({"success": True})
            else: self._send_text("Not Found", status=404)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path, qs, inline = parsed.path, urllib.parse.parse_qs(parsed.query), "inline=1" in (parsed.query or "")
            if path == "/api/ping":
                qstr, is_loc = parsed.query or "", self._is_local()
                if is_loc:
                    if "quit=1" in qstr: file_queue.quit_requested = True
                    elif "probe=1" not in qstr: file_queue.request_wakeup()
                info = {"status": "ok", "app": "FileHelper", **({"boot_ts": file_queue.boot_ts, "desktop": file_queue.desktop_name, "exe": _NORM_EXE} if is_loc else {})}
                return self._send_json(info)
            if path in ("/", "/index.html", "/api/files") or path.startswith("/download/"): self._touch_peer(qs=qs)
            icons = {"/apple-touch-icon.png": (APPLE_TOUCH_ICON_PATH, "image/png"), "/apple-touch-icon-precomposed.png": (APPLE_TOUCH_ICON_PATH, "image/png"), "/app-icon.png": (ICON_PNG_PATH, "image/png"), "/favicon.ico": (ICON_ICO_PATH, "image/x-icon")}
            if path in icons and os.path.exists(icons[path][0]):
                with open(icons[path][0], "rb") as f: return self._send_text(f.read(), content_type=icons[path][1])
            if path == "/android.apk":
                apk = os.path.join(BASE_DIR, "dist", "FileHelper-Android.apk")
                return self._stream_disk_file({"id": "", "name": "FileHelper-Android.apk", "path": apk, "mime": "application/vnd.android.package-archive"}, disp="attachment") if os.path.exists(apk) else self._send_text("APK Not Found", status=404)
            if path == "/manifest.webmanifest":
                return self._send_json({"name": "传输助手", "short_name": "传输助手", "start_url": "/", "display": "standalone", "background_color": "#F7F7F7", "theme_color": "#F7F7F7", "icons": [{"src": "/apple-touch-icon.png?v=2", "sizes": "180x180", "type": "image/png"}, {"src": "/app-icon.png?v=2", "sizes": "256x256", "type": "image/png"}]})
            if path == "/api/files":
                keys = ("id", "kind", "sender", "sender_id", "sender_label", "name", "mime", "text", "size", "size_str", "status", "progress", "ts")
                ratio = lambda t: round(t.size[1] / max(1, t.size[0]), 4) if t is not None else None
                files_out = [{**{k: it.get(k) for k in keys}, "url": f"/download/{it['id']}", "ratio": ratio(it.get("thumb"))} for it in file_queue.get_all()]
                return self._send_json({"count": len(files_out), "version": file_queue.version, "page_ver": int(os.path.getmtime(MOBILE_HTML_PATH)), "alt_ports": getattr(file_queue, "alt_ports", []), "mdns": f"{socket.gethostname()}.local", "devices": file_queue.get_active_devices(), "files": files_out})
            if path.startswith("/thumb/"):
                item = file_queue.get_by_id(path.split("/thumb/")[1])
                if not item or item.get("thumb") is None: return self._send_text("Not Found", status=404)
                buf = io.BytesIO(); item["thumb"].convert("RGB").save(buf, "JPEG", quality=85)
                return self._send_text(buf.getvalue(), content_type="image/jpeg", cache=True)
            if path.startswith("/api/latest") or path.startswith("/api/next"):
                item = file_queue.get_next_pending()
                return self._stream_item(item) if item else self._send_text("暂无待发送文件", status=404)
            if path.startswith("/download/"):
                item = file_queue.get_by_id(path.split("/download/")[1])
                return self._stream_item(item, inline=inline) if item else self._send_text("Not Found", status=404)
            if path in ("/", "/index.html"): return self._render_mobile_portal()
            self._send_text("Not Found", status=404)

        def _send_text(self, text, status=200, content_type="text/plain; charset=utf-8", cache=False):
            payload = text.encode("utf-8") if isinstance(text, str) else text
            self.send_response(status); self.send_cors_headers(cache=cache)
            self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(payload)))
            self.end_headers(); self.wfile.write(payload)

        def _send_json(self, obj, status=200):
            self._send_text(json.dumps(obj, ensure_ascii=False), status=status, content_type="application/json; charset=utf-8")

        def _disp_header(self, disp, name, ext):
            stem = "".join(c if 32 <= ord(c) < 127 and c not in '"\\/' else "" for c in os.path.splitext(name)[0]).strip("._ ") or "file"
            return f'{disp}; filename="{stem}{ext}"; filename*=UTF-8\'\'{urllib.parse.quote(name)}'

        def _stream_item(self, item, inline=False):
            disp = "inline" if inline else "attachment"
            if item.get("path") and os.path.exists(item["path"]):
                return self._stream_disk_file(item, disp=disp)
            raw = item.get("bytes") or b""
            ext = os.path.splitext(item["name"])[1].lower() or ".bin"
            self.send_response(200); self.send_cors_headers()
            self.send_header("Content-Type", item.get("mime") or "application/octet-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Content-Disposition", self._disp_header(disp, item["name"], ext))
            self.end_headers(); self.wfile.write(raw)
            if disp != "inline": file_queue.update_status(item["id"], status="已完成", progress=100)

        def _stream_disk_file(self, item, disp="attachment"):
            file_path = item.get("path", "")
            if not os.path.exists(file_path): return self._send_text("File Missing", status=404)
            file_size = os.path.getsize(file_path)
            ext = os.path.splitext(item["name"])[1].lower() or ".bin"
            content_type = MIME_OVERRIDES.get(ext) or item.get("mime") or mimetypes.guess_type(item["name"])[0] or "application/octet-stream"
            if file_size == 0:
                self.send_response(200); self.send_cors_headers()
                self.send_header("Content-Type", content_type); self.send_header("Content-Length", "0")
                self.send_header("Content-Disposition", self._disp_header(disp, item["name"], ext))
                return self.end_headers()
            range_header = self.headers.get("Range", "")
            start, end, is_range = 0, file_size - 1, False
            if range_header.startswith("bytes="):
                try:
                    p0, p1 = (range_header[6:].split(",")[0].split("-") + [""])[:2]
                    if p0 == "" and p1: start, end = max(0, file_size - int(p1)), file_size - 1
                    else: start, end = (int(p0) if p0 else 0), min(file_size - 1, int(p1) if p1 else file_size - 1)
                    if start > end or start >= file_size:
                        self.send_response(416); self.send_header("Content-Range", f"bytes */{file_size}"); return self.end_headers()
                    is_range = True
                except ValueError: pass

            content_length = end - start + 1
            self.send_response(206 if is_range else 200)
            if is_range: self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_cors_headers()
            self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(content_length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Disposition", self._disp_header(disp, item["name"], ext))
            self.end_headers()

            bytes_sent, start_ts, last_notify, prev_status = 0, time.time(), 0.0, item.get("status", "等待发送")
            track = (disp != "inline") and (content_length > 65536 or content_length == file_size)
            if track: file_queue.update_status(item["id"], status="正在传输", progress=0)
            try:
                with open(file_path, "rb") as f:
                    f.seek(start); remaining = content_length
                    while remaining > 0:
                        chunk = f.read(min(STREAM_CHUNK_SIZE, remaining))
                        if not chunk: break
                        self.wfile.write(chunk); remaining -= len(chunk); bytes_sent += len(chunk)
                        now = time.time()
                        if track and now - last_notify > 0.25:
                            pct = int(((start + bytes_sent) / file_size) * 100)
                            file_queue.update_status(item["id"], status=f"传输中 {pct}%", progress=pct, speed=f"{format_size(bytes_sent / max(now - start_ts, 0.001))}/s")
                            last_notify = now
                if track: file_queue.update_status(item["id"], status="已完成", progress=100, speed="")
            except Exception:
                if track: file_queue.update_status(item["id"], status=prev_status, progress=100 if prev_status == "已完成" else 0, speed="")

        def _render_mobile_portal(self):
            with open(MOBILE_HTML_PATH, "r", encoding="utf-8") as f: tpl = f.read()
            page = tpl.replace("{{HOST_IP}}", server_ref.host_ip).replace("{{PORT}}", str(self.server.server_port))
            self._send_text(page, content_type="text/html; charset=utf-8")

    return FileHelperHandler


class ServerThread:
    def __init__(self, file_queue, port=DEFAULT_PORT):
        self.file_queue, self.port, self.host_ip = file_queue, port, get_local_ip()
        self.httpd, self.extra_servers, self._beacon_stop = None, [], threading.Event()
    @staticmethod
    def _retire_stale_self(port):
        try:
            with _LOOPBACK_OPENER.open(f"http://127.0.0.1:{port}/api/ping?probe=1", timeout=0.25) as r:
                if json.loads(r.read().decode("utf-8")).get("app") == "FileHelper":
                    _LOOPBACK_OPENER.open(f"http://127.0.0.1:{port}/api/ping?quit=1", timeout=0.25).close()
                    time.sleep(0.25)
        except Exception: pass
    def start(self):
        for cand in (self.port, self.port, 8787, 8898, 0):
            try:
                srv = ThreadedHTTPServer(("0.0.0.0", cand), make_handler(self, self.file_queue, cand or self.port))
                self.httpd, self.port = srv, srv.server_port
                break
            except OSError:
                if cand == self.port: self._retire_stale_self(self.port)
        if not self.httpd: raise RuntimeError("无法启动局域网传输服务端口")
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        start_lan_beacon(lambda: self.port, self._beacon_stop)
        self.file_queue.alt_ports = []
        def _bind_extras():
            for alt_port in (8787, 80, 0):
                if alt_port == 0 and self.file_queue.alt_ports: break
                if alt_port == self.port: continue
                try:
                    srv = ThreadedHTTPServer(("0.0.0.0", alt_port), make_handler(self, self.file_queue, alt_port))
                    self.extra_servers.append(srv); self.file_queue.alt_ports.append(srv.server_port)
                    threading.Thread(target=srv.serve_forever, daemon=True).start()
                except Exception: pass
        threading.Thread(target=_bind_extras, daemon=True).start()
    def stop(self):
        self._beacon_stop.set()
        for srv in [self.httpd, *self.extra_servers]:
            if srv:
                try: srv.shutdown(); srv.server_close()
                except Exception: pass

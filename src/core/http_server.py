import os, io, json, time, socket, mimetypes, threading, subprocess, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from config.settings import APPLE_TOUCH_ICON_PATH, DEFAULT_PORT, ICON_ICO_PATH, MIME_OVERRIDES, MOBILE_HTML_PATH, STREAM_CHUNK_SIZE
from src.core.queue_manager import get_local_ip, format_size


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_handler(file_queue, host_ip, port):
    class FileHelperHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send_cors_headers(self, cache=False):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
            self.send_header("Cache-Control", "private, max-age=3600" if cache else "no-store, no-cache, must-revalidate")

        def do_OPTIONS(self):
            self.send_response(200); self.send_cors_headers(); self.end_headers()

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if 0 < length <= 200 * 1024 * 1024 else b""
            if path == "/api/add":
                try:
                    data = json.loads(body.decode("utf-8"))
                    added = file_queue.add_files(data.get("paths", []))
                    file_queue.request_wakeup()
                    self._send_json({"success": True, "added": added})
                except Exception as e: self._send_text(str(e), status=400)
            elif path == "/api/text":
                try:
                    file_queue.mark_phone_connected()
                    data = json.loads(body.decode("utf-8"))
                    item = file_queue.add_text_item(data.get("text", ""), sender=data.get("sender", "phone"))
                    self._send_json({"success": bool(item), "item": item})
                except Exception as e: self._send_text(str(e), status=400)
            elif path == "/api/upload":
                file_queue.mark_phone_connected()
                qs = urllib.parse.parse_qs(parsed.query)
                name, mime = qs.get("name", ["手机图片.png"])[0], qs.get("mime", ["image/png"])[0]
                item = file_queue.add_memory_item(name, body, mime=mime, sender=qs.get("sender", ["phone"])[0])
                self._send_json({"success": bool(item), "item": item})
            elif path == "/api/delete":
                try: file_queue.remove(json.loads(body.decode("utf-8")).get("id", "")); self._send_json({"success": True})
                except Exception as e: self._send_text(str(e), status=400)
            elif path == "/api/clear":
                file_queue.clear_all(); self._send_json({"success": True})
            else:
                self._send_text("Not Found", status=404)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path, inline = parsed.path, "inline=1" in (parsed.query or "")
            if path == "/api/ping":
                if "quit=1" in (parsed.query or ""): file_queue.quit_requested = True
                else: file_queue.request_wakeup()
                return self._send_json({"status": "ok", "app": "FileHelper", "boot_ts": file_queue.boot_ts})
            if path in ("/", "/index.html", "/api/files") or path.startswith("/download/"):
                file_queue.mark_phone_connected()
            if path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
                if os.path.exists(APPLE_TOUCH_ICON_PATH):
                    with open(APPLE_TOUCH_ICON_PATH, "rb") as f:
                        return self._send_text(f.read(), content_type="image/png")
            if path == "/favicon.ico" and os.path.exists(ICON_ICO_PATH):
                with open(ICON_ICO_PATH, "rb") as f:
                    return self._send_text(f.read(), content_type="image/x-icon")
            if path == "/manifest.webmanifest":
                return self._send_json({"name": "传输助手", "short_name": "传输助手", "start_url": "/", "display": "standalone", "background_color": "#ffffff", "theme_color": "#ffffff", "icons": [{"src": "/apple-touch-icon.png?v=2", "sizes": "180x180", "type": "image/png"}]})
            if path == "/api/files":
                keys = ("id", "kind", "sender", "name", "text", "size", "size_str", "status", "progress", "ts")
                ratio = lambda t: round(t.size[1] / max(1, t.size[0]), 4) if t is not None else None
                files_out = [{**{k: it.get(k) for k in keys}, "url": f"/download/{it['id']}", "ratio": ratio(it.get("thumb"))} for it in file_queue.get_all()]
                page_ver = int(os.path.getmtime(MOBILE_HTML_PATH))
                return self._send_json({"count": len(files_out), "version": file_queue.version, "page_ver": page_ver, "files": files_out})
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

        def _send_json(self, obj):
            self._send_text(json.dumps(obj, ensure_ascii=False), content_type="application/json; charset=utf-8")

        def _stream_item(self, item, inline=False):
            disp = "inline" if inline else "attachment"
            if item.get("kind") == "memory":
                raw = item.get("bytes") or b""
                self.send_response(200); self.send_cors_headers()
                self.send_header("Content-Type", item.get("mime") or "application/octet-stream")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Content-Disposition", f"{disp}; filename*=UTF-8''{urllib.parse.quote(item['name'])}")
                self.end_headers(); self.wfile.write(raw)
                if item.get("sender") != "phone": file_queue.update_status(item["id"], status="已完成", progress=100)
                return
            self._stream_disk_file(item, disp=disp)

        def _stream_disk_file(self, item, disp="attachment"):
            file_path = item.get("path", "")
            if not os.path.exists(file_path):
                return self._send_text("File Missing", status=404)
            file_size = os.path.getsize(file_path)
            ext = os.path.splitext(item["name"])[1].lower() or ".bin"
            content_type = MIME_OVERRIDES.get(ext) or mimetypes.guess_type(file_path)[0] or "application/octet-stream"
            range_header = self.headers.get("Range")
            start, end = 0, file_size - 1
            if range_header and range_header.startswith("bytes="):
                parts = range_header[6:].split("-")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1

            content_length = end - start + 1
            self.send_response(206 if range_header else 200)
            if range_header:
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_cors_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(content_length))
            self.send_header("Accept-Ranges", "bytes")
            safe_utf8 = urllib.parse.quote(item["name"])
            self.send_header("Content-Disposition", f'{disp}; filename="Media{ext}"; filename*=UTF-8\'\'{safe_utf8}')
            self.end_headers()

            bytes_sent, start_ts, last_notify, track = 0, time.time(), 0.0, (disp != "inline")
            if track: file_queue.update_status(item["id"], status="正在传输", progress=0)
            try:
                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk = f.read(min(STREAM_CHUNK_SIZE, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                        bytes_sent += len(chunk)
                        now = time.time()
                        if track and now - last_notify > 0.25:
                            speed_str = f"{format_size(bytes_sent / max(now - start_ts, 0.001))}/s"
                            pct = int(((start + bytes_sent) / file_size) * 100)
                            file_queue.update_status(item["id"], status=f"传输中 {pct}%", progress=pct, speed=speed_str)
                            last_notify = now
                if track: file_queue.update_status(item["id"], status="已完成", progress=100, speed="")
            except Exception:
                pass

        def _render_mobile_portal(self):
            with open(MOBILE_HTML_PATH, "r", encoding="utf-8") as f:
                tpl = f.read()
            page = tpl.replace("{{HOST_IP}}", host_ip).replace("{{PORT}}", str(port))
            self._send_text(page, content_type="text/html; charset=utf-8")

    return FileHelperHandler


class ServerThread:
    def __init__(self, file_queue, port=DEFAULT_PORT):
        self.file_queue = file_queue
        self.port = port
        self.host_ip = get_local_ip()
        self.httpd = None
        self.extra_servers = []

    @staticmethod
    def _reclaim_port(port):
        try:
            out = subprocess.check_output(["netstat", "-ano", "-p", "TCP"], text=True, creationflags=0x08000000)
            for line in out.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    pid = int(line.strip().split()[-1])
                    if pid > 0 and pid != os.getpid():
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.15)
        except Exception:
            pass

    def start(self):
        handler_cls = make_handler(self.file_queue, self.host_ip, self.port)
        for _ in range(3):
            try:
                self.httpd = ThreadedHTTPServer(("0.0.0.0", self.port), handler_cls)
                break
            except OSError:
                self._reclaim_port(self.port)
        if not self.httpd:
            raise RuntimeError(f"无法绑定局域网服务端口 {self.port}")
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        def _bind_extras():
            for alt_port in (8787, 80):
                try:
                    srv = ThreadedHTTPServer(("0.0.0.0", alt_port), make_handler(self.file_queue, self.host_ip, alt_port))
                    self.extra_servers.append(srv)
                    threading.Thread(target=srv.serve_forever, daemon=True).start()
                except Exception:
                    pass
        threading.Thread(target=_bind_extras, daemon=True).start()

    def stop(self):
        for srv in [self.httpd, *self.extra_servers]:
            if srv:
                try: srv.shutdown(); srv.server_close()
                except Exception: pass

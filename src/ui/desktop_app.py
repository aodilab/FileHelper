import gc, io, os, sys, ctypes
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageGrab, ImageOps, ImageTk

from config.settings import DEFAULT_PORT, ICON_ICO_PATH, ICON_PNG_PATH, IMAGE_EXTS, TOKENS, WIN_WIDTH, WIN_HEIGHT
from src.core.queue_manager import FileQueue, copy_image_to_clipboard, get_local_ip
from src.core.http_server import ServerThread
from src.ui.renderer import AppleNeoRenderer
from src.ui.image_viewer import ImageViewerWindow
from src.ui.tray_icon import TrayController, trim_working_set


class FileHelperApp:
    """Main desktop window controller powered by TkinterDnD and AppleNeoRenderer."""

    def __init__(self, root, initial_files=None, start_hidden=False):
        self.root = root
        try: self.dpi_scale = max(1.0, ctypes.windll.user32.GetDpiForSystem() / 96.0)
        except Exception: self.dpi_scale = 1.0
        self.win_w, self.win_h = int(WIN_WIDTH * self.dpi_scale), int(WIN_HEIGHT * self.dpi_scale)
        self.root.title("文件传输助手"); self.root.geometry(f"{self.win_w}x{self.win_h}")
        self.root.minsize(int(380 * self.dpi_scale), int(480 * self.dpi_scale)); self.root.resizable(True, True); self.root.configure(bg=TOKENS["canvas_bg_hex"])
        try:
            if os.path.exists(ICON_ICO_PATH): self.root.iconbitmap(default=ICON_ICO_PATH)
            if os.path.exists(ICON_PNG_PATH): self._icon_img = ImageTk.PhotoImage(Image.open(ICON_PNG_PATH)); self.root.iconphoto(True, self._icon_img)
        except Exception: pass
        fams = set(tkfont.families(self.root))
        self.ui_font = next((f for f in ("HarmonyOS Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", "SimHei") if f in fams), "TkDefaultFont")
        self.file_queue = FileQueue()
        self.server_thread = ServerThread(self.file_queue, port=DEFAULT_PORT); self.server_thread.start()
        self.renderer, self.image_viewer = AppleNeoRenderer(self.win_w, self.win_h, ui_scale=self._calc_scale()), ImageViewerWindow(self)
        self.scroll_y, self.target_scroll_y, self._scroll_job, self.hover_id = 0.0, 0.0, None, None
        self.modal_open, self.drag_active, self.draft_image = False, False, None
        self.hitboxes, self.tk_img, self._entry_state, self.last_item_count, self.last_queue_version = {}, None, None, 0, -1
        self.canvas = tk.Canvas(self.root, width=self.win_w, height=self.win_h, bg=TOKENS["canvas_bg_hex"], highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True); self.canvas_img_id = self.canvas.create_image(0, 0, anchor="nw")
        self.input_entry = tk.Entry(self.root, bg="#ffffff", fg="#111111", insertbackground="#07c160", relief="flat", bd=0, highlightthickness=0, font=(self.ui_font, 11))
        self.input_entry.bind("<Return>", lambda e: self.send_input_text())
        self.entry_menu = tk.Menu(self.root, tearoff=0)
        for lbl, fn in [("粘贴", self.on_paste), ("清空输入", self._clear_composer)]: self.entry_menu.add_command(label=lbl, command=fn)
        self.input_entry.bind("<Button-3>", lambda e: self.entry_menu.tk_popup(e.x_root, e.y_root))
        self._sync_input_entry()
        for seq, fn in [
            ("<Motion>", self.on_mouse_move), ("<Leave>", self.on_mouse_leave), ("<Button-1>", self.on_mouse_click),
            ("<Button-3>", self.on_right_click), ("<Configure>", self.on_resize),
            ("<Return>", lambda e: self.send_input_text() if self.draft_image else None),
            ("<BackSpace>", self._on_draft_key), ("<Delete>", self._on_draft_key), ("<Escape>", self._on_draft_key),
        ]: self.canvas.bind(seq, fn)
        self.canvas.bind_all("<MouseWheel>", self.on_mouse_wheel)
        for seq in ("<Control-v>", "<Control-V>"): self.root.bind_all(seq, self.on_paste)
        self.tray = TrayController(self.file_queue.request_wakeup, lambda: setattr(self.file_queue, "quit_requested", True)); self.tray.start()
        for w in (self.root, self.input_entry):
            w.drop_target_register(DND_FILES)
            for seq, fn in [("<<DropEnter>>", self.on_drag_enter), ("<<DropLeave>>", self.on_drag_leave), ("<<Drop>>", self.on_tkdnd_drop)]: w.dnd_bind(seq, fn)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        if initial_files: self.file_queue.add_files(initial_files)
        self.last_item_count = len(self.file_queue.get_all())
        if start_hidden: self.root.withdraw(); trim_working_set()
        else:
            if self.last_item_count: self._scroll_to_bottom()
            self.redraw(); self.root.after(5, self._present_window)
        self.poll_queue()

    def _calc_scale(self): return self.dpi_scale * (1.2 if self.win_w > int(900 * self.dpi_scale) else 1.0)
    def _draft_pil(self): return self.draft_image["pil"] if self.draft_image else None
    def _sync_input_entry(self):
        hide = self.modal_open or (self.draft_image is not None)
        state = (hide, self.win_w, self.win_h, self.renderer.ui_scale)
        if state == self._entry_state: return
        self._entry_state = state
        if hide:
            self.input_entry.place_forget()
            if self.draft_image and not self.modal_open: self.canvas.focus_set()
            return
        sc = self.renderer.ui_scale
        self.input_entry.configure(font=(self.ui_font, max(10, int(round(11 * sc / self.dpi_scale)))))
        self.input_entry.place(x=int(64 * sc), y=int((self.renderer.height - 39) * sc), width=max(120, int((self.renderer.width - 148) * sc)), height=int(24 * sc))
    def on_resize(self, event):
        if event.width > 200 and event.height > 200 and (event.width != self.win_w or event.height != self.win_h):
            self.win_w, self.win_h = event.width, event.height; self.renderer.set_size(self.win_w, self.win_h, ui_scale=self._calc_scale()); self.redraw()
    def _present_window(self):
        try:
            self.root.deiconify(); self.root.wm_state("normal"); self.root.update_idletasks()
            u32 = ctypes.windll.user32; hwnd = u32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            if os.path.exists(ICON_ICO_PATH):
                hicon = u32.LoadImageW(0, ICON_ICO_PATH, 1, 256, 256, 0x0010)
                if hicon: u32.SendMessageW(hwnd, 0x0080, 1, hicon); u32.SendMessageW(hwnd, 0x0080, 0, hicon)
            u32.ShowWindow(hwnd, 5); u32.ShowWindow(hwnd, 9); u32.SetForegroundWindow(hwnd)
            self.root.attributes("-topmost", True); self.root.lift(); self.root.focus_force(); self.redraw(); self.input_entry.focus_set()
            self.root.after(180, lambda: self.root.attributes("-topmost", False))
        except Exception: pass
    def _scroll_to_bottom(self): self.scroll_y = self.target_scroll_y = float(self.renderer.max_scroll(self.file_queue.get_all(), self._draft_pil()))
    def _clear_composer(self): self.draft_image = None; self.input_entry.delete(0, tk.END); self.redraw(); self.input_entry.focus_set()
    def set_draft_image(self, pil_img, raw_bytes, name=None):
        self.draft_image = {"pil": pil_img.convert("RGBA"), "bytes": raw_bytes, "name": name or (self.draft_image or {}).get("name", "剪贴板截图.png")}; self.redraw()
    def _on_draft_key(self, event=None):
        if self.draft_image and not self.modal_open: self.draft_image, self.hover_id = None, None; self.redraw(); self.input_entry.focus_set()
    def send_input_text(self):
        sent = False
        if self.draft_image:
            d, self.draft_image, self.hover_id = self.draft_image, None, None; sent = True
            self.file_queue.add_files([d["path"]]) if d.get("path") else self.file_queue.add_memory_item(d["name"], d["bytes"], mime="image/png", sender="pc")
        txt = self.input_entry.get().strip()
        if txt: self.input_entry.delete(0, tk.END); self.file_queue.add_text_item(txt, sender="pc"); sent = True
        if sent: self._scroll_to_bottom(); self.redraw(); self.input_entry.focus_set()
    def redraw(self):
        self._sync_input_entry()
        pil_img, self.hitboxes = self.renderer.render(items=self.file_queue.get_all(), host_ip=self.server_thread.host_ip, port=self.server_thread.port, scroll_y=self.scroll_y, hover_id=self.hover_id, modal_open=self.modal_open, drag_active=self.drag_active, phone_connected=self.file_queue.phone_connected, draft_img=self._draft_pil())
        self.tk_img = ImageTk.PhotoImage(pil_img); self.canvas.itemconfig(self.canvas_img_id, image=self.tk_img)
    def _hit_test(self, x, y):
        if self.modal_open:
            box, cbox = self.hitboxes.get("modal_done"), self.hitboxes.get("modal_card_block")
            if box and box[0] <= x <= box[2] and box[1] <= y <= box[3]: return "modal_done"
            return None if (cbox and cbox[0] <= x <= cbox[2] and cbox[1] <= y <= cbox[3]) else "modal_backdrop"
        return next((k for k, box in (reversed(list(self.hitboxes.items())) if self.hitboxes else ()) if box[0] <= x <= box[2] and box[1] <= y <= box[3]), None)
    def on_mouse_move(self, event):
        hit = self._hit_test(event.x, event.y)
        self.root.configure(cursor="hand2" if (hit and hit not in ("modal_backdrop", "composer_box")) else "")
        if hit != self.hover_id: self.hover_id = hit; self.redraw()
    def on_mouse_leave(self, event):
        if self.hover_id is not None: self.hover_id = None; self.root.configure(cursor=""); self.redraw()
    def on_right_click(self, event):
        if not self.modal_open and event.y >= (self.renderer.height - self.renderer.draft_dims(self._draft_pil())[2]) * self.renderer.ui_scale: self.entry_menu.tk_popup(event.x_root, event.y_root)

    def on_paste(self, event=None):
        try: clip_data = ImageGrab.grabclipboard()
        except Exception: clip_data = None
        if isinstance(clip_data, Image.Image):
            buf = io.BytesIO(); clip_data.save(buf, format="PNG")
            self.set_draft_image(clip_data, buf.getvalue(), name="剪贴板截图.png"); return "break"
        if isinstance(clip_data, list) and clip_data:
            p0 = str(clip_data[0])
            if len(clip_data) == 1 and os.path.isfile(p0) and os.path.splitext(p0)[1].lower() in (*IMAGE_EXTS, ".bmp"):
                try: self.draft_image = {"pil": ImageOps.exif_transpose(Image.open(p0)).convert("RGBA"), "path": p0, "name": os.path.basename(p0)}; self.redraw(); return "break"
                except Exception: pass
            self.file_queue.add_files([str(p) for p in clip_data]); self._scroll_to_bottom(); return "break"
        if event is not None and getattr(event, "widget", None) == self.input_entry and not self.draft_image: return
        try:
            txt = self.root.clipboard_get()
            if txt and txt.strip(): self.draft_image = None; self._sync_input_entry(); self.input_entry.focus_set(); self.input_entry.insert(tk.INSERT, txt.strip()); self.redraw()
        except Exception: pass

    def on_mouse_click(self, event):
        hit = self._hit_test(event.x, event.y)
        if not hit: return
        if hit == "btn_send": self.send_input_text()
        elif hit == "draft_clear": self._on_draft_key()
        elif hit == "draft_preview" and self.draft_image: self.image_viewer.open_pil(self.draft_image["pil"])
        elif hit == "composer_box": (self.canvas if self.draft_image else self.input_entry).focus_set()
        elif hit == "btn_connect": self.server_thread.host_ip = get_local_ip(); self.modal_open, self.hover_id = True, None; self.redraw()
        elif hit in ("modal_done", "modal_backdrop"): self.modal_open, self.hover_id = False, None; self.redraw()
        elif hit == "btn_choose": self.choose_files()
        elif hit == "btn_clear": self.scroll_y = self.target_scroll_y = 0.0; self.file_queue.clear_all()
        elif hit.startswith("del_"): self.file_queue.remove(hit.split("del_")[1])
        elif hit.startswith("save_"): self._save_item_to_disk(hit.split("save_")[1])
        elif hit.startswith(("row_", "copy_")): self._handle_row_click(hit.split("_", 1)[1], hit.split("_", 1)[0])

    def _flash_status(self, item_id, label):
        self.file_queue.update_status(item_id, status=label)
        self.root.after(1500, lambda: self.file_queue.update_status(item_id, status="已完成"))

    def _save_item_to_disk(self, item_id):
        item = self.file_queue.get_by_id(item_id)
        src_p, raw = (item.get("path") if item else None), (item.get("bytes") if item else None)
        if not raw and (not src_p or not os.path.exists(src_p)): return
        save_p = filedialog.asksaveasfilename(initialfile=item.get("name", "image.png"), title="保存图片或文件")
        if save_p:
            if raw: open(save_p, "wb").write(raw)
            elif os.path.abspath(src_p) != os.path.abspath(save_p): __import__("shutil").copyfile(src_p, save_p)
            self._flash_status(item_id, "已保存")

    def _handle_row_click(self, item_id, action="row"):
        item = self.file_queue.get_by_id(item_id)
        if not item: return
        if item.get("kind") == "text": self.root.clipboard_clear(); self.root.clipboard_append(item.get("text", "")); self._flash_status(item_id, "已复制")
        elif item.get("thumb") is not None:
            if action == "copy" and copy_image_to_clipboard(item): self._flash_status(item_id, "已复制")
            elif action != "copy": self.image_viewer.open_item(item_id)
        elif item.get("kind") == "memory": self._save_item_to_disk(item_id)

    def on_mouse_wheel(self, event):
        if self.modal_open or (self.image_viewer.win and self.image_viewer.win.winfo_exists() and event.widget.winfo_toplevel() == self.image_viewer.win): return
        max_sc = float(self.renderer.max_scroll(self.file_queue.get_all(), self._draft_pil()))
        if max_sc <= 0: return
        self.target_scroll_y = max(0.0, min(max_sc, self.target_scroll_y - (event.delta / 120.0) * 96.0))
        if self._scroll_job is None: self._tick_scroll()

    def _tick_scroll(self):
        diff = self.target_scroll_y - self.scroll_y
        if abs(diff) <= 0.8: self.scroll_y, self._scroll_job = self.target_scroll_y, None; return self.redraw()
        self.scroll_y += diff * 0.38; self.redraw(); self._scroll_job = self.root.after(12, self._tick_scroll)

    def on_drag_enter(self, event):
        if not self.drag_active: self.drag_active = True; self.redraw()
    def on_drag_leave(self, event):
        if self.drag_active: self.drag_active = False; self.redraw()
    def on_tkdnd_drop(self, event):
        self.drag_active = False
        if not event or not event.data: return self.redraw()
        try: raw_files = self.root.tk.splitlist(event.data)
        except Exception: raw_files = [event.data]
        self.file_queue.add_files([str(f) for f in raw_files]); self._scroll_to_bottom(); self.redraw()
    def choose_files(self):
        files = filedialog.askopenfilenames(title="选择要发送的视频、图片或文件", filetypes=[("所有文件", "*.*")])
        if files: self.file_queue.add_files(files); self._scroll_to_bottom()

    def poll_queue(self):
        if self.file_queue.quit_requested: return self.quit_app()
        hidden = self.root.state() == "withdrawn"
        if self.file_queue.consume_wakeup():
            if len(self.file_queue.get_all()) > self.last_item_count: self._scroll_to_bottom()
            self.last_item_count = len(self.file_queue.get_all()); self.last_queue_version = self.file_queue.version
            self._present_window(); hidden = False
        elif self.file_queue.version != self.last_queue_version:
            self.last_queue_version = self.file_queue.version
            if self.file_queue.phone_connected and self.modal_open: self.modal_open = False
            cur_len = len(self.file_queue.get_all())
            if cur_len == 0: self.renderer.p._img_cache.clear()
            if cur_len > self.last_item_count: self._scroll_to_bottom()
            self.last_item_count = cur_len
            if not hidden: self.redraw()
        self.root.after(150 if hidden else 60, self.poll_queue)

    def on_close(self):
        if self.image_viewer.win and self.image_viewer.win.winfo_exists():
            try: self.image_viewer.win.destroy()
            except Exception: pass
        self.modal_open = False; self.root.withdraw()
        self.tk_img = None; self.canvas.itemconfig(self.canvas_img_id, image=""); self.renderer.p._img_cache.clear(); gc.collect(); trim_working_set()

    def quit_app(self):
        for fn in (self.tray.stop, lambda: self.image_viewer.win and self.image_viewer.win.winfo_exists() and self.image_viewer.win.destroy(), self.server_thread.stop, self.root.destroy):
            try: fn()
            except Exception: pass
        sys.exit(0)


def launch_desktop_app(initial_files=None, start_hidden=False):
    try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FileHelper.App.1"); ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    root = TkinterDnD.Tk()
    if start_hidden: root.withdraw()
    try: FileHelperApp(root, initial_files=initial_files, start_hidden=start_hidden); root.mainloop()
    except SystemExit: raise
    except Exception as e: messagebox.showerror("文件传输助手", f"启动失败：{e}"); raise

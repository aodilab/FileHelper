import io, os, sys, ctypes
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageGrab, ImageTk

from config.settings import DEFAULT_PORT, ICON_ICO_PATH, ICON_PNG_PATH, TOKENS, WIN_WIDTH, WIN_HEIGHT
from src.core.queue_manager import FileQueue, copy_image_to_clipboard
from src.core.http_server import ServerThread
from src.ui.renderer import AppleNeoRenderer


class AppleDropApp:
    """Main desktop window controller powered by TkinterDnD and AppleNeoRenderer."""

    def __init__(self, root, initial_files=None):
        self.root = root
        try: self.dpi_scale = max(1.0, ctypes.windll.user32.GetDpiForSystem() / 96.0)
        except Exception: self.dpi_scale = 1.0
        self.win_w, self.win_h = int(WIN_WIDTH * self.dpi_scale), int(WIN_HEIGHT * self.dpi_scale)
        self.root.title("文件传输助手"); self.root.geometry(f"{self.win_w}x{self.win_h}")
        self.root.minsize(int(380 * self.dpi_scale), int(480 * self.dpi_scale))
        self.root.resizable(True, True); self.root.configure(bg=TOKENS["canvas_bg_hex"])
        try:
            if os.path.exists(ICON_ICO_PATH): self.root.iconbitmap(default=ICON_ICO_PATH)
            if os.path.exists(ICON_PNG_PATH):
                self._icon_img = ImageTk.PhotoImage(Image.open(ICON_PNG_PATH))
                self.root.iconphoto(True, self._icon_img)
        except Exception: pass
        self.file_queue = FileQueue()
        self.server_thread = ServerThread(self.file_queue, port=DEFAULT_PORT); self.server_thread.start()
        self.renderer = AppleNeoRenderer(self.win_w, self.win_h, ui_scale=self._calc_scale())
        self.scroll_y, self.hover_id = 0, None
        self.modal_open, self.copied_toast, self.drag_active = False, False, False
        self.hitboxes, self.tk_img = {}, None
        self.last_item_count, self.last_queue_version = 0, -1

        self.canvas = tk.Canvas(self.root, width=self.win_w, height=self.win_h, bg=TOKENS["canvas_bg_hex"], highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas_img_id = self.canvas.create_image(0, 0, anchor="nw")

        self.input_entry = tk.Entry(
            self.root, bg="#ffffff", fg="#111111", insertbackground="#07c160",
            relief="flat", bd=0, highlightthickness=0, font=("HarmonyOS Sans SC", 11)
        )
        self.input_entry.bind("<Return>", lambda e: self.send_input_text())
        self._sync_input_entry()

        for seq, fn in [("<Motion>", self.on_mouse_move), ("<Leave>", self.on_mouse_leave), ("<Button-1>", self.on_mouse_click), ("<Configure>", self.on_resize)]:
            self.canvas.bind(seq, fn)
        self.canvas.bind_all("<MouseWheel>", self.on_mouse_wheel)
        for seq in ("<Control-v>", "<Control-V>"):
            self.root.bind_all(seq, self.on_paste)

        self.root.drop_target_register(DND_FILES)
        for seq, fn in [("<<DropEnter>>", self.on_drag_enter), ("<<DropLeave>>", self.on_drag_leave), ("<<Drop>>", self.on_tkdnd_drop)]:
            self.root.dnd_bind(seq, fn)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if initial_files:
            self.file_queue.add_files(initial_files)
        self.redraw()
        self.root.after(50, self._present_window)
        self.poll_queue()

    def _calc_scale(self):
        return self.dpi_scale * (1.2 if self.win_w > int(900 * self.dpi_scale) else 1.0)

    def _sync_input_entry(self):
        if self.modal_open:
            self.input_entry.place_forget()
            return
        sc = self.renderer.ui_scale
        self.input_entry.configure(font=("HarmonyOS Sans SC", max(10, int(round(11 * sc / self.dpi_scale)))))
        self.input_entry.place(
            x=int(64 * sc), y=int((self.renderer.height - 39) * sc),
            width=max(120, int((self.renderer.width - 148) * sc)), height=int(24 * sc)
        )

    def on_resize(self, event):
        if event.width > 200 and event.height > 200 and (event.width != self.win_w or event.height != self.win_h):
            self.win_w, self.win_h = event.width, event.height
            self.renderer.set_size(self.win_w, self.win_h, ui_scale=self._calc_scale())
            self.redraw()

    def _present_window(self):
        try:
            self.root.wm_state("normal"); self.root.deiconify(); self.root.update_idletasks()
            u32 = ctypes.windll.user32
            hwnd = u32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            if os.path.exists(ICON_ICO_PATH):
                hicon = u32.LoadImageW(0, ICON_ICO_PATH, 1, 256, 256, 0x0010)
                if hicon:
                    u32.SendMessageW(hwnd, 0x0080, 1, hicon)
                    u32.SendMessageW(hwnd, 0x0080, 0, hicon)
            u32.ShowWindow(hwnd, 9); u32.SetForegroundWindow(hwnd)
            self.root.attributes("-topmost", True); self.root.lift(); self.root.focus_force()
            self.input_entry.focus_set()
            self.root.after(180, lambda: self.root.attributes("-topmost", False))
        except Exception: pass

    def _scroll_to_bottom(self):
        self.scroll_y = self.renderer.max_scroll(self.file_queue.get_all())

    def send_input_text(self):
        txt = self.input_entry.get()
        if not txt or not txt.strip(): return
        self.input_entry.delete(0, tk.END)
        self.file_queue.add_text_item(txt.strip(), sender="pc")
        self._scroll_to_bottom(); self.redraw()

    def redraw(self):
        self._sync_input_entry()
        pil_img, self.hitboxes = self.renderer.render(
            items=self.file_queue.get_all(), host_ip=self.server_thread.host_ip, port=self.server_thread.port,
            scroll_y=self.scroll_y, hover_id=self.hover_id, modal_open=self.modal_open,
            copied_toast=self.copied_toast, drag_active=self.drag_active, phone_connected=self.file_queue.phone_connected,
        )
        self.tk_img = ImageTk.PhotoImage(pil_img)
        self.canvas.itemconfig(self.canvas_img_id, image=self.tk_img)

    def _hit_test(self, x, y):
        if self.modal_open:
            for k in ("modal_close", "modal_done"):
                box = self.hitboxes.get(k)
                if box and box[0] <= x <= box[2] and box[1] <= y <= box[3]: return k
            cbox = self.hitboxes.get("modal_card_block")
            return None if (cbox and cbox[0] <= x <= cbox[2] and cbox[1] <= y <= cbox[3]) else "modal_backdrop"
        for k, box in reversed(list(self.hitboxes.items())):
            if box[0] <= x <= box[2] and box[1] <= y <= box[3]: return k
        return None

    def on_mouse_move(self, event):
        hit = self._hit_test(event.x, event.y)
        self.root.configure(cursor="hand2" if (hit and hit != "modal_backdrop") else "")
        if hit != self.hover_id: self.hover_id = hit; self.redraw()

    def on_mouse_leave(self, event):
        if self.hover_id is not None: self.hover_id = None; self.root.configure(cursor=""); self.redraw()

    def on_paste(self, event=None):
        try: clip_data = ImageGrab.grabclipboard()
        except Exception: clip_data = None
        if isinstance(clip_data, Image.Image):
            if messagebox.askyesno("确认发送图片", "检测到剪贴板截图，确定发送到传输助手吗？", parent=self.root):
                buf = io.BytesIO(); clip_data.save(buf, format="PNG")
                self.file_queue.add_memory_item("剪贴板截图.png", buf.getvalue(), mime="image/png", sender="pc")
                self._scroll_to_bottom()
            return "break"
        if isinstance(clip_data, list) and clip_data:
            self.file_queue.add_files([str(p) for p in clip_data]); self._scroll_to_bottom()
            return "break"
        if event and getattr(event, "widget", None) == self.input_entry: return
        try:
            txt = self.root.clipboard_get()
            if txt and txt.strip(): self.input_entry.focus_set(); self.input_entry.insert(tk.INSERT, txt.strip())
        except Exception: pass

    def on_mouse_click(self, event):
        hit = self._hit_test(event.x, event.y)
        if not hit: return
        if hit == "btn_send": self.send_input_text()
        elif hit == "btn_connect": self.modal_open, self.hover_id = True, None; self.redraw()
        elif hit in ("modal_close", "modal_done", "modal_backdrop"):
            self.modal_open, self.copied_toast, self.hover_id = False, False, None; self.redraw()
        elif hit == "btn_choose": self.choose_files()
        elif hit == "btn_clear": self.scroll_y = 0; self.file_queue.clear_all()
        elif hit.startswith("del_"): self.file_queue.remove(hit.split("del_")[1])
        elif hit.startswith("save_"): self._save_item_to_disk(hit.split("save_")[1])
        elif hit.startswith(("row_", "copy_")): self._handle_row_click(hit.split("_", 1)[1])

    def _flash_status(self, item_id, label):
        self.file_queue.update_status(item_id, status=label)
        self.root.after(1500, lambda: self.file_queue.update_status(item_id, status="已完成"))

    def _save_item_to_disk(self, item_id):
        item = self.file_queue.get_by_id(item_id)
        if not item: return
        raw = item.get("bytes")
        if not raw and item.get("path") and os.path.exists(item["path"]):
            with open(item["path"], "rb") as f: raw = f.read()
        if not raw: return
        save_p = filedialog.asksaveasfilename(initialfile=item.get("name", "image.png"), title="保存图片或文件")
        if save_p:
            with open(save_p, "wb") as f: f.write(raw)
            self._flash_status(item_id, "已保存")

    def _handle_row_click(self, item_id):
        item = self.file_queue.get_by_id(item_id)
        if not item: return
        if item.get("kind") == "text":
            self.root.clipboard_clear(); self.root.clipboard_append(item.get("text", ""))
            self._flash_status(item_id, "已复制")
        elif item.get("thumb") is not None:
            if copy_image_to_clipboard(item): self._flash_status(item_id, "已复制")
        elif item.get("kind") == "memory" and item.get("bytes"):
            self._save_item_to_disk(item_id)

    def on_mouse_wheel(self, event):
        if self.modal_open: return
        max_sc = self.renderer.max_scroll(self.file_queue.get_all())
        if max_sc <= 0: return
        new_scroll = max(0, min(max_sc, self.scroll_y + int(-1 * (event.delta / 120) * 72)))
        if new_scroll != self.scroll_y: self.scroll_y = new_scroll; self.redraw()

    def on_drag_enter(self, event):
        if not self.drag_active: self.drag_active = True; self.redraw()

    def on_drag_leave(self, event):
        if self.drag_active: self.drag_active = False; self.redraw()

    def on_tkdnd_drop(self, event):
        self.drag_active = False
        if not event or not event.data: return self.redraw()
        try: raw_files = self.root.tk.splitlist(event.data)
        except Exception: raw_files = [event.data]
        self.file_queue.add_files([str(f) for f in raw_files])
        self._scroll_to_bottom(); self.redraw()

    def choose_files(self):
        files = filedialog.askopenfilenames(title="选择要发送的视频或照片", filetypes=[("所有文件", "*.*")])
        if files: self.file_queue.add_files(files); self._scroll_to_bottom()

    def poll_queue(self):
        if self.file_queue.consume_wakeup(): self._present_window()
        current_ver = self.file_queue.version
        if current_ver != self.last_queue_version:
            self.last_queue_version = current_ver
            if self.file_queue.phone_connected and self.modal_open: self.modal_open = False
            cur_len = len(self.file_queue.get_all())
            if cur_len > self.last_item_count: self._scroll_to_bottom()
            self.last_item_count = cur_len; self.redraw()
        self.root.after(100, self.poll_queue)

    def on_close(self):
        try: self.file_queue.clear_all(); self.server_thread.stop()
        except Exception: pass
        self.root.destroy(); sys.exit(0)


def launch_desktop_app(initial_files=None):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FileHelper.App.1")
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    root = TkinterDnD.Tk()
    AppleDropApp(root, initial_files=initial_files)
    root.mainloop()

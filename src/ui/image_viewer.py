import io, os
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageDraw, ImageOps, ImageTk
from config.settings import ICON_ICO_PATH, SUPERSAMPLE_SCALE as S, TOKENS
from src.core.queue_manager import copy_image_to_clipboard
from src.ui.components import DrawPrimitives
from src.ui.image_editor import ImageEditorSession

TOP_H, PAD_X, PAD_Y, MIN_W, MIN_ZOOM, MAX_ZOOM = 40, 16, 12, 420, 0.15, 8.0
STAGE_BG, BAR_BG = TOKENS["viewer_stage_bg"], TOKENS["viewer_bar_bg"]


def load_full_image(item):
    """Load full-resolution RGBA image from RAM bytes or disk path without temp copies."""
    if not item: return None
    try:
        if item.get("bytes"): return ImageOps.exif_transpose(Image.open(io.BytesIO(item["bytes"]))).convert("RGBA")
        if item.get("path") and os.path.exists(item["path"]): return ImageOps.exif_transpose(Image.open(item["path"])).convert("RGBA")
    except Exception: pass
    return item["thumb"].convert("RGBA") if item.get("thumb") is not None else None


class ImageViewerRenderer:
    """2x supersampled WeChat-style minimalist image viewer renderer with symmetric margins and top icon bar."""

    def __init__(self, width=MIN_W, height=760, ui_scale=1.0):
        self.p = DrawPrimitives(); self.set_size(width, height, ui_scale)

    def set_size(self, phys_w, phys_h, ui_scale=1.0):
        self.ui_scale, self.phys_w, self.phys_h = max(1.0, float(ui_scale)), max(320, int(phys_w)), max(360, int(phys_h))
        self.width, self.height, self.W, self.H = self.phys_w / self.ui_scale, self.phys_h / self.ui_scale, self.phys_w * S, self.phys_h * S
        self.p.set_scale(S * self.ui_scale)

    def calc_fit_zoom(self, img_w, img_h):
        return min(2.2, max(100, self.width - PAD_X * 2) / max(1, img_w), max(100, self.height - TOP_H - PAD_Y * 2) / max(1, img_h))

    def _draw_icon(self, draw, kind, cx, cy, col):
        sc, sw = self.p.scale, max(2, int(round(1.35 * self.p.scale)))
        P = lambda x, y: (int(round((cx + x) * sc)), int(round((cy + y) * sc)))
        if kind in ("btn_prev", "btn_next"):
            d = -1 if kind == "btn_prev" else 1
            draw.line([P(-6, 0), P(6, 0)], fill=col, width=sw); draw.line([P(d, -4.8), P(d * 6, 0), P(d, 4.8)], fill=col, width=sw, joint="curve")
        elif kind in ("btn_zoom_in", "btn_zoom_out"):
            draw.ellipse([*P(-7, -7), *P(4.2, 4.2)], outline=col, width=sw); draw.line([P(2.8, 2.8), P(6.8, 6.8)], fill=col, width=sw)
            draw.line([P(-4.1, -1.4), P(1.3, -1.4)], fill=col, width=sw)
            if kind == "btn_zoom_in": draw.line([P(-1.4, -4.1), P(-1.4, 1.3)], fill=col, width=sw)
        elif kind == "btn_zoom_toggle":
            draw.rounded_rectangle([*P(-8.5, -6.2), *P(8.5, 6.2)], radius=int(round(2.2 * sc)), outline=col, width=sw)
            self.p.text(draw, cx, cy + 0.3, "1:1", size=8.5, bold=True, color=col, anchor="mm")
        elif kind == "btn_rotate":
            draw.rounded_rectangle([*P(-4.5, -2.5), *P(7.0, 6.5)], radius=int(round(1.8 * sc)), outline=col, width=sw)
            draw.line([P(-7.0, 2.0), P(-7.0, -5.5), P(-0.5, -5.5)], fill=col, width=sw, joint="curve"); draw.line([P(-2.8, -7.6), P(-0.3, -5.5), P(-2.8, -3.4)], fill=col, width=sw, joint="curve")
        elif kind == "btn_edit":
            draw.line([P(1.2, -6.8), P(-6.8, -6.8), P(-6.8, 6.8), P(6.8, 6.8), P(6.8, -1.2)], fill=col, width=sw, joint="curve")
            draw.line([P(-1.8, 1.8), P(6.6, -6.6)], fill=col, width=sw); draw.line([P(-2.4, 2.4), P(-0.4, 1.8)], fill=col, width=sw)
        elif kind == "btn_save":
            draw.rounded_rectangle([*P(-7.2, -7.2), *P(7.2, 7.2)], radius=int(round(2.2 * sc)), outline=col, width=sw)
            draw.line([P(0, -4.5), P(0, 3.2)], fill=col, width=sw); draw.line([P(-3.2, 0.2), P(0, 3.5), P(3.2, 0.2)], fill=col, width=sw, joint="curve")

    def render(self, pil_img, zoom=1.0, pan_x=0.0, pan_y=0.0, has_prev=False, has_next=False, hover_id=None, status_toast="", fast=False, editor=None):
        hitboxes, ed_active, sc, img_box = {}, bool(editor and editor.active), self.p.scale, None
        canvas = Image.new("RGB", (self.W, self.H), STAGE_BG)
        stage_cx, stage_cy = self.width / 2.0, (TOP_H + self.height) / 2.0
        if pil_img is not None:
            iw, ih = pil_img.size
            zw, zh = max(1, int(round(iw * zoom * sc))), max(1, int(round(ih * zoom * sc)))
            x0, y0 = int(round((stage_cx + pan_x) * sc - zw / 2.0)), int(round((stage_cy + pan_y) * sc - zh / 2.0))
            vx0, vy0, vx1, vy1 = max(0, x0), max(int(round(TOP_H * sc)), y0), min(self.W, x0 + zw), min(self.H, y0 + zh)
            if vx1 > vx0 and vy1 > vy0:
                sx0, sy0, sx1, sy1 = max(0.0, (vx0 - x0) / zw * iw), max(0.0, (vy0 - y0) / zh * ih), min(float(iw), (vx1 - x0) / zw * iw), min(float(ih), (vy1 - y0) / zh * ih)
                flt = Image.Resampling.NEAREST if zoom >= 4.0 else (Image.Resampling.BILINEAR if fast else Image.Resampling.LANCZOS)
                patch = pil_img.crop((sx0, sy0, max(sx0 + 1, sx1), max(sy0 + 1, sy1))).resize((vx1 - vx0, vy1 - vy0), flt)
                canvas.paste(patch, (vx0, vy0), patch if patch.mode == "RGBA" else None); img_box = [vx0, vy0, vx1 - 1, vy1 - 1]
        draw = ImageDraw.Draw(canvas)
        if img_box: draw.rectangle(img_box, outline=(218, 218, 222), width=max(1, int(sc / 2)))
        if ed_active:
            draw = editor.render_stage_and_bar(canvas, draw, hitboxes, self, TOP_H, hover_id)
        else:
            bar_h_px = int(round(TOP_H * sc))
            draw.rectangle([0, 0, self.W, bar_h_px], fill=BAR_BG); draw.line([(0, bar_h_px), (self.W, bar_h_px)], fill=(220, 220, 224), width=max(1, int(sc / 2)))
            items = [("btn_prev", has_prev), ("btn_next", has_next), ("sep", False), ("btn_zoom_in", True), ("btn_zoom_out", True), ("btn_zoom_toggle", True), ("sep", False), ("btn_rotate", True), ("btn_edit", True), ("btn_save", True)]
            cur_x, cy = 14.0, TOP_H / 2.0
            for key, enabled in items:
                if key == "sep":
                    dx = int(round((cur_x + 3) * sc))
                    draw.line([(dx, int(round((cy - 7) * sc))), (dx, int(round((cy + 7) * sc)))], fill=(208, 208, 212), width=max(1, int(sc / 2))); cur_x += 12.0; continue
                bx, by, bw = cur_x, cy - 14, 28
                if enabled and hover_id == key: self.p.rounded_box(draw, bx, by, bw, bw, radius=5, bg=(218, 218, 222))
                self._draw_icon(draw, key, bx + bw / 2.0, cy, (44, 44, 46) if enabled else (180, 180, 185))
                if enabled: hitboxes[key] = (bx, by, bx + bw, by + bw)
                cur_x += 34.0
        if status_toast:
            pw, ph = self.p.measure(draw, status_toast, size=13)[0] + 28, 32
            px, py = (self.width - pw) / 2.0, (TOP_H + self.height - ph) / 2.0
            self.p.rounded_box(draw, px, py, pw, ph, radius=6, bg=(38, 38, 40))
            self.p.text(draw, self.width / 2.0, py + ph / 2.0, status_toast, size=13, color=(255, 255, 255), anchor="mm")
        if self.ui_scale != 1.0: hitboxes = {k: tuple(int(round(v * self.ui_scale)) for v in box) for k, box in hitboxes.items()}
        return canvas.reduce(S), hitboxes


class ImageViewerWindow:
    """WeChat-style standalone image viewer with symmetric margins and top-bar vector annotation editor."""

    def __init__(self, app):
        self.app, self.renderer, self.editor = app, ImageViewerRenderer(MIN_W, 760, ui_scale=app.dpi_scale), ImageEditorSession(self)
        self.win = self.canvas = self.canvas_img_id = self.tk_img = self.item_id = self.pil_img = None
        self.zoom, self.pan_x, self.pan_y, self.auto_fit = 1.0, 0.0, 0.0, True
        self.hover_id, self.status_toast, self._toast_job, self.hitboxes, self._drag_origin = None, "", None, {}, None

    def open_item(self, item_id, resize_win=True):
        img = load_full_image(self.app.file_queue.get_by_id(item_id))
        if img is not None: self._open_loaded(str(item_id), img, resize_win=resize_win)
    def open_pil(self, pil_img):
        if pil_img is not None: self._open_loaded("", pil_img.convert("RGBA"), resize_win=True)
    def _open_loaded(self, item_id, img, resize_win=True):
        self.editor.stop(); self.item_id, self.pil_img, self.status_toast = item_id, img, ""
        self._ensure_window(img.size, resize_win=resize_win); self.fit_to_window()

    def _ensure_window(self, img_size, resize_win=True):
        dpi, sw, sh = self.app.dpi_scale, self.app.root.winfo_screenwidth(), self.app.root.winfo_screenheight()
        iw, ih = max(1, img_size[0]), max(1, img_size[1])
        fz = min(2.2, (sw * 0.82 - PAD_X * 2 * dpi) / (iw * dpi), (sh * 0.84 - (TOP_H + PAD_Y * 2) * dpi) / (ih * dpi))
        tw, th = int(min(sw * 0.84, max(MIN_W * dpi, round((iw * fz + PAD_X * 2) * dpi)))), int(min(sh * 0.86, max(400 * dpi, round((ih * fz + TOP_H + PAD_Y * 2) * dpi))))
        geom = f"{tw}x{th}+{max(20, (sw - tw) // 2)}+{max(20, (sh - th) // 2)}"
        if self.win is not None and self.win.winfo_exists():
            if resize_win and self.win.state() == "normal": self.win.geometry(geom); self.renderer.set_size(tw, th, ui_scale=dpi)
            self.win.deiconify(); self.win.lift(); self.win.focus_force(); return
        self.win = tk.Toplevel(self.app.root); self.win.title("图片查看器")
        self.win.geometry(geom); self.win.minsize(int(MIN_W * dpi), int(380 * dpi)); self.win.configure(bg="#ededf0")
        if os.path.exists(ICON_ICO_PATH):
            try: self.win.iconbitmap(default=ICON_ICO_PATH)
            except Exception: pass
        self.renderer.set_size(tw, th, ui_scale=dpi)
        self.canvas = tk.Canvas(self.win, width=tw, height=th, bg="#ededf0", highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True); self.canvas_img_id = self.canvas.create_image(0, 0, anchor="nw")
        self.ctx_menu = tk.Menu(self.win, tearoff=0)
        for lbl, fn in [("复制", self._do_copy), ("编辑", self._start_edit), ("另存为...", self._do_save), ("旋转", self._do_rotate), ("实际大小 (1:1)", lambda: self._zoom_at(1.0)), ("适应窗口", self.fit_to_window)]:
            self.ctx_menu.add_command(label=lbl, command=fn)
        for seq, fn in [("<Motion>", self._on_motion), ("<ButtonPress-1>", self._on_press), ("<B1-Motion>", self._on_drag), ("<ButtonRelease-1>", self._on_release), ("<Double-Button-1>", self._on_double_click), ("<Button-3>", lambda e: self.ctx_menu.tk_popup(e.x_root, e.y_root)), ("<MouseWheel>", self._on_wheel), ("<Configure>", self._on_resize)]:
            self.canvas.bind(seq, fn)
        for seq, fn in [("<Escape>", self._on_esc), ("<Return>", lambda e: self.editor.handle_action("ed_done") if self.editor.active else None), ("<Left>", lambda e: None if self.editor.active else self._step_image(-1)), ("<Right>", lambda e: None if self.editor.active else self._step_image(1)), ("<Control-z>", lambda e: self.editor.undo() if self.editor.active else None), ("<Control-Z>", lambda e: self.editor.undo() if self.editor.active else None), ("<Control-c>", lambda e: self._do_copy()), ("<Control-C>", lambda e: self._do_copy()), ("<Control-s>", lambda e: self._do_save()), ("<Control-S>", lambda e: self._do_save())]:
            self.win.bind(seq, fn)

    def _on_esc(self, event=None):
        if self.editor.active: self.editor.stop(); self.fit_to_window()
        elif self.win: self.win.destroy()
    def _start_edit(self):
        if not self.editor.active and self.pil_img is not None: self.editor.start(self.pil_img); self.redraw()
    def _image_ids(self): return [it["id"] for it in self.app.file_queue.get_all() if it.get("thumb") is not None]
    def fit_to_window(self):
        cur = self.editor.current_image()
        if cur is None: return
        self.auto_fit, self.pan_x, self.pan_y, self.zoom = True, 0.0, 0.0, self.renderer.calc_fit_zoom(*cur.size); self.redraw()
    def _zoom_at(self, new_zoom, cx_log=None, cy_log=None):
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, new_zoom))
        if abs(new_zoom - self.zoom) < 1e-4: return
        self.auto_fit = False
        if cx_log is not None and cy_log is not None:
            scx, scy, r = self.renderer.width / 2.0, (TOP_H + self.renderer.height) / 2.0, new_zoom / self.zoom
            self.pan_x, self.pan_y = cx_log - scx - (cx_log - scx - self.pan_x) * r, cy_log - scy - (cy_log - scy - self.pan_y) * r
        self.zoom = new_zoom; self.redraw()
    def _step_image(self, delta):
        ids = self._image_ids()
        if self.item_id in ids and 0 <= ids.index(self.item_id) + delta < len(ids): self.open_item(ids[ids.index(self.item_id) + delta], resize_win=True)
    def _show_toast(self, msg):
        self.status_toast = msg; self.redraw()
        if self._toast_job and self.win and self.win.winfo_exists(): self.win.after_cancel(self._toast_job)
        if self.win and self.win.winfo_exists(): self._toast_job = self.win.after(1100, lambda: (setattr(self, "status_toast", ""), self.redraw()))

    def _do_copy(self):
        buf = io.BytesIO(); cur = self.editor.current_image()
        if cur is None: return
        cur.save(buf, format="PNG")
        if copy_image_to_clipboard({"bytes": buf.getvalue()}):
            if self.item_id: self.app._flash_status(self.item_id, "已复制")
            self._show_toast("已复制")

    def _do_save(self, override_img=None):
        cur = override_img or self.editor.current_image()
        if cur is None: return
        item = self.app.file_queue.get_by_id(self.item_id) if self.item_id else None
        save_p = filedialog.asksaveasfilename(initialfile=(item.get("name", "image.png") if item else "图片.png"), title="保存图片", parent=self.win)
        if save_p:
            cur.save(save_p); self._show_toast("已保存")
            if item: self.app._flash_status(self.item_id, "已保存")

    def _do_rotate(self):
        if self.pil_img is not None: self.pil_img = self.pil_img.rotate(-90, expand=True); self.fit_to_window()
    def _hit_test(self, x, y):
        return next((k for k, b in reversed(list(self.hitboxes.items())) if b[0] <= x <= b[2] and b[1] <= y <= b[3]), None)
    def _on_motion(self, event):
        hit = self._hit_test(event.x, event.y)
        self.win.configure(cursor="hand2" if hit else ("crosshair" if self.editor.active and event.y > TOP_H * self.renderer.ui_scale else ""))
        if hit != self.hover_id: self.hover_id = hit; self.redraw()

    def _on_press(self, event):
        if self.editor.active and self.editor.on_press(event.x, event.y, TOP_H): return
        hit = self._hit_test(event.x, event.y)
        if hit:
            self._drag_origin = None
            actions = {"btn_prev": lambda: self._step_image(-1), "btn_next": lambda: self._step_image(1), "btn_zoom_in": lambda: self._zoom_at(self.zoom * 1.25), "btn_zoom_out": lambda: self._zoom_at(self.zoom / 1.25), "btn_zoom_toggle": lambda: self._zoom_at(1.0) if abs(self.zoom - 1.0) > 0.05 else self.fit_to_window(), "btn_rotate": self._do_rotate, "btn_edit": self._start_edit, "btn_save": self._do_save}
            if hit in actions: actions[hit]()
            return
        if event.y > TOP_H * self.renderer.ui_scale: self._drag_origin = (event.x, event.y, self.pan_x, self.pan_y)

    def _on_drag(self, event):
        if self.editor.active and self.editor.on_drag(event.x, event.y, TOP_H): return
        if not self._drag_origin: return
        self.auto_fit = False; ox, oy, opx, opy = self._drag_origin; sc = self.renderer.ui_scale
        self.pan_x, self.pan_y = opx + (event.x - ox) / sc, opy + (event.y - oy) / sc; self.redraw(fast=True)
    def _on_release(self, event):
        if self.editor.active and self.editor.on_release(): return
        if self._drag_origin: self._drag_origin = None; self.redraw()
    def _on_double_click(self, event):
        if self.editor.active or self._hit_test(event.x, event.y) or self.pil_img is None or event.y <= TOP_H * self.renderer.ui_scale: return
        sc = self.renderer.ui_scale; self._zoom_at(1.0, event.x / sc, event.y / sc) if abs(self.zoom - 1.0) > 0.05 else self.fit_to_window()
    def _on_wheel(self, event):
        sc = self.renderer.ui_scale; self._zoom_at(self.zoom * (1.18 if event.delta > 0 else 1.0 / 1.18), event.x / sc, event.y / sc)
    def _on_resize(self, event):
        if event.width > 280 and event.height > 300 and (event.width != self.renderer.phys_w or event.height != self.renderer.phys_h):
            self.renderer.set_size(event.width, event.height, ui_scale=self.app.dpi_scale)
            self.fit_to_window() if self.auto_fit else self.redraw()

    def redraw(self, fast=False):
        cur = self.editor.current_image()
        if not self.win or not self.win.winfo_exists() or cur is None: return
        ids = self._image_ids(); idx = ids.index(self.item_id) if self.item_id in ids else -1
        pil_out, self.hitboxes = self.renderer.render(cur, zoom=self.zoom, pan_x=self.pan_x, pan_y=self.pan_y, has_prev=idx > 0, has_next=0 <= idx < len(ids) - 1, hover_id=self.hover_id, status_toast=self.status_toast, fast=fast, editor=self.editor)
        self.tk_img = ImageTk.PhotoImage(pil_out); self.canvas.itemconfig(self.canvas_img_id, image=self.tk_img)

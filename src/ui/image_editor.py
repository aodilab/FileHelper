import io, math
from PIL import Image, ImageDraw
from config.settings import TOKENS
from src.core.queue_manager import copy_image_to_clipboard

RED_INK = TOKENS["editor_red_ink"]
WX_GREEN, WX_GREEN_HOV = TOKENS["wx_green"][:3], TOKENS["wx_green_hover"][:3]


class ImageEditorSession:
    """WeChat PC style top-bar vector image editor focused on daily box-framing, arrows, mosaic & crop."""

    TOOLS = ("rect", "oval", "arrow", "pen", "mosaic", "crop")

    def __init__(self, viewer):
        self.v, self.active, self.tool = viewer, False, "rect"
        self.work_img = self.crop_box = None
        self.history, self.points, self.dragging = [], [], False

    def start(self, pil_img):
        if pil_img is None: return
        self.active, self.tool = True, "rect"
        self.work_img = pil_img.convert("RGBA").copy()
        self.history, self.points, self.dragging, self.crop_box = [], [], False, None

    def stop(self):
        self.active, self.points, self.dragging, self.crop_box = False, [], False, None

    def current_image(self):
        return self.work_img if (self.active and self.work_img is not None) else self.v.pil_img

    def _stage_origin(self, top_h):
        iw, ih = self.work_img.size
        scx, scy = self.v.renderer.width / 2.0, (top_h + self.v.renderer.height) / 2.0
        return scx + self.v.pan_x - (iw * self.v.zoom) / 2.0, scy + self.v.pan_y - (ih * self.v.zoom) / 2.0

    def _screen_to_img(self, ex, ey, top_h):
        sc = self.v.renderer.ui_scale
        lx, ly = ex / sc, ey / sc
        iw, ih = self.work_img.size
        x0, y0 = self._stage_origin(top_h)
        z = max(1e-4, self.v.zoom)
        return max(0.0, min(float(iw), (lx - x0) / z)), max(0.0, min(float(ih), (ly - y0) / z))

    def _draw_vector_shape(self, d, tool, pts, width):
        if tool in ("rect", "oval"):
            (x0, y0), (x1, y1) = pts[0], pts[-1]
            box = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
            if box[2] - box[0] > 3 and box[3] - box[1] > 3:
                (d.rectangle if tool == "rect" else d.ellipse)(box, outline=RED_INK, width=width)
        elif tool == "arrow":
            (x0, y0), (x1, y1) = pts[0], pts[-1]
            dx, dy = x1 - x0, y1 - y0
            if math.hypot(dx, dy) > 8:
                ang, hl = math.atan2(dy, dx), max(16.0, width * 4.4)
                d.line([(x0, y0), (x1 - math.cos(ang) * hl * 0.68, y1 - math.sin(ang) * hl * 0.68)], fill=RED_INK, width=width)
                d.polygon([(x1, y1), (x1 - hl * math.cos(ang - 0.46), y1 - hl * math.sin(ang - 0.46)), (x1 - hl * math.cos(ang + 0.46), y1 - hl * math.sin(ang + 0.46))], fill=RED_INK)
        elif tool == "pen" and len(pts) >= 2:
            d.line(pts, fill=RED_INK, width=width, joint="curve")
            for px, py in (pts[0], pts[-1]): d.ellipse([px - width / 2, py - width / 2, px + width / 2, py + width / 2], fill=RED_INK)

    def _apply_stroke(self, img, tool, pts):
        iw, ih = img.size
        sw = max(3, int(round(2.6 / max(0.15, self.v.zoom))))
        if tool in ("rect", "oval", "arrow", "pen"):
            xs, ys, pad = [p[0] for p in pts], [p[1] for p in pts], sw * 5 + 8
            bx0, by0 = max(0, int(min(xs) - pad)), max(0, int(min(ys) - pad))
            bx1, by1 = min(iw, int(max(xs) + pad)), min(ih, int(max(ys) + pad))
            pw, ph = bx1 - bx0, by1 - by0
            if pw > 2 and ph > 2:
                ov = Image.new("RGBA", (pw * 2, ph * 2), (0, 0, 0, 0))
                self._draw_vector_shape(ImageDraw.Draw(ov), tool, [((x - bx0) * 2.0, (y - by0) * 2.0) for x, y in pts], sw * 2)
                img.alpha_composite(ov.resize((pw, ph), Image.Resampling.BILINEAR), (bx0, by0))
        elif tool == "mosaic":
            blk = max(10, int(round(max(iw, ih) / 68.0)))
            xs, ys, pad = [p[0] for p in pts], [p[1] for p in pts], blk * 2
            bx0, by0 = max(0, (int(min(xs) - pad) // blk) * blk), max(0, (int(min(ys) - pad) // blk) * blk)
            bx1, by1 = min(iw, int(max(xs) + pad) + blk), min(ih, int(max(ys) + pad) + blk)
            pw, ph = bx1 - bx0, by1 - by0
            if pw > 2 and ph > 2:
                sub = img.crop((bx0, by0, bx1, by1))
                px_sub = sub.resize((max(1, pw // blk), max(1, ph // blk)), Image.Resampling.BILINEAR).resize((pw, ph), Image.Resampling.NEAREST)
                mask = Image.new("L", (pw, ph), 0); md = ImageDraw.Draw(mask); mw = blk * 2
                loc = [(x - bx0, y - by0) for x, y in pts]
                if len(loc) >= 2: md.line(loc, fill=255, width=mw, joint="curve")
                for px, py in loc: md.ellipse([px - mw / 2, py - mw / 2, px + mw / 2, py + mw / 2], fill=255)
                img.paste(px_sub, (bx0, by0), mask)

    def on_press(self, ex, ey, top_h):
        hit = self.v._hit_test(ex, ey)
        if hit and hit.startswith("ed_"): self.handle_action(hit); return True
        if ey <= top_h * self.v.renderer.ui_scale: return False
        pt = self._screen_to_img(ex, ey, top_h)
        self.dragging, self.points = True, [pt]
        if self.tool == "crop": self.crop_box = (pt[0], pt[1], pt[0], pt[1])
        return True

    def on_drag(self, ex, ey, top_h):
        if not self.dragging: return False
        pt = self._screen_to_img(ex, ey, top_h)
        if self.tool in ("rect", "oval", "arrow", "crop"):
            self.points = [self.points[0], pt]
            if self.tool == "crop":
                (x0, y0), (x1, y1) = self.points[0], pt
                self.crop_box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        elif math.hypot(pt[0] - self.points[-1][0], pt[1] - self.points[-1][1]) >= 1.5:
            self.points.append(pt)
            if self.tool == "mosaic":
                if len(self.points) == 2:
                    self.history.append(self.work_img.copy())
                    if len(self.history) > 20: self.history.pop(0)
                self._apply_stroke(self.work_img, "mosaic", self.points[-2:])
        self.v.redraw(fast=True); return True

    def on_release(self):
        if not self.dragging: return False
        self.dragging = False
        if self.tool not in ("crop", "mosaic") and len(self.points) >= 2:
            self.history.append(self.work_img.copy())
            if len(self.history) > 20: self.history.pop(0)
            self._apply_stroke(self.work_img, self.tool, self.points)
        self.points = []; self.v.redraw(); return True

    def undo(self):
        if self.crop_box is not None: self.crop_box = None
        elif self.history: self.work_img = self.history.pop()
        self.v.fit_to_window()

    def apply_crop(self):
        if not self.crop_box: return
        x0, y0, x1, y1 = [int(round(v)) for v in self.crop_box]
        self.crop_box = None
        if x1 - x0 >= 16 and y1 - y0 >= 16:
            self.history.append(self.work_img.copy())
            self.work_img = self.work_img.crop((x0, y0, x1, y1))
            self.v.fit_to_window()
        else: self.v.redraw()

    def encode_png(self):
        buf = io.BytesIO(); self.work_img.save(buf, format="PNG"); return buf.getvalue()

    def handle_action(self, key):
        if key.startswith("ed_tool_"):
            if self.crop_box: self.apply_crop()
            self.tool = key.split("ed_tool_")[1]; self.v.redraw()
        elif key == "ed_crop_ok": self.apply_crop()
        elif key == "ed_crop_no": self.crop_box = None; self.v.redraw()
        elif key == "ed_undo": self.undo()
        elif key == "ed_save":
            if self.crop_box: self.apply_crop()
            self.v._do_save(override_img=self.work_img)
        elif key == "ed_cancel": self.stop(); self.v.fit_to_window()
        elif key == "ed_done":
            if self.crop_box: self.apply_crop()
            done_img, raw_png = self.work_img.copy(), self.encode_png()
            self.v.pil_img = done_img
            copy_image_to_clipboard({"bytes": raw_png})
            if not self.v.item_id and getattr(self.v.app, "draft_image", None) is not None:
                self.v.app.set_draft_image(done_img, raw_png)
            self.stop(); self.v.fit_to_window(); self.v._show_toast("已完成并复制")

    def _draw_tool_icon(self, draw, kind, cx, cy, col, sc):
        sw = max(2, int(round(1.35 * sc)))
        P = lambda x, y: (int(round((cx + x) * sc)), int(round((cy + y) * sc)))
        if kind == "rect":
            draw.rounded_rectangle([*P(-6.5, -6.2), *P(6.5, 6.2)], radius=int(round(1.4 * sc)), outline=col, width=sw)
        elif kind == "oval":
            draw.ellipse([*P(-6.8, -6.5), *P(6.8, 6.5)], outline=col, width=sw)
        elif kind == "arrow":
            draw.line([P(-5.6, 5.6), P(5.6, -5.6)], fill=col, width=sw)
            draw.line([P(-0.5, -5.6), P(5.6, -5.6), P(5.6, 0.5)], fill=col, width=sw, joint="curve")
        elif kind == "pen":
            draw.polygon([P(-6.2, 6.2), P(-5.4, 2.2), P(3.4, -6.6), P(6.6, -3.4), P(-2.2, 5.4)], outline=col, width=sw)
            draw.line([P(1.4, -4.6), P(4.6, -1.4)], fill=col, width=sw)
        elif kind == "mosaic":
            draw.rounded_rectangle([*P(-6.8, -6.8), *P(6.8, 6.8)], radius=int(round(1.6 * sc)), outline=col, width=sw)
            for r in (-1, 0, 1):
                for c in (-1, 0, 1):
                    if (r + c) % 2 == 0: draw.rectangle([*P(c * 3.2 - 1.3, r * 3.2 - 1.3), *P(c * 3.2 + 1.3, r * 3.2 + 1.3)], fill=col)
        elif kind == "crop":
            draw.line([P(-4.5, -7.2), P(-4.5, 4.5), P(7.2, 4.5)], fill=col, width=sw, joint="curve")
            draw.line([P(-7.2, -4.5), P(4.5, -4.5), P(4.5, 7.2)], fill=col, width=sw, joint="curve")
        elif kind == "undo":
            draw.line([P(-5.5, -2.2), P(2.5, -2.2), P(5.5, 0.6), P(5.5, 4.2), P(2.0, 5.8), P(-3.5, 5.8)], fill=col, width=sw, joint="curve")
            draw.line([P(-2.4, -5.0), P(-5.8, -2.2), P(-2.4, 0.6)], fill=col, width=sw, joint="curve")

    def render_stage_and_bar(self, canvas, draw, hitboxes, renderer, top_h, hover_id):
        p, sc = renderer.p, renderer.p.scale
        ix0, iy0 = self._stage_origin(top_h)
        if self.dragging and len(self.points) >= 2 and self.tool in ("rect", "oval", "arrow", "pen"):
            scr_pts = [((ix0 + x * self.v.zoom) * sc, (iy0 + y * self.v.zoom) * sc) for x, y in self.points]
            self._draw_vector_shape(draw, self.tool, scr_pts, max(2, int(round(2.6 * sc))))
        if self.crop_box:
            iw, ih = self.work_img.size
            gx0, gy0 = round(ix0 * sc), round(max(top_h, iy0) * sc)
            gx1, gy1 = round((ix0 + iw * self.v.zoom) * sc), round((iy0 + ih * self.v.zoom) * sc)
            cx0, cy0, cx1, cy1 = self.crop_box
            rx0, ry0 = round((ix0 + cx0 * self.v.zoom) * sc), round((iy0 + cy0 * self.v.zoom) * sc)
            rx1, ry1 = round((ix0 + cx1 * self.v.zoom) * sc), round((iy0 + cy1 * self.v.zoom) * sc)
            if rx1 - rx0 > 6 and ry1 - ry0 > 6:
                scrim = Image.new("RGBA", (canvas.width, canvas.height), (0, 0, 0, 0))
                sd = ImageDraw.Draw(scrim)
                sd.rectangle([max(0, gx0), max(round(top_h * sc), gy0), min(canvas.width, gx1), min(canvas.height, gy1)], fill=(0, 0, 0, 105))
                sd.rectangle([rx0, ry0, rx1, ry1], fill=(0, 0, 0, 0))
                canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), scrim).convert("RGB"))
                draw = ImageDraw.Draw(canvas)
                draw.rectangle([rx0, ry0, rx1, ry1], outline=WX_GREEN, width=max(2, round(1.6 * sc)))
                if rx1 - rx0 >= round(24 * sc) and ry1 - ry0 >= round(24 * sc):
                    px, py = min(renderer.width - 76, max(8, rx1 / sc - 68)), min(renderer.height - 32, ry1 / sc + 6)
                    p.rounded_box(draw, px, py, 68, 26, radius=5, bg=(38, 38, 42))
                    p.text(draw, px + 17, py + 13, "×", size=14, color=(220, 220, 225), anchor="mm")
                    p.text(draw, px + 51, py + 13, "✓", size=13, bold=True, color=WX_GREEN, anchor="mm")
                    hitboxes["ed_crop_no"] = (px, py, px + 34, py + 26)
                    hitboxes["ed_crop_ok"] = (px + 34, py, px + 68, py + 26)

        bar_h_px = int(round(top_h * sc))
        draw.rectangle([0, 0, renderer.W, bar_h_px], fill=(235, 235, 237))
        draw.line([(0, bar_h_px), (renderer.W, bar_h_px)], fill=(220, 220, 224), width=max(1, int(sc / 2)))
        cur_x, cy = 12.0, top_h / 2.0
        for t in self.TOOLS:
            k, is_on = f"ed_tool_{t}", (self.tool == t)
            if is_on or hover_id == k: p.rounded_box(draw, cur_x, cy - 14, 28, 28, radius=5, bg=(214, 214, 218))
            self._draw_tool_icon(draw, t, cur_x + 14, cy, (30, 30, 32), sc)
            hitboxes[k] = (cur_x, cy - 14, cur_x + 28, cy + 14); cur_x += 32.0
        dx = int(round((cur_x + 3) * sc))
        draw.line([(dx, int(round((cy - 7) * sc))), (dx, int(round((cy + 7) * sc)))], fill=(208, 208, 212), width=max(1, int(sc / 2)))
        cur_x += 10.0
        can_undo = bool(self.history or self.crop_box)
        if can_undo and hover_id == "ed_undo": p.rounded_box(draw, cur_x, cy - 14, 28, 28, radius=5, bg=(218, 218, 222))
        self._draw_tool_icon(draw, "undo", cur_x + 14, cy, (44, 44, 46) if can_undo else (182, 182, 186), sc)
        if can_undo: hitboxes["ed_undo"] = (cur_x, cy - 14, cur_x + 28, cy + 14)
        cur_x += 32.0
        if hover_id == "ed_save": p.rounded_box(draw, cur_x, cy - 14, 28, 28, radius=5, bg=(218, 218, 222))
        renderer._draw_icon(draw, "btn_save", cur_x + 14, cy, (44, 44, 46))
        hitboxes["ed_save"] = (cur_x, cy - 14, cur_x + 28, cy + 14)

        done_x, cancel_x = renderer.width - 64, renderer.width - 108
        if hover_id == "ed_cancel": p.rounded_box(draw, cancel_x, cy - 13, 38, 26, radius=5, bg=(218, 218, 222))
        p.text(draw, cancel_x + 19, cy, "取消", size=12.5, color=(88, 88, 92), anchor="mm")
        hitboxes["ed_cancel"] = (cancel_x, cy - 13, cancel_x + 38, cy + 13)
        p.rounded_box(draw, done_x, cy - 13, 52, 26, radius=5, bg=WX_GREEN_HOV if hover_id == "ed_done" else WX_GREEN)
        p.text(draw, done_x + 26, cy, "完成", size=12.5, bold=True, color=(255, 255, 255), anchor="mm")
        hitboxes["ed_done"] = (done_x, cy - 13, done_x + 52, cy + 13)
        return draw

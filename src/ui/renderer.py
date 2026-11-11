from PIL import Image, ImageDraw, ImageFilter
from config.settings import SUPERSAMPLE_SCALE as S, TOKENS, WIN_WIDTH, WIN_HEIGHT
from src.ui.components import DrawPrimitives
from src.ui.chat_items import CHIP_H, ChatItemPainter, format_chip_time

NAV_H = 40
COMPOSER_H = 56
CHIP_GAP_SEC = 300


class AppleNeoRenderer:
    """Renders the WeChat File-Transfer style chat window: top links, message list, composer, QR sheet."""

    def __init__(self, width=WIN_WIDTH, height=WIN_HEIGHT, ui_scale=1.0):
        self.p = DrawPrimitives()
        self.painter = ChatItemPainter(self.p)
        self.set_size(width, height, ui_scale)

    def set_size(self, phys_w, phys_h, ui_scale=1.0):
        self.ui_scale = max(1.0, float(ui_scale))
        self.phys_w = max(320, int(phys_w))
        self.phys_h = max(360, int(phys_h))
        self.width = self.phys_w / self.ui_scale
        self.height = self.phys_h / self.ui_scale
        self.W = self.phys_w * S
        self.H = self.phys_h * S
        self.p.set_scale(S * self.ui_scale)

    # ---------- layout ----------
    def _max_bubble_w(self):
        return min(520, int(self.width * 0.68))

    def build_rows(self, items):
        """Flatten items into rows, inserting a centered time chip when messages are 5+ minutes apart."""
        rows, prev_ts, max_w = [], None, self._max_bubble_w()
        for it in items:
            ts = it.get("ts")
            if ts and (prev_ts is None or ts - prev_ts > CHIP_GAP_SEC):
                rows.append(("chip", format_chip_time(ts), None, CHIP_H))
            if ts:
                prev_ts = ts
            lay = self.painter.layout(it, max_w)
            rows.append(("item", it, lay, self.painter.row_height(lay[2])))
        return rows

    def draft_dims(self, draft_img=None):
        if draft_img is None:
            return 0, 0, COMPOSER_H
        iw, ih = draft_img.size
        ratio = min(min(196.0, self.width - 168.0) / max(1, iw), 96.0 / max(1, ih), 1.0)
        dw, dh = max(44, int(round(iw * ratio))), max(44, int(round(ih * ratio)))
        return dw, dh, dh + 36

    def max_scroll(self, items, draft_img=None):
        total_h = sum(r[3] for r in self.build_rows(items)) + 12
        avail_h = self.height - NAV_H - self.draft_dims(draft_img)[2]
        return max(0, int(total_h - avail_h))

    # ---------- render ----------
    def render(self, items, host_ip, port, scroll_y=0, hover_id=None, modal_open=False, drag_active=False, phone_connected=False, draft_img=None):
        hitboxes = {}
        need_alpha = modal_open or drag_active
        canvas = Image.new("RGBA" if need_alpha else "RGB", (self.W, self.H), TOKENS["canvas_bg"] if need_alpha else TOKENS["canvas_bg"][:3])
        dw, dh, comp_h = self.draft_dims(draft_img)
        comp_top = self.height - comp_h

        if items:
            self._render_messages(canvas, hitboxes, items, comp_top, scroll_y, hover_id)
        draw = ImageDraw.Draw(canvas)
        if drag_active:
            self.p.rounded_box(draw, 16, NAV_H + 8, self.width - 32, comp_top - NAV_H - 16, radius=14, bg=(7, 193, 96, 20), border=TOKENS["wx_green"])
            self.p.text(draw, self.width / 2, (NAV_H + comp_top) / 2, "松开鼠标即可发送", size=15, bold=True, color=TOKENS["semantic_green_text"], anchor="mm")

        self._render_top_links(draw, hitboxes, hover_id, phone_connected)
        self._render_composer(canvas, draw, hitboxes, comp_top, comp_h, hover_id, draft_img, dw, dh)

        if modal_open:
            canvas = self._render_modal_sheet(canvas, hitboxes, host_ip, port, hover_id)

        if self.ui_scale != 1.0:
            hitboxes = {k: tuple(int(round(v * self.ui_scale)) for v in box) for k, box in hitboxes.items()}
        return canvas.reduce(S), hitboxes

    def _render_messages(self, canvas, hitboxes, items, comp_top, scroll_y, hover_id):
        draw = ImageDraw.Draw(canvas)
        cur_y = NAV_H + 4 - scroll_y
        for kind, obj, lay, row_h in self.build_rows(items):
            if cur_y + row_h < NAV_H:
                cur_y += row_h
                continue
            if cur_y > comp_top:
                break
            if kind == "chip":
                self.p.text(draw, self.width / 2, cur_y + CHIP_H / 2, obj, size=12, color=TOKENS["text_secondary"], anchor="mm")
            else:
                is_mine = obj.get("sender", "pc") != "phone"
                tail = 5 if lay[0] == "text" else 0
                x = (self.width - 18 - tail - lay[1]) if is_mine else 18 + tail
                self.painter.paint(canvas, draw, hitboxes, obj, lay, x, cur_y, hover_id)
                draw = ImageDraw.Draw(canvas)
            cur_y += row_h

    def _render_top_links(self, draw, hitboxes, hover_id, phone_connected):
        sc = self.p.scale
        draw.rectangle([0, 0, self.W, round(NAV_H * sc)], fill=TOKENS["canvas_bg"])
        clr_col = TOKENS["link_blue_hover"] if hover_id == "btn_clear" else TOKENS["link_blue"]
        self.p.text(draw, self.width - 16, NAV_H / 2, "清空", size=14, color=clr_col, anchor="rm")
        hitboxes["btn_clear"] = (self.width - 54, 6, self.width - 10, NAV_H - 6)
        if not phone_connected:
            conn_col = TOKENS["link_blue_hover"] if hover_id == "btn_connect" else TOKENS["link_blue"]
            self.p.text(draw, self.width - 64, NAV_H / 2, "手机连接", size=14, color=conn_col, anchor="rm")
            hitboxes["btn_connect"] = (self.width - 132, 6, self.width - 58, NAV_H - 6)

    def _render_composer(self, canvas, draw, hitboxes, comp_top, comp_h, hover_id, draft_img=None, dw=0, dh=0):
        sc = self.p.scale
        draw.rectangle([0, round(comp_top * sc), self.W, self.H], fill=TOKENS["composer_bg"])
        self.p.hairline(draw, 0, comp_top, self.width)

        btn_y = comp_top + comp_h - 46
        px, pw = 12, 36
        p_bg = TOKENS["neutral_pill_hover"] if hover_id == "btn_choose" else TOKENS["card_bg"]
        self.p.rounded_box(draw, px, btn_y, pw, pw, radius=18, bg=p_bg, border=TOKENS["card_border"])
        self.p.text(draw, px + pw / 2, btn_y + pw / 2 - 1, "+", size=21, color=TOKENS["text_body"], anchor="mm")
        hitboxes["btn_choose"] = (px, btn_y, px + pw, btn_y + pw)

        ix, iy, iw, ih_box = 56, comp_top + 10, self.width - 132, comp_h - 20
        self.p.rounded_box(draw, ix, iy, iw, ih_box, radius=8, bg=TOKENS["card_bg"], border=TOKENS["card_border"])
        hitboxes["composer_box"] = (ix, iy, ix + iw, iy + ih_box)

        if draft_img is not None:
            dx, dy = ix + 8, iy + 8
            self.p.paste_rounded_image(canvas, draft_img, dx, dy, dw, dh, radius=4)
            draw = ImageDraw.Draw(canvas)
            self.p.rounded_box(draw, dx, dy, dw, dh, radius=4, bg=None, border=(228, 228, 232, 255))
            cx = round((dx + dw + 5) * sc)
            draw.line([(cx, round((dy + 1) * sc)), (cx, round((dy + dh - 1) * sc))], fill=TOKENS["wx_green"][:3], width=max(2, round(1.5 * sc)))
            hitboxes["draft_preview"] = (dx, dy, dx + dw, dy + dh)
            if hover_id in ("composer_box", "draft_preview", "draft_clear"):
                bx, by, br = dx + dw - 11, dy + 11, 8.0
                col = (29, 29, 31) if hover_id == "draft_clear" else (75, 75, 78)
                draw.ellipse([round((bx - br) * sc), round((by - br) * sc), round((bx + br) * sc), round((by + br) * sc)], fill=col)
                d = 2.8 * sc
                draw.line([(round(bx * sc - d), round(by * sc - d)), (round(bx * sc + d), round(by * sc + d))], fill=(255, 255, 255), width=max(2, round(1.3 * sc)))
                draw.line([(round(bx * sc - d), round(by * sc + d)), (round(bx * sc + d), round(by * sc - d))], fill=(255, 255, 255), width=max(2, round(1.3 * sc)))
                hitboxes["draft_clear"] = (bx - 10, by - 10, bx + 10, by + 10)

        sx, sw, sh = self.width - 68, 56, 36
        s_bg = TOKENS["wx_green_hover"] if hover_id == "btn_send" else TOKENS["wx_green"]
        self.p.rounded_box(draw, sx, btn_y, sw, sh, radius=8, bg=s_bg)
        self.p.text(draw, sx + sw / 2, btn_y + sh / 2, "发送", size=14, bold=True, color=(255, 255, 255, 255), anchor="mm")
        hitboxes["btn_send"] = (sx, btn_y, sx + sw, btn_y + sh)

    def _render_modal_sheet(self, canvas, hitboxes, host_ip, port, hover_id):
        blurred = canvas.filter(ImageFilter.GaussianBlur(10 * S))
        overlay = Image.new("RGBA", (self.W, self.H), (20, 20, 24, 76))
        canvas = Image.alpha_composite(blurred, overlay)

        hitboxes.clear()
        hitboxes["modal_backdrop"] = (0, 0, self.width, self.height)

        mw, mh = 340, 344
        mx, my = (self.width - mw) / 2, (self.height - mh) / 2
        self.p.shadow_card(canvas, mx, my, mw, mh, radius=18, shadow_alpha=36, shadow_blur=20, offset_y=6)
        draw = ImageDraw.Draw(canvas)
        hitboxes["modal_card_block"] = (mx, my, mx + mw, my + mh)

        url_str = f"http://{host_ip}:{port}"
        self.p.text(draw, mx + mw / 2, my + 32, "用 iPhone 相机扫码", size=17, bold=True, color=TOKENS["space_black"], anchor="mm")
        self.p.paste_qr_code(canvas, url_str, mx + mw / 2, my + 58, size_px=168)
        draw = ImageDraw.Draw(canvas)
        self.p.text(draw, mx + mw / 2, my + 246, url_str, size=12.5, mono=True, color=TOKENS["text_body"], anchor="mm")
        self.p.text(draw, mx + mw / 2, my + 268, "需和电脑连同一个 Wi-Fi", size=12, color=TOKENS["text_secondary"], anchor="mm")

        bx, by, bw, bh = mx + 24, my + mh - 52, mw - 48, 38
        self.p.rounded_box(draw, bx, by, bw, bh, radius=8, bg=TOKENS["wx_green_hover"] if hover_id == "modal_done" else TOKENS["wx_green"])
        self.p.text(draw, bx + bw / 2, by + bh / 2, "完成", size=14, bold=True, color=(255, 255, 255, 255), anchor="mm")
        hitboxes["modal_done"] = (bx, by, bx + bw, by + bh)
        return canvas

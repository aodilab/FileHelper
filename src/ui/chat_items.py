import os
import time
from config.settings import IMAGE_EXTS, TOKENS, VIDEO_EXTS

TEXT_SIZE = 14.5
LINE_H = 21
META_H = 18
ROW_GAP = 0
CHIP_H = 36
MAX_LINES = 10
HOVER_PREFIXES = ("row", "copy", "save", "del")


def format_chip_time(ts):
    lt, now = time.localtime(ts), time.localtime()
    if lt.tm_year == now.tm_year and lt.tm_yday == now.tm_yday:
        return time.strftime("%H:%M", lt)
    return time.strftime("%m月%d日 %H:%M", lt)


def file_badge(name):
    ext = os.path.splitext(name or "")[1].lower()
    label = (ext[1:].upper()[:4]) or "FILE"
    if ext in VIDEO_EXTS:
        return label, (88, 132, 245, 255)
    if ext in IMAGE_EXTS:
        return label, TOKENS["wx_green"]
    return label, (142, 142, 147, 255)


def file_status_text(it, is_mine):
    st = it.get("status", "")
    if "传输" in st:
        return st
    if st == "等待发送":
        return "等待手机接收"
    if st == "已完成":
        return "已发送" if is_mine else "已接收"
    if st == "已保存":
        return "已保存"
    return "点击另存为" if it.get("kind") == "memory" else st


class ChatItemPainter:
    """Lays out and paints one chat message: wrapped text bubble, image preview or file card."""

    def __init__(self, primitives):
        self.p = primitives
        self._wrap_cache = {}

    # ---------- layout ----------
    def wrap_text(self, text, max_w, size=TEXT_SIZE, max_lines=MAX_LINES):
        key = (text, int(max_w), size, max_lines, round(self.p.scale, 3))
        if key in self._wrap_cache:
            return self._wrap_cache[key]
        font = self.p.font(size)
        sc = self.p.scale
        lines = []
        for para in (text or "")[:1200].replace("\r", "").split("\n"):
            cur, cur_w = "", 0.0
            for ch in para:
                cw = font.getlength(ch) / sc
                if cur and cur_w + cw > max_w:
                    lines.append(cur)
                    cur, cur_w = ch, cw
                else:
                    cur, cur_w = cur + ch, cur_w + cw
            lines.append(cur)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1][:-1] + "…"
        widths = [font.getlength(ln) / sc for ln in lines]
        if len(self._wrap_cache) > 400:
            self._wrap_cache.clear()
        self._wrap_cache[key] = (lines, widths)
        return lines, widths

    def layout(self, it, max_bub_w):
        """Return (kind, bubble_w, bubble_h, extra) for one queue item."""
        thumb = it.get("thumb")
        if thumb is not None:
            iw, ih = thumb.size
            ratio = min(240.0 / max(1, iw), 250.0 / max(1, ih))
            return "image", max(64, round(iw * ratio)), max(48, round(ih * ratio)), None
        if it.get("kind") == "text":
            lines, widths = self.wrap_text(it.get("text") or it.get("name", ""), max_bub_w - 24)
            w = max(44, int(max(widths or [0]) + 25))
            return "text", w, len(lines) * LINE_H + 18, lines
        w = min(max_bub_w, 268)
        name_lines, _ = self.wrap_text(it.get("name", ""), w - 78, size=13.5, max_lines=2)
        return "file", w, (68 if len(name_lines) <= 1 else 84), name_lines

    @staticmethod
    def row_height(bub_h):
        return bub_h + META_H + ROW_GAP

    # ---------- painting ----------
    def paint(self, canvas, draw, hitboxes, it, lay, x, y, hover_id):
        kind, w, h, extra = lay
        is_mine = it.get("sender", "pc") != "phone"
        if kind == "text":
            self._paint_text(draw, x, y, w, h, extra, is_mine)
        elif kind == "image":
            self.p.paste_rounded_image(canvas, it["thumb"], x, y, w, h, radius=8)
        else:
            self._paint_file_card(draw, it, x, y, w, h, extra or [it.get("name", "")], is_mine)
        hovered = bool(hover_id) and hover_id.split("_", 1)[0] in HOVER_PREFIXES and hover_id.split("_", 1)[-1] == it["id"]
        x0, x1 = self._paint_meta(draw, hitboxes, it, kind, x, y + h, w, is_mine, hovered, hover_id)
        hitboxes[f"row_{it['id']}"] = (min(x, x0), y, max(x + w, x1), y + h + META_H)
        for k in [k for k in hitboxes if k.endswith(f"_{it['id']}") and not k.startswith("row_")]:
            hitboxes[k] = hitboxes.pop(k)

    def _paint_text(self, draw, x, y, w, h, lines, is_mine):
        bg = TOKENS["wx_green_bubble"] if is_mine else TOKENS["card_bg"]
        self.p.rounded_box(draw, x, y, w, h, radius=6, bg=bg)
        sc = self.p.scale
        tx = x + w if is_mine else x
        d = 5 if is_mine else -5
        pts = [(tx, y + 11), (tx + d, y + 16), (tx, y + 21)]
        draw.polygon([(round(px * sc), round(py * sc)) for px, py in pts], fill=bg)
        for i, ln in enumerate(lines):
            self.p.text(draw, x + 12, y + 9 + i * LINE_H + LINE_H / 2, ln, size=TEXT_SIZE, color=TOKENS["space_black"], anchor="lm")

    def _paint_file_card(self, draw, it, x, y, w, h, name_lines, is_mine):
        self.p.rounded_box(draw, x, y, w, h, radius=8, bg=TOKENS["card_bg"], border=TOKENS["card_border"])
        if len(name_lines) <= 1:
            self.p.text(draw, x + 14, y + 23, name_lines[0] if name_lines else "", size=13.5, color=TOKENS["space_black"], anchor="lm")
            sub_y = y + 47
        else:
            self.p.text(draw, x + 14, y + 19, name_lines[0], size=13.5, color=TOKENS["space_black"], anchor="lm")
            self.p.text(draw, x + 14, y + 37, name_lines[1], size=13.5, color=TOKENS["space_black"], anchor="lm")
            sub_y = y + 61
        sub = f"{it.get('size_str', '')}   {file_status_text(it, is_mine)}"
        self.p.text(draw, x + 14, sub_y, sub, size=12, color=TOKENS["text_secondary"], anchor="lm")
        label, col = file_badge(it.get("name"))
        bx, by = x + w - 50, y + (h - 42) / 2
        self.p.rounded_box(draw, bx, by, 36, 42, radius=6, bg=col)
        self.p.text(draw, bx + 18, by + 21, label, size=10.5, bold=True, color=(255, 255, 255, 255), anchor="mm")
        pct = it.get("progress") or 0
        if "传输" in it.get("status", "") and pct > 0:
            self.p.rounded_box(draw, x + 14, y + h - 7, (w - 28) * min(100, pct) / 100, 3, radius=1.5, bg=TOKENS["wx_green"])

    def _paint_meta(self, draw, hitboxes, it, kind, bx, top, bw, is_mine, hovered, hover_id):
        """Hover-only action links keep consecutive items spaced cleanly like WeChat; feedback flashes in place."""
        iid, st = it["id"], it.get("status", "")
        green, gray, link = TOKENS["semantic_green_text"], TOKENS["text_secondary"], TOKENS["link_blue"]
        actions = []
        if kind in ("text", "image"):
            copied = st == "已复制"
            actions.append(("已复制" if copied else "复制", green if copied else link, f"copy_{iid}", copied))
        if kind == "image" or (kind == "file" and it.get("kind") == "memory"):
            saved = st == "已保存"
            actions.append(("已保存" if saved else "另存为", green if saved else link, f"save_{iid}", saved))
        del_col = TOKENS["semantic_red_text"] if hover_id == f"del_{iid}" else gray
        actions.append(("删除", del_col, f"del_{iid}", False))
        vis = [s for s in actions if s[3] or hovered]
        if not vis:
            return bx, bx
        gap, size = 12, 11.5
        widths = [self.p.measure(draw, t, size=size)[0] for t, _, _, _ in vis]
        total = sum(widths) + gap * max(0, len(vis) - 1)
        cur = (bx + bw - total) if is_mine else bx
        x0, cy = cur, top + META_H / 2
        for (txt, col, key, _), sw in zip(vis, widths):
            self.p.text(draw, cur, cy, txt, size=size, color=col, anchor="lm")
            if key:
                hitboxes[key] = (cur - 4, top, cur + sw + 4, top + META_H)
            cur += sw + gap
        return x0, cur - gap

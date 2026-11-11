import itertools
import os
import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from config.settings import SUPERSAMPLE_SCALE as S, TOKENS

_IMG_SEQ = itertools.count(1)


class DrawPrimitives:
    """Low-level 2x supersampled drawing primitives and vector icons following Apple Neo Design."""

    def __init__(self):
        self._fonts = {}
        self._img_cache = {}
        self.scale = float(S)

    def set_scale(self, scale):
        self.scale = max(1.0, float(scale))

    def font(self, size, bold=False, mono=False):
        scaled = max(10, int(round(size * self.scale)))
        key = (scaled, bold, mono)
        if key not in self._fonts:
            dirs = [
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts"),
                r"C:\Windows\Fonts",
            ]
            if mono:
                names = ["HarmonyOS_Sans_SC_Medium.ttf", "consola.ttf", "Noto Sans SC (TrueType).otf"]
            elif bold:
                names = [
                    "HarmonyOS_Sans_SC_Medium.ttf",
                    "SourceHanSansCN-Medium.ttf",
                    "Noto Sans SC Medium (TrueType).otf",
                    "Dengb.ttf",
                ]
            else:
                names = [
                    "HarmonyOS_Sans_SC_Regular.ttf",
                    "SourceHanSansCN-Regular.ttf",
                    "Noto Sans SC (TrueType).otf",
                    "Deng.ttf",
                ]
            loaded = None
            for fn in names:
                for d in dirs:
                    p = os.path.join(d, fn)
                    if os.path.exists(p):
                        try:
                            loaded = ImageFont.truetype(p, scaled)
                            break
                        except Exception:
                            pass
                if loaded:
                    break
            self._fonts[key] = loaded or ImageFont.load_default()
        return self._fonts[key]

    def text(self, draw, x, y, txt, size=14, color=TOKENS["space_black"], bold=False, mono=False, anchor="la"):
        f = self.font(size, bold=bold, mono=mono)
        sc = self.scale
        draw.text((int(round(x * sc)), int(round(y * sc))), txt, font=f, fill=color, anchor=anchor)

    def measure(self, draw, txt, size=14, bold=False, mono=False):
        f = self.font(size, bold=bold, mono=mono)
        bbox = draw.textbbox((0, 0), txt, font=f)
        return (bbox[2] - bbox[0]) / self.scale, (bbox[3] - bbox[1]) / self.scale

    def fit_text_size(self, draw, txt, max_w, start_size=14.0, min_size=10.5, bold=True):
        """Dynamically scale font size so long filenames never truncate with ellipsis."""
        sz = start_size
        while sz > min_size:
            w, _ = self.measure(draw, txt, size=sz, bold=bold)
            if w <= max_w:
                return sz
            sz -= 0.5
        return min_size

    def pill(self, draw, x, y, w, h, bg, border=None):
        sc = self.scale
        X, Y, W, H = int(round(x * sc)), int(round(y * sc)), int(round(w * sc)), int(round(h * sc))
        draw.rounded_rectangle(
            [X, Y, X + W, Y + H], radius=H // 2, fill=bg, outline=border, width=max(1, int(sc / 2)) if border else 0
        )

    def rounded_box(self, draw, x, y, w, h, radius, bg, border=None):
        sc = self.scale
        X, Y, W, H = int(round(x * sc)), int(round(y * sc)), int(round(w * sc)), int(round(h * sc))
        draw.rounded_rectangle(
            [X, Y, X + W, Y + H], radius=int(round(radius * sc)), fill=bg, outline=border, width=max(1, int(sc / 2)) if border else 0
        )

    def hairline(self, draw, x1, y, x2):
        sc = self.scale
        Y = int(round(y * sc))
        draw.line([(int(round(x1 * sc)), Y), (int(round(x2 * sc)), Y)], fill=TOKENS["hairline"], width=max(1, int(sc / 2)))

    def shadow_card(self, base_img, x, y, w, h, radius=20, bg=TOKENS["card_bg"],
                    border=None, shadow_alpha=9, shadow_blur=12, offset_y=2):
        """Apple Neo card with subtle 0 2px 12px rgba(0,0,0,0.03) ambient shadow."""
        sc = self.scale
        X, Y, W, H = int(round(x * sc)), int(round(y * sc)), int(round(w * sc)), int(round(h * sc))
        R = int(round(radius * sc))
        pad = int(round((shadow_blur + 10) * sc))

        patch = Image.new("RGBA", (W + pad * 2, H + pad * 2), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(patch)

        if shadow_alpha > 0:
            sy = pad + int(round(offset_y * sc))
            pdraw.rounded_rectangle([pad, sy, pad + W, sy + H], radius=R, fill=(0, 0, 0, shadow_alpha))
            patch = patch.filter(ImageFilter.GaussianBlur(shadow_blur * sc / 2))
            pdraw = ImageDraw.Draw(patch)

        pdraw.rounded_rectangle(
            [pad, pad, pad + W, pad + H], radius=R, fill=bg, outline=border, width=max(1, int(sc / 2)) if border else 0
        )
        base_img.alpha_composite(patch, (X - pad, Y - pad))

    def paste_qr_code(self, canvas, url, center_x, top_y, size_px=128):
        sc = self.scale
        qr_size = int(round(size_px * sc))
        qr = qrcode.QRCode(version=1, box_size=4, border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA").resize((qr_size, qr_size), Image.Resampling.NEAREST)
        canvas.alpha_composite(qr_img, (int(round(center_x * sc)) - qr_size // 2, int(round(top_y * sc))))

    def paste_rounded_image(self, canvas, pil_img, x, y, w, h, radius=10):
        sc = self.scale
        X, Y, W, H = int(round(x * sc)), int(round(y * sc)), max(1, int(round(w * sc))), max(1, int(round(h * sc)))
        R = int(round(radius * sc))
        uid = getattr(pil_img, "_cache_uid", 0)
        if not uid:
            uid = next(_IMG_SEQ); pil_img._cache_uid = uid
        key = (uid, W, H, R)
        patch = self._img_cache.get(key)
        if patch is None:
            fg = Image.new("RGBA", (W, H), (255, 255, 255, 255))
            fg.alpha_composite(pil_img.resize((W, H), Image.Resampling.LANCZOS).convert("RGBA"))
            mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill=255)
            patch = Image.new("RGBA", (W, H), TOKENS["canvas_bg"])
            patch.paste(fg, (0, 0), mask)
            ImageDraw.Draw(patch).rounded_rectangle([0, 0, W - 1, H - 1], radius=R, outline=TOKENS["card_border"], width=max(1, int(sc / 2)))
            if len(self._img_cache) > 64: self._img_cache.clear()
            self._img_cache[key] = patch
        canvas.paste(patch, (X, Y))

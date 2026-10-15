"""Brand templates for post images, drawn with Pillow (no AI imagery, no per-image cost).

Every image is 1080x1350 (Instagram 4:5 portrait) JPEG, because Instagram's publishing API
accepts JPEG only. Reel covers are 1080x1920.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).parent / "fonts"
F_DISPLAY = str(FONTS / "InterDisplay-ExtraBold.ttf")
F_SEMI = str(FONTS / "Inter-SemiBold.ttf")
F_BODY = str(FONTS / "Inter-Regular.ttf")

INDIGO = (61, 59, 243)
INDIGO_DEEP = (43, 41, 196)
SAFFRON = (255, 159, 28)
BG = (250, 247, 242)
INK = (20, 20, 43)
MUTED = (91, 91, 115)
WHITE = (255, 255, 255)
LINE = (231, 226, 217)

W, H = 1080, 1350
M = 96  # outer margin

PILLAR_LABEL = {"tool_test": "TOOL TEST", "workflow": "WORKFLOW", "prompts": "PROMPTS",
                "news": "AI NEWS", "career": "CAREER"}

# Characters Inter cannot draw (emoji, pictographs) are removed rather than shown as boxes.
_UNSUPPORTED = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


def clean(text: str | None) -> str:
    text = _UNSUPPORTED.sub("", text or "")
    return re.sub(r"[ \t]+", " ", text).strip()


@dataclass
class Brand:
    name: str = "Kaam Ka AI"
    handle: str = "@kaamka.ai"


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words, line = para.split(), ""
        for w in words:
            trial = f"{line} {w}".strip()
            if draw.textlength(trial, font=font) <= max_w:
                line = trial
            else:
                if line:
                    lines.append(line)
                # a single word wider than the box is broken by characters
                while draw.textlength(w, font=font) > max_w and len(w) > 1:
                    cut = len(w)
                    while cut > 1 and draw.textlength(w[:cut], font=font) > max_w:
                        cut -= 1
                    lines.append(w[:cut])
                    w = w[cut:]
                line = w
        lines.append(line)
    return [ln for ln in lines if ln] or [""]


def fit_text(draw, text, font_path, max_w, max_h, start, minimum, leading=1.18):
    """Largest font size (start→minimum) at which the wrapped text fits the box.
    At the minimum size, overflowing lines are cut and end with an ellipsis."""
    size = start
    while True:
        font = _font(font_path, size)
        lines = _wrap(draw, text, font, max_w)
        lh = int(size * leading)
        if len(lines) * lh <= max_h or size <= minimum:
            break
        size -= 4
    max_lines = max(1, max_h // lh)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last[:-1].rstrip()
        lines[-1] = last + "…"
    return font, lines, lh


def _draw_lines(draw, xy, lines, font, lh, fill):
    x, y = xy
    for ln in lines:
        draw.text((x, y), ln, font=font, fill=fill)
        y += lh
    return y


def _header(draw, brand: Brand, counter: str | None, on_dark: bool):
    fg = WHITE if on_dark else INK
    mark_bg = WHITE if on_dark else INDIGO
    mark_fg = INDIGO if on_dark else WHITE
    draw.rounded_rectangle((M, 72, M + 60, 132), radius=16, fill=mark_bg)
    k = _font(F_DISPLAY, 38)
    kw = draw.textlength("K", font=k)
    draw.text((M + 30 - kw / 2, 78), "K", font=k, fill=mark_fg)
    draw.text((M + 80, 82), brand.name, font=_font(F_SEMI, 34), fill=fg)
    if counter:
        f = _font(F_SEMI, 30)
        tw = draw.textlength(counter, font=f)
        draw.text((W - M - tw, 86), counter, font=f, fill=(fg if on_dark else MUTED))


def _footer(draw, brand: Brand, on_dark: bool, height: int, extra: str | None = None):
    f = _font(F_SEMI, 30)
    color = (220, 220, 255) if on_dark else MUTED
    draw.text((M, height - 120), brand.handle, font=f, fill=color)
    if extra:
        tw = draw.textlength(extra, font=f)
        draw.text((W - M - tw, height - 120), extra, font=f, fill=SAFFRON)


def _pill(draw, xy, text):
    f = _font(F_SEMI, 28)
    tw = draw.textlength(text, font=f)
    x, y = xy
    draw.rounded_rectangle((x, y, x + tw + 48, y + 56), radius=28, fill=SAFFRON)
    draw.text((x + 24, y + 11), text, font=f, fill=INK)
    return y + 56


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90, optimize=True, progressive=True)
    return buf.getvalue()


def cover(headline: str, subline: str, pillar: str | None, brand: Brand, counter: str | None = None,
          swipe: bool = False, height: int = H) -> bytes:
    img = Image.new("RGB", (W, height), INDIGO)
    d = ImageDraw.Draw(img)
    d.ellipse((W - 420, height - 520, W + 260, height + 160), fill=INDIGO_DEEP)  # quiet depth, no gradient
    _header(d, brand, counter, on_dark=True)
    y = 230
    if pillar in PILLAR_LABEL:
        y = _pill(d, (M, y), PILLAR_LABEL[pillar]) + 48
    box_h = int((height - y - 260) * (0.72 if subline else 1.0))
    font, lines, lh = fit_text(d, clean(headline), F_DISPLAY, W - 2 * M, box_h, start=124, minimum=64, leading=1.08)
    y = _draw_lines(d, (M, y), lines, font, lh, WHITE) + 36
    if subline:
        sfont, slines, slh = fit_text(d, clean(subline), F_BODY, W - 2 * M, height - y - 220, 46, 34, 1.3)
        _draw_lines(d, (M, y), slines, sfont, slh, (226, 226, 255))
    _footer(d, brand, True, height, "Swipe →" if swipe else None)
    return _jpeg(img)


_STEP_PREFIX = re.compile(r"^\s*(step|tip|day|#)\s*\d+\s*[:.)\-–—]\s*", re.I)


def content(number: int, title: str, body: str, brand: Brand, counter: str, progress: tuple[int, int]) -> bytes:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    _header(d, brand, counter, on_dark=False)
    title = _STEP_PREFIX.sub("", clean(title))  # the number badge already says "Step N"
    top, bottom = 200, H - 210
    tfont, tlines, tlh = fit_text(d, title, F_DISPLAY, W - 2 * M, 340, 96, 56, 1.1)
    bfont, blines, blh = fit_text(d, clean(body), F_BODY, W - 2 * M, 520, 58, 38, 1.36)
    block = 120 + 48 + len(tlines) * tlh + 40 + 8 + 48 + len(blines) * blh
    y = top + max(0, (bottom - top - block) // 2)  # centre the block between header and footer
    d.ellipse((M, y, M + 120, y + 120), fill=SAFFRON)
    nf = _font(F_DISPLAY, 64)
    ns = str(number)
    d.text((M + 60 - d.textlength(ns, font=nf) / 2, y + 18), ns, font=nf, fill=INK)
    y += 120 + 48
    y = _draw_lines(d, (M, y), tlines, tfont, tlh, INK) + 40
    d.rectangle((M, y, M + 96, y + 8), fill=INDIGO)
    y += 8 + 48
    _draw_lines(d, (M, y), blines, bfont, blh, INK)
    cur, total = progress
    dot_y, gap = H - 168, 30
    start_x = W - M - (total - 1) * gap
    for i in range(total):
        r = 8 if i == cur else 6
        cx = start_x + i * gap
        d.ellipse((cx - r, dot_y - r, cx + r, dot_y + r), fill=INDIGO if i == cur else LINE)
    _footer(d, brand, False, H)
    return _jpeg(img)


def cta(title: str, body: str, brand: Brand, counter: str) -> bytes:
    img = Image.new("RGB", (W, H), INDIGO)
    d = ImageDraw.Draw(img)
    _header(d, brand, counter, on_dark=True)
    y = 300
    tfont, tlines, tlh = fit_text(d, clean(title) or "Save this for later", F_DISPLAY, W - 2 * M, 380, 108, 60, 1.08)
    y = _draw_lines(d, (M, y), tlines, tfont, tlh, WHITE) + 40
    if body:
        bfont, blines, blh = fit_text(d, clean(body), F_BODY, W - 2 * M, 300, 48, 36, 1.3)
        y = _draw_lines(d, (M, y), blines, bfont, blh, (226, 226, 255)) + 60
    f = _font(F_SEMI, 40)
    x = M
    for label in ("Save", "Share", "Follow"):
        tw = d.textlength(label, font=f)
        d.rounded_rectangle((x, y, x + tw + 64, y + 84), radius=42, outline=SAFFRON, width=4)
        d.text((x + 32, y + 18), label, font=f, fill=WHITE)
        x += tw + 64 + 24
    _footer(d, brand, True, H, brand.handle and "Follow for more")
    return _jpeg(img)

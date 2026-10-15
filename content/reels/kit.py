"""Shared Reel kit: brand colours, fonts, easing, text/pill/card helpers and the encoder.
Text stays inside the Reels safe area (top 260 px, bottom 430 px kept for Instagram UI)."""
import math
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

import os
import os
F = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../backend/app/render/fonts/")
W, H, FPS = 1080, 1920, 30
INDIGO = (61, 59, 243); DEEP = (43, 41, 196); SAFF = (255, 159, 28); WHITE = (255, 255, 255)
CREAM = (250, 247, 242); INK = (20, 20, 43); MUTED = (91, 91, 115); GREEN = (43, 182, 115); RED = (214, 69, 69)
TINT = (236, 235, 254)
M = 90  # side margin
TOP, BOTTOM = 260, H - 430  # safe area


def font(name, size):
    return ImageFont.truetype(F + name, size)


XB = lambda s: font("InterDisplay-ExtraBold.ttf", s)
SB = lambda s: font("Inter-SemiBold.ttf", s)
RG = lambda s: font("Inter-Regular.ttf", s)


def ease(x):  # easeOutCubic, clamped
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def wrap(d, text, f, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    return lines


def text_block(d, img, x, y, text, f, fill, t, start, width=W - 2 * M, lh=1.18, rise=60):
    """Lines slide up + fade in, staggered. Returns bottom y."""
    for i, line in enumerate(wrap(d, text, f, width)):
        p = ease((t - start - i * 0.08) / 0.45)
        if p <= 0:
            y += int(f.size * lh); continue
        layer = Image.new("RGBA", (W, int(f.size * 1.5)), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((x, 0), line, font=f, fill=fill + (int(255 * p),))
        img.alpha_composite(layer, (0, int(y + (1 - p) * rise)))
        y += int(f.size * lh)
    return y


def pill(img, x, y, text, f, bg, fg, t, start, pad=(34, 20)):
    p = ease((t - start) / 0.35)
    if p <= 0:
        return y
    d = ImageDraw.Draw(img)
    tw = d.textlength(text, font=f)
    w, h = tw + pad[0] * 2, f.size + pad[1] * 2
    s = 0.85 + 0.15 * p
    layer = Image.new("RGBA", (int(w) + 4, int(h) + 4), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle((0, 0, w, h), radius=h // 2, fill=bg + (int(255 * p),))
    ld.text((pad[0], pad[1] - f.size * 0.12), text, font=f, fill=fg + (int(255 * p),))
    layer = layer.resize((max(1, int(layer.width * s)), max(1, int(layer.height * s))))
    img.alpha_composite(layer, (int(x), int(y + (1 - p) * 20)))
    return y + h


def card(img, y, h, t, start, fill=WHITE, outline=None):
    p = ease((t - start) / 0.4)
    if p <= 0:
        return
    layer = Image.new("RGBA", (W, h + 60), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((M, 0, W - M, h), radius=36, fill=fill + (int(255 * p),),
                                            outline=(outline + (int(255 * p),)) if outline else None, width=4)
    img.alpha_composite(layer, (0, int(y + (1 - p) * 50)))


def brand(img, dark):
    d = ImageDraw.Draw(img)
    bg, fg = (WHITE, INDIGO) if dark else (INDIGO, WHITE)
    d.rounded_rectangle((M, 150, M + 64, 214), radius=16, fill=bg)
    d.text((M + 32, 182), "K", font=XB(40), fill=fg, anchor="mm")
    d.text((M + 84, 182), "@kaamkaai.official", font=SB(30), fill=WHITE if dark else INK, anchor="lm")


def progress(img, t, total, dark):
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 10), fill=(255, 255, 255, 60) if dark else (231, 226, 217))
    d.rectangle((0, 0, int(W * t / total), 10), fill=SAFF)


def sparkle(d, cx, cy, R, fill=SAFF):
    r = R * 0.25
    d.polygon([(cx, cy - R), (cx + r, cy - r), (cx + R, cy), (cx + r, cy + r), (cx, cy + R), (cx - r, cy + r),
               (cx - R, cy), (cx - r, cy - r)], fill=fill)




def caption(img, text, t, start, end):
    """Burned-in subtitle for the voiceover line, just above Instagram's bottom UI."""
    if not (start <= t < end) or not text:
        return
    d = ImageDraw.Draw(img)
    f = SB(42)
    lines = wrap(d, text, f, W - 2 * M - 60)
    lh = 56
    h = lh * len(lines) + 40
    y0 = BOTTOM - h - 10
    p = ease((t - start) / 0.25)
    layer = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle((M - 10, 0, W - M + 10, h), radius=24, fill=(20, 20, 43, int(200 * p)))
    for i, line in enumerate(lines):
        ld.text((W / 2, 20 + i * lh + lh / 2), line, font=f, fill=(255, 255, 255, int(255 * p)), anchor="mm")
    img.alpha_composite(layer, (0, y0))


def render(scenes, out, captions=(), stills=None):
    """scenes: [(name, seconds, draw_fn(img, t), dark_bg)], captions: [(start, end, text)] in absolute seconds."""
    total = sum(s[1] for s in scenes)

    def frame_at(T):
        acc = 0.0
        for i, (name, dur, fn, dark) in enumerate(scenes):
            if T < acc + dur or i == len(scenes) - 1:
                img = Image.new("RGBA", (W, H), (INDIGO if dark else CREAM) + (255,))
                fn(img, T - acc)
                for a, b, txt in captions:
                    caption(img, txt, T, a, b)
                brand(img, dark)
                progress(img, T, total, dark)
                return img.convert("RGB")
            acc += dur

    if stills:
        return [frame_at(T) for T in stills]
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-profile:v", "high",
                           "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", out], stdin=subprocess.PIPE)
    for i in range(int(total * FPS)):
        ff.stdin.write(frame_at(i / FPS).tobytes())
    ff.stdin.close()
    ff.wait()
    return total

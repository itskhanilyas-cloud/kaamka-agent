"""Kaam Ka AI Reel #1 - "Google AI Plus free for 1 year (students) - par ek catch hai".
Renders 1080x1920 @30fps with Pillow, pipes raw frames to ffmpeg (H.264 + silent AAC track).
Text is kept inside the Reels safe area (top 250px and bottom 420px stay clear of Instagram UI).
"""
import math
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

import os
F = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../backend/app/render/fonts/")
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


# ---------------- scenes ----------------
def s_hook(img, t):  # 0.0-3.2 s
    d = ImageDraw.Draw(img)
    d.ellipse((W * 0.45, H * 0.62, W * 1.5, H * 1.25), fill=DEEP)
    pill(img, M, TOP + 200, "COLLEGE STUDENTS, INDIA", SB(38), SAFF, INK, t, 0.0)
    p = ease((t - 0.6) / 0.4)
    if p > 0:
        sparkle(d, W - M - 80, TOP + 230, 80 * p)
    y = text_block(d, img, M, TOP + 380, "Google ka AI plan,", XB(98), WHITE, t, 0.15)
    y = text_block(d, img, M, y + 10, "1 saal FREE.", XB(160), WHITE, t, 0.45)
    text_block(d, img, M, y + 90, "Par ek catch hai.", XB(96), SAFF, t, 1.5)


def s_setup(img, t):  # 3.2-7.4
    d = ImageDraw.Draw(img)
    pill(img, M, TOP + 160, "THE OFFER", SB(36), INDIGO, WHITE, t, 0.0)
    y = text_block(d, img, M, TOP + 300, "Google AI Plus", XB(110), INK, t, 0.1)
    card(img, y + 50, 420, t, 0.5)
    text_block(d, img, M + 60, y + 100, "Normally", SB(44), MUTED, t, 0.7)
    p = ease((t - 0.9) / 0.4)
    if p > 0:
        d.text((M + 60, y + 170), "₹399/month", font=XB(110), fill=INK)
        if t > 1.8:  # strike-through draws across
            q = ease((t - 1.8) / 0.4)
            x1 = M + 60 + d.textlength("₹399/month", font=XB(110)) * q
            d.line((M + 55, y + 235, x1, y + 235), fill=RED, width=12)
    text_block(d, img, M + 60, y + 330, "Eligible students: ₹0 for 12 months", SB(46), GREEN, t, 2.3, width=W - 2 * M - 120)
    text_block(d, img, M, y + 560, "Claim by 31 December 2026.", XB(58), INK, t, 2.9)


def s_value(img, t):  # 7.4-12.4
    d = ImageDraw.Draw(img)
    pill(img, M, TOP + 120, "WHAT YOU GET", SB(36), INDIGO, WHITE, t, 0.0)
    text_block(d, img, M, TOP + 250, "Free plan mein:", XB(104), INK, t, 0.1)
    items = [("2x", "Gemini usage limits", "vs free users"), ("400 GB", "cloud storage", "Drive, Gmail, Photos"),
             ("Study", "tools in Gemini", "quizzes + study plans")]
    y = TOP + 470
    for i, (big, a, b) in enumerate(items):
        st = 0.6 + i * 0.9
        card(img, y, 250, t, st, fill=WHITE)
        p = ease((t - st - 0.15) / 0.4)
        if p > 0:
            layer = Image.new("RGBA", (W, 260), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
            ld.text((M + 50, 125), big, font=XB(92), fill=INDIGO + (int(255 * p),), anchor="lm")
            bx = M + 90 + ld.textlength(big, font=XB(92))
            ld.text((bx, 95), a, font=SB(46), fill=INK + (int(255 * p),), anchor="lm")
            ld.text((bx, 158), b, font=RG(38), fill=MUTED + (int(255 * p),), anchor="lm")
            img.alpha_composite(layer, (0, y))
        y += 290


def s_how(img, t):  # 12.4-19.4
    d = ImageDraw.Draw(img)
    pill(img, M, TOP + 90, "HOW TO CLAIM", SB(36), INDIGO, WHITE, t, 0.0)
    text_block(d, img, M, TOP + 220, "3 steps:", XB(104), INK, t, 0.1)
    steps = [("Kholo", "one.google.com/ai-student"), ("'Get student offer'", "SheerID se student verify karo"),
             ("Card add karo", "Free year mein ₹0 charge*")]
    y = TOP + 420
    for i, (a, b) in enumerate(steps):
        st = 0.5 + i * 1.7
        active = st <= t < st + 1.7 or (i == 2 and t >= st)
        card(img, y, 270, t, st, fill=TINT if active else WHITE, outline=INDIGO if active else None)
        p = ease((t - st - 0.15) / 0.4)
        if p > 0:
            layer = Image.new("RGBA", (W, 280), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
            ld.ellipse((M + 40, 75, M + 160, 195), fill=INDIGO + (int(255 * p),))
            ld.text((M + 100, 135), str(i + 1), font=XB(64), fill=WHITE + (int(255 * p),), anchor="mm")
            ld.text((M + 200, 100), a, font=XB(54), fill=INK + (int(255 * p),), anchor="lm")
            ld.text((M + 200, 170), b, font=SB(38), fill=MUTED + (int(255 * p),), anchor="lm")
            img.alpha_composite(layer, (0, y))
        y += 300
    text_block(d, img, M, y + 10, "*Sign-up pe ₹2 tak ka check ho sakta hai, refund hota hai.", RG(32), MUTED, t, 5.6)


def s_catch(img, t):  # 19.4-25.0
    d = ImageDraw.Draw(img)
    d.ellipse((-W * 0.4, H * 0.66, W * 0.5, H * 1.2), fill=DEEP)
    pill(img, M, TOP + 130, "THE CATCH", SB(38), SAFF, INK, t, 0.0)
    y = text_block(d, img, M, TOP + 270, "12 mahine baad", XB(100), WHITE, t, 0.1)
    y = text_block(d, img, M, y, "auto-renew:", XB(96), WHITE, t, 0.3)
    y = text_block(d, img, M, y + 10, "₹399/month.", XB(120), SAFF, t, 0.7)
    card(img, y + 70, 380, t, 1.6, fill=WHITE)
    p = ease((t - 1.8) / 0.4)
    if p > 0:
        # calendar icon
        cx, cy = M + 120, y + 70 + 190
        d.rounded_rectangle((cx - 60, cy - 60, cx + 60, cy + 70), radius=16, fill=TINT, outline=INDIGO, width=6)
        d.rectangle((cx - 60, cy - 60, cx + 60, cy - 20), fill=INDIGO)
        d.text((cx, cy + 25), "!", font=XB(64), fill=INDIGO, anchor="mm")
    text_block(d, img, M + 230, y + 130, "Abhi calendar reminder lagao.", XB(50), INK, t, 2.0, width=W - 2 * M - 270)
    text_block(d, img, M + 230, y + 270, "Continue ya cancel: tumhara choice.", SB(38), MUTED, t, 2.6, width=W - 2 * M - 270)


def s_cta(img, t):  # 25.0-29.0
    d = ImageDraw.Draw(img)
    pill(img, M, TOP + 240, "SHARE KARO", SB(36), INDIGO, WHITE, t, 0.0)
    y = text_block(d, img, M, TOP + 380, "Us dost ko bhejo", XB(110), INK, t, 0.1)
    y = text_block(d, img, M, y + 10, "jo AI ke liye pay karne wala tha.", XB(88), INDIGO, t, 0.5)
    text_block(d, img, M, y + 80, "Offer 31 Dec 2026 tak. Terms Google ke page pe check karo.", SB(44), MUTED, t, 1.2)
    p = ease((t - 1.8) / 0.4)
    if p > 0:
        sparkle(d, W - M - 60, BOTTOM - 80, 60 * p)
        d.text((M, BOTTOM - 80), "Follow @kaamkaai.official", font=SB(44), fill=INK, anchor="lm")


SCENES = [  # (name, duration seconds, draw fn, dark background?)
    ("hook", 3.2, s_hook, True),
    ("setup", 4.2, s_setup, False),
    ("value", 5.0, s_value, False),
    ("how", 7.0, s_how, False),
    ("catch", 5.6, s_catch, True),
    ("cta", 4.0, s_cta, False),
]
TOTAL = sum(s[1] for s in SCENES)


def frame_at(T):
    acc = 0.0
    for name, dur, fn, dark in SCENES:
        if T < acc + dur or name == SCENES[-1][0]:
            t = T - acc
            img = Image.new("RGBA", (W, H), (INDIGO if dark else CREAM) + (255,))
            fn(img, t)
            brand(img, dark)
            progress(img, T, TOTAL, dark)
            # quick white flash-free cut: fade the last 0.12s to the next scene's background colour
            return img.convert("RGB")
        acc += dur


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "reel.mp4"
    if "--stills" in sys.argv:
        for T in [0.2, 1.2, 2.9, 6.5, 11.8, 18.9, 24.5, 28.5]:
            frame_at(T).save(f"still_{T:04.1f}.png")
        sys.exit()
    n = int(TOTAL * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                           "-shortest", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                           "-profile:v", "high", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", out],
                          stdin=subprocess.PIPE)
    for i in range(n):
        ff.stdin.write(frame_at(i / FPS).tobytes())
    ff.stdin.close(); ff.wait()
    frame_at(1.4).save("cover_frame.png")
    print("frames", n, "seconds", TOTAL)

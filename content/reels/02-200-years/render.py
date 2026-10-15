"""Reel 02: "Imagine if people lived 200 years." (draft 641fd8a1 in the app).
24 s, 1080x1920. Voiceover lines are burned in as captions so the Reel works on mute.
Usage: python3 render.py out.mp4   |   python3 render.py --stills
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kit import (BOTTOM, CREAM, DEEP, GREEN, INDIGO, INK, M, MUTED, SAFF, SB, TINT, TOP, WHITE, XB, RG,  # noqa: E402
                 W, H, card, ease, pill, render, sparkle, text_block)
from PIL import Image, ImageDraw  # noqa: E402


def s_hook(img, t):  # 3.0 s
    d = ImageDraw.Draw(img)
    d.ellipse((W * 0.5, H * 0.55, W * 1.5, H * 1.2), fill=DEEP)
    pill(img, M, TOP + 60, "IMAGINE KARO", SB(38), SAFF, INK, t, 0.0)
    y = text_block(d, img, M, TOP + 190, "What if life lasted", XB(92), WHITE, t, 0.1, width=W - 2 * M + 20)
    y = text_block(d, img, M, y + 10, "200 years?", XB(150), SAFF, t, 0.45, width=W)
    # a lifetime ruler that draws itself, 0 to 200
    y0 = y + 170
    p = ease((t - 0.8) / 1.6)
    if p > 0:
        x1 = M + (W - 2 * M) * p
        d.line((M, y0, x1, y0), fill=WHITE, width=8)
        for i, age in enumerate(range(0, 201, 50)):
            x = M + (W - 2 * M) * age / 200
            if x <= x1 + 1:
                d.line((x, y0 - 22, x, y0 + 22), fill=WHITE, width=6)
                d.text((x, y0 + 60), str(age), font=SB(36), fill=WHITE, anchor="mm")
        d.ellipse((x1 - 20, y0 - 20, x1 + 20, y0 + 20), fill=SAFF)
        # today's ~80-year span, for scale
        if t > 2.0:
            q = ease((t - 2.0) / 0.5)
            xe = M + (W - 2 * M) * 80 / 200
            d.rectangle((M, y0 - 64, M + (xe - M) * q, y0 - 46), fill=SAFF)
            d.text((M + (xe - M) * q + 20, y0 - 55), "a long life today", font=SB(32), fill=WHITE, anchor="lm")


def s_changes(img, t):  # 5.0 s
    d = ImageDraw.Draw(img)
    pill(img, M, TOP + 60, "EVERYTHING CHANGES", SB(36), INDIGO, WHITE, t, 0.0)
    text_block(d, img, M, TOP + 190, "One life,", XB(104), INK, t, 0.1)
    text_block(d, img, M, TOP + 310, "many chapters.", XB(104), INDIGO, t, 0.3)
    steps = [("School", "the first chapter"), ("First career", "decades longer than today"),
             ("Career switch", "maybe two or three"), ("Re-skill", "again, and again")]
    x = M + 50
    y = TOP + 470
    lp = ease((t - 0.6) / 3.0)
    d.line((x, y + 40, x, y + 40 + 3 * 135 * lp), fill=INDIGO, width=8)
    for i, (a, b) in enumerate(steps):
        st = 0.7 + i * 0.75
        p = ease((t - st) / 0.4)
        if p <= 0:
            continue
        cy = y + 40 + i * 135
        r = 26 * p
        d.ellipse((x - r, cy - r, x + r, cy + r), fill=SAFF if i == 3 else INDIGO)
        layer = Image.new("RGBA", (W, 140), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.text((x + 70, 40), a, font=XB(58), fill=INK + (int(255 * p),), anchor="lm")
        ld.text((x + 70, 100), b, font=SB(38), fill=MUTED + (int(255 * p),), anchor="lm")
        img.alpha_composite(layer, (int((1 - p) * 40), cy - 40))


def s_learn(img, t):  # 5.0 s
    d = ImageDraw.Draw(img)
    d.ellipse((-W * 0.5, H * 0.6, W * 0.45, H * 1.2), fill=DEEP)
    pill(img, M, TOP + 60, "ONE THING STAYS", SB(36), SAFF, INK, t, 0.0)
    text_block(d, img, M, TOP + 190, "Keep learning.", XB(124), WHITE, t, 0.15)
    # a loop that draws itself, with three stops
    cx, cy, R = W / 2, TOP + 680, 220
    p = ease((t - 0.6) / 2.2)
    if p > 0:
        d.arc((cx - R, cy - R, cx + R, cy + R), -90, -90 + 340 * p, fill=WHITE, width=14)
        if p > 0.98:  # arrow head
            a = math.radians(-90 + 340)
            hx, hy = cx + R * math.cos(a), cy + R * math.sin(a)
            d.polygon([(hx + 30, hy - 8), (hx - 18, hy - 34), (hx - 10, hy + 22)], fill=WHITE)
    for i, (label, ang) in enumerate((("Notes", -90), ("Laptop", 30), ("Interview prep", 150))):
        q = ease((t - 0.9 - i * 0.6) / 0.4)
        if q <= 0:
            continue
        a = math.radians(ang)
        nx, ny = cx + R * math.cos(a), cy + R * math.sin(a)
        rr = 62 * q
        d.ellipse((nx - rr, ny - rr, nx + rr, ny + rr), fill=SAFF)
        d.text((nx, ny), str(i + 1), font=XB(56), fill=INK, anchor="mm")
        if ang == -90:
            d.text((nx + 90, ny), label, font=SB(44), fill=WHITE, anchor="lm")
        else:
            d.text((min(max(nx, M + 170), W - M - 170), ny + 115), label, font=SB(44), fill=WHITE, anchor="mm")


def s_skills(img, t):  # 6.0 s
    d = ImageDraw.Draw(img)
    pill(img, M, TOP + 60, "START NOW", SB(36), INDIGO, WHITE, t, 0.0)
    text_block(d, img, M, TOP + 190, "Practical skills", XB(104), INK, t, 0.1)
    text_block(d, img, M, TOP + 310, "> panic", XB(132), INDIGO, t, 0.35)
    tiles = [("AI tools", "better prompts"), ("Writing", "clear emails"),
             ("Interviews", "tell your story"), ("Excel", "formulas, shortcuts")]
    gw = (W - 2 * M - 30) / 2
    for i, (a, b) in enumerate(tiles):
        st = 0.9 + i * 0.55
        p = ease((t - st) / 0.4)
        if p <= 0:
            continue
        col, row = i % 2, i // 2
        x0 = M + col * (gw + 30)
        y0 = TOP + 500 + row * 255
        layer = Image.new("RGBA", (int(gw) + 2, 240), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle((0, 0, gw, 230), radius=32, fill=(WHITE if i % 3 else TINT) + (int(255 * p),))
        ld.text((40, 85), a, font=XB(58), fill=INDIGO + (int(255 * p),), anchor="lm")
        ld.text((40, 160), b, font=SB(36), fill=MUTED + (int(255 * p),), anchor="lm")
        s = 0.9 + 0.1 * p
        layer = layer.resize((int(layer.width * s), int(layer.height * s)))
        img.alpha_composite(layer, (int(x0 + (1 - s) * gw / 2), int(y0 + (1 - p) * 30)))


def s_next(img, t):  # 5.0 s
    d = ImageDraw.Draw(img)
    # soft glow behind a big question mark
    p = ease(t / 0.8)
    for k in range(6, 0, -1):
        r = 140 + k * 26 * p
        a = int(24 * p)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse((W / 2 - r, TOP + 300 - r, W / 2 + r, TOP + 300 + r), fill=(255, 159, 28, a))
        img.alpha_composite(layer)
    d.text((W / 2, TOP + 300), "?", font=XB(320), fill=WHITE, anchor="mm")
    sparkle(d, W / 2 + 190, TOP + 160, 46 * p)
    y = text_block(d, img, M, TOP + 560, "Agla future", XB(100), WHITE, t, 0.4)
    y = text_block(d, img, M, y, "kaunsa explore karein?", XB(76), SAFF, t, 0.7)
    pill(img, M, y + 60, "Comment karo", SB(44), WHITE, INDIGO, t, 1.6)
    q = ease((t - 2.2) / 0.4)
    if q > 0:
        d.text((M, y + 230), "Follow @kaamkaai.official for kaam ki baat.", font=SB(40), fill=(220, 220, 255))


SCENES = [("hook", 3.0, s_hook, True), ("changes", 5.0, s_changes, False), ("learn", 5.0, s_learn, True),
          ("skills", 6.0, s_skills, False), ("next", 5.0, s_next, True)]
CAPTIONS = [  # the draft's voiceover lines
    (0.3, 3.0, "Imagine if people lived 200 years."),
    (3.0, 8.0, "Education, careers, and retirement would all look very different."),
    (8.0, 13.0, "But one thing would stay the same: the need to keep learning."),
    (13.0, 19.0, "AI tools, writing, interviews, and Excel are practical skills to build now."),
    (19.0, 24.0, "The future is interesting. Your preparation should be too."),
]

if __name__ == "__main__":
    if "--stills" in sys.argv:
        for T, im in zip(STILLS := [1.0, 2.8, 6.5, 11.5, 17.5, 22.5], render(SCENES, None, CAPTIONS, stills=[1.0, 2.8, 6.5, 11.5, 17.5, 22.5])):
            im.save(f"still_{T:04.1f}.png")
        sys.exit()
    total = render(SCENES, sys.argv[1] if len(sys.argv) > 1 else "reel.mp4", CAPTIONS)
    render(SCENES, None, CAPTIONS, stills=[2.9])[0].save("cover.jpg", quality=92)
    print("seconds", total)

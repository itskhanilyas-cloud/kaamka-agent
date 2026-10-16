"""Reel 03: "Notes 14 baar padhe, phir bhi blank?" Make AI quiz you instead of re-reading.
Fact source: Roediger & Karpicke (2006), Psychological Science 17(3) 249-255.
28 s, 1080x1920, captions burned in, original music + sound effects (music.py).
Usage: python3 render.py out.mp4   |   python3 render.py --stills
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from kit import (BOTTOM, CREAM, DEEP, GREEN, INDIGO, INK, M, MUTED, RED, SAFF, SB, TINT, TOP, WHITE, XB, RG,  # noqa: E402
                 W, H, card, ease, pill, render, sparkle, text_block, wrap)
from PIL import Image, ImageDraw  # noqa: E402
import music  # noqa: E402


def s_hook(img, t):  # 3.2 s: notebook pages flip, counter climbs to 14
    d = ImageDraw.Draw(img)
    d.ellipse((W * 0.5, H * 0.58, W * 1.5, H * 1.2), fill=DEEP)
    pill(img, M, TOP + 60, "EXAM SEASON", SB(38), SAFF, INK, t, 0.0)
    y = text_block(d, img, M, TOP + 180, "Notes 14 baar padhe,", XB(88), WHITE, t, 0.05, width=W - 2 * M + 30)
    y = text_block(d, img, M, y, "phir bhi exam mein", XB(88), WHITE, t, 0.2, width=W - 2 * M + 30)
    y = text_block(d, img, M, y, "blank?", XB(150), SAFF, t, 0.9)
    # stack of note pages flipping, with a re-read counter
    x0, y0 = M + 40, y + 70
    n = min(14, int(1 + 13 * ease((t - 0.2) / 2.2)))
    for k in range(5, 0, -1):
        d.rounded_rectangle((x0 + k * 10, y0 + k * 10, x0 + 340 + k * 10, y0 + 230 + k * 10), radius=18,
                            fill=(235, 235, 255), outline=(200, 200, 240), width=2)
    d.rounded_rectangle((x0, y0, x0 + 340, y0 + 230), radius=18, fill=WHITE)
    for li in range(5):
        d.line((x0 + 30, y0 + 45 + li * 38, x0 + 310 - (li % 2) * 70, y0 + 45 + li * 38), fill=(190, 190, 215), width=8)
    d.text((x0 + 420, y0 + 70), "Re-read", font=SB(40), fill=(220, 220, 255), anchor="lm")
    d.text((x0 + 420, y0 + 150), f"×{n}", font=XB(110), fill=WHITE, anchor="lm")


def s_setup(img, t):  # 5.0 s: the 2006 experiment, two groups
    d = ImageDraw.Draw(img)
    pill(img, M, TOP + 60, "A FAMOUS STUDY (2006)", SB(36), INDIGO, WHITE, t, 0.0)
    text_block(d, img, M, TOP + 190, "Two groups.", XB(104), INK, t, 0.1)
    text_block(d, img, M, TOP + 310, "Same lesson.", XB(104), INDIGO, t, 0.3)
    groups = [("Group A", "Read it again and again", "about 14 times", INK),
              ("Group B", "Read it about 3 times,", "then tested themselves", INDIGO)]
    y = TOP + 480
    for i, (a, b, c, col) in enumerate(groups):
        st = 0.8 + i * 1.3
        card(img, y, 215, t, st, fill=WHITE if i == 0 else TINT)
        p = ease((t - st - 0.15) / 0.4)
        if p > 0:
            layer = Image.new("RGBA", (W, 240), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            ld.text((M + 50, 55), a, font=XB(54), fill=col + (int(255 * p),), anchor="lm")
            ld.text((M + 50, 115), b, font=SB(40), fill=INK + (int(255 * p),), anchor="lm")
            ld.text((M + 50, 168), c, font=SB(40), fill=MUTED + (int(255 * p),), anchor="lm")
            img.alpha_composite(layer, (0, y))
        y += 240


def s_result(img, t):  # 6.0 s: bar chart, one week later
    d = ImageDraw.Draw(img)
    pill(img, M, TOP + 60, "ONE WEEK LATER", SB(36), INDIGO, WHITE, t, 0.0)
    text_block(d, img, M, TOP + 190, "Kisko zyada yaad raha?", XB(80), INK, t, 0.1)
    base = TOP + 860
    bars = [("Re-read ×14", 40, MUTED), ("Self-test", 61, INDIGO)]
    bw, gap = 300, 120
    x = (W - (2 * bw + gap)) / 2
    for i, (label, val, col) in enumerate(bars):
        st = 0.7 + i * 1.0
        p = ease((t - st) / 0.9)
        hgt = 480 * val / 70 * p
        d.rounded_rectangle((x, base - hgt, x + bw, base), radius=20, fill=col)
        if p > 0.05:
            d.text((x + bw / 2, base - hgt - 60), f"{round(val * p)}%", font=XB(84), fill=col, anchor="mm")
        d.text((x + bw / 2, base + 50), label, font=SB(40), fill=INK, anchor="mm")
        x += bw + gap
    if t > 3.0:
        text_block(d, img, M, base + 105, "yaad raha, ek hafte baad.", SB(42), MUTED, t, 3.0, width=W - 2 * M)


def s_ai(img, t):  # 8.0 s: turn AI into a quiz master
    d = ImageDraw.Draw(img)
    d.ellipse((-W * 0.5, H * 0.62, W * 0.45, H * 1.2), fill=DEEP)
    pill(img, M, TOP + 60, "AI KO QUIZ-MASTER BANAO", SB(36), SAFF, INK, t, 0.0)
    text_block(d, img, M, TOP + 185, "Summary nahi,", XB(96), WHITE, t, 0.1)
    text_block(d, img, M, TOP + 300, "sawaal maango.", XB(96), SAFF, t, 0.3)
    card(img, TOP + 440, 290, t, 0.9, fill=WHITE)
    p = ease((t - 1.1) / 0.4)
    if p > 0:
        d.text((M + 50, TOP + 480), "Free mode on karo:", font=SB(40), fill=MUTED)
        d.text((M + 50, TOP + 540), "ChatGPT → Study mode", font=XB(54), fill=INK)
        d.text((M + 50, TOP + 620), "Gemini → Guided Learning", font=XB(54), fill=INK)
    # prompt card types itself
    prompt = "\"Mujhe [topic] pe 5 sawaal pucho, ek-ek karke. Mera jawab check karo. Jo galat ho, wahi dobara pucho.\""
    st = 3.4
    if t > st:
        card(img, TOP + 760, 270, t, st, fill=TINT)
        shown = prompt[: int(len(prompt) * ease((t - st - 0.2) / 2.6))]
        f = SB(40)
        lines = wrap(d, shown, f, W - 2 * M - 100) if shown else []
        for i, line in enumerate(lines[:5]):
            d.text((M + 50, TOP + 790 + i * 52), line, font=f, fill=INDIGO)


def s_cta(img, t):  # 5.8 s
    d = ImageDraw.Draw(img)
    pill(img, M, TOP + 200, "SAVE KARO", SB(38), INDIGO, WHITE, t, 0.0)
    y = text_block(d, img, M, TOP + 330, "Padhna kam,", XB(110), INK, t, 0.1)
    y = text_block(d, img, M, y, "yaad zyada.", XB(110), INDIGO, t, 0.35)
    text_block(d, img, M, y + 60, "Exam se pehle ye Reel kaam aayegi.", SB(46), MUTED, t, 0.9)
    q = ease((t - 1.6) / 0.4)
    if q > 0:
        sparkle(d, W - M - 60, y + 260, 60 * q)
        d.text((M, y + 260), "Follow @kaamkaai.official", font=SB(44), fill=INK, anchor="lm")


SCENES = [("hook", 3.2, s_hook, True), ("setup", 5.0, s_setup, False), ("result", 6.0, s_result, False),
          ("ai", 8.0, s_ai, True), ("cta", 5.8, s_cta, False)]
CAPTIONS = [
    (0.2, 3.2, "Notes 14 baar padhe, phir bhi exam mein blank?"),
    (3.2, 8.2, "2006 ki ek famous study: ek group ne baar-baar padha, dusre ne khud ko test kiya."),
    (8.2, 14.2, "Ek hafte baad: re-read wale ko 40% yaad raha, self-test wale ko 61%."),
    (14.2, 18.2, "Toh AI se summary mat maango. Sawaal maango."),
    (18.2, 22.2, "ChatGPT ka Study mode ya Gemini ka Guided Learning on karo. Dono free hain."),
    (22.2, 28.0, "Padhna kam, yaad zyada. Save karo, exam se pehle kaam aayega."),
]
HITS = [(0.05, "whoosh"), (1.0, "pop"), (3.2, "whoosh"), (4.0, "pop"), (5.3, "pop"), (8.2, "whoosh"), (9.0, "tick"),
        (10.0, "tick"), (11.4, "pop"), (14.2, "whoosh"), (15.2, "pop"), (17.7, "tick"), (22.2, "whoosh"), (23.9, "pop")]

if __name__ == "__main__":
    if "--stills" in sys.argv:
        ts = [1.2, 3.0, 6.5, 13.0, 16.0, 21.0, 26.5]
        for T, im in zip(ts, render(SCENES, None, CAPTIONS, stills=ts)):
            im.save(f"still_{T:04.1f}.png")
        sys.exit()
    out = sys.argv[1] if len(sys.argv) > 1 else "reel.mp4"
    total = sum(s[1] for s in SCENES)
    wav = music.make_track(total, HITS, os.path.splitext(out)[0] + ".wav", music_db=-11, sfx_db=-7)
    render(SCENES, out, CAPTIONS, audio=wav)
    render(SCENES, None, CAPTIONS, stills=[3.0])[0].save(os.path.splitext(out)[0] + "-cover.jpg", quality=92)
    print("seconds", total)

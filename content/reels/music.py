"""Original background music + sound effects, synthesised from scratch (no samples, no licences needed).

make_track(seconds, hits=[...], path) writes a 48 kHz stereo WAV: a soft lo-fi loop
(Am - F - C - G pads, gentle kick and hat at 90 BPM) mixed low under short "pop" and "tick" effects.
"""
import wave

import numpy as np

SR = 48000
BPM = 90
NOTES = {"A2": 110.0, "F2": 87.31, "C3": 130.81, "G2": 98.0,
         "A3": 220.0, "C4": 261.63, "E4": 329.63, "F3": 174.61, "A4": 440.0, "G3": 196.0, "B3": 246.94, "D4": 293.66, "G4": 392.0}
CHORDS = [("A2", ["A3", "C4", "E4"]), ("F2", ["F3", "A3", "C4"]), ("C3", ["G3", "C4", "E4"]), ("G2", ["G3", "B3", "D4"])]


def _env(n, attack=0.02, release=0.3):
    t = np.arange(n) / SR
    a = np.clip(t / attack, 0, 1)
    r = np.clip((n / SR - t) / release, 0, 1)
    return a * r


def _pad(freq, n):
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t + 0.3)
            + 0.15 * np.sin(2 * np.pi * freq * 3 * t + 0.7))
    vib = 1 + 0.003 * np.sin(2 * np.pi * 4.5 * t)
    return tone * vib * _env(n, 0.25, 0.6)


def _kick(n=int(0.35 * SR)):
    t = np.arange(n) / SR
    f = 110 * np.exp(-t * 18) + 45
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def _hat(rng, n=int(0.06 * SR)):
    return rng.standard_normal(n) * np.exp(-np.arange(n) / SR * 70) * 0.5


def pop(n=int(0.12 * SR)):
    t = np.arange(n) / SR
    f = 900 * np.exp(-t * 30) + 500
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35)


def tick(n=int(0.05 * SR)):
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 90)


def whoosh(rng, n=int(0.4 * SR)):
    noise = rng.standard_normal(n)
    k = np.ones(40) / 40
    soft = np.convolve(noise, k, mode="same")
    shape = np.sin(np.linspace(0, np.pi, n)) ** 2
    return soft * shape * 0.8


def make_track(seconds, hits, path, music_db=-20.0, sfx_db=-12.0, seed=7):
    """hits: list of (time_seconds, kind) with kind in {"pop", "tick", "whoosh"}."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    music = np.zeros(n)
    beat = 60 / BPM
    bar = 4 * beat
    i = 0
    while i * bar < seconds:
        root, chord = CHORDS[i % 4]
        s0 = int(i * bar * SR)
        seg = min(int(bar * SR), n - s0)
        if seg <= 0:
            break
        music[s0:s0 + seg] += 0.5 * _pad(NOTES[root], seg)
        for note in chord:
            music[s0:s0 + seg] += 0.22 * _pad(NOTES[note], seg)
        for b in range(4):  # kick on 1 and 3, hat on every 8th
            for half in (0, 0.5):
                p = int((i * bar + (b + half) * beat) * SR)
                if p >= n:
                    continue
                h = _hat(rng)
                music[p:p + len(h)] += 0.12 * h[: max(0, min(len(h), n - p))]
                if half == 0 and b in (0, 2):
                    k = _kick()
                    music[p:p + len(k)] += 0.8 * k[: max(0, min(len(k), n - p))]
        i += 1
    music = np.convolve(music, np.ones(6) / 6, mode="same")  # soften: lo-fi feel
    music /= np.max(np.abs(music)) + 1e-9
    fade = int(1.0 * SR)
    music[:fade] *= np.linspace(0, 1, fade)
    music[-fade:] *= np.linspace(1, 0, fade)
    music *= 10 ** (music_db / 20)

    sfx = np.zeros(n)
    for t0, kind in hits:
        s = {"pop": pop(), "tick": tick(), "whoosh": whoosh(rng)}[kind]
        p = int(t0 * SR)
        m = min(len(s), n - p)
        if m > 0:
            sfx[p:p + m] += s[:m]
    if np.max(np.abs(sfx)) > 0:
        sfx = sfx / np.max(np.abs(sfx)) * 10 ** (sfx_db / 20)

    mix = np.clip(music + sfx, -1, 1)
    left = mix
    right = np.roll(mix, int(0.004 * SR))  # tiny delay = width
    data = (np.stack([left, right], axis=1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    return path

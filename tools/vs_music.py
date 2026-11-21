"""A music bed made here, from nothing but numbers: no one else's recording, so no copyright claim.

Calm, warm and steady (the "farm at golden hour" kind): a soft pad, a picked arpeggio, a round bass and
light drums that come in after the start and leave before the end. Its length is the video's; the
sections follow it (quiet start, full middle, slow end). Different `seed`s and `key`s give different
tracks. For a real upload, music from YouTube's Audio Library (Studio > Audio Library) is better.

    python vs_music.py out.wav 95 [--seed 3] [--key D] [--bpm 92]
"""
import argparse, wave
import numpy as np

RATE = 48000
NOTES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
# I - V - vi - IV and I - iii - IV - V, in scale steps of a major key
PROGRESSIONS = [[0, 4, 5, 3], [0, 2, 3, 4], [5, 3, 0, 4], [0, 3, 5, 4]]
MAJOR = [0, 2, 4, 5, 7, 9, 11]


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def chord(root_midi, degree):
    """Triad (plus the ninth for color) on a degree of the major scale."""
    def note(step):
        octave, k = divmod(degree + step, 7)
        return root_midi + MAJOR[k] + 12 * octave
    return [note(0), note(2), note(4), note(8)]


def envelope(n, attack, release, sustain=1.0):
    env = np.full(n, sustain, dtype=np.float32)
    a, r = min(n, int(attack * RATE)), min(n, int(release * RATE))
    if a:
        env[:a] = np.linspace(0, sustain, a, dtype=np.float32)
    if r:
        env[-r:] *= np.linspace(1, 0, r, dtype=np.float32)
    return env


def pad_voice(freq, n, rng):
    t = np.arange(n, dtype=np.float32) / RATE
    out = np.zeros(n, dtype=np.float32)
    for detune in (-0.12, 0.0, 0.11):           # three slightly detuned voices: width
        f = freq * 2 ** (detune / 12)
        ph = rng.uniform(0, 2 * np.pi)
        # a soft saw: the first harmonics, falling off fast
        for h in range(1, 7):
            out += np.sin(2 * np.pi * f * h * t + ph * h) / (h ** 1.6)
    return out / 6


def pluck(freq, n, bright=0.5):
    t = np.arange(n, dtype=np.float32) / RATE
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t) * np.exp(-t * 6) \
        + 0.15 * bright * np.sin(2 * np.pi * freq * 3 * t) * np.exp(-t * 10)
    return (tone * np.exp(-t * 3.2) * np.minimum(1, t * 400)).astype(np.float32)


def kick(n):
    t = np.arange(n, dtype=np.float32) / RATE
    f = 48 + 70 * np.exp(-t * 30)
    return (np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 7)).astype(np.float32)


def fft_filter(x, response):
    """Filters x by a frequency response (a function of Hz), all at once in the frequency domain."""
    n = len(x)
    size = 1 << (n - 1).bit_length()
    X = np.fft.rfft(x, size)
    X *= response(np.fft.rfftfreq(size, 1 / RATE))
    return np.fft.irfft(X, size)[:n].astype(np.float32)


def lowpass(x, cutoff, order=2):
    return fft_filter(x, lambda f: 1 / np.sqrt(1 + (f / cutoff) ** (2 * order)))


def bandpass(x, lo, hi):
    return fft_filter(x, lambda f: (1 / np.sqrt(1 + (lo / np.maximum(f, 1)) ** 4)) / np.sqrt(1 + (f / hi) ** 4))


def hat(n, rng):
    t = np.arange(n, dtype=np.float32) / RATE
    noise = bandpass(rng.standard_normal(n).astype(np.float32), 6000, 10000)
    return noise * np.exp(-t * 70) * 0.5


def reverb(x, seconds=2.4, mix=0.28, seed=0):
    """Convolution with a decaying noise tail (in blocks, so long tracks fit in memory)."""
    rng = np.random.default_rng(seed + 99)
    n = int(seconds * RATE)
    t = np.arange(n, dtype=np.float32) / RATE
    ir = rng.standard_normal(n).astype(np.float32) * np.exp(-t * 6.9 / seconds)
    ir = lowpass(ir, 3500)
    ir /= np.sqrt((ir ** 2).sum())
    block = 1 << 18
    size = 1
    while size < block + n:
        size <<= 1
    H = np.fft.rfft(ir, size)
    wet = np.zeros(len(x) + n, dtype=np.float32)
    for s in range(0, len(x), block):
        seg = x[s:s + block]
        y = np.fft.irfft(np.fft.rfft(seg, size) * H, size)[:len(seg) + n]
        wet[s:s + len(y)] += y.astype(np.float32)
    return (1 - mix) * x + mix * wet[:len(x)] * 2.2


def make(seconds, seed=1, key="D", bpm=92):
    rng = np.random.default_rng(seed)
    total = int(seconds * RATE)
    beat = 60.0 / bpm
    bar = 4 * beat
    root = 50 + NOTES.get(key, 2)                 # around D3
    prog = PROGRESSIONS[seed % len(PROGRESSIONS)]
    L = np.zeros(total + RATE * 3, dtype=np.float32)
    R = np.zeros_like(L)
    DL, DR = np.zeros_like(L), np.zeros_like(L)        # drums: dry, no reverb
    bars = int(np.ceil(seconds / bar))
    drums_from, drums_to = 4, max(5, bars - 4)    # drums after the first 4 bars, gone for the last 4

    def add(sig, start, pan=0.0, gain=1.0, drum=False):
        i = int(start * RATE)
        if i >= len(L):
            return
        sig = sig[:len(L) - i] * gain
        l, r = (DL, DR) if drum else (L, R)
        l[i:i + len(sig)] += sig * np.float32(np.sqrt(0.5 * (1 - pan)))
        r[i:i + len(sig)] += sig * np.float32(np.sqrt(0.5 * (1 + pan)))

    arp_pattern = [0, 1, 2, 3, 2, 1, 2, 3] if seed % 2 else [0, 2, 1, 3, 0, 2, 3, 2]
    for b in range(bars):
        start = b * bar
        deg = prog[(b // 2) % len(prog)]          # each chord for two bars
        notes = chord(root, deg)
        intensity = min(1.0, 0.45 + b / 6) if b < bars - 3 else max(0.3, (bars - b) / 4)
        if b % 2 == 0:
            n = int(bar * 2 * RATE) + RATE
            env = envelope(n, 1.2, 1.4, 1.0)
            for k, m in enumerate(notes[:3]):
                v = lowpass(pad_voice(midi_hz(m + 12), n, rng), 1800 + 900 * intensity)
                add(v * env, start, pan=(k - 1) * 0.5, gain=0.09)
            # bass: root, on 1 and the "and" of 3
            for off, length in ((0, 2.5), (2.5, 1.5), (4, 2.5), (6.5, 1.5)):
                nb = int(length * beat * RATE)
                tb = np.arange(nb, dtype=np.float32) / RATE
                f = midi_hz(notes[0] - 12)
                bass = (np.sin(2 * np.pi * f * tb) + 0.25 * np.sin(4 * np.pi * f * tb)) * envelope(nb, 0.01, 0.15, 1.0) * np.exp(-tb * 1.2)
                add(bass.astype(np.float32), start + off * beat, gain=0.17 * (0.6 + 0.4 * intensity))
        # arpeggio in eighths, a fifth above the pad
        if b >= 1:
            for i in range(8):
                m = notes[arp_pattern[i] % 4] + 24
                add(pluck(midi_hz(m), int(beat * 1.5 * RATE), bright=intensity), start + i * beat / 2,
                    pan=0.35 if i % 2 else -0.35, gain=0.075 * intensity * (1.0 if i % 4 == 0 else 0.8))
        if drums_from <= b < drums_to:
            for i in range(4):
                if i in (0, 2):
                    add(kick(int(0.4 * RATE)), start + i * beat, gain=0.28, drum=True)
                add(hat(int(0.08 * RATE), rng), start + i * beat + beat / 2, pan=0.2, gain=0.35, drum=True)
            if b % 4 == 3:          # a soft clap/snare on 4 every fourth bar
                ns = int(0.25 * RATE)
                ts = np.arange(ns, dtype=np.float32) / RATE
                sn = rng.standard_normal(ns).astype(np.float32) * np.exp(-ts * 18) * 0.25
                add(lowpass(sn, 3500), start + 3 * beat, gain=0.4, drum=True)
    L, R = reverb(L, seed=seed) + DL, reverb(R, seed=seed + 1) + DR
    # the top gently rolled off, the very bottom cleaned up: warm, not hissy, no rumble
    tone = lambda f: (1 / np.sqrt(1 + (f / 9000) ** 2)) / np.sqrt(1 + (35 / np.maximum(f, 1)) ** 4)
    L, R = fft_filter(L[:total], tone), fft_filter(R[:total], tone)
    # fade in and out, then a gentle limiter and level
    fade_in, fade_out = int(1.5 * RATE), int(min(5.0, seconds / 6) * RATE)
    ramp = np.ones(total, dtype=np.float32)
    ramp[:fade_in] = np.linspace(0, 1, fade_in) ** 2
    ramp[-fade_out:] *= np.linspace(1, 0, fade_out) ** 1.5
    st = np.stack([L * ramp, R * ramp], axis=1)
    st = np.tanh(st * 1.4) / 1.4
    peak = np.abs(st).max() or 1
    return (st / peak * 0.89).astype(np.float32)


def write(path, seconds, seed=1, key="D", bpm=92):
    audio = make(seconds, seed, key, bpm)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((audio * 32767).astype("<i2").tobytes())
    return path


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out")
    p.add_argument("seconds", type=float)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--key", default="D", choices=sorted(NOTES))
    p.add_argument("--bpm", type=float, default=92)
    a = p.parse_args()
    print(write(a.out, a.seconds, a.seed, a.key, a.bpm))

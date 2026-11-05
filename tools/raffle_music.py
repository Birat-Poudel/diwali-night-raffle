"""Music for the Diwali Night raffle - a festive Panche Baja-inspired synth arranged as four cues
the page schedules on the Web Audio clock around a draw:

  groove    15.0 s  GO hit + accelerating tyamko roll (numbers speed up), then the full Panche Baja groove at 144 bpm,
                    sahanai on the main festive motif: A1 (ends on Sa at 5.42 s, where the 10 s spin starts to slow), B2 hook,
                    A2, B1. The page cuts it wherever the spin starts slowing.
  sting      2.5 s  crash + damaha + low narsingha and a falling gliss: the wheel starts to slow.
  suspense   7.5 s  END-ALIGNED: tanpura + dark pad, damaha heartbeat, gated riser into a reverse crash that peaks
                    0.35 s before the end, then a breath of silence. The page starts it part-way in so its end lands
                    exactly on the winning number.
  reveal    14.0 s  the winner: big hit, then the joyful second motif (B1 B2 B3) over the groove, its cadence
                    D C B -> Sa and a final hit.

  /Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 tools/raffle_music.py

Writes tools/build/*.wav, encodes them to AAC (macOS afconvert) and embeds them base64 in audio-data.js, so the page
also works opened straight from disk (file://, where fetch() is blocked).
"""
import sys, wave
import numpy as np

SR = 48000
FPS = 24
DUR = 30.0
N = int(SR * DUR)
E = 5 / FPS                    # an eighth = 5 frames (144 bpm)
rng = np.random.default_rng(144)
BUS = {k: [np.zeros(N), np.zeros(N)] for k in ('drums', 'tonal', 'fx', 'bass')}


def T(frame):
    return frame / FPS


# ---------------------------------------------------------------- the tune (MIDI, durations in eighths), whole bars
A1 = [(64, 1), (64, 1), (69, 1), (69, 1), (67, 1), (67, 1), (66, 1), (64, 2), (62, 1), (64, 1), (65, 1), (64, 1),
      (62, 1), (60, 1), (59, 1), (57, 6)]                                  # + 2 rest = 3 bars
A2 = [(56, 1), (56, 1), (56, 1), (57, 1), (59, 1), (62, 1), (62, 1), (59, 1), (62, 1), (64, 1), (65, 1), (64, 1),
      (62, 2), (60, 1), (59, 1), (57, 6)]                                  # + 2 rest = 3 bars
B1 = [(71, 1), (71, 1), (71, 1), (72, 1), (72, 1), (72, 1), (71, 1), (69, 1), (71, 1), (69, 1), (69, 1), (68, 1),
      (68, 1), (69, 3)]                                                    # 2 bars
B2 = [(62, 1), (62, 1), (62, 1.5), (62, 1), (64, 1), (61, 1), (62, 1.5)]  # 1 bar
B3 = [(62, 1), (64, 1), (66, 1), (68, 1), (68, 1), (69, 1), (68, 1), (69, 1), (71, 1), (72, 1), (71, 1), (69, 1),
      (68, 1), (66, 1), (64, 2)]                                           # 2 bars
CAD = [(62, 2), (60, 1), (59, 1), (57, 12)]                                # D C B -> Sa on f580
FORM = [('A1', A1, 120), ('A2', A2, 240), ('B1', B1, 360), ('B2', B2, 440), ('B3', B3, 480), ('CAD', CAD, 560)]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def fft_filter(x, lo=None, hi=None, order=2):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    H = np.ones_like(f)
    if lo:
        H *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** (2 * order))
    if hi:
        H *= 1 / np.sqrt(1 + (f / hi) ** (2 * order))
    return np.fft.irfft(X * H, len(x))


def noise(n):
    return rng.standard_normal(n)


def put(sig, t0, gain=1.0, pan=0.0, bus='fx'):
    i0 = int(round(t0 * SR))
    if i0 >= N:
        return
    s = sig[:max(0, N - i0)] * gain
    if i0 < 0:
        s = s[-i0:]
        i0 = 0
    a = (pan + 1) * np.pi / 4
    L, R = BUS[bus]
    L[i0:i0 + len(s)] += s * np.cos(a)
    R[i0:i0 + len(s)] += s * np.sin(a)


def env_adsr(n, a=0.005, d=0.08, s=0.7, r=0.05):
    e = np.full(n, s)
    na, nd, nr = int(a * SR), int(d * SR), int(r * SR)
    na = min(na, n)
    e[:na] = np.linspace(0, 1, na)
    nd = min(nd, n - na)
    e[na:na + nd] = np.linspace(1, s, nd)
    nr = min(nr, n)
    e[n - nr:] *= np.linspace(1, 0, nr)
    return e


# ---------------------------------------------------------------- melodic instruments
def pitch_track(notes, e, octave, glide=0.03, scoop=0.0, release=0.2):
    """Continuous frequency + note-onset amplitude for a legato line (meend glides; repeated notes re-tongued)."""
    durs = [d * e for m, d in notes]
    n = int((sum(durs) + release + 0.05) * SR)
    f = np.zeros(n)
    amp = np.zeros(n)
    onsets = []
    pos, prev = 0.0, None
    for (m, d), dur in zip(notes, durs):
        h = hz(m + octave)
        a, b = int(pos * SR), int((pos + dur) * SR)
        f[a:b] = h
        seg = np.ones(b - a)
        src = prev if (prev is not None and abs(prev - h) > 1e-6) else (h * 2 ** (-scoop / 12) if scoop else None)
        if src is not None:
            g = min(int(glide * SR), b - a)
            f[a:a + g] = src * (h / src) ** (np.linspace(0, 1, g) ** 0.6)
        if prev is not None and abs(prev - h) < 1e-6:
            k = min(int(0.045 * SR), b - a)
            seg[:k] = 0.3 + 0.7 * np.linspace(0, 1, k) ** 0.6
        amp[a:b] = seg
        onsets.append((a, b, dur))
        prev = h
        pos += dur
    end = int(pos * SR)
    f[end:] = f[end - 1]
    rl = min(int(release * SR), n - end)
    amp[end:end + rl] = amp[end - 1] * np.linspace(1, 0, rl) ** 2
    return f, amp, onsets, end


def vibrato(n, onsets, depth, rate=5.4, delay=0.18):
    """Vibrato that blooms on held notes only (depth in ratio)."""
    v = np.zeros(n)
    for a, b, dur in onsets:
        if dur < 0.3:
            continue
        k = np.arange(b - a) / SR
        v[a:b] = depth * np.clip((k - delay) / 0.25, 0, 1)
    t = np.arange(n) / SR
    return 1 + v * np.sin(2 * np.pi * rate * t)


def flute(notes, e, vel=1.0, octave=12, breath=0.07, vib=0.006, release=0.25, attack=0.05):
    """Bansuri: soft fundamental-heavy tone, breath noise and chiff, meend glides."""
    f, amp, on, end = pitch_track(notes, e, octave, glide=0.035, release=release)
    n = len(f)
    at = int(attack * SR)
    amp[:at] *= np.linspace(0, 1, at) ** 1.5
    ph = 2 * np.pi * np.cumsum(f * vibrato(n, on, vib)) / SR
    tone = np.sin(ph) + 0.22 * np.sin(2 * ph + 0.4) + 0.075 * np.sin(3 * ph + 0.2) + 0.03 * np.sin(4 * ph)
    nz = fft_filter(noise(n), lo=1800, hi=7000)
    nz /= np.max(np.abs(nz)) + 1e-9
    chiff = np.zeros(n)
    for a, b, dur in on:
        k = min(int(0.03 * SR), n - a)
        chiff[a:a + k] += np.exp(-np.arange(k) / (0.006 * SR))
    sig = tone * amp + breath * nz * (amp * 0.8 + chiff * 1.5)
    return fft_filter(sig, hi=6500, order=1) * vel * 0.3


def formants(fk):
    return (0.22 + 1.0 * np.exp(-((fk - 1150) / 380) ** 2) + 0.75 * np.exp(-((fk - 2650) / 650) ** 2)
            + 0.3 * np.exp(-((fk - 4300) / 900) ** 2)) / (1 + (fk / 7000) ** 2)


def sahanai(notes, e, vel=1.0, octave=0, vib=0.011, release=0.12):
    """Sahanai (shehnai), the Panche Baja's double reed: bright, nasal, buzzing - harmonics through two formants,
    a scoop into every note, a quick wide vibrato on the long ones."""
    f, amp, on, end = pitch_track(notes, e, octave, glide=0.028, scoop=0.7, release=release)
    n = len(f)
    at = int(0.015 * SR)
    amp[:at] *= np.linspace(0, 1, at)
    fv = f * vibrato(n, on, vib, rate=6.2, delay=0.12)
    ph = 2 * np.pi * np.cumsum(fv) / SR
    sig = np.zeros(n)
    for k in range(1, 26):
        fk = fv * k
        w = formants(fk) * (fk < 15000) / k ** 0.25
        sig += w * np.sin(k * ph + 0.3 * k)
    reed = fft_filter(noise(n), lo=2500, hi=6000) * 0.05
    sig = sig / (np.max(np.abs(sig)) + 1e-9) + reed
    return sig * amp * vel * 0.3


def horn(m, dur, vel=1.0, slur=2.0, fall=True, attack=0.16):
    """Narsingha (the long copper horn): a lip slur up into the note, brassy swell, a fall-off at the end."""
    n = int((dur + 0.45) * SR)
    t = np.arange(n) / SR
    h = hz(m)
    f = np.full(n, h)
    g = int(0.14 * SR)
    f[:g] = h * 2 ** (-slur / 12 * (1 - np.linspace(0, 1, g) ** 0.5))
    nd = int(dur * SR)
    if fall:
        k = n - nd
        f[nd:] = h * 2 ** (-3.5 / 12 * np.linspace(0, 1, k) ** 1.6)
    f *= 1 + 0.004 * np.clip((t - 0.5) / 0.4, 0, 1) * np.sin(2 * np.pi * 4.8 * t)
    amp = np.clip(t / attack, 0, 1) ** 1.3
    amp[nd:] *= np.linspace(1, 0, n - nd) ** 1.4
    amp *= 1 + 0.12 * np.clip(t / max(dur, 0.1), 0, 1)
    bright = 0.25 + 0.75 * amp
    ph = 2 * np.pi * np.cumsum(f) / SR
    sig = np.zeros(n)
    for k in range(1, 22):
        sig += np.exp(-k / (1.5 + 9 * bright)) * np.sin(k * ph + 0.2 * k) * (f * k < 12000)
    sig += 0.05 * fft_filter(noise(n), lo=300, hi=2200) * amp
    return sig * amp * vel * 0.22


def braam(ms, dur, vel=1.0):
    return sum(horn(m, dur, vel / len(ms) ** 0.5, slur=1.0, fall=False, attack=0.05) for m in ms)


def pluck(m, vel=1.0, dur=1.3):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f0 = hz(m)
    s = sum((1 / k) * np.sin(2 * np.pi * f0 * k * t) * np.exp(-t / (0.75 / k)) for k in range(1, 7))
    return s * np.minimum(1, t / 0.002) * 0.08 * vel


def gliss(t0, notes, step=0.05, vel=0.6, pan=0.3):
    for i, m in enumerate(notes):
        put(pluck(m, vel * 0.9, 1.4), t0 + i * step, pan=pan, bus='tonal')


def tanpura(m, dur=3.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f0 = hz(m)
    s = np.zeros(n)
    for k in range(1, 15):
        bloom = 1.0 if k <= 3 else (1 - np.exp(-t / 0.12)) * 0.9
        s += (1 / k ** 0.75) * np.sin(2 * np.pi * f0 * k * (1 + 0.0004 * k) * t + rng.uniform(0, 6.28)) * \
             np.exp(-t / (2.6 / (1 + 0.1 * k))) * bloom
    return s * np.minimum(1, t / 0.01) * 0.032


def pad(m_list, dur, vel=1.0, attack=1.2, release=1.0):
    """Dark sustained pad (detuned saws, low-passed) - the drone under the intro and the dip."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.zeros(n)
    for m in m_list:
        for det in (-0.08, 0.0, 0.07):
            f = hz(m + det)
            for k in range(1, 12):
                s += np.sin(2 * np.pi * f * k * t + rng.uniform(0, 6.28)) / k
    s = fft_filter(s, hi=700, order=2)
    e = np.clip(t / attack, 0, 1) ** 1.5 * np.clip((dur - t) / release, 0, 1)
    return s / (np.max(np.abs(s)) + 1e-9) * e * vel * 0.12


def bass(m, dur, vel=1.0):
    n = int((dur + 0.03) * SR)
    t = np.arange(n) / SR
    f0 = hz(m)
    s = 0.9 * np.sin(2 * np.pi * f0 * t) + sum(np.sin(2 * np.pi * f0 * k * t) / k ** 1.4 for k in range(2, 9)) * 0.55
    return s * env_adsr(n, 0.004, 0.09, 0.6, 0.03) * vel * 0.3


# ---------------------------------------------------------------- percussion + fx
def damaha(vel=1.0, f0=56):
    """The Panche Baja's big kettle drum: a deep boom with a falling pitch."""
    n = int(1.5 * SR)
    t = np.arange(n) / SR
    f = f0 + 75 * np.exp(-t / 0.045)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-t / 0.5) + 0.35 * np.sin(1.52 * ph) * np.exp(-t / 0.2) + 0.18 * np.sin(2.31 * ph) * np.exp(-t / 0.1)
    s += 0.5 * fft_filter(noise(n), lo=80, hi=1800) * np.exp(-t / 0.012)
    return s * np.minimum(1, t / 0.002) * vel * 0.55


def kick(vel=1.0):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 46 + 120 * np.exp(-t / 0.028)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.26)
    s += 0.25 * fft_filter(noise(n), lo=2500, hi=9000) * np.exp(-t / 0.004)
    return s * np.minimum(1, t / 0.001) * vel * 0.5


def madal(kind, vel=1.0):
    if kind == 'B':
        n = int(0.5 * SR)
        t = np.arange(n) / SR
        f = 72 + 46 * np.exp(-t / 0.035)
        ph = 2 * np.pi * np.cumsum(f) / SR
        s = np.sin(ph) * np.exp(-t / 0.2) + 0.25 * np.sin(2.2 * ph) * np.exp(-t / 0.05)
        s += 0.25 * fft_filter(noise(n), lo=200, hi=2500) * np.exp(-t / 0.005)
        return s * vel * 0.42
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    f0 = 410 if kind == 'T' else 520
    s = sum(a * np.sin(2 * np.pi * f0 * r * t + rng.uniform(0, 6.28)) * np.exp(-t / d)
            for r, a, d in ((1, 1, 0.08), (1.59, 0.55, 0.055), (2.14, 0.35, 0.04), (2.65, 0.25, 0.03), (3.16, 0.15, 0.025)))
    s += 0.5 * fft_filter(noise(n), lo=1500, hi=8000) * np.exp(-t / 0.004)
    return s * vel * 0.3


def tyamko(vel=1.0):
    """Small high drum played with sticks: a dry crack."""
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 640 * t) * np.exp(-t / 0.045) + 0.55 * np.sin(2 * np.pi * 1030 * t) * np.exp(-t / 0.028)
    crack = fft_filter(noise(n), lo=1200, hi=7500) * np.exp(-t / 0.007)
    return (0.55 * tone + crack) * vel * 0.26


def jhyamta(vel=1.0, open_=False):
    d = 0.9 if open_ else 0.2
    n = int(d * SR)
    t = np.arange(n) / SR
    s = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / (d * rng.uniform(0.3, 0.5)))
            for f in (3150, 3720, 4410, 5030, 5980, 6870, 7600, 8350, 9120))
    s = s / 9 + 0.5 * fft_filter(noise(n), lo=5000, hi=12000) * np.exp(-t / (d * 0.25))
    return s * vel * 0.12


def crash(vel=1.0, dur=2.8):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / rng.uniform(0.5, 1.1))
            for f in rng.uniform(2200, 9500, 28)) / 28
    s += 0.9 * fft_filter(noise(n), lo=3500, hi=13000) * (np.exp(-t / 0.8) + 0.6 * np.exp(-t / 0.05))
    return s * np.minimum(1, t / 0.001) * vel * 0.16


def ghanta(f0=660.0, dur=5.0, vel=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.zeros(n)
    for r, a, d in ((0.5, 0.3, 4.5), (1.0, 1.0, 3.4), (1.19, 0.5, 2.6), (1.56, 0.45, 2.1), (2.0, 0.35, 1.7),
                    (2.51, 0.22, 1.3), (2.66, 0.18, 1.1), (3.01, 0.14, 0.9), (4.1, 0.07, 0.5)):
        beat = 1 + 0.12 * np.sin(2 * np.pi * rng.uniform(0.6, 1.8) * t)
        s += a * np.sin(2 * np.pi * f0 * r * t + rng.uniform(0, 6.28)) * np.exp(-t / d) * beat
    s += 0.6 * fft_filter(noise(n), lo=2000, hi=9000) * np.exp(-t / 0.003)
    return s * np.minimum(1, t / 0.002) * vel * 0.16


def clap(vel=1.0):
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    e = sum(np.exp(-np.clip(t - d, 0, None) / 0.004) * (t >= d) for d in (0.0, 0.009, 0.018))
    e += 0.6 * np.exp(-np.clip(t - 0.02, 0, None) / 0.07) * (t >= 0.02)
    return fft_filter(noise(n), lo=900, hi=5200) * e * vel * 0.2


def thunder(vel=1.0):
    n = int(2.6 * SR)
    t = np.arange(n) / SR
    s = fft_filter(noise(n), lo=30, hi=420) * (np.exp(-t / 0.7) * 0.8 + np.exp(-t / 0.05))
    s += 0.4 * fft_filter(noise(n), lo=900, hi=4000) * np.exp(-t / 0.02)
    return s * vel * 0.32


def boom(vel=1.0, dur=2.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 36 + 70 * np.exp(-t / 0.09)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.8) * np.minimum(1, t / 0.002) * vel * 0.6


def riser(dur, vel=1.0, f_lo=250.0, f_hi=7000.0, gate=None):
    """Noise swept up through a narrowing band (overlap-added FFT blocks) plus a rising tone; crescendo.
    gate: optional seconds per pulse for a rhythmic (16th-note) chop in the last half."""
    n = int(dur * SR)
    out = np.zeros(n + SR)
    blk, hop = int(0.08 * SR), int(0.04 * SR)
    win = np.hanning(blk)
    nb = n // hop
    freqs = np.fft.rfftfreq(blk, 1 / SR)
    for i in range(nb):
        fc = f_lo * (f_hi / f_lo) ** (i / nb)
        H = np.exp(-np.log(np.maximum(freqs, 1) / fc) ** 2 / (2 * 0.45 ** 2))
        seg = np.fft.irfft(np.fft.rfft(noise(blk)) * H, blk) * win
        out[i * hop:i * hop + blk] += seg
    out = out[:n]
    t = np.arange(n) / SR
    f = 180 * (2 ** (np.log2(2200 / 180) * (t / dur) ** 1.3))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.4 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    s = out / (np.max(np.abs(out)) + 1e-9) + 0.25 * tone
    e = (t / dur) ** 2.2
    if gate:
        g = 0.35 + 0.65 * (np.sin(2 * np.pi * t / gate) > -0.3)
        e *= np.where(t > dur * 0.5, g, 1.0)
    return s * e * vel * 0.3


def reverse_crash(dur=1.6, vel=1.0):
    c = crash(1.0, dur)[::-1]
    return c * vel


def whoosh(dur=0.55, vel=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n + SR)
    blk, hop = int(0.06 * SR), int(0.03 * SR)
    win = np.hanning(blk)
    freqs = np.fft.rfftfreq(blk, 1 / SR)
    nb = n // hop
    for i in range(nb):
        x = i / nb
        fc = 500 + 3500 * np.sin(np.pi * x)
        H = np.exp(-np.log(np.maximum(freqs, 1) / fc) ** 2 / (2 * 0.6 ** 2))
        out[i * hop:i * hop + blk] += np.fft.irfft(np.fft.rfft(noise(blk)) * H, blk) * win
    s = out[:n] / (np.max(np.abs(out)) + 1e-9)
    return s * np.sin(np.pi * t / dur) ** 2 * vel * 0.18


def sparkler_swoosh(dur=0.95, vel=1.0):
    """A festive sparkler sweep: an air whoosh plus a fast crackling flutter, loudest as it crosses."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.sin(np.pi * t / dur) ** 3
    paper = fft_filter(noise(n), lo=1400, hi=5200) * (1 + 0.6 * np.sin(2 * np.pi * 23 * t)) * env
    paper /= np.max(np.abs(paper)) + 1e-9
    return whoosh(dur, 1.0) + paper * vel * 0.07


def put_sweep(sig, t0, pan0, pan1, bus='fx'):
    """Place a sound whose pan moves from pan0 to pan1 over its length."""
    i0 = int(round(t0 * SR))
    s = sig[:max(0, N - i0)]
    a = (np.linspace(pan0, pan1, len(s)) + 1) * np.pi / 4
    L, R = BUS[bus]
    L[i0:i0 + len(s)] += s * np.cos(a)
    R[i0:i0 + len(s)] += s * np.sin(a)


def buzz(dur=0.36, vel=1.0):
    """A phone vibrating on a bed."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.sign(np.sin(2 * np.pi * 148 * t)) * (1 + 0.45 * np.sin(2 * np.pi * 37 * t))
    s = fft_filter(s, lo=90, hi=1400)
    e = np.clip(t / 0.012, 0, 1) * np.clip((dur - t) / 0.02, 0, 1)
    return s / (np.max(np.abs(s)) + 1e-9) * e * vel * 0.16


# ---------------------------------------------------------------- arrangement helpers
def hit(f, vel=1.0, big=False, bell=False, horn_m=None, thunder_=False):
    t = T(f)
    put(damaha(vel), t, pan=0.0, bus='drums')
    put(crash(0.9 * vel, 3.0 if big else 2.0), t, pan=0.15, bus='drums')
    put(boom(0.7 * vel if big else 0.45 * vel), t, bus='fx')
    if bell:
        put(ghanta(660, 5.0, 0.8 * vel), t + 0.005, pan=-0.1, bus='fx')
    if horn_m:
        put(braam(horn_m, 1.6 if big else 0.9, 1.1 * vel), t, pan=0.0, bus='fx')
    if thunder_:
        put(thunder(vel), t, pan=0.1, bus='fx')


def drums(f0, f1, pat, vel=1.0, step=5, ramp=None, jh=None, jh_vel=0.6):
    """Madal pattern on a frame grid (step frames per slot) between frames f0 and f1."""
    k, f = 0, f0
    while f < f1:
        p = pat[k % len(pat)]
        v = vel if ramp is None else vel * (ramp[0] + (ramp[1] - ramp[0]) * (f - f0) / max(1, f1 - f0))
        hum = rng.normal(0, 0.003)
        if p in 'BTH':
            accent = 1.12 if k % len(pat) == 0 else 1.0
            put(madal(p, v * accent * rng.uniform(0.9, 1.05)), T(f) + hum, pan=0.12 if p == 'B' else -0.18, bus='drums')
        elif p == 'K':
            put(tyamko(v * rng.uniform(0.85, 1.0)), T(f) + hum, pan=-0.3, bus='drums')
        if jh and jh[k % len(jh)] != '-':
            put(jhyamta(jh_vel * v / max(vel, 1e-6) * rng.uniform(0.85, 1.0), open_=jh[k % len(jh)] == 'O'), T(f) + hum,
                pan=0.35, bus='drums')
        f += step
        k += 1


def roll(f0, f1, vel0=0.3, vel1=1.0, inst='K'):
    """Accelerating roll: eighths -> sixteenths -> thirty-seconds, crescendo."""
    t0, t1 = T(f0), T(f1)
    t = t0
    while t < t1 - 1e-4:
        x = (t - t0) / (t1 - t0)
        v = vel0 + (vel1 - vel0) * x ** 1.5
        put(tyamko(v) if inst == 'K' else madal('T', v), t, pan=-0.25 * (1 if int(t * 50) % 2 else -1), bus='drums')
        t += E / (1 if x < 0.35 else 2 if x < 0.7 else 4)


def line(seq, f, vel=1.0, inst='flute', pan=-0.08, **kw):
    sig = flute(seq, E, vel, **kw) if inst == 'flute' else sahanai(seq, E, vel, **kw)
    put(sig, T(f), pan=pan, bus='tonal')


def plucked(seq, f, vel=1.0, octave=12, pan=0.25):
    t = T(f)
    for m, d in seq:
        put(pluck(m + octave, vel * rng.uniform(0.85, 1.0)), t, pan=pan, bus='tonal')
        t += d * E


def bassline(f0, f1, root, pattern='octave', vel=1.0):
    f = f0
    i = 0
    while f < f1:
        m = root if (pattern != 'octave' or i % 2 == 0) else root + 12
        put(bass(m, E * 0.85, vel * (1.0 if i % 2 == 0 else 0.8)), T(f), bus='bass')
        f += 5
        i += 1


def bass_pulse(f0, f1, root, vel=1.0, every=10):
    f = f0
    while f < f1:
        put(bass(root, E * 1.6, vel), T(f), bus='bass')
        f += every


KICKS = []


def four(f0, f1, vel=1.0, every=10):
    f = f0
    while f < f1:
        put(kick(vel), T(f), bus='drums')
        KICKS.append(T(f))
        f += every


def claps(f0, f1, vel=1.0):
    f = f0 + 10
    while f < f1:
        put(clap(vel * rng.uniform(0.9, 1.0)), T(f) + rng.normal(0, 0.002), pan=rng.uniform(-0.2, 0.2), bus='drums')
        f += 20



# ---------------------------------------------------------------- mix and master
def reverb(x, rt60=1.8, wet=0.22, seed=1):
    r = np.random.default_rng(seed)
    n = int(rt60 * 1.2 * SR)
    t = np.arange(n) / SR
    ir = r.standard_normal(n) * np.exp(-6.9 * t / rt60)
    ir = fft_filter(ir, hi=5000, order=1)
    ir[: int(0.012 * SR)] = 0
    ir /= np.sqrt(np.sum(ir ** 2))
    m = 1 << int(np.ceil(np.log2(len(x) + n)))
    y = np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(ir, m), m)[: len(x)]
    return x * (1 - wet) + y * wet * 2.2


def duck(n, times, depth=0.4, rel=0.09):
    """Sidechain pump: dip after every kick."""
    g = np.ones(n)
    for tk in times:
        i0 = int(tk * SR)
        k = min(int(0.35 * SR), n - i0)
        if k > 0:
            g[i0:i0 + k] = np.minimum(g[i0:i0 + k], 1 - depth * np.exp(-np.arange(k) / (rel * SR)))
    return g


def limiter(L, R, ceiling=0.89, block=128, rel=0.08):
    peak = np.maximum(np.abs(L), np.abs(R))
    nb = int(np.ceil(len(peak) / block))
    bp = np.array([peak[i * block:(i + 1) * block].max() for i in range(nb)])
    bp = np.maximum(bp, np.concatenate([bp[1:], bp[-1:]]))           # one block of look-ahead
    g = np.minimum(1.0, ceiling / np.maximum(bp, 1e-9))
    a = np.exp(-block / (rel * SR))
    out = np.empty(nb)
    cur = 1.0
    for i in range(nb):
        cur = g[i] if g[i] < cur else a * cur + (1 - a) * g[i]
        out[i] = cur
    gs = np.repeat(out, block)[:len(peak)]
    return L * gs, R * gs



# ================================================================= the raffle cues
import os, subprocess, base64

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, 'build')
os.makedirs(BUILD, exist_ok=True)
P_B = ['B', 'T', 'K', 'B', 'T', 'H', 'B', 'K', 'B', 'T', 'K', 'B', 'H', 'T', 'B', 'K']
J_B = ['-', '-', 'C', '-', '-', '-', 'C', '-', '-', '-', 'C', '-', '-', '-', 'O', '-']
CUES = {}


def new_track(dur):
    global N, BUS, KICKS
    N = int(SR * dur)
    BUS = {k: [np.zeros(N), np.zeros(N)] for k in ('drums', 'tonal', 'fx', 'bass')}
    KICKS = []


def tune(seq, f, sah=1.8, fl=0.8, pl=0.6, **kw):
    line(seq, f, vel=sah, inst='sahanai', pan=-0.05, **{k: v for k, v in kw.items() if k == 'release'})
    line(seq, f, vel=fl, inst='flute', octave=12, pan=0.18, breath=0.05,
         release=kw.get('flute_release', 0.25))
    if pl:
        plucked(seq, f, vel=pl, octave=0)


def master(name, level=1.0, fade_out=0.6, hard_end=None):
    pump = duck(N, KICKS) if KICKS else np.ones(N)
    LEVEL = {'drums': 1.0, 'tonal': 0.9, 'fx': 0.85, 'bass': 0.8}
    SPACE = {'drums': (0.7, 0.1), 'tonal': (1.9, 0.24), 'fx': (2.6, 0.3), 'bass': (0.5, 0.0)}
    L, R = np.zeros(N), np.zeros(N)
    for k, (bl, br) in BUS.items():
        rt, wet = SPACE[k]
        if wet:
            bl, br = reverb(bl, rt, wet, 1), reverb(br, rt, wet, 2)
        g = LEVEL[k] * (pump if k == 'bass' else 1.0)
        L += bl * g
        R += br * g
    L, R = fft_filter(L, lo=35), fft_filter(R, lo=35)
    env = np.ones(N)
    if hard_end is not None:                        # the breath: everything stops dead before the winner lands
        e = int(hard_end * SR)
        k = int(0.05 * SR)
        env[e - k:e] = np.linspace(1, 0, k)
        env[e:] = 0
    elif fade_out:
        k = int(fade_out * SR)
        env[-k:] = np.linspace(1, 0, k) ** 1.5
    L, R = L * env, R * env
    pk = max(np.max(np.abs(L)), np.max(np.abs(R)))
    L, R = L / pk * 1.6, R / pk * 1.6
    L, R = limiter(L, R)
    L = np.tanh(L * 1.05) / np.tanh(1.05) * 0.95 * level
    R = np.tanh(R * 1.05) / np.tanh(1.05) * 0.95 * level
    path = os.path.join(BUILD, name + '.wav')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.stack([L, R], 1) * 32767).astype('<i2').tobytes())
    CUES[name] = N / SR
    print('wrote %-9s %5.2f s' % (name, N / SR))


# ---- groove: GO, the wind-up roll (0-20 = the speed-up), then the groove from f20 (G)
new_track(15.0)
G = 20
hit(0, 1.0, big=True, bell=True, horn_m=[33, 45, 52])
gliss(0.03, [57, 60, 64, 69, 72, 76, 81, 84], step=0.045, vel=0.5)
roll(0, G, 0.3, 1.0)
put(reverse_crash(0.6, 0.6), T(G) - 0.6, bus='fx')
drums(G, 352, P_B, vel=1.0, step=2.5, jh=J_B, jh_vel=0.75)
four(G, 352, 0.8)
claps(G, 352, 0.9)
for f in range(G, 352, 40):
    put(damaha(0.6), T(f), bus='drums')
tune(A1, G)                                          # A1 resolves to Sa on f130 = 5.42 s
bassline(G, 140, 33)
tune(B2, 140)                                        # the hook, on D, with a horn stab
put(horn(45, 0.5, 0.7), T(140), bus='fx')
bassline(140, 180, 38)
tune(A2, 180)
bassline(180, 300, 33)
tune(B1, 300)
bassline(300, 360, 33)
master('groove', fade_out=0.5)

# ---- sting: the wheel starts to slow
new_track(2.5)
put(damaha(0.95), 0.0, bus='drums')
put(crash(0.8, 2.2), 0.0, pan=0.15, bus='drums')
put(braam([33, 45], 0.9, 0.9), 0.0, bus='fx')
put(bass(33, 1.2, 0.9), 0.0, bus='bass')
gliss(0.02, [81, 76, 72, 69, 64, 60, 57], step=0.05, vel=0.45, pan=-0.2)
master('sting', level=0.9, fade_out=0.8)

# ---- suspense (end-aligned): drone, heartbeat, riser -> breath
SUS, BREATH = 7.5, 0.35
new_track(SUS)
t, i = 0.0, 0
while t < SUS:
    put(tanpura([52, 57, 57, 45][i % 4]), t, gain=0.8, pan=0.25 if i % 2 else -0.25, bus='tonal')
    t += 0.625
    i += 1
put(pad([45, 52, 57], SUS + 0.5, 0.9, attack=0.4, release=0.3), 0.0, bus='fx')
t = 0.0
while t < SUS - BREATH - 0.3:
    v = 0.35 + 0.5 * t / SUS
    put(damaha(v, f0=50), t, bus='drums')
    put(damaha(v * 0.55, f0=50), t + 0.22, bus='drums')
    t += 4 * E                                        # every two beats
put(horn(33, 3.2, 0.55, slur=1.0, fall=False, attack=0.9), 0.6, bus='fx')
RIS = 4.2
put(riser(RIS, 1.0, gate=E / 2), SUS - BREATH - RIS, bus='fx')
put(reverse_crash(1.3, 0.9), SUS - BREATH - 1.3, bus='fx')
master('suspense', level=0.85, hard_end=SUS - BREATH)

# ---- reveal: the winner
new_track(14.0)
hit(0, 1.25, big=True, bell=True, horn_m=[33, 45, 52, 57])
put(bass(33, 2.5, 1.0), 0.0, bus='bass')
put(ghanta(880, 5.0, 0.6), 0.01, pan=0.2, bus='fx')
gliss(0.08, [69, 71, 72, 74, 76, 77, 79, 81, 83, 84], step=0.045, vel=0.5)
drums(0, 240, P_B, vel=1.0, step=2.5, jh=J_B, jh_vel=0.75)
four(0, 240, 0.8)
claps(0, 240, 1.0)
for f in range(40, 240, 40):
    put(damaha(0.6), T(f), bus='drums')
tune(B1, 40, pl=0.7)
tune(B2, 120, pl=0.7)
tune(B3, 160, pl=0.7)
bassline(0, 120, 33)
bassline(120, 160, 38)
bassline(160, 220, 33)
bassline(220, 240, 40)
roll(230, 240, 0.6, 1.1)
put(reverse_crash(0.8, 0.7), T(240) - 0.8, bus='fx')
tune(CAD, 240, pl=0.7, release=0.5, flute_release=1.6)
for f, m in ((240, 38), (250, 36), (255, 35)):
    put(damaha(0.9), T(f), bus='drums')
    put(crash(0.55, 1.2), T(f), bus='drums')
    put(bass(m, E * 1.6, 1.1), T(f), bus='bass')
put(reverse_crash(1.0, 0.8), T(260) - 1.0, bus='fx')
hit(260, 1.15, big=True, bell=True, horn_m=[45, 52, 57])
put(bass(33, 2.0, 0.9), T(260), bus='bass')
gliss(T(260) + 0.05, [57, 60, 64, 69, 72, 76, 81], step=0.06, vel=0.45)
master('reveal', fade_out=1.2)

# ---- encode (AAC 128k) and embed
parts = []
for name, dur in CUES.items():
    wav = os.path.join(BUILD, name + '.wav')
    m4a = os.path.join(BUILD, name + '.m4a')
    subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', '128000', wav, m4a], check=True)
    with open(m4a, 'rb') as fh:
        b64 = base64.b64encode(fh.read()).decode()
    parts.append('  %s: { dur: %.4f, data: "%s" }' % (name, dur, b64))
js = os.path.join(HERE, '..', 'audio-data.js')
with open(js, 'w') as fh:
    fh.write('// Generated by tools/raffle_music.py (Panche Baja synth, AAC base64) - do not edit by hand.\n')
    fh.write('window.RAFFLE_AUDIO = {\n' + ',\n'.join(parts) + '\n};\n')
print('wrote audio-data.js  %.0f KB' % (os.path.getsize(js) / 1024))

"""테스트 픽스처 생성 — 정답을 아는 베이스 라인 + 드럼 클릭.

beat_this가 비트를 잡으려면 타악이 필요하므로 킥/하이햇을 섞는다.
베이스만 담은 버전과 믹스 버전을 둘 다 만들어서,
- 믹스: 비트 추적용 (그리고 Demucs 테스트용)
- 베이스 단독: 채보 상한 측정용 (--skip-separate)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
BPM = 120.0
BEATS_PER_BAR = 4
BARS = 8
BEAT_SEC = 60.0 / BPM          # 0.5s
BAR_SEC = BEAT_SEC * BEATS_PER_BAR

OUT = Path(__file__).resolve().parent.parent / "data" / "_fixture"
OUT.mkdir(parents=True, exist_ok=True)

# 8분음표 워킹 베이스. (MIDI, 슬롯길이 in 8분음표)
# E1=28 G1=31 A1=33 B1=35 C2=36 D2=38
PATTERN = [
    (28, 2), (28, 2), (31, 2), (33, 2),   # bar 1
    (33, 2), (33, 2), (35, 2), (36, 2),   # bar 2
    (28, 4), (31, 2), (33, 2),            # bar 3
    (38, 2), (36, 2), (35, 2), (33, 2),   # bar 4
]
EIGHTH = BEAT_SEC / 2


def midi_to_hz(m: int) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def pluck(midi: int, dur: float) -> np.ndarray:
    """배음이 있는 베이스 음. 어택이 있고 감쇠한다."""
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    f0 = midi_to_hz(midi)
    sig = np.zeros_like(t)
    for h, amp in [(1, 1.0), (2, 0.45), (3, 0.22), (4, 0.1), (5, 0.05)]:
        sig += amp * np.sin(2 * np.pi * f0 * h * t)
    # 지수 감쇠 + 짧은 어택
    env = np.exp(-t * 3.0)
    a = max(1, int(SR * 0.006))
    env[:a] *= np.linspace(0, 1, a)
    return sig * env * 0.28


def kick() -> np.ndarray:
    dur = 0.14
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    f = np.linspace(110, 45, len(t))
    sig = np.sin(2 * np.pi * np.cumsum(f) / SR)
    return sig * np.exp(-t * 22) * 0.55


def hat() -> np.ndarray:
    dur = 0.045
    n = int(SR * dur)
    rng = np.random.default_rng(7)
    t = np.linspace(0, dur, n, endpoint=False)
    return rng.standard_normal(n) * np.exp(-t * 130) * 0.14


def snare() -> np.ndarray:
    """2·4박 백비트. 이게 없으면 킥(1·3박)만으로는 4/4와 2/4가 구분되지 않는다."""
    dur = 0.16
    n = int(SR * dur)
    rng = np.random.default_rng(11)
    t = np.linspace(0, dur, n, endpoint=False)
    noise = rng.standard_normal(n) * np.exp(-t * 28)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return (noise * 0.5 + body * 0.35) * 0.5


def main() -> None:
    total_sec = BARS * BAR_SEC
    total = int(SR * total_sec)
    bass = np.zeros(total, dtype=np.float64)
    drums = np.zeros(total, dtype=np.float64)

    # 베이스 — 4마디 패턴을 2번 반복
    truth: list[dict] = []
    cursor = 0.0
    for _ in range(BARS // 4):
        for midi, eighths in PATTERN:
            dur = eighths * EIGHTH
            start_i = int(cursor * SR)
            wave = pluck(midi, dur)
            end_i = min(total, start_i + len(wave))
            bass[start_i:end_i] += wave[: end_i - start_i]
            truth.append({
                "start": round(cursor, 6),
                "end": round(cursor + dur, 6),
                "pitch": midi,
                "bar": int(cursor // BAR_SEC),
            })
            cursor += dur

    # 드럼 — 킥 1·3박, 스네어 2·4박(백비트), 하이햇 8분음표
    k, s, h = kick(), snare(), hat()

    def place(sample: np.ndarray, at_sec: float) -> None:
        i = int(at_sec * SR)
        if i >= total:
            return
        seg = drums[i : i + len(sample)]
        seg += sample[: len(seg)]

    for bar in range(BARS):
        bar_start = bar * BAR_SEC
        for beat in (0, 2):
            place(k, bar_start + beat * BEAT_SEC)
        for beat in (1, 3):
            place(s, bar_start + beat * BEAT_SEC)
        for e in range(BEATS_PER_BAR * 2):
            place(h, bar_start + e * EIGHTH)

    def to_stereo(x: np.ndarray) -> np.ndarray:
        peak = np.max(np.abs(x)) or 1.0
        x = (x / peak * 0.85).astype(np.float32)
        return np.stack([x, x], axis=1)

    bass_path = OUT / "bass_only.wav"
    mix_path = OUT / "mix.wav"
    sf.write(bass_path, to_stereo(bass), SR)
    sf.write(mix_path, to_stereo(bass + drums), SR)

    meta = {
        "bpm": BPM,
        "beatsPerBar": BEATS_PER_BAR,
        "bars": BARS,
        "durationSec": round(total_sec, 3),
        "noteCount": len(truth),
        "notes": truth,
    }
    (OUT / "truth.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"[fixture] {bass_path.name}  베이스 단독")
    print(f"[fixture] {mix_path.name}   베이스+드럼 믹스")
    print(f"[fixture] {BPM}BPM {BEATS_PER_BAR}/4 {BARS}마디 {total_sec:.1f}s, 정답 {len(truth)}음")


if __name__ == "__main__":
    main()

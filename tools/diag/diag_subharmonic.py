"""검출 피치 아래(f/2·f/3)에 실제 에너지가 있는지 잰다 — 배음 오인 진단.

가설(NEXT.md 결함 2): Come Together에서 CREPE가 일부 음의 3배음을 f0로
잡는다(+19반음 = 피치클래스 +7). 그렇다면 검출 피치 f의 1/3 지점에
기음 에너지가 실재해야 한다. 반대로 기음을 제대로 잡은 음이라면 f/2·f/3에는
(서브하모닉은 물리적으로 없으므로) 에너지가 거의 없어야 한다.

측정 설계
- 곡 전체 STFT 한 번(n_fft 크게 — 저역 분해능 확보), 음 구간 프레임 평균.
- 각 음의 f, f/2, f/3 주변 ±3%(반음의 약 절반) 대역 에너지 비율.
- 대조군(배음 문제가 없다고 보는 곡)과 분포를 비교해 임계 근거를 만든다.

사용:
  .venv/Scripts/python.exe tools/diag/diag_subharmonic.py data/78d6e3fc12388629 [data/...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import librosa
import numpy as np

N_FFT = 16384  # 44.1kHz에서 약 2.7Hz/bin — E1(41.2Hz)과 그 반음 이웃을 가른다
HOP = 2048
BAND = 0.03  # 중심 주파수 ±3% 대역 (반음 간격은 약 ±6%)
# f/k 에너지가 f 에너지의 이 비율을 넘으면 "아래에 기음이 실재"로 본다.
# 값 자체는 대조군 분포를 보고 읽는다 — 절대 판정용이 아니라 곡 간 비교용.
SUSPECT_RATIO = 0.5


def band_energy(mag: np.ndarray, freqs: np.ndarray, f: float) -> float:
    lo, hi = f * (1 - BAND), f * (1 + BAND)
    idx = (freqs >= lo) & (freqs <= hi)
    if not idx.any():
        return 0.0
    return float(mag[idx].max())  # 대역 내 피크 (평균은 대역폭에 민감)


def analyze(data_dir: Path) -> dict:
    notes = json.loads((data_dir / "notes.json").read_text(encoding="utf-8"))
    wav = data_dir / "stems" / "bass.wav"
    y, sr = librosa.load(str(wav), sr=None, mono=True)
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    frame_sec = HOP / sr

    rows = []
    for n in notes:
        f = librosa.midi_to_hz(n["pitch"])
        a = int(n["start"] / frame_sec)
        b = max(a + 1, int(n["end"] / frame_sec))
        if b > S.shape[1]:
            b = S.shape[1]
        if a >= b:
            continue
        mag = S[:, a:b].mean(axis=1)
        e1 = band_energy(mag, freqs, f)
        if e1 <= 0:
            continue
        e_half = band_energy(mag, freqs, f / 2) if f / 2 >= freqs[1] else 0.0
        e_third = band_energy(mag, freqs, f / 3) if f / 3 >= freqs[1] else 0.0
        rows.append({
            "pitch": n["pitch"],
            "start": n["start"],
            "r2": e_half / e1,
            "r3": e_third / e1,
        })

    r2 = np.array([r["r2"] for r in rows])
    r3 = np.array([r["r3"] for r in rows])
    sus2 = (r2 > SUSPECT_RATIO)
    sus3 = (r3 > SUSPECT_RATIO)
    sus_pitches = [r["pitch"] for r, s in zip(rows, sus3) if s]
    return {
        "dir": data_dir.name,
        "n": len(rows),
        "r2_median": float(np.median(r2)) if len(rows) else 0.0,
        "r3_median": float(np.median(r3)) if len(rows) else 0.0,
        "suspect_half_pct": float(sus2.mean() * 100) if len(rows) else 0.0,
        "suspect_third_pct": float(sus3.mean() * 100) if len(rows) else 0.0,
        "suspect_third_pitch_median": float(np.median(sus_pitches)) if sus_pitches else None,
        "all_pitch_median": float(np.median([r["pitch"] for r in rows])) if rows else None,
    }


def main() -> None:
    dirs = [Path(p) for p in sys.argv[1:]]
    if not dirs:
        print(__doc__)
        sys.exit(1)
    print(f"{'곡':<20} {'음수':>4} {'r2중앙':>7} {'r3중앙':>7} {'f/2혐의%':>8} {'f/3혐의%':>8} {'혐의피치중앙':>10} {'전체피치중앙':>10}")
    for d in dirs:
        r = analyze(d)
        print(
            f"{r['dir']:<20} {r['n']:>4} {r['r2_median']:>7.3f} {r['r3_median']:>7.3f} "
            f"{r['suspect_half_pct']:>8.1f} {r['suspect_third_pct']:>8.1f} "
            f"{str(r['suspect_third_pitch_median']):>10} {str(r['all_pitch_median']):>10}"
        )


if __name__ == "__main__":
    main()

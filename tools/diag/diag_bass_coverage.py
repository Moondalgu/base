"""악보가 오디오의 베이스를 실제로 담았는지, 그리고 음량으로 연주를 가를 수 있는지.

## 왜 다시 재는가

앞서 "진폭으로 두 연주를 가를 수 없다"고 판정했는데 그 측정이 틀렸다.
`Note.amplitude`에는 **음량이 아니라 CREPE periodicity(피치 확신도)**가 들어
있다(`transcribe_crepe.transcribe` 주석). 확신도는 원래 높은 쪽에 몰리므로
분포가 단봉으로 나오는 것이 당연하고, 음량과는 다른 값이다.

여기서는 **오디오에서 직접 RMS를 재서** 음량을 쓴다.

## 재는 것

1) 마디별 베이스 스템 RMS — 실제로 베이스가 울리는 마디가 어디인가
2) 마디별 우리 악보 음 수 — 위와 비교해 **놓친 구간**을 찾는다
3) 음별 실제 음량(RMS)의 분포 — 두 봉우리인가
4) 확신도와 음량의 상관 — 둘이 다른 값임을 확인
5) 음량 임계별 격자 정렬 — 큰 음만 남기면 한 연주로 수렴하는가

사용:
    python tools/diag/diag_bass_coverage.py data/<hash>
"""

from __future__ import annotations

import argparse
import bisect
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import bassclean, beats as beats_mod, quantize as quantize_mod  # noqa: E402

ODD_SIXTEENTH_MARGIN = 0.125
# 마디 RMS가 곡 최대의 이 비율을 넘으면 "베이스가 울리는 마디"로 본다.
ACTIVE_RATIO = 0.15


def note_loudness(y, sr: int, notes: list) -> list[float]:
    """음 구간의 RMS. 음량이다(확신도와 다르다)."""
    import numpy as np

    out: list[float] = []
    for n in notes:
        a = max(0, int(n.start * sr))
        b = min(len(y), int(max(n.start + 0.02, n.end) * sr))
        seg = y[a:b]
        out.append(float(np.sqrt(np.mean(seg**2))) if len(seg) else 0.0)
    return out


def bar_rms(y, sr: int, bars) -> list[float]:
    import numpy as np

    out = []
    for bar in bars:
        a = max(0, int(bar.start_sec * sr))
        b = min(len(y), int(bar.end_sec * sr))
        seg = y[a:b]
        out.append(float(np.sqrt(np.mean(seg**2))) if len(seg) else 0.0)
    return out


def grid_fit(onsets: list[float], beats: list[float]) -> dict | None:
    if len(beats) < 2 or not onsets:
        return None
    eighth = (0.0, 0.5, 1.0)
    sixteenth = (0.0, 0.25, 0.5, 0.75, 1.0)
    used = on_eighth = needs16 = 0
    for t in onsets:
        i = bisect.bisect_right(beats, t) - 1
        if i < 0 or i + 1 >= len(beats):
            continue
        span = beats[i + 1] - beats[i]
        if span <= 0:
            continue
        pos = (t - beats[i]) / span
        used += 1
        dist8 = min(abs(pos - s) for s in eighth)
        if dist8 <= ODD_SIXTEENTH_MARGIN:
            on_eighth += 1
        near16 = min(sixteenth, key=lambda s: abs(pos - s))
        if near16 in (0.25, 0.75) and dist8 > ODD_SIXTEENTH_MARGIN:
            needs16 += 1
    if not used:
        return None
    return {
        "used": used,
        "eighthRatio": on_eighth / used,
        "needs16Ratio": needs16 / used,
    }


def histogram(values: list[float], bins: int = 12) -> None:
    if not values:
        return
    lo, hi = min(values), max(values)
    width = (hi - lo) / bins if hi > lo else 1.0
    counts = [0] * bins
    for v in values:
        counts[min(bins - 1, int((v - lo) / width))] += 1
    peak = max(counts) or 1
    for k, c in enumerate(counts):
        left = lo + width * k
        print(f"    {left:.4f}~{left + width:.4f}  {c:4d} {'#' * round(40 * c / peak)}")


def main() -> int:
    import librosa
    import numpy as np

    parser = argparse.ArgumentParser(description="베이스 커버리지·음량 진단")
    parser.add_argument("workdir", type=Path)
    args = parser.parse_args()

    notes = bassclean.load_notes(args.workdir / "notes.json")
    grid = beats_mod.BeatGrid.from_json(args.workdir / "beats.json")
    notes.sort(key=lambda n: n.start)
    qscore = quantize_mod.quantize(notes, grid)

    stem = args.workdir / "stems" / "bass.wav"
    y, sr = librosa.load(str(stem), sr=22050, mono=True)

    print(f"=== {args.workdir.name} — 악보 {len(notes)}음, {len(qscore.bars)}마디 ===")

    print()
    print("[1] 마디별 베이스 RMS 대 악보 음 수 — 놓친 구간 찾기")
    rms = bar_rms(y, sr, qscore.bars)
    peak = max(rms) if rms else 1.0
    threshold = peak * ACTIVE_RATIO
    active = [i for i, v in enumerate(rms) if v >= threshold]
    empty_but_active = [
        i for i in active if not qscore.bars[i].notes
    ]
    notes_per_active = [
        len(qscore.bars[i].notes) for i in active if qscore.bars[i].notes
    ]
    print(f"    베이스가 울리는 마디 {len(active)}/{len(rms)} (RMS >= 최대의 {ACTIVE_RATIO:.0%})")
    print(f"    그중 악보가 **비어 있는** 마디 {len(empty_but_active)}개"
          + (f" → {empty_but_active[:20]}" if empty_but_active else ""))
    if notes_per_active:
        print(f"    소리 나는 마디의 음 수: 중앙 {statistics.median(notes_per_active):.1f}, "
              f"최소 {min(notes_per_active)}, 최대 {max(notes_per_active)}")
    silent_with_notes = [
        i for i, v in enumerate(rms) if v < threshold and qscore.bars[i].notes
    ]
    print(f"    소리가 없는데 음이 적힌 마디 {len(silent_with_notes)}개"
          + (f" → {silent_with_notes[:20]}" if silent_with_notes else ""))

    print()
    print("[2] 음별 실제 음량(RMS) 분포 — 두 봉우리인가")
    loud = note_loudness(y, sr, notes)
    print(f"    최소 {min(loud):.4f}  중앙 {statistics.median(loud):.4f}  "
          f"최대 {max(loud):.4f}  표준편차 {statistics.pstdev(loud):.4f}")
    histogram(loud)

    print()
    print("[3] 확신도(Note.amplitude)와 음량의 상관 — 둘은 다른 값이다")
    conf = [n.amplitude for n in notes]
    r = float(np.corrcoef(conf, loud)[0, 1])
    print(f"    상관계수 {r:.4f}")
    print(f"    확신도 중앙 {statistics.median(conf):.4f} (범위 {min(conf):.3f}~{max(conf):.3f})")

    print()
    print("[4] 음량 임계별 격자 정렬 — 큰 음만 남기면 한 연주로 수렴하는가")
    base = grid_fit([n.start for n in notes], grid.beats)
    if base:
        print(f"    임계 없음   {base['used']:4d}음  8분자리 {100 * base['eighthRatio']:5.1f}%  "
              f"16분요구 {100 * base['needs16Ratio']:5.1f}%")
    order = sorted(range(len(notes)), key=lambda i: loud[i])
    for q in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        keep_idx = set(order[int(q * len(order)):])
        kept = [notes[i].start for i in sorted(keep_idx)]
        thr = loud[order[int(q * len(order))]]
        r2 = grid_fit(kept, grid.beats)
        if not r2:
            continue
        print(f"    상위 {100 * (1 - q):3.0f}% (RMS>={thr:.4f})  {r2['used']:4d}음  "
              f"8분자리 {100 * r2['eighthRatio']:5.1f}%  "
              f"16분요구 {100 * r2['needs16Ratio']:5.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

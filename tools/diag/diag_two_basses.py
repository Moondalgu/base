"""베이스가 둘 섞인 입력에서 진폭으로 한쪽을 가를 수 있는지 잰다.

연습 영상은 원곡 음원을 반주로 틀고 그 위에 커버 베이시스트가 연주한다.
Demucs는 두 베이스를 하나의 스템으로 합치므로, 채보하면 두 연주가 섞인다.
사용자가 배우려는 것은 **커버 파트**이고 그쪽이 더 크게 녹음돼 있을 것이라는
가설이 있다. 그러면 진폭으로 가를 수 있다.

추측으로 정하지 않고 세 가지를 잰다.

1) **진폭 분포가 두 봉우리인가.** 두 연주가 섞였고 한쪽이 일관되게 크다면
   봉우리가 둘이어야 한다. 하나면 진폭으로는 못 가른다.
2) **같은 피치가 짧은 간격으로 겹쳐 나오는 쌍이 있는가.** 두 사람이 같은
   근음을 조금 다른 타점에 치면 그런 쌍이 생긴다. 쌍 안의 진폭 비율이
   한쪽으로 쏠려 있으면(늘 앞이 크거나 늘 뒤가 크면) 가를 단서가 된다.
3) **진폭 임계로 약한 음을 버리면 격자 정렬이 좋아지는가.** 이것이 결정적
   근거다. 남은 온셋이 한 사람의 연주라면 박·8분 자리에 훨씬 잘 걸려야 한다.
   섞인 상태에서는 8분 자리 비율이 44.7%인데, 정상 곡은 90%를 넘는다.

사용:
    python tools/diag/diag_two_basses.py data/<hash>
"""

from __future__ import annotations

import argparse
import bisect
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import bassclean, beats as beats_mod  # noqa: E402

# 홀수 16분에 얹혔다고 인정하는 여유(박 단위). eval/eval_grid_resolution.py와 같다.
ODD_SIXTEENTH_MARGIN = 0.125

# 같은 피치가 이 간격(초) 안에 다시 나오면 "두 사람이 같은 음을 쳤을" 후보 쌍이다.
# 75BPM 16분음표가 0.2초다.
PAIR_WINDOW_SEC = 0.2


def grid_fit(onsets: list[float], beats: list[float]) -> dict | None:
    """온셋이 박·8분·16분 자리에 얼마나 걸리는지."""
    if len(beats) < 2 or not onsets:
        return None
    eighth = (0.0, 0.5, 1.0)
    sixteenth = (0.0, 0.25, 0.5, 0.75, 1.0)
    used = 0
    on_eighth = 0
    needs16 = 0
    d8: list[float] = []
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
        d8.append(dist8)
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
        "residual8": statistics.fmean(d8) / 0.5,
    }


def histogram(values: list[float], bins: int = 10) -> None:
    if not values:
        return
    lo, hi = min(values), max(values)
    width = (hi - lo) / bins if hi > lo else 1.0
    counts = [0] * bins
    for v in values:
        k = min(bins - 1, int((v - lo) / width))
        counts[k] += 1
    peak = max(counts) or 1
    for k, c in enumerate(counts):
        left = lo + width * k
        bar = "#" * round(40 * c / peak)
        print(f"    {left:.3f}~{left + width:.3f}  {c:4d} {bar}")


def main() -> int:
    parser = argparse.ArgumentParser(description="두 베이스 판별 기준 측정")
    parser.add_argument("workdir", type=Path, help="data/<hash>")
    args = parser.parse_args()

    notes = bassclean.load_notes(args.workdir / "notes.json")
    grid = beats_mod.BeatGrid.from_json(args.workdir / "beats.json")
    notes.sort(key=lambda n: n.start)
    amps = [n.amplitude for n in notes]

    print(f"=== {args.workdir.name} — {len(notes)}음 ===")
    print()
    print("[1] 진폭 분포 (봉우리가 둘이어야 진폭으로 가를 수 있다)")
    print(f"    최소 {min(amps):.3f}  중앙 {statistics.median(amps):.3f}  최대 {max(amps):.3f}  "
          f"표준편차 {statistics.pstdev(amps):.3f}")
    histogram(amps)

    print()
    print(f"[2] 같은 피치가 {PAIR_WINDOW_SEC}초 안에 다시 나오는 쌍")
    pairs = []
    for a, b in zip(notes, notes[1:]):
        if a.pitch == b.pitch and 0 < (b.start - a.start) <= PAIR_WINDOW_SEC:
            pairs.append((a, b))
    print(f"    쌍 {len(pairs)}개 / 인접 {len(notes) - 1}쌍 ({100 * len(pairs) / max(1, len(notes) - 1):.1f}%)")
    if pairs:
        ratios = [b.amplitude / a.amplitude for a, b in pairs if a.amplitude > 0]
        louder_second = sum(1 for r in ratios if r > 1.0)
        gaps = [b.start - a.start for a, b in pairs]
        print(f"    진폭비(뒤/앞) 중앙 {statistics.median(ratios):.2f}  "
              f"뒤가 더 큼 {louder_second}/{len(ratios)}건")
        print(f"    간격 중앙 {statistics.median(gaps) * 1000:.0f}ms  "
              f"최소 {min(gaps) * 1000:.0f}ms  최대 {max(gaps) * 1000:.0f}ms")
        print("    → 한쪽으로 쏠리지 않으면(50% 근처) 순서로는 못 가른다")

    print()
    print("[3] 진폭 임계별 격자 정렬 — 결정적 근거")
    print("    (8분자리 = 박 또는 8분 위치에 걸린 온셋 비율. 정상 곡은 90% 이상)")
    base = grid_fit([n.start for n in notes], grid.beats)
    if base:
        print(f"    임계 없음   {base['used']:4d}음  8분자리 {100 * base['eighthRatio']:5.1f}%  "
              f"8분잔차 {base['residual8']:.3f}  16분요구 {100 * base['needs16Ratio']:5.1f}%")
    quantiles = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    ordered = sorted(amps)
    for q in quantiles:
        thr = ordered[int(q * len(ordered))]
        kept = [n.start for n in notes if n.amplitude >= thr]
        r = grid_fit(kept, grid.beats)
        if not r:
            continue
        print(f"    상위 {100 * (1 - q):3.0f}% (amp≥{thr:.3f})  {r['used']:4d}음  "
              f"8분자리 {100 * r['eighthRatio']:5.1f}%  8분잔차 {r['residual8']:.3f}  "
              f"16분요구 {100 * r['needs16Ratio']:5.1f}%")

    print()
    print("    판정: 임계를 올려도 8분자리 비율이 오르지 않으면 진폭으로는 못 가른다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

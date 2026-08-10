"""같은 곡의 두 녹음을 마디 단위로 대조한다.

용도: "원곡" 대 "그 위에 연주한 연습 영상"처럼 **같은 곡·다른 녹음**의 채보를
나란히 놓고, 두 베이스가 섞인 입력이 실제로 무엇을 망가뜨리는지 정량화한다.
Songsterr 정답이 없어도 성립한다 — 한쪽(깨끗한 원곡)을 기준으로 삼는다.

주의: 두 녹음은 템포도 마디 수도 다를 수 있다. 마디 오프셋을 근음 일치
기준으로 스캔해서 맞춘 뒤 비교한다(eval_songsterr와 같은 방식). 이조도
스캔한다 — 커버가 키를 옮겨 불렀을 수 있다.

사용:
    python tools/diag/compare_two_takes.py data/<기준hash> data/<비교hash>
    python tools/diag/compare_two_takes.py ... --labels 원곡 연습영상
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(ROOT / "eval"))

from eval_video_bars import our_bars  # noqa: E402

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def load_bars(workdir: Path) -> dict[int, dict]:
    manifest = json.loads((workdir / "manifest.json").read_text(encoding="utf-8"))
    tex = (workdir / "score.alphatex").read_text(encoding="utf-8")
    return our_bars(tex, manifest.get("subdivision", 4))


def main_pitch(bar: dict, tuning=(28, 33, 38, 43)) -> int | None:
    """마디의 대표 근음 피치클래스 — 최저음 기준(베이스는 근음을 밑에 둔다)."""
    pitches = [
        tuning[s - 1] + f
        for s, f in bar["attacks"]
        if f is not None and 1 <= s <= len(tuning)
    ]
    return min(pitches) % 12 if pitches else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base", type=Path, help="기준 (예: 깨끗한 원곡)")
    ap.add_argument("other", type=Path, help="비교 (예: 두 베이스 섞인 연습 영상)")
    ap.add_argument("--labels", nargs=2, default=["기준", "비교"])
    args = ap.parse_args()

    a, b = load_bars(args.base), load_bars(args.other)
    la, lb = args.labels

    # 마디 오프셋·이조 스캔 — 근음 일치가 가장 높은 조합
    best = (-1, 0, 0)   # (일치 수, 오프셋, 이조)
    for off in range(-8, 9):
        for tr in range(12):
            hit = 0
            for n, bar in a.items():
                pa, ob = main_pitch(bar), b.get(n + off)
                if pa is None or ob is None:
                    continue
                pb = main_pitch(ob)
                if pb is not None and (pa + tr) % 12 == pb:
                    hit += 1
            if hit > best[0]:
                best = (hit, off, tr)
    _, off, tr = best

    rows = []
    for n in sorted(a):
        bar_a, bar_b = a[n], b.get(n + off)
        if bar_b is None:
            continue
        pa, pb = main_pitch(bar_a), main_pitch(bar_b)
        na, nb = len(bar_a["attacks"]), len(bar_b["attacks"])
        rows.append((n, pa, pb, na, nb))

    if not rows:
        print("겹치는 마디가 없다 — 오프셋 범위를 넓히거나 입력을 확인할 것")
        return 1

    both = [r for r in rows if r[1] is not None and r[2] is not None]
    same_pitch = sum(1 for _, pa, pb, _, _ in both if (pa + tr) % 12 == pb)
    same_att = sum(1 for _, _, _, na, nb in rows if na == nb)
    only_a = sum(1 for _, pa, pb, _, _ in rows if pa is not None and pb is None)
    only_b = sum(1 for _, pa, pb, _, _ in rows if pa is None and pb is not None)
    diff = [nb - na for _, _, _, na, nb in rows]

    print(f"=== {la} ↔ {lb} (마디 오프셋 {off:+d}, 이조 {tr if tr <= 6 else tr - 12:+d}반음) ===")
    print(f"겹친 마디 {len(rows)} | 양쪽에 음 있는 마디 {len(both)}")
    print(f"  근음 일치     {same_pitch}/{len(both)} ({same_pitch / max(len(both), 1):.0%})")
    print(f"  타현 수 일치  {same_att}/{len(rows)} ({same_att / max(len(rows), 1):.0%})")
    print(f"  타현 수 차이  평균 {sum(diff) / len(diff):+.2f}  "
          f"({lb}가 더 많은 마디 {sum(1 for d in diff if d > 0)}, "
          f"적은 마디 {sum(1 for d in diff if d < 0)})")
    print(f"  한쪽만 음 있음: {la}만 {only_a}마디, {lb}만 {only_b}마디")

    print(f"\n마디별 (근음·타현) — 다른 곳만")
    print(f"{'마디':>4} {la[:8]:>12} {lb[:8]:>12}   비고")
    shown = 0
    for n, pa, pb, na, nb in rows:
        pitch_ok = (pa is not None and pb is not None and (pa + tr) % 12 == pb)
        if pitch_ok and na == nb:
            continue
        sa = f"{NAMES[pa] if pa is not None else '-':>3}/{na:<2}"
        sb = f"{NAMES[pb] if pb is not None else '-':>3}/{nb:<2}"
        why = []
        if not pitch_ok and pa is not None and pb is not None:
            why.append("근음 다름")
        if na != nb:
            why.append(f"타현 {nb - na:+d}")
        print(f"{n:>4} {sa:>12} {sb:>12}   {' · '.join(why)}")
        shown += 1
        if shown >= 40:
            print("   … (이하 생략)")
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

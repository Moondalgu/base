"""Songsterr 사람 채보와 우리 산출물을 마디별로 대조한다.

## 두 가지를 먼저 맞춘다 — 마디 오프셋과 **이조**

### 이조

**유튜브 음원이 악보와 다른 키일 수 있다.** 실측: Queen "Another One Bites the
Dust" 공식 뮤비 음원은 악보(Em)보다 **정확히 반음 높다**(Fm). 우리 검출은 그
음원에 대해 맞는데, 이조를 모르고 대조하면 자리 일치가 5%로 나온다 —
**파이프라인 실패로 오해하게 된다.**

그래서 12개 이조를 다 대보고 피치클래스 분포 상관이 가장 높은 값을 찾는다.
Queen에서 +1반음일 때 상관 0.905, 0반음일 때 −0.192로 갈린다.

## 마디 정렬

Songsterr의 1마디와 우리 1마디가 같은 자리라는 보장이 없다. 인트로 무음 길이,
비트 추적의 위상, 픽업 마디가 다 영향을 준다. **오프셋을 모르고 정확도를 재면
0%가 나오고, 그것을 검출 실패로 오해한다.**

그래서 오프셋을 −8~+8 범위에서 훑어 **자리(현·프렛) 일치가 최대가 되는 값**을
찾아 함께 보고한다. 오프셋이 크거나 최대 일치가 낮으면 정확도가 아니라 **정렬을
먼저 봐야 한다**는 신호다.

## 무엇을 재는가

`eval_video_bars.py`와 같은 두 축이다.

- **자리** — 그 마디에서 주로 짚는 (현, 프렛)
- **타현 수** — 실제로 뜯는 횟수. 타이는 세지 않는다

여기에 하나 더:

- **구간별** — Songsterr의 섹션 마커로 나눠 본다. 벌스와 코러스의 정확도가
  다르다는 것을 이미 알고 있고(반복 85% 대 비반복 25%), 섹션 이름이 있으면
  그것을 곡 구조 이름으로 말할 수 있다

## 한계

사람 채보도 해석이다. 특히 고스트 노트와 타이는 적는 사람마다 다르다. 이 대조는
"정답과 얼마나 같은가"가 아니라 **"사람이 적은 것과 얼마나 같은가"**다.

사용:
    python eval/eval_songsterr.py data/<hash> eval/golden/songsterr_<이름>.json
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_video_bars import our_bars  # noqa: E402

# 마디 오프셋 탐색 범위. 이보다 크게 어긋나면 정렬 문제가 아니라
# 다른 곡이거나 비트 추적이 실패한 것이다.
OFFSET_RANGE = range(-8, 9)

# 이조를 채택하려면 최적 이조의 상관이 0반음 상관보다 이만큼 커야 한다.
# 실측 근거 (2026-08-08): 진짜 이조(Queen +1반음)는 차이가 1.097
# (0.905 대 −0.192)이고, 가짜 이조(Come Together +7)는 0.085(0.727 대
# 0.642)였다. 가짜 +7은 리프의 5도(A)·슬라이드 부속음(C#)이 피치클래스
# 분포를 오염시킨 것으로, 서브하모닉 측정(diag_subharmonic.py)에서 배음
# 오인 0%로 반증됐다. 두 군 사이 어디든 되지만 여유 있게 중간에 둔다.
MIN_TRANSPOSE_MARGIN = 0.3


TUNING = [43, 38, 33, 28]      # 1현~4현. 우리 standard.


def comparable_tuning(golden: dict) -> bool:
    """이 정답으로 **자리(현·프렛)**를 비교할 수 있는가.

    Songsterr에는 같은 곡 탭이 여럿이고 튜닝이 다르다. 튜닝이 다르면 같은 음도
    프렛 번호가 통째로 달라지므로 자리 비교가 성립하지 않는다 — 그런데 이
    도구는 튜닝을 안 보고 비교해서 **일치 0%를 "우리가 다 틀렸다"로 보고했다**
    (HTH 커버 0/47, 정답은 E♭탭 [42,37,32,27]). 피치클래스는 여전히 유효하다.

    튜닝이 안 적힌 옛 정답 파일은 우리 standard로 본다.
    """
    return list(golden.get("tuning") or TUNING) == TUNING


def pitch_of(string: int, fret: int) -> int:
    return TUNING[string - 1] + fret


def find_transpose(ours: dict, golden: list[dict]) -> tuple[int, float]:
    """음원이 악보와 몇 반음 차이 나는가. (반음, 상관).

    피치클래스 분포의 상관으로 찾는다. 마디 정렬과 무관하게 계산되므로
    오프셋 탐색보다 **먼저** 해야 한다 — 이조가 틀리면 어떤 오프셋에서도
    자리가 안 맞아 오프셋 탐색이 무의미해진다.
    """
    o = [0.0] * 12
    t = [0.0] * 12
    for bar in ours.values():
        for string, fret in bar["attacks"]:
            o[pitch_of(string, fret) % 12] += 1
    for row in golden:
        if row.get("pitch") is not None:
            t[row["pitch"] % 12] += row["attacks"]
    if not sum(o) or not sum(t):
        return 0, 0.0
    o = [x / sum(o) for x in o]
    t = [x / sum(t) for x in t]

    def corr(a: list[float], b: list[float]) -> float:
        ma, mb = sum(a) / 12, sum(b) / 12
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        da = sum((x - ma) ** 2 for x in a) ** 0.5
        db = sum((y - mb) ** 2 for y in b) ** 0.5
        return num / (da * db) if da * db else 0.0

    scored = [(corr([o[(i + k) % 12] for i in range(12)], t), k) for k in range(12)]
    best, k = max(scored)
    base = next(c for c, kk in scored if kk == 0)
    # 최적이 0반음을 크게 이기지 못하면 이조가 아니다 — 검출 편향(5도·경과음)이
    # 만든 가짜 상관일 수 있다. 그때는 이조 없음으로 두고 자리 비교를 유지한다.
    if k != 0 and best - base < MIN_TRANSPOSE_MARGIN:
        return 0, base
    return k, best


def score_at(
    ours: dict, golden: list[dict], offset: int, transpose: int = 0,
    *, compare_place: bool = True,
) -> tuple[int, int, int, int]:
    """오프셋·이조를 적용해 (자리 일치, 피치클래스 일치, 타현 일치, 비교 마디 수).

    자리(현·프렛)와 피치클래스를 **둘 다** 센다. 자리는 운지 선택이 다르면
    같은 음도 틀리다고 보므로(같은 D2가 A현 5프렛일 수도 E현 10프렛일 수도),
    "맞는 음을 냈는가"는 피치클래스가 답한다. 이조가 있으면 자리 비교는
    성립하지 않으므로 피치클래스만 유효하다.
    """
    place = pc = attack = compared = 0
    for row in golden:
        if row.get("string") is None:
            continue                    # 쉬는 마디는 비교 대상이 아니다
        got = ours.get(row["bar"] + offset)
        if not got:
            continue
        compared += 1
        places = got["attacks"]
        if places:
            main = max(set(places), key=places.count)
            want = (row["pitch"] + transpose) % 12
            pc += pitch_of(*main) % 12 == want
            if not transpose and compare_place:
                place += main == (row["string"], row["fret"])
        attack += len(places) == row["attacks"]
    return place, pc, attack, compared


def main() -> int:
    ap = argparse.ArgumentParser(description="Songsterr 사람 채보와 마디별 대조")
    ap.add_argument("workdir", type=Path)
    ap.add_argument("golden", type=Path)
    ap.add_argument("--offset", type=int, help="마디 오프셋을 직접 지정")
    args = ap.parse_args()

    manifest = json.loads((args.workdir / "manifest.json").read_text(encoding="utf-8"))
    tex = (args.workdir / "score.alphatex").read_text(encoding="utf-8")
    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    bars = golden["bars"]

    ours = our_bars(tex, manifest.get("subdivision", 4))
    played = [b for b in bars if b.get("string") is not None]
    place_ok = comparable_tuning(golden)

    print(f"=== {args.golden.name} ===")
    print(f"정답 {len(bars)}마디 (연주 {len(played)}마디) / 우리 {len(ours)}마디")

    transpose, quality = find_transpose(ours, bars)
    if transpose:
        print(f"**음원이 악보와 {transpose:+d}반음 차이** (피치클래스 상관 {quality:.3f})")
        print("   자리 비교를 피치클래스 비교로 바꾼다 — 이조되면 짚는 자리가 달라진다")
    else:
        print(f"이조 차이 없음 (피치클래스 상관 {quality:.3f})")
    if not place_ok:
        print(f"**정답 탭 튜닝 {golden['tuning']} ≠ 우리 {TUNING}** — 자리 비교를 건너뛴다")
        print("   같은 음도 프렛 번호가 통째로 달라진다. 피치클래스는 유효하다")

    if args.offset is not None:
        offset = args.offset
    else:
        # 피치클래스 일치가 최대가 되는 오프셋. 타현 수는 흔들리지만
        # 피치는 코드 진행이라 정렬 신호로 더 안정적이고, 자리보다
        # 운지 선택 차이에 강건하다.
        best = max(
            OFFSET_RANGE,
            key=lambda o: (lambda r: (r[1], r[3]))(
                score_at(ours, bars, o, transpose, compare_place=place_ok)
            ),
        )
        offset = best
        scores = [
            (o,) + score_at(ours, bars, o, transpose, compare_place=place_ok)
            for o in OFFSET_RANGE
        ]
        top = sorted(scores, key=lambda s: -s[2])[:3]
        print("최적 마디 오프셋 탐색 (피치클래스 일치 기준):")
        for o, p, q, a, c in top:
            print(f"  오프셋 {o:+3d}: 자리 {p:3}/{c:<3} 피치클래스 {q:3}/{c:<3} 타현 {a:3}/{c}")

    place, pc, attack, compared = score_at(
        ours, bars, offset, transpose, compare_place=place_ok
    )
    if not compared:
        print("\n[실패] 비교할 마디가 없다. 마디 수나 오프셋을 확인하라.")
        return 1

    print(f"\n오프셋 {offset:+d} 적용")
    if not transpose and place_ok:
        print(f"  자리(현·프렛) {place}/{compared} ({place / compared:.0%})")
    print(f"  피치클래스    {pc}/{compared} ({pc / compared:.0%})")
    print(f"  타현 수       {attack}/{compared} ({attack / compared:.0%})")

    # 섹션별
    section_of: dict[int, str] = {}
    for sec in golden.get("sections") or []:
        for b in range(sec["startBar"], sec["startBar"] + sec["bars"]):
            section_of[b] = sec["name"]
    if section_of:
        buckets: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
        for row in played:
            got = ours.get(row["bar"] + offset)
            if not got:
                continue
            places = got["attacks"]
            main = max(set(places), key=places.count) if places else None
            if main is None:
                hit = False
            elif transpose:
                hit = pitch_of(*main) % 12 == (row["pitch"] + transpose) % 12
            else:
                hit = main == (row["string"], row["fret"])
            buckets[section_of.get(row["bar"], "?")].append((
                hit,
                len(places) == row["attacks"],
            ))
        print("\n섹션별:")
        print(f"  {'섹션':18} {'마디':>4} {'자리':>8} {'타현':>8}")
        for name, rows in buckets.items():
            n = len(rows)
            print(f"  {name:18} {n:>4} "
                  f"{sum(r[0] for r in rows) / n:8.0%} "
                  f"{sum(r[1] for r in rows) / n:8.0%}")

    errs = []
    for row in played:
        got = ours.get(row["bar"] + offset)
        if got:
            errs.append(abs(len(got["attacks"]) - row["attacks"]))
    if errs:
        print(f"\n타현 수 평균 오차 {st.fmean(errs):.2f}")

    key = manifest.get("key") or {}
    if key:
        print(f"조성 검출: {key.get('name')} "
              f"(조표 {key.get('signatureName')}, 확신도 {key.get('confidence')}, "
              f"신뢰 {key.get('trusted')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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


TUNING = [43, 38, 33, 28]      # 1현~4현. Songsterr와 우리가 같다.


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
    return k, best


def score_at(
    ours: dict, golden: list[dict], offset: int, transpose: int = 0
) -> tuple[int, int, int]:
    """오프셋·이조를 적용해 (자리 일치, 타현 일치, 비교한 마디 수).

    이조가 있으면 **자리(현·프렛)를 그대로 비교할 수 없다.** 같은 음이라도
    다른 자리에서 나기 때문이다. 그때는 피치클래스로 비교한다 — 우리가 그
    음을 어디서 짚는지가 아니라 **맞는 음을 냈는지**를 묻는 것이다.
    """
    place = attack = compared = 0
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
            if transpose:
                want = (row["pitch"] + transpose) % 12
                place += pitch_of(*main) % 12 == want
            else:
                place += main == (row["string"], row["fret"])
        attack += len(places) == row["attacks"]
    return place, attack, compared


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

    print(f"=== {args.golden.name} ===")
    print(f"정답 {len(bars)}마디 (연주 {len(played)}마디) / 우리 {len(ours)}마디")

    transpose, quality = find_transpose(ours, bars)
    if transpose:
        print(f"**음원이 악보와 {transpose:+d}반음 차이** (피치클래스 상관 {quality:.3f})")
        print("   자리 비교를 피치클래스 비교로 바꾼다 — 이조되면 짚는 자리가 달라진다")
    else:
        print(f"이조 차이 없음 (피치클래스 상관 {quality:.3f})")

    if args.offset is not None:
        offset = args.offset
    else:
        # 자리 일치가 최대가 되는 오프셋. 타현 수는 흔들리지만 자리는
        # 코드 진행이라 정렬 신호로 더 안정적이다.
        best = max(
            OFFSET_RANGE,
            key=lambda o: (lambda r: (r[0], r[2]))(
                score_at(ours, bars, o, transpose)
            ),
        )
        offset = best
        scores = [(o,) + score_at(ours, bars, o, transpose) for o in OFFSET_RANGE]
        top = sorted(scores, key=lambda s: -s[1])[:3]
        print("최적 마디 오프셋 탐색 (자리 일치 기준):")
        for o, p, a, c in top:
            print(f"  오프셋 {o:+3d}: 자리 {p:3}/{c:<3} 타현 {a:3}/{c}")

    place, attack, compared = score_at(ours, bars, offset, transpose)
    if not compared:
        print("\n[실패] 비교할 마디가 없다. 마디 수나 오프셋을 확인하라.")
        return 1

    print(f"\n오프셋 {offset:+d} 적용")
    print(f"  자리(현·프렛) {place}/{compared} ({place / compared:.0%})")
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

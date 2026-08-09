"""드럼 킥/스네어/햇 분류 채점 — Songsterr 드럼 탭(사람 채보)이 정답.

사용: .venv/Scripts/python.exe eval/eval_drums.py [--offset N] [--lo X --mid Y]

Queen AOBTD(528aa2e6986aa42a) 드럼 스템의 온셋 분류를 골든
(eval/golden/songsterr_queen_drums_raw.json, GM 퍼커션: 36=킥 38=스네어
42/46=햇)과 마디×8분 슬롯 단위로 대조한다. 좌표는 **악보(ledger)
barStarts** — beats.json 다운비트는 위상 보정 전이라 쓰면 안 된다(실측).
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HASH = "528aa2e6986aa42a"

KICK = {35, 36}
SNARE = {38, 40, 37}
HAT = {42, 44, 46, 49, 51, 52, 53, 55, 57, 59}


def golden_grid() -> dict[tuple[int, int], set[str]]:
    """{(마디0-, 슬롯0-7): {"K","S","H"}} — 골든 드럼 탭에서."""
    d = json.loads((ROOT / "eval/golden/songsterr_queen_drums_raw.json")
                   .read_text(encoding="utf-8"))
    out: dict[tuple[int, int], set[str]] = {}
    for mi, m in enumerate(d["measures"]):
        pos = 0.0  # 마디 안 위치(온음표=1)
        for beat in (m.get("voices") or [{}])[0].get("beats", []):
            slot = round(pos * 8)
            for n in beat.get("notes") or []:
                f = n.get("fret")
                cell = out.setdefault((mi, slot), set())
                if f in KICK:
                    cell.add("K")
                elif f in SNARE:
                    cell.add("S")
                elif f in HAT:
                    cell.add("H")
            # duration = [분자, 분모] — [1, 8] = 8분음표 (실측: 뒤집으면 슬롯 64·128대로 폭발)
            dur = beat.get("duration") or [1, 8]
            pos += dur[0] / dur[1] if isinstance(dur, list) else 1 / 8
    return out


def our_events():
    """드럼 스템 온셋 → (시각, 분류). **프로덕션 경로(pipeline.drums.detect)
    그대로** 채점한다 — 여기 복사본을 두면 상수(LO_RATIO 등)가 어긋난 걸
    채점하게 된다(실측: 복사본 기본값이 킥 F1 0.74, 실제 상수는 0.785)."""
    import sys

    sys.path.insert(0, str(ROOT / "apps" / "worker"))
    from pipeline import drums

    raw = drums.detect(ROOT / f"data/{HASH}/stems/drums.wav")
    return [(e["t"], set(e["labels"])) for e in raw]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offset", type=int, default=None,
                    help="골든 마디 - 우리 마디 오프셋(자동 탐색 생략)")
    args = ap.parse_args()

    led = json.loads(urllib.request.urlopen(
        f"http://localhost:8000/api/scores/{HASH}/ledger.json?level=3",
        timeout=120).read())
    starts, ends = led["barStarts"], led["barEnds"]
    gold = golden_grid()
    events = our_events()

    # 우리 이벤트 → (우리 마디0-, 슬롯)
    ours: dict[tuple[int, int], set[str]] = {}
    for t, labels in events:
        i = int(np.searchsorted(starts, t)) - 1
        if i < 0 or i + 1 >= len(starts):
            continue
        span = ends[i] - starts[i]
        slot = round((t - starts[i]) / span * 8)
        if slot >= 8:
            i, slot = i + 1, 0
        ours.setdefault((i, slot), set()).update(labels)

    def score(off: int) -> tuple[float, dict]:
        stats = {k: [0, 0, 0] for k in "KSH"}  # [hit, gold_n, ours_n]
        for (gm, slot), gl in gold.items():
            om = gm - off
            ol = ours.get((om, slot), set())
            for k in "KSH":
                if k in gl:
                    stats[k][1] += 1
                    if k in ol:
                        stats[k][0] += 1
        for (om, slot), ol in ours.items():
            for k in "KSH":
                if k in ol:
                    stats[k][2] += 1
        f1s = {}
        for k, (hit, gn, on) in stats.items():
            p = hit / on if on else 0
            r = hit / gn if gn else 0
            f1s[k] = 2 * p * r / (p + r) if p + r else 0
        return (f1s["K"] + f1s["S"]) / 2, {k: round(v, 3) for k, v in f1s.items()}

    if args.offset is not None:
        offsets = [args.offset]
    else:
        offsets = range(-4, 5)
    best = max(offsets, key=lambda o: score(o)[0])
    val, f1s = score(best)
    print(f"[드럼 채점] 오프셋 {best}: F1 킥 {f1s['K']}, 스네어 {f1s['S']}, "
          f"햇 {f1s['H']} (킥·스네어 평균 {val:.3f})")


if __name__ == "__main__":
    main()

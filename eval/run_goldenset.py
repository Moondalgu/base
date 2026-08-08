"""골든셋 일괄 회귀 — 6곡을 한 번에 재고 표로 낸다.

파이프라인을 고칠 때마다 이것을 돌린다. 곡 하나로 보면 과적합을 못 잡는다
(16마디 100% → 59마디 63% 전례). 피치클래스가 3%p 이상 떨어지면 회귀다.

`--level 2`를 주면 각 곡의 Lv2(하향) 악보를 그 자리에서 만들어 같은 정답과
대조한다. Lv2는 마디당 근음만 남으므로 **피치클래스 = 근음 정확도**가 된다
(LVL-09 레벨별 품질의 측정 경로).

사용:
    .venv/Scripts/python.exe eval/run_goldenset.py
    .venv/Scripts/python.exe eval/run_goldenset.py --level 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_songsterr import find_transpose, score_at, OFFSET_RANGE  # noqa: E402
from eval_video_bars import our_bars  # noqa: E402

# (이름, data 해시, 정답 파일). SET.md의 곡 목록과 일치해야 한다.
SONGS = [
    ("Champagne(커버영상)", "975e4e588d282666", "songsterr_champagne_bass.json"),
    ("Queen AOBTD", "528aa2e6986aa42a", "songsterr_queen_aobtd.json"),
    ("Come Together", "78d6e3fc12388629", "songsterr_beatles_come_together.json"),
    ("Virtual Insanity", "d4fd7b689b9db1bb", "songsterr_jamiroquai_virtual_insanity.json"),
    ("Drowning", "65ef1cf020561a5c", "songsterr_woodz_drowning.json"),
    ("예뻤어", "8181e1aa7d7a0be1", "songsterr_day6_ywb.json"),
]


def eval_one(workdir: Path, golden_path: Path, tex: str | None = None) -> dict | None:
    manifest = json.loads((workdir / "manifest.json").read_text(encoding="utf-8"))
    if tex is None:
        tex = (workdir / "score.alphatex").read_text(encoding="utf-8")
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    bars = golden["bars"]

    ours = our_bars(tex, manifest.get("subdivision", 4))
    transpose, corr = find_transpose(ours, bars)
    offset = max(
        OFFSET_RANGE,
        key=lambda o: (lambda r: (r[1], r[3]))(score_at(ours, bars, o, transpose)),
    )
    place, pc, attack, compared = score_at(ours, bars, offset, transpose)
    if not compared:
        return None
    return {
        "transpose": transpose,
        "corr": corr,
        "offset": offset,
        "place": place / compared,
        "pc": pc / compared,
        "attack": attack / compared,
        "compared": compared,
        "engine": manifest.get("engine", "?"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="골든셋 일괄 회귀")
    ap.add_argument("--level", type=int, help="하향 레벨 악보를 만들어 대조 (예: 2)")
    args = ap.parse_args()

    if args.level:
        import jobs  # 변형 생성은 웹과 같은 경로를 쓴다

    rows = []
    for name, h, golden in SONGS:
        workdir = ROOT / "data" / h
        gpath = ROOT / "eval" / "golden" / golden
        if not workdir.exists() or not gpath.exists():
            rows.append((name, None, "데이터 없음"))
            continue
        tex = None
        if args.level:
            try:
                tex = jobs.build_score_variant(h, level=args.level).tex
            except Exception as exc:  # noqa: BLE001
                rows.append((name, None, f"변형 실패: {type(exc).__name__}"))
                continue
        r = eval_one(workdir, gpath, tex)
        rows.append((name, r, ""))

    title = f"Lv{args.level}" if args.level else "원곡(Lv5)"
    print(f"=== 골든셋 {len(rows)}곡 — {title} ===")
    print(f"{'곡':<20} {'이조':>4} {'오프셋':>4} {'피치클래스':>8} {'자리':>6} {'타현':>6} {'마디':>5} {'엔진':>12}")
    for name, r, err in rows:
        if r is None:
            print(f"{name:<20} {err}")
            continue
        print(
            f"{name:<20} {r['transpose']:>+4d} {r['offset']:>+4d} "
            f"{r['pc']:>7.0%} {r['place']:>6.0%} {r['attack']:>6.0%} "
            f"{r['compared']:>5} {r['engine']:>12}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

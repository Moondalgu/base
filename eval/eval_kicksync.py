"""킥 동기화 평가 — 실곡 정답 59마디로 잰다.

## IDMT로는 못 잰다

IDMT는 **베이스 단독 녹음**이라 드럼이 없다. 킥 동기화는 정의상 드럼 스템을
쓰므로 IDMT에서 검증할 수 없다. 이 프로젝트에서 "IDMT와 실곡 둘 다 본다"는
규칙을 지키지 못하는 드문 경우이고, 그래서 **결과를 한 곡 기준으로만 읽어야
한다.** 골든셋이 늘어나면 그때 다시 잰다(`eval/golden/SET.md`).

## 무엇을 재는가

`playing.json` kickLock이 말하는 **락 비율(킥 중 베이스 온셋이 함께 있는 비율)을
먼저 실측한다.** 문헌값은 80%다. 우리 곡에서 그 값이 나오지 않으면 킥 동기화를
걸 전제 자체가 성립하지 않는다 — 그것을 확인하지 않고 문턱만 훑으면 근거 없는
값을 고르게 된다.

그다음 마디별 타현 일치를 기준선과 비교한다.

사용:
    python eval/eval_kicksync.py
    python eval/eval_kicksync.py --sweep
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import (  # noqa: E402
    bassclean, beats as beats_mod, inertia, kicksync, quantize,
)

SONG = ROOT / "data" / "975e4e588d282666"


def load_gold() -> dict[int, int]:
    gold: dict[int, int] = {}
    for name in ("champagne_video_bars25_40", "champagne_video_bars41_99"):
        data = json.loads(
            (ROOT / "eval" / "golden" / f"{name}.json").read_text(encoding="utf-8")
        )
        for row in data["bars"]:
            gold[row["ourBar"]] = row["attacks"]
    return gold


def run(gold: dict[int, int], *, enabled: bool, **kw) -> dict:
    grid = beats_mod.BeatGrid.from_json(SONG / "beats.json")
    notes = bassclean.load_notes(SONG / "notes_raw.json")
    bassclean.measure_loudness(notes, SONG / "stems" / "bass.wav")

    report = kicksync.KickReport()
    if enabled:
        notes, report = kicksync.revive_missing(
            notes,
            SONG / "stems" / "drums.wav",
            SONG / "stems" / "bass.wav",
            min_lock=kw.get("min_lock", 0.5),
            energy_ratio=kw.get("energy_ratio", 0.5),
        )

    gated, _ = bassclean.gate_by_loudness(
        notes, grid.beats, beats_per_bar=grid.beats_per_bar
    )
    qs = quantize.quantize(gated, grid)
    qs, _ = inertia.apply_inertia(qs)
    counts = {i + 1: len(b.notes) for i, b in enumerate(qs.bars)}

    rep_bars = [b for b, a in gold.items() if a == 3]
    non_bars = [b for b, a in gold.items() if a != 3]
    return {
        "repOk": sum(1 for b in rep_bars if counts.get(b, 0) == gold[b]),
        "repTotal": len(rep_bars),
        "nonOk": sum(1 for b in non_bars if counts.get(b, 0) == gold[b]),
        "nonTotal": len(non_bars),
        "allOk": sum(1 for b, a in gold.items() if counts.get(b, 0) == a),
        "allTotal": len(gold),
        "err": st.fmean(abs(counts.get(b, 0) - a) for b, a in gold.items()),
        "notes": len(gated),
        "kick": report,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="킥 동기화 평가")
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()

    gold = load_gold()

    # 전제 확인부터. 락 비율이 낮으면 문턱을 훑을 이유가 없다.
    kicks = kicksync.detect_kicks(SONG / "stems" / "drums.wav")
    notes = bassclean.load_notes(SONG / "notes_raw.json")
    lock = kicksync.measure_lock([n.start for n in notes], kicks)
    print(f"킥 {len(kicks)}개 검출, 락 비율 {100 * lock:.1f}% "
          f"(playing.json 문헌값 80%)")
    if lock < 0.5:
        print("  -> 락 비율이 낮다. 이 곡에서 킥 동기화의 전제가 약하다.")

    configs: list[tuple[str, dict]] = [("끄기(기준선)", {"enabled": False})]
    if args.sweep:
        for ratio in (0.3, 0.5, 0.8, 1.2):
            configs.append((f"에너지 문턱 {ratio:.1f}",
                            {"enabled": True, "energy_ratio": ratio}))
    else:
        configs.append(("켜기", {"enabled": True}))

    print(f"\n{'설정':20} {'남은음':>6} {'반복구간':>10} {'비반복':>9} "
          f"{'전체':>10} {'평균오차':>8}  되살림")
    for label, kw in configs:
        r = run(gold, **kw)
        k = r["kick"]
        print(f"{label:20} {r['notes']:6} "
              f"{r['repOk']:4}/{r['repTotal']:<5} {r['nonOk']:3}/{r['nonTotal']:<5} "
              f"{r['allOk']:4}/{r['allTotal']:<5} {r['err']:8.2f}  "
              f"{k.revived}음 (짝없는킥 {k.orphan}, 조용 {k.rejected_quiet})")
    print("\n반복 = 정답 3타 47마디 / 비반복 = 필인·속주 12마디")
    print("**드럼이 없는 IDMT로는 검증할 수 없다. 한 곡 기준으로만 읽어라.**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

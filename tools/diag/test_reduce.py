"""하향 엔진 검증 — 불변식이 지켜지는지, 레벨이 실제로 쉬워지는지.

불변식(reduce.py 머리말)을 코드로 고정한다. 이 테스트가 깨지면 하향판이
원곡과 다른 시간축을 갖게 되거나 초급자가 못 짚는 악보가 나온다.

사용:
    python tools/diag/test_reduce.py data/<hash>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import bassclean, beats as beats_mod, compose, fretting, reduce  # noqa: E402

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    parser = argparse.ArgumentParser(description="하향 엔진 검증")
    parser.add_argument("workdir", type=Path, help="data/<hash>")
    args = parser.parse_args()

    notes = bassclean.load_notes(args.workdir / "notes.json")
    grid = beats_mod.BeatGrid.from_json(args.workdir / "beats.json")

    print(f"=== {args.workdir.name} — {len(notes)}음 ===")
    built: dict[int, compose.BuiltScore] = {}
    for level in sorted(reduce.LEVELS):
        built[level] = compose.build(notes, grid, level=level, title="test")

    original = built[reduce.ORIGINAL_LEVEL]
    print()
    print("레벨별 산출")
    for level in sorted(built):
        b = built[level]
        r = b.reduction
        prof = reduce.profile_of(level)
        frets = [n.fret for bar in b.fscore.bars for n in bar.notes]
        print(
            f"  Lv{level} {prof.name:4s} {r.notes_after:4d}음  subdiv={b.qscore.subdivision}  "
            f"마디 {len(b.fscore.bars)}  최대프렛 {max(frets) if frets else 0:2d}  "
            f"템플릿 {r.templated_bars:3d}마디  쉼표 {r.silent_bars:3d}마디"
        )

    print()
    print("불변식 1 — 시간축 불변 (마디 수·마디 시각)")
    for level, b in built.items():
        same_count = len(b.fscore.bars) == len(original.fscore.bars)
        same_times = all(
            abs(a.start_sec - c.start_sec) < 1e-6
            for a, c in zip(b.fscore.bars, original.fscore.bars)
        )
        check(same_count and same_times, f"Lv{level} 마디 수·시각 동일",
              f"{len(b.fscore.bars)}마디")

    print()
    print("불변식 2 — 근음 불변 (마디 첫 음이 원곡 근음과 같은 피치클래스)")
    # 균일 템플릿 단계만 본다. 원곡 리듬을 유지하는 단계는 마디 첫 음이
    # 다운비트가 아닐 수 있어(당김음) 이 비교가 성립하지 않는다.
    orig_roots = [reduce.bar_root(bar) for bar in original.qscore.bars]
    for level in sorted(built):
        if not reduce.profile_of(level).uniform_rhythm:
            continue
        b = built[level]
        mismatch = 0
        compared = 0
        for bar, orig_root in zip(b.qscore.bars, orig_roots):
            if orig_root is None or not bar.notes:
                continue
            compared += 1
            if bar.notes[0].pitch % 12 != orig_root % 12:
                mismatch += 1
        check(mismatch == 0, f"Lv{level} 근음 피치클래스 유지",
              f"{compared}마디 비교, 불일치 {mismatch}")

    print()
    print("불변식 3 — 다운비트에 음이 있다 (균일 템플릿 단계만, 원곡이 쉬는 마디는 예외)")
    # 원곡 리듬을 유지하는 단계(중급)에는 적용하지 않는다. 원곡이 당김음으로
    # 1박을 비웠으면 그것이 정답이고, 억지로 채우면 리듬이 달라진다.
    for level in sorted(built):
        if not reduce.profile_of(level).uniform_rhythm:
            continue
        b = built[level]
        bad = []
        for bar, orig in zip(b.qscore.bars, original.qscore.bars):
            if not orig.notes:
                continue          # 원곡이 통째로 쉬는 마디는 비워둔다
            if not bar.notes or bar.notes[0].slot != 0:
                bad.append(bar.index)
        check(not bad, f"Lv{level} 1박에 음 있음", f"위반 {len(bad)}마디")

    print()
    print("불변식 4 — 운지 제약 (프렛 상한·이동 폭)")
    for level in sorted(built):
        prof = reduce.profile_of(level)
        if prof.max_fret is None:
            continue
        b = built[level]
        over = [n.fret for bar in b.fscore.bars for n in bar.notes if n.fret > prof.max_fret]
        check(not over, f"Lv{level} 프렛 <= {prof.max_fret}",
              f"초과 {len(over)}음" + (f" 최대 {max(over)}" if over else ""))

        seq = [(n.string, n.fret) for bar in b.fscore.bars for n in bar.notes]
        moves = [
            fretting._move_span(a, c) for a, c in zip(seq, seq[1:])
        ] if prof.max_move is not None else []
        over_move = [m for m in moves if m > prof.max_move]
        if prof.max_move is not None:
            check(not over_move, f"Lv{level} 이동 <= {prof.max_move}프렛",
                  f"초과 {len(over_move)}회" + (f" 최대 {max(over_move)}" if over_move else ""))

    print()
    print("단조성 — 레벨이 낮을수록 단순해야 한다")
    counts = [built[lv].reduction.notes_after for lv in sorted(built)]
    check(all(a <= b for a, b in zip(counts, counts[1:])),
          "음 수가 레벨 순으로 증가", " <= ".join(str(c) for c in counts))

    # 음 수만으로는 Lv3~5를 구분할 수 없다. 도수 필터는 음을 지우지 않고
    # 근음으로 **대체**하므로 개수가 그대로다. 실제로 단순해졌는지는 쓰인
    # 피치 종류로 봐야 한다.
    variety = [
        len({n.pitch for bar in built[lv].qscore.bars for n in bar.notes})
        for lv in sorted(built)
    ]
    check(all(a <= b for a, b in zip(variety, variety[1:])),
          "쓰인 피치 종류가 레벨 순으로 증가", " <= ".join(str(v) for v in variety))

    print()
    print("표기 — 생성된 AlphaTex에 음이 실제로 들어 있다")
    for level in sorted(built):
        tex = built[level].tex
        has_notes = any(
            tok and tok[0].isdigit() and tok.count(".") >= 2
            for line in tex.splitlines()
            if not line.startswith("\\") and line != "."
            for tok in line.replace("|", " ").split()
        )
        check(has_notes, f"Lv{level} 음표 토큰 존재")

    print()
    print(f"실패 {len(failures)}건" + (": " + ", ".join(failures) if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

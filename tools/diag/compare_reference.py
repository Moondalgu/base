"""참조 악보 캐시(reference.json) vs 우리 채보 — 마디 자동 대조 리포트.

사용: .venv/Scripts/python.exe tools/diag/compare_reference.py <content_hash> [--level 1]

참조 악보는 반복 기호로 접혀 있고 우리 악보는 펼쳐져 있어 마디 번호가
1:1이 아니다. **근음 피치클래스 열의 단조 정렬(DP)**로 매핑을 만든다 —
반복·생략을 스킵 비용으로 흡수하고, 매칭된 쌍에서 코드·운지를 대조한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "worker"))

PC = {"C": 0, "Db": 1, "C#": 1, "D": 2, "Eb": 3, "D#": 3, "E": 4, "F": 5,
      "Gb": 6, "F#": 6, "G": 7, "Ab": 8, "G#": 8, "A": 9, "Bb": 10, "A#": 10,
      "B": 11, "Cb": 11}


def chord_root_pc(symbol: str) -> int | None:
    """코드 심볼("Dbm6/E")에서 루트 피치클래스."""
    if not symbol:
        return None
    head = symbol.split("/")[0].strip()
    for ln in (2, 1):
        if head[:ln] in PC:
            return PC[head[:ln]]
    return None


def ref_bar_roots(ref: dict) -> list[tuple[int, int | None, dict]]:
    """(악보 마디번호, 근음 pc, 마디 dict). 코드 없는 마디는 앞 코드 승계."""
    out = []
    cur = None
    for b in ref["bars"]:
        chords = b.get("chords") or []
        if chords:
            cur = chord_root_pc(chords[0])
        tab = b.get("tab") or []
        # 근음은 **연주가 있을 때만** — 인트로처럼 코드 심볼만 인쇄되고
        # 베이스는 쉬는 마디에 pc를 주면 우리 쉼표 마디와 가짜 어긋남이 난다.
        pc = cur if tab else None
        out.append((b["bar"], pc, b))
    return out


def our_bar_roots(hash_: str, level: int) -> list[tuple[int, int | None, list]]:
    """(우리 마디번호 1-, 근음 pc, [(string,fret)...]) — 빌드된 변형에서."""
    import jobs

    built = jobs.build_score_variant(hash_, level=level)
    rows_by_bar: dict[int, list] = {}
    for r in built.ledger or []:
        rows_by_bar.setdefault(r["bar"], []).append(r)
    out = []
    for i in range(1, len(built.qscore.bars) + 1):
        rows = sorted(rows_by_bar.get(i, []), key=lambda r: r["slot"])
        if not rows:
            out.append((i, None, []))
            continue
        from collections import Counter
        pc = Counter(r["pitch_written"] % 12 for r in rows
                     if isinstance(r["pitch_written"], int)).most_common(1)[0][0]
        out.append((i, pc, [(r["string"], r["fret"]) for r in rows]))
    return out


def align(ref_seq: list, our_seq: list) -> list[tuple[int | None, int | None]]:
    """근음 pc 열의 단조 DP 정렬. 반환 [(ref_idx|None, our_idx|None)...]."""
    R, O = len(ref_seq), len(our_seq)
    MATCH, MISMATCH, SKIP = 0.0, 2.0, 1.0
    INF = float("inf")
    dp = [[INF] * (O + 1) for _ in range(R + 1)]
    back = [[None] * (O + 1) for _ in range(R + 1)]
    dp[0][0] = 0.0
    for i in range(R + 1):
        for j in range(O + 1):
            if dp[i][j] == INF:
                continue
            base = dp[i][j]
            if i < R and j < O:
                rp, op = ref_seq[i][1], our_seq[j][1]
                cost = MATCH if (rp is None and op is None) or rp == op else MISMATCH
                if base + cost < dp[i + 1][j + 1]:
                    dp[i + 1][j + 1] = base + cost
                    back[i + 1][j + 1] = "d"
            if i < R and base + SKIP < dp[i + 1][j]:
                dp[i + 1][j] = base + SKIP
                back[i + 1][j] = "u"
            if j < O and base + SKIP < dp[i][j + 1]:
                dp[i][j + 1] = base + SKIP
                back[i][j + 1] = "l"
    pairs = []
    i, j = R, O
    while i > 0 or j > 0:
        move = back[i][j]
        if move == "d":
            pairs.append((i - 1, j - 1)); i, j = i - 1, j - 1
        elif move == "u":
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    return list(reversed(pairs))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("content_hash")
    ap.add_argument("--level", type=int, default=1)
    args = ap.parse_args()

    ref = json.loads((ROOT / "data" / args.content_hash / "reference.json")
                     .read_text(encoding="utf-8"))
    refs = ref_bar_roots(ref)
    ours = our_bar_roots(args.content_hash, args.level)
    pairs = align(refs, ours)

    matched = root_ok = fret_ok = fret_total = 0
    diffs = []
    for ri, oi in pairs:
        if ri is None or oi is None:
            continue
        rbar, rpc, rb = refs[ri]
        obar, opc, otab = ours[oi]
        if rpc is None and opc is None:
            continue
        matched += 1
        if rpc == opc:
            root_ok += 1
        else:
            diffs.append(f"근음: 악보{rbar}({rpc}) vs 우리{obar}({opc})")
        rtab = rb.get("tab") or []
        if rtab and otab:
            fret_total += 1
            rfirst = (rtab[0].get("string"), rtab[0].get("fret"))
            ofirst = otab[0]
            if rfirst == ofirst:
                fret_ok += 1
            else:
                diffs.append(f"운지: 악보{rbar} {rfirst} vs 우리{obar} {ofirst}")
    print(f"[대조] 매칭 {matched}마디: 근음 일치 {root_ok}/{matched} "
          f"({root_ok / max(1, matched):.0%}), "
          f"첫 온셋 운지 일치 {fret_ok}/{fret_total} "
          f"({fret_ok / max(1, fret_total):.0%})")
    for d in diffs[:20]:
        print("  " + d)
    if len(diffs) > 20:
        print(f"  … 외 {len(diffs) - 20}건")


if __name__ == "__main__":
    main()

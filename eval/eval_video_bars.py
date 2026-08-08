"""화면 악보 정답과 마디별 대조 — 자리(현·프렛)와 타현 수를 함께 본다.

## compare_bars.py와 무엇이 다른가

`compare_bars.py`는 슬롯·피치·길이를 마디 안에서 나란히 놓는 도구이고, 정답
스키마가 `bar` 키를 쓴다. 이쪽 정답은 유튜브 **화면 TAB을 사람이 읽은 것**이라
스키마가 다르다(`videoBar`/`ourBar`, `string`/`fret`, `attacks`/`writtenNotes`).
그리고 묻는 것도 다르다 — "몇 번째 슬롯인가"가 아니라 **"연주자가 이 마디에서
어디를 몇 번 짚는가"**다. 악보를 쓸 수 있는지 가르는 것은 후자다.

## 타현 수를 세는 규칙

화면 TAB의 숫자 개수를 세면 안 된다. 곡선(타이)으로 이어진 음은 적혀 있어도
다시 뜯지 않는다 — 실측 예: 숫자 6개인 마디의 실제 타현은 3회다
(`harmony.json`의 `articulation.comparisonRule`). 정답 파일의 `attacks`가
타현이고 `writtenNotes`가 적힌 숫자다. **우리 쪽도 타이를 빼고 센다.**

## 이 대조가 성립하는 조건

이 곡은 연습 영상(원곡 반주 + 커버 연주)이다. 음량 게이트로 큰 소리 쪽만
남겨야 우리 출력과 화면 악보가 **같은 연주자**를 가리킨다. 게이트가 발동하지
않았다면 이 대조는 무의미하므로 그 경우 경고를 낸다.

사용:
    python eval/eval_video_bars.py data/<hash> eval/golden/<정답>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import alphatex  # noqa: E402


def our_bars(tex: str, subdivision: int) -> dict[int, dict]:
    """AlphaTex를 마디별 (타현 목록)으로 되돈다. 마디 번호는 1부터.

    타현만 센다 — 이어짐(`-.현.길이`)과 쉼표(`r.길이`)는 타현이 아니다.

    **3단 악보 대응**: `\\track`이 여러 개면 베이스 트랙(`\\staff{score tabs}`가
    있는 트랙)만 읽는다. 트랙을 무시하고 전체를 이어 붙이면 보컬 마디가 앞에
    끼어들어 마디 번호가 통째로 밀린다(2026-08-08, 3단 도입과 함께 수정).
    """
    body = tex.split("\n.", 1)[-1] if "\n." in tex else tex
    if "\\track" in body:
        segments = body.split("\\track")[1:]
        bass_segs = [s for s in segments if "\\staff{score tabs}" in s]
        if bass_segs:
            body = bass_segs[-1]
    result: dict[int, dict] = {}
    for i, raw in enumerate(body.split("|"), start=1):
        attacks: list[tuple[int, int]] = []      # (현, 프렛)
        written = 0
        for token in raw.split():
            if token.startswith("\\") or token.startswith("."):
                continue
            parts = token.split(".")
            if len(parts) < 2:
                continue
            head = parts[0]
            if head.startswith("r"):             # 쉼표
                continue
            written += 1
            if head.startswith("-"):             # 타이 — 적히지만 뜯지 않는다
                continue
            try:
                fret = int(head)
                string = int(parts[1])
            except ValueError:
                continue
            attacks.append((string, fret))
        if attacks or written:
            result[i] = {"attacks": attacks, "written": written}
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="화면 악보 정답과 마디별 대조")
    ap.add_argument("workdir", type=Path, help="data/<hash>")
    ap.add_argument("golden", type=Path, help="eval/golden/*.json")
    args = ap.parse_args()

    manifest = json.loads((args.workdir / "manifest.json").read_text(encoding="utf-8"))
    tex = (args.workdir / "score.alphatex").read_text(encoding="utf-8")
    golden = json.loads(args.golden.read_text(encoding="utf-8"))

    gate = manifest.get("loudnessGate") or {}
    if not gate.get("applied"):
        print("[경고] 음량 게이트가 발동하지 않았다. 이 정답은 커버 연주를")
        print("       분리했다는 전제로 읽은 것이므로 대조가 성립하지 않는다.")

    ours = our_bars(tex, manifest.get("subdivision", 4))

    print(f"=== {args.golden.name} — {len(golden['bars'])}마디 대조 ===")
    print(f"{'영상':>4} {'우리':>4}  {'정답 자리':>10} {'우리 자리':>10} "
          f"{'정답타현':>6} {'우리타현':>6}  판정")

    place_ok = attack_ok = 0
    for row in golden["bars"]:
        n = row["ourBar"]
        got = ours.get(n, {"attacks": [], "written": 0})
        want_place = (row["string"], row["fret"])
        # 자리는 그 마디에서 **가장 많이 나온** 짚는 자리로 본다. 필인이 섞여도
        # 그 마디의 주된 자리는 하나다.
        places = got["attacks"]
        our_place = max(set(places), key=places.count) if places else None
        p_ok = our_place == want_place
        a_ok = len(places) == row["attacks"]
        place_ok += p_ok
        attack_ok += a_ok
        mark = {(True, True): "일치", (True, False): "타현X",
                (False, True): "자리X", (False, False): "둘다X"}[(p_ok, a_ok)]
        fmt = lambda p: f"{p[0]}현{p[1]}프" if p else "없음"      # noqa: E731
        print(f"{row['videoBar']:>4} {n:>4}  {fmt(want_place):>10} "
              f"{fmt(our_place):>10} {row['attacks']:>6} {len(places):>6}  {mark}")

    total = len(golden["bars"])
    print(f"\n자리 {place_ok}/{total} ({place_ok / total:.0%})   "
          f"타현수 {attack_ok}/{total} ({attack_ok / total:.0%})")
    print(f"게이트: {gate.get('kept')}음 남김 / 격자정렬 "
          f"{gate.get('gridBefore')} -> {gate.get('gridAfter')}")
    return 0 if place_ok == total and attack_ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

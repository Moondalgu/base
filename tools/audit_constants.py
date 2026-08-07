"""파이프라인의 규칙·정책 상수를 전수 조사한다.

## 왜 도구로 만드는가

이 프로젝트의 판단은 대부분 **상수 하나**에 들어 있다. 게이트 문턱 0.95,
관성 창 12마디, 운지 가중치 0.2 — 이 값들이 산출물을 결정한다. 그런데 값이
어디서 왔는지(실측인가 추측인가)가 코드 주석에만 있어서, **근거 없는 값이
몇 개인지 아무도 몰랐다.**

눈으로 고르면 놓친다. 그래서 AST로 긁는다. `POLICY.md`는 이 도구의 출력에
근거 분류를 사람이 붙인 것이고, 상수를 새로 추가하면 이 도구가 먼저 잡아낸다.

## 근거 등급

`POLICY.md`에서 쓰는 분류다. 여기서는 주석 줄 수만 세고 등급은 붙이지 않는다 —
등급은 사람이 판단할 일이다.

- **실측** — 정답 데이터로 재서 정한 값. 재현 명령이 있다
- **차용** — 문헌·다른 구현·도메인 관습에서 가져온 값
- **자명** — 음악 이론상 정해진 값(장3도 = 4반음)
- **추측** — 감으로 정하고 아직 재지 않은 값. **이것이 줄어야 할 대상이다**

사용:
    python tools/audit_constants.py              # 표
    python tools/audit_constants.py --json       # 기계용
    python tools/audit_constants.py --undocumented   # 주석 없는 것만
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [ROOT / "apps" / "worker" / "pipeline"]

# 이름만으로 자명한 것들. 근거를 요구하지 않는다.
#
# 음악 이론이 정한 값(장3도 = 4반음), 포맷이 정한 값(스템 이름), 표 자체가
# 근거인 값(음이름 배열)이다. 이 목록에 넣는 것 자체가 판단이므로 짧게 유지한다.
SELF_EVIDENT = {
    "MINOR_THIRD", "MAJOR_THIRD", "PERFECT_FIFTH", "MINOR_SEVENTH",
    "MAJOR_SEVENTH", "PITCH_NAMES", "STEM_NAMES", "MAJOR_TRIADS",
    "MINOR_TRIADS", "UNISON_OCTAVE", "THIRDS", "FIFTHS", "SEVENTHS",
    "BEGINNER", "INTERMEDIATE", "ORIGINAL_LEVEL",
    "_STEPS", "_ALTERS", "_TYPE_BY_QUARTERS", "_DURATION_EFFECTS",
    "FEATURES_RHYTHM", "FEATURES_FULL",
    "HARMONY_PATH", "PLAYING_PATH", "SECTION_PATH",
}


def collect() -> list[dict]:
    rows: list[dict] = []
    for target in TARGETS:
        for path in sorted(target.glob("*.py")):
            if path.name == "__init__.py":
                continue
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            tree = ast.parse(text)
            for node in tree.body:
                # `AnnAssign`(타입 주석 붙은 대입)도 읽는다. `TUNING_PRESETS:
                # dict[...] = {...}`처럼 쓰면 `Assign`이 아니라 `AnnAssign`이라
                # 놓치면 조사에서 빠진다.
                if isinstance(node, ast.AnnAssign):
                    node_targets = [node.target]
                    node_value = node.value
                elif isinstance(node, ast.Assign):
                    node_targets = node.targets
                    node_value = node.value
                else:
                    continue
                if node_value is None:
                    continue
                for target_node in node_targets:
                    if not isinstance(target_node, ast.Name):
                        continue
                    name = target_node.id
                    # 대문자 상수만. 소문자는 모듈 상태이고 정책이 아니다.
                    if not (name.replace("_", "").isupper() and len(name) > 2):
                        continue
                    try:
                        value = ast.literal_eval(node_value)
                    except Exception:
                        value = "<계산식>"
                    # 바로 위에 붙은 주석 줄 수. 근거가 적혀 있는지의 대리 지표다.
                    i = node.lineno - 2
                    comment = 0
                    while i >= 0 and lines[i].strip().startswith("#"):
                        comment += 1
                        i -= 1
                    rows.append({
                        "module": path.stem,
                        "name": name,
                        "value": value if isinstance(
                            value, (int, float, str, bool, type(None))
                        ) else repr(value),
                        "commentLines": comment,
                        "selfEvident": name in SELF_EVIDENT,
                        "line": node.lineno,
                    })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="규칙·정책 상수 전수 조사")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--undocumented", action="store_true",
                    help="주석 없고 자명하지도 않은 것만")
    args = ap.parse_args()

    rows = collect()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    needs = [r for r in rows if r["commentLines"] == 0 and not r["selfEvident"]]
    show = needs if args.undocumented else rows

    print(f"{'모듈':20} {'상수':30} {'값':>26} {'근거줄':>6}")
    for r in show:
        v = str(r["value"])
        if len(v) > 26:
            v = v[:23] + "..."
        mark = "" if r["commentLines"] or r["selfEvident"] else "  <- 근거 없음"
        print(f"{r['module']:20} {r['name']:30} {v:>26} {r['commentLines']:>6}{mark}")

    documented = sum(1 for r in rows if r["commentLines"])
    evident = sum(1 for r in rows if r["selfEvident"] and not r["commentLines"])
    print(f"\n총 {len(rows)}개 — 근거 주석 {documented}, 자명 {evident}, "
          f"**근거 없음 {len(needs)}**")
    if needs and not args.undocumented:
        print("근거 없는 것만 보려면 --undocumented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

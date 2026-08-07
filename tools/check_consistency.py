"""정합성 검사 — 문서·코드·실측이 서로 어긋나지 않는가.

## 왜 필요한가

이 프로젝트의 사고는 대부분 **세 곳이 어긋나서** 났다.

1. **코드끼리** — 이름을 바꿨는데 부르는 쪽 하나를 놓친다. 한 세션에 네 번 났고
   전부 "값이 없으면 안전해 보이는 기본값으로 흘러" 조용히 틀렸다
   (웹 라우트 `ORIGINAL_LEVEL = 5`, UI `eighthAfter`, `slots_of`, CLI `eighth_after`).
2. **문서와 코드** — 문서에 적힌 수치가 코드 상수와 다르다
3. **문서와 실측** — 문서가 "93%"라고 하는데 다시 재면 다른 값이 나온다

사람이 눈으로 보면 놓친다. 기계가 잡을 수 있는 것만 잡는다.

## 무엇을 검사하는가

- 같은 값을 여러 곳에 적어둔 **상수 쌍**이 실제로 같은가
- 문서가 인용한 **상수 값**이 코드와 같은가
- manifest 키를 읽는 쪽이 **실제 키 이름**을 쓰는가 (rename 누락 탐지)
- 문서가 주장하는 **점수**가 지금 재도 같은가 (`--measure`)

## 무엇을 검사하지 못하는가

의미의 정합성은 못 본다. "같은 숫자를 다른 모집단에 쓴 것"(POLICY.md 6.5)은
값이 같은지가 아니라 **같아야 하는지**의 문제라 기계가 판정할 수 없다.
그런 것은 사람이 봐야 한다.

사용:
    python tools/check_consistency.py              # 빠른 검사 (측정 없음)
    python tools/check_consistency.py --measure    # 점수까지 다시 재기 (느림)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

failures: list[str] = []
checks = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(f"{label}: {detail}")


def constants() -> dict[str, object]:
    """`모듈.상수` -> 값. `tools/audit_constants.py`와 같은 방식으로 읽는다."""
    out: dict[str, object] = {}
    for path in sorted((ROOT / "apps" / "worker" / "pipeline").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            # **`AnnAssign`도 읽어야 한다.** `TUNING_PRESETS: dict[...] = {...}`처럼
            # 타입 주석이 붙으면 `Assign`이 아니라 `AnnAssign`이고, 놓치면
            # "worker=[]"처럼 빈 값으로 보여 없는 불일치를 만든다.
            if isinstance(node, ast.AnnAssign):
                targets = [node.target]
                value = node.value
            elif isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            else:
                continue
            if value is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    try:
                        out[f"{path.stem}.{target.id}"] = ast.literal_eval(value)
                    except Exception:
                        pass
    return out


def check_cross_references(const: dict) -> None:
    """여러 곳에 적힌 같은 값이 실제로 같은가.

    **의도적으로 다른 것은 여기 넣지 않는다.** 예를 들어
    `bassclean.GATE_TARGET_GRID_RATIO`(0.95)와 `diagnose.TRUSTED_GRID_RATIO`(0.85)는
    재는 대상이 달라 **달라야 한다**(POLICY.md 6.5). 같기를 요구하면 안 된다.
    """
    print("\n[1] 여러 곳에 적힌 같은 값")

    # 워커의 원본 레벨 == 웹 라우트의 원본 레벨 == UI의 원본 레벨
    worker = const.get("reduce.ORIGINAL_LEVEL")
    route = ROOT / "apps/web/app/api/scores/[hash]/route.ts"
    ui = ROOT / "apps/web/components/player/ScoreControls.tsx"
    route_val = _number(route, r"const ORIGINAL_LEVEL = (\d+)")
    ui_val = _number(ui, r"export const ORIGINAL_LEVEL = (\d+)")
    check("ORIGINAL_LEVEL 삼자 일치",
          worker == route_val == ui_val,
          f"worker={worker} route={route_val} ui={ui_val}")

    # 이조 한계
    limit = const.get("compose.TRANSPOSE_LIMIT")
    ui_limit = _number(ui, r"export const TRANSPOSE_LIMIT = (\d+)")
    check("TRANSPOSE_LIMIT 일치", limit == ui_limit,
          f"worker={limit} ui={ui_limit}")

    # 튜닝 프리셋 목록 == UI 버튼 목록
    presets = set(const.get("fretting.TUNING_PRESETS") or {})
    ui_text = ui.read_text(encoding="utf-8") if ui.exists() else ""
    ui_presets = set(re.findall(r'key: "(\w+)", label:', ui_text))
    check("튜닝 프리셋 목록 일치", presets == ui_presets,
          f"worker={sorted(presets)} ui={sorted(ui_presets)}")


def check_manifest_keys() -> None:
    """manifest에 실제로 있는 키를 읽는 쪽이 쓰고 있는가.

    이름을 바꾸고 호출부를 놓치는 사고를 잡는다. 옛 이름이 코드 어딘가에
    **문자열로** 남아 있으면 조용히 undefined가 된다.
    """
    print("\n[2] manifest 키 rename 누락")

    # 산출물에서 실제 키를 모은다.
    keys: set[str] = set()
    for m in (ROOT / "data").glob("*/manifest.json"):
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
        except Exception:
            continue
        for section in ("loudnessGate", "inputDiagnosis"):
            keys |= set((data.get(section) or {}).keys())
    if not keys:
        check("manifest 산출물 존재", False, "data/*/manifest.json이 없다 — 이 검사를 건너뛴다")
        return

    # 폐기된 옛 이름이 코드에 남아 있는가.
    retired = {
        "eighthBefore": "gridBefore",
        "eighthAfter": "gridAfter",
        "eighth_before": "grid_before",
        "eighth_after": "grid_after",
    }
    targets = list((ROOT / "apps").rglob("*.py")) + \
        list((ROOT / "apps").rglob("*.ts")) + \
        list((ROOT / "apps").rglob("*.tsx")) + \
        list((ROOT / "scripts").rglob("*.py"))
    for old, new in retired.items():
        hits = []
        for f in targets:
            if "node_modules" in str(f):
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                # 주석에 남긴 설명은 사고가 아니다.
                stripped = line.strip()
                if stripped.startswith(("#", "//", "*", "/*")):
                    continue
                if old in line:
                    hits.append(f"{f.relative_to(ROOT)}:{i}")
        check(f"폐기된 이름 `{old}` 미사용 (-> {new})", not hits, ", ".join(hits[:3]))

    check("gridAfter 키 존재", "gridAfter" in keys, f"실제 키: {sorted(keys)[:6]}")
    check("rhythmConfident 키 존재", "rhythmConfident" in keys)


def check_doc_numbers(const: dict) -> None:
    """문서가 인용한 상수 값이 코드와 같은가.

    `POLICY.md` 1장 표는 `| \\`모듈.상수\\` | 값 | ...` 형식이다. 그 값을 코드와
    대조한다. 문서가 낡으면 다음 세션이 틀린 값을 근거로 판단한다.
    """
    print("\n[3] 문서가 인용한 상수 값")
    policy = ROOT / "POLICY.md"
    if not policy.exists():
        check("POLICY.md 존재", False)
        return

    pattern = re.compile(r"^\|\s*`([\w.]+)`\s*\|\s*([-\d.]+)\s*\|", re.M)
    found = 0
    for name, quoted in pattern.findall(policy.read_text(encoding="utf-8")):
        if name not in const:
            continue
        found += 1
        actual = const[name]
        try:
            same = abs(float(quoted) - float(actual)) < 1e-9
        except (TypeError, ValueError):
            same = str(quoted) == str(actual)
        check(f"POLICY.md `{name}`", same, f"문서 {quoted} vs 코드 {actual}")
    check("POLICY.md에서 대조한 상수 수", found >= 5, f"{found}개")


def check_measured_scores() -> None:
    """문서가 주장하는 점수를 지금 다시 재도 같은가."""
    print("\n[4] 문서가 주장하는 점수 재측정")
    song = ROOT / "data" / "975e4e588d282666"
    golden = ROOT / "eval" / "golden" / "champagne_video_bars41_99.json"
    if not (song / "score.alphatex").exists():
        check("실곡 산출물 존재", False, f"{song.name}이 없다 — SET.md 절차로 재생성")
        return

    out = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "eval_video_bars.py"), str(song), str(golden)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    match = re.search(r"자리 (\d+)/(\d+).*?타현수 (\d+)/(\d+)", out)
    if not match:
        check("정답 대조 실행", False, out.strip().splitlines()[-1] if out else "출력 없음")
        return
    place = int(match.group(1)) / int(match.group(2))
    attack = int(match.group(3)) / int(match.group(4))

    # HANDOFF.md·START_HERE.md가 주장하는 값
    claimed = re.search(
        r"자리 (\d+)/(\d+) \((\d+)%\)\s+타현수 (\d+)/(\d+) \((\d+)%\)",
        (ROOT / "START_HERE.md").read_text(encoding="utf-8"),
    )
    if claimed:
        check("START_HERE.md 자리 점수",
              round(place * 100) == int(claimed.group(3)),
              f"실측 {place:.0%} vs 문서 {claimed.group(3)}%")
        check("START_HERE.md 타현 점수",
              round(attack * 100) == int(claimed.group(6)),
              f"실측 {attack:.0%} vs 문서 {claimed.group(6)}%")
    else:
        check("START_HERE.md에 점수 기록", False, "기대값 문구를 찾지 못했다")


def _number(path: Path, pattern: str) -> int | None:
    if not path.exists():
        return None
    match = re.search(pattern, path.read_text(encoding="utf-8"))
    return int(match.group(1)) if match else None


def main() -> int:
    ap = argparse.ArgumentParser(description="문서·코드·실측 정합성 검사")
    ap.add_argument("--measure", action="store_true",
                    help="점수까지 다시 잰다 (느리다)")
    args = ap.parse_args()

    const = constants()
    print(f"파이프라인 상수 {len(const)}개 읽음")
    check_cross_references(const)
    check_manifest_keys()
    check_doc_numbers(const)
    if args.measure:
        check_measured_scores()
    else:
        print("\n[4] 점수 재측정 — 건너뜀 (--measure로 실행)")

    print(f"\n검사 {checks}건, 실패 {len(failures)}건")
    for f in failures:
        print(f"  - {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""레벨 × 이조 × 튜닝 조합 전수로 악보가 파싱되는지 확인한다 (PRD 12.2 N7).

원곡·무이조 하나만 검증하면 조합에서 생기는 어긋남을 놓친다. 실제로 놓쳤다 —
음량 게이트가 어떤 마디의 음을 전부 버렸는데 코드 이름은 오디오 분석에서 나온
것이라 남아 있었고, 결과적으로 **쉼표 토큰에 코드가 붙어** alphaTab이
`Unexpected 'LBrace'`로 렌더를 포기했다. 브라우저 콘솔을 보고서야 발견했다.

파이썬 쪽에서 조합마다 AlphaTex를 만들고, Node 검증기로 실제 파싱까지 돌린다.
표기 규칙 검산(review_score.py)은 파싱이 되는지를 보지 않으므로 이것과 다르다.

사용:
    python tools/diag/test_variants.py data/<hash>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

import jobs  # noqa: E402
from pipeline import fretting, reduce  # noqa: E402

VALIDATOR = ROOT / "tools" / "validate_alphatex.mjs"
# 검증기는 apps/web에서 실행해야 모듈이 해석된다(CLAUDE.md 함정).
VALIDATOR_CWD = ROOT / "apps" / "web"

# 이조는 경계와 중간만 본다. 전 범위를 돌면 조합이 곱으로 늘어나는데
# 파싱 실패는 경계에서 나온다.
TRANSPOSES = (-6, -1, 0, 2, 6)


def validate(tex: str, label: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".alphatex", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(tex)
        path = Path(fh.name)
    try:
        proc = subprocess.run(
            ["node", str(VALIDATOR), str(path)],
            cwd=str(VALIDATOR_CWD),
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        ok = "PARSE OK" in out
        detail = ""
        if not ok:
            # 첫 Error 줄만 뽑는다. 전체를 찍으면 표가 읽히지 않는다.
            for line in out.splitlines():
                if "Error" in line or "FAIL" in line:
                    detail = line.strip()
                    break
            if not detail:
                detail = out.strip().splitlines()[0] if out.strip() else "출력 없음"
        return ok, detail
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="악보 변형 조합 파싱 검증")
    parser.add_argument("workdir", type=Path, help="data/<hash>")
    args = parser.parse_args()

    content_hash = args.workdir.name
    tunings = sorted(fretting.TUNING_PRESETS)
    levels = sorted(reduce.LEVELS)

    print(f"=== {content_hash} — 레벨 {len(levels)} × 이조 {len(TRANSPOSES)} × 튜닝 {len(tunings)} ===")
    failures: list[str] = []
    total = 0

    for tuning in tunings:
        for level in levels:
            marks = []
            for transpose in TRANSPOSES:
                total += 1
                label = f"{tuning}/Lv{level}/{transpose:+d}"
                try:
                    built = jobs.build_score_variant(
                        content_hash, level=level, transpose=transpose, tuning=tuning
                    )
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{label}: 생성 실패 {type(exc).__name__}: {exc}")
                    marks.append("E")
                    continue
                ok, detail = validate(built.tex, label)
                marks.append("." if ok else "X")
                if not ok:
                    failures.append(f"{label}: {detail}")
            print(f"  {tuning:14s} Lv{level}  " + " ".join(
                f"{t:+d}{m}" for t, m in zip(TRANSPOSES, marks)
            ))

    print()
    print(f"조합 {total}개, 실패 {len(failures)}건")
    for f in failures[:20]:
        print(f"  {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

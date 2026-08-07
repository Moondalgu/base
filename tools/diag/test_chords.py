"""코드 판정을 합성 화음으로 채점한다 — 특히 분수 코드.

실곡(Champagne Supernova)은 전부 근음 자리라서 분수 코드 판정을 검증할 수
없다. 구성음이 확실한 크로마를 직접 만들어 넣으면 판정 규칙만 따로 채점할 수
있다. 크로마 계산이나 오디오 분리는 여기서 재지 않는다 — 규칙이 맞는지만 본다.

사용:
    python tools/diag/test_chords.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import chords  # noqa: E402

PC = {name: i for i, name in enumerate(chords.PITCH_NAMES)}
# 이명동음 별칭. 테스트를 읽기 쉽게 하려는 것뿐이다.
PC.update({"C#": 1, "D#": 3, "F#": 6, "G#": 8, "A#": 10})

# 화음에 없는 음에도 약간의 에너지를 준다. 실제 크로마는 배음과 인접 화음이
# 새어 들어와 0이 되지 않는다. 0으로 두면 판정이 실제보다 쉬워진다.
LEAK = 0.15
TONE = 1.0

failures: list[str] = []


def profile(*note_names: str):
    """구성음만 강한 크로마 한 벌을 만든다."""
    import numpy as np

    out = np.full(12, LEAK)
    for name in note_names:
        out[PC[name]] = TONE
    return out


def check(label: str, prof, bass: str, expect: str) -> None:
    root, quality, inverted, conf = chords.decide(prof, PC[bass])
    got = chords.name_of(root, quality, PC[bass] if inverted else None)
    ok = got == expect
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {label:34s} 기대 {expect:8s} 결과 {got:8s} 확신도 {conf:.2f}")
    if not ok:
        failures.append(f"{label}: 기대 {expect}, 결과 {got}")


def main() -> int:
    print("=== 근음 자리 (분수 코드가 아니어야 한다) ===")
    check("E장3화음 위의 E", profile("E", "G#", "B"), "E", "E")
    check("E단3화음 위의 E", profile("E", "G", "B"), "E", "Em")
    check("C장3화음 위의 C", profile("C", "E", "G"), "C", "C")
    check("A단3화음 위의 A", profile("A", "C", "E"), "A", "Am")

    print()
    print("=== 분수 코드 (베이스가 3음·5음) ===")
    check("C장3화음 위의 E (3음)", profile("C", "E", "G"), "E", "C/E")
    check("C장3화음 위의 G (5음)", profile("C", "E", "G"), "G", "C/G")
    check("Am 위의 C (3음)", profile("A", "C", "E"), "C", "Am/C")
    check("Eb장3화음 위의 G (3음)", profile("Eb", "G", "Bb"), "G", "Eb/G")
    check("Ebm 위의 Gb (3음)", profile("Eb", "Gb", "Bb"), "Gb", "Ebm/Gb")

    print()
    print("=== 구분되지 않는 경우 (품질을 찍지 않아야 한다) ===")
    # 3도가 연주되지 않은 구간. 근음과 5도만 있으면 장/단을 알 수 없다.
    check("근음+5도만 (3도 없음)", profile("E", "B"), "E", "E")

    print()
    print(f"실패 {len(failures)}건")
    for f in failures:
        print(f"  {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

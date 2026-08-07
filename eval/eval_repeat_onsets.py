"""반복 타격 온셋을 놓치는지 정답으로 확인한다 (PRD 13장 2번).

## 가설

`transcribe_crepe._segment`는 음을 두 경우에만 끊는다 — 무성 프레임이거나
**반음이 바뀔 때**. 그러면 같은 음을 반복해서 치는 구간(루트 페달)은 피치가
변하지 않으므로 **하나의 긴 음으로 합쳐진다.** 8분 페달 여덟 번이 마디당 1음이
된다. 이것이 "마디당 타수 부족"의 구조적 원인이라는 가설이다.

"검출 실패"와 "분절 규칙의 한계"는 다른 문제다. 전자라면 피치 추적을 바꿔야
하고, 후자라면 분절만 고치면 된다. 어느 쪽인지 정답으로 가른다.

## 방법

IDMT 정답 온셋을 두 갈래로 나눈다.
  - **반복 타격**: 앞 음과 피치가 같은 온셋
  - **음 변화**: 앞 음과 피치가 다른 온셋

두 갈래의 온셋 재현율을 따로 잰다. 가설이 맞으면 반복 타격 재현율만 크게
낮아야 한다. 둘이 비슷하게 낮으면 분절이 아니라 검출 자체의 문제다.

사용:
    python eval/eval_repeat_onsets.py
    python eval/eval_repeat_onsets.py --limit 5
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

try:
    import defusedxml.ElementTree as ET
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as ET  # type: ignore[no-redef]

from pipeline import transcribe_crepe  # noqa: E402

IDMT = ROOT / "data" / "_datasets" / "idmt_single"

# 온셋이 맞았다고 보는 허용 오차. 연습 관점 기준(eval_practice.py)과 같이 둔다.
TOLERANCE_SEC = 0.15


def truth_events(xml_path: Path) -> list[tuple[float, int]]:
    root = ET.parse(xml_path).getroot()
    out = []
    for ev in root.iter("event"):
        onset = ev.findtext("onsetSec")
        pitch = ev.findtext("pitch")
        if onset is None or pitch is None:
            continue
        out.append((float(onset), int(pitch)))
    return sorted(out)


def split_by_repeat(
    events: list[tuple[float, int]]
) -> tuple[list[float], list[float]]:
    """정답 온셋을 (반복 타격, 음 변화)로 나눈다. 첫 음은 음 변화로 센다."""
    repeats: list[float] = []
    changes: list[float] = []
    prev_pitch: int | None = None
    for onset, pitch in events:
        if prev_pitch is not None and pitch == prev_pitch:
            repeats.append(onset)
        else:
            changes.append(onset)
        prev_pitch = pitch
    return repeats, changes


def recall(reference: list[float], estimated: list[float]) -> tuple[int, int]:
    """정답 온셋 중 추정 온셋이 허용 오차 안에 있는 것의 수. 반환 (맞음, 전체).

    추정을 재사용하지 않는다 — 한 추정 온셋이 정답 두 개를 동시에 맞혔다고
    세면 반복 타격을 하나로 합친 경우가 정상처럼 보인다. 그것이 바로 여기서
    가려내려는 현상이다.
    """
    used: set[int] = set()
    hit = 0
    for t in reference:
        best = None
        for i, e in enumerate(estimated):
            if i in used:
                continue
            d = abs(e - t)
            if d <= TOLERANCE_SEC and (best is None or d < best[0]):
                best = (d, i)
        if best is not None:
            used.add(best[1])
            hit += 1
    return hit, len(reference)


def main() -> int:
    parser = argparse.ArgumentParser(description="반복 타격 온셋 재현율")
    parser.add_argument("--limit", type=int, default=0, help="앞 N곡만")
    args = parser.parse_args()

    xmls = sorted((IDMT / "annotation").glob("*.xml"))
    if args.limit:
        xmls = xmls[: args.limit]
    if not xmls:
        print(f"[오류] IDMT 어노테이션이 없습니다: {IDMT / 'annotation'}")
        return 1

    print(f"=== 반복 타격 대 음 변화 온셋 재현율 (IDMT {len(xmls)}곡, 허용 ±{TOLERANCE_SEC * 1000:.0f}ms) ===")
    print(f"  {'트랙':6s} {'반복':>16s} {'음변화':>16s}   차이")
    rows = []
    for xml in xmls:
        audio = IDMT / "audio" / f"{xml.stem}.wav"
        if not audio.exists():
            print(f"  {xml.stem:6s} 오디오 없음")
            continue

        events = truth_events(xml)
        repeats, changes = split_by_repeat(events)
        est = [e[0] for e in transcribe_crepe.transcribe(audio)]

        r_hit, r_total = recall(repeats, est)
        c_hit, c_total = recall(changes, est)
        r_rate = r_hit / r_total if r_total else float("nan")
        c_rate = c_hit / c_total if c_total else float("nan")
        rows.append((r_hit, r_total, c_hit, c_total))
        print(
            f"  {xml.stem:6s} {r_hit:4d}/{r_total:4d} {100 * r_rate:5.1f}% "
            f"{c_hit:4d}/{c_total:4d} {100 * c_rate:5.1f}%   "
            f"{100 * (c_rate - r_rate):+6.1f}pp"
        )

    if not rows:
        return 1
    r_hit = sum(r[0] for r in rows)
    r_total = sum(r[1] for r in rows)
    c_hit = sum(r[2] for r in rows)
    c_total = sum(r[3] for r in rows)
    print()
    print(f"  반복 타격 재현율  {r_hit}/{r_total} = {100 * r_hit / max(r_total, 1):.1f}%")
    print(f"  음 변화 재현율    {c_hit}/{c_total} = {100 * c_hit / max(c_total, 1):.1f}%")
    print()
    print("  해석: 반복 타격만 크게 낮으면 **분절 규칙**의 문제다(같은 피치를 안 끊는다).")
    print("        둘이 비슷하게 낮으면 검출 자체의 문제다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

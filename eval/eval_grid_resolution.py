"""리듬 격자 해상도 측정 — 8분 격자로 충분한가, 16분이 정말 필요한가.

지금 `quantize.DEFAULT_SUBDIVISION = 4`로 격자를 16분에 고정하고 있다. 그 결과
실곡 표기가 16분 299 / 8분 242로 나오는데 같은 곡 참조 악보는 8분 중심이다.
격자를 적응적으로 고르도록 바꾸기 전에 먼저 재야 한다.

## 추정하지 않는다

IDMT-SMT-BASS-SINGLE-TRACKS에는 정답이 두 겹으로 들어 있다.
  - `misc/music_xml/` — 사람이 적은 **정답 악보**. 음표마다 리듬 값(eighth,
    16th, quarter...)이 있다. "이 연주에 16분음표가 몇 개인가"의 직답이다.
  - `misc/beats_csv/` — `시각,마디.박` 형식의 **정답 비트**. 비트 길이와 위상을
    둘 다 준다.

이 둘이 있으므로 템포·위상을 추정할 필요가 없다. 추정하면 측정이 무너진다 —
16분 격자 잔차로 위상을 구하면 답이 16분 간격만큼 임의로 밀리고, 허용 잔차로
격자를 고르면 음악이 아니라 임계값이 격자를 정한다. 둘 다 실제로 겪었다.

## 재는 것

1) 정답 악보의 리듬 값 분포 — 16분음표가 실제로 쓰이는 비율
2) 정답 비트 위에서 정답 온셋의 잔차 — 8분 격자 대 16분 격자
   판정: 온셋이 홀수 16분에 가장 가깝고 **동시에** 가장 가까운 8분 슬롯에서
   0.125박 넘게 떨어져 있으면 그 온셋은 16분 격자를 요구한다.

사용:
    python eval/eval_grid_resolution.py                    # IDMT 정답 17곡
    python eval/eval_grid_resolution.py --song data/<hash> # 우리 산출물
"""

from __future__ import annotations

import argparse
import bisect
import csv
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

try:
    import defusedxml.ElementTree as ET
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as ET  # type: ignore[no-redef]

IDMT = ROOT / "data" / "_datasets" / "idmt_single"

# 홀수 16분에 얹혔다고 인정하려면 8분 슬롯에서 이만큼(박 단위) 이상 떨어져야 한다.
# 16분 간격의 절반이다 — 이보다 가까우면 8분 위의 연주 흔들림과 구분되지 않는다.
ODD_SIXTEENTH_MARGIN = 0.125

# MusicXML 음표 종류를 4분음표 대비 비율로. 16분보다 짧은 값이 있는지도 본다.
_NOTE_TYPE_ORDER = [
    "whole", "half", "quarter", "eighth", "16th", "32nd", "64th",
]


def truth_onsets(xml_path: Path) -> list[float]:
    root = ET.parse(xml_path).getroot()
    out = [
        float(ev.findtext("onsetSec"))
        for ev in root.iter("event")
        if ev.findtext("onsetSec") is not None
    ]
    return sorted(out)


def truth_beats(csv_path: Path) -> tuple[list[float], list[str]]:
    """정답 비트. 반환 (시각 목록, 마디.박 라벨 목록)."""
    times: list[float] = []
    labels: list[str] = []
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if len(row) < 2:
                continue
            try:
                times.append(float(row[0]))
            except ValueError:
                continue
            labels.append(row[1].strip())
    return times, labels


def notated_durations(xml_path: Path) -> Counter:
    """정답 악보의 음표 종류 분포. 쉼표는 세지 않는다(리듬 해상도만 본다)."""
    root = ET.parse(xml_path).getroot()
    counts: Counter = Counter()
    for note in root.iter("note"):
        if note.find("rest") is not None:
            continue
        kind = note.findtext("type")
        if kind:
            dotted = note.find("dot") is not None
            counts[f"{kind}{'.' if dotted else ''}"] += 1
    return counts


def beat_residuals(onsets: list[float], beats: list[float]) -> dict | None:
    """정답 비트 위에서 온셋의 박 내 위치와 잔차를 구한다."""
    if len(beats) < 2 or not onsets:
        return None

    eighth = (0.0, 0.5, 1.0)
    sixteenth = (0.0, 0.25, 0.5, 0.75, 1.0)

    d8: list[float] = []
    d16: list[float] = []
    needs16 = 0
    buckets = [0, 0, 0, 0]
    used = 0

    for t in onsets:
        i = bisect.bisect_right(beats, t) - 1
        if i < 0 or i + 1 >= len(beats):
            continue
        span = beats[i + 1] - beats[i]
        if span <= 0:
            continue
        pos = (t - beats[i]) / span
        used += 1

        dist8 = min(abs(pos - s) for s in eighth)
        nearest16 = min(sixteenth, key=lambda s: abs(pos - s))
        d8.append(dist8)
        d16.append(abs(pos - nearest16))
        if nearest16 in (0.25, 0.75) and dist8 > ODD_SIXTEENTH_MARGIN:
            needs16 += 1
        buckets[min(range(4), key=lambda k: abs(pos - k * 0.25)) % 4] += 1

    if not used:
        return None
    return {
        "used": used,
        # 각 격자의 슬롯 간격으로 정규화한다(8분 슬롯은 16분 슬롯의 두 배 폭).
        "residual8": statistics.fmean(d8) / 0.5,
        "residual16": statistics.fmean(d16) / 0.25,
        "needs16Ratio": needs16 / used,
        "buckets": buckets,
    }


def _fmt_durations(counts: Counter) -> str:
    total = sum(counts.values())
    if not total:
        return "(음표 없음)"
    ordered = sorted(
        counts.items(),
        key=lambda kv: (
            _NOTE_TYPE_ORDER.index(kv[0].rstrip("."))
            if kv[0].rstrip(".") in _NOTE_TYPE_ORDER
            else 99
        ),
    )
    return " ".join(f"{k}={v}" for k, v in ordered)


def run_idmt() -> None:
    ann = sorted((IDMT / "annotation").glob("*.xml"))
    if not ann:
        print(f"[오류] IDMT 어노테이션이 없습니다: {IDMT / 'annotation'}")
        return

    print(f"=== IDMT 정답 {len(ann)}곡 — 정답 악보와 정답 비트로 측정 ===")
    print()
    print("[1] 정답 악보의 리듬 값 분포")
    total_counts: Counter = Counter()
    sixteenth_songs = 0
    for xml in ann:
        mx = IDMT / "misc" / "music_xml" / xml.name
        if not mx.exists():
            print(f"  {xml.stem:5s} music_xml 없음")
            continue
        counts = notated_durations(mx)
        total_counts.update(counts)
        has16 = any(k.rstrip(".") in ("16th", "32nd", "64th") for k in counts)
        if has16:
            sixteenth_songs += 1
        print(f"  {xml.stem:5s} {'16분↑ 있음' if has16 else '8분까지 '}  {_fmt_durations(counts)}")

    total = sum(total_counts.values())
    print()
    print(f"  전체 음표 {total}개: {_fmt_durations(total_counts)}")
    fine = sum(v for k, v in total_counts.items() if k.rstrip(".") in ("16th", "32nd", "64th"))
    print(f"  16분음표 이상 비율 {100 * fine / total:.1f}%  ({fine}/{total})")
    print(f"  16분음표를 쓰는 곡 {sixteenth_songs}/{len(ann)}")

    print()
    print("[2] 정답 비트 위에서 정답 온셋의 잔차")
    print("  (슬롯분포 = 박을 4등분한 위치별 온셋 비율. 0/2번이 8분 자리, 1/3번이 홀수 16분)")
    rows = []
    for xml in ann:
        beats_csv = IDMT / "misc" / "beats_csv" / f"{xml.stem}_beats.csv"
        if not beats_csv.exists():
            print(f"  {xml.stem:5s} beats_csv 없음")
            continue
        beats, _ = truth_beats(beats_csv)
        r = beat_residuals(truth_onsets(xml), beats)
        if r is None:
            print(f"  {xml.stem:5s} 판정 불가")
            continue
        bpm = 60.0 / statistics.median(
            [b - a for a, b in zip(beats, beats[1:]) if b > a]
        )
        pct = [f"{100 * x / r['used']:4.1f}" for x in r["buckets"]]
        print(
            f"  {xml.stem:5s} {r['used']:4d}음 {bpm:6.1f}BPM  "
            f"8분잔차 {r['residual8']:.3f}  16분잔차 {r['residual16']:.3f}  "
            f"16분필요 {100 * r['needs16Ratio']:5.1f}%  "
            f"슬롯 {pct[0]}/{pct[1]}/{pct[2]}/{pct[3]}"
        )
        rows.append(r)

    if not rows:
        return
    used = sum(r["used"] for r in rows)
    print()
    print(f"  합계 {used}음")
    print(f"  8분 격자 잔차 중앙값  {statistics.median(r['residual8'] for r in rows):.3f}")
    print(f"  16분 격자 잔차 중앙값 {statistics.median(r['residual16'] for r in rows):.3f}")
    print(f"  16분 필요 비율(음 가중) {100 * sum(r['needs16Ratio'] * r['used'] for r in rows) / used:.1f}%")
    per_song = sorted(r["needs16Ratio"] for r in rows)
    print(
        f"  곡별 16분 필요 비율 중앙값 {100 * statistics.median(per_song):.1f}%  "
        f"최소 {100 * per_song[0]:.1f}%  최대 {100 * per_song[-1]:.1f}%"
    )


def run_song(workdir: Path) -> None:
    from pipeline import bassclean, beats as beats_mod

    notes_path = workdir / "notes.json"
    beats_path = workdir / "beats.json"
    if not notes_path.exists():
        print(f"[오류] {notes_path}가 없습니다. tools/diag/regen_notes.py로 만들 수 있습니다.")
        return

    notes = bassclean.load_notes(notes_path)
    grid = beats_mod.BeatGrid.from_json(beats_path)
    onsets = sorted(n.start for n in notes)

    # 우리 파이프라인이 실제로 쓰는 격자를 그대로 쓴다. 여기서 다시 피팅하면
    # "가장 잘 맞는 격자"를 재게 되어 질문이 달라진다.
    r = beat_residuals(onsets, grid.beats)
    if r is None:
        print("[오류] 비트 그리드로 판정할 수 없습니다.")
        return

    intervals = [b - a for a, b in zip(grid.beats, grid.beats[1:]) if b > a]
    bpm = 60.0 / statistics.median(intervals) if intervals else 0.0
    pct = [f"{100 * x / r['used']:4.1f}" for x in r["buckets"]]
    print(f"=== 우리 산출물 {workdir.name} ===")
    print(f"  검출 {len(onsets)}음, 판정 {r['used']}음, {bpm:.1f}BPM (variance {grid.bpm_variance:.4f})")
    print(f"  8분 격자 잔차  {r['residual8']:.3f}")
    print(f"  16분 격자 잔차 {r['residual16']:.3f}")
    print(f"  16분 필요 비율 {100 * r['needs16Ratio']:.1f}%")
    print(f"  슬롯 분포 {pct[0]}/{pct[1]}/{pct[2]}/{pct[3]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="리듬 격자 해상도 측정")
    parser.add_argument("--song", type=Path, help="data/<hash> — 우리 산출물로 측정")
    args = parser.parse_args()

    if args.song:
        run_song(args.song)
    else:
        run_idmt()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

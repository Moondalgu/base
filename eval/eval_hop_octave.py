"""한 번에 두 가지를 잰다 — 처리 시간 절반 실험과 옥타브 오탐률.

## 왜 같이 재는가

둘 다 IDMT 정답으로 CREPE를 전곡 돌려야 한다. 따로 돌리면 같은 연산을 두 번
한다. 오디오 처리가 이 프로젝트의 최대 병목이므로 한 번에 끝낸다.

## 1) 처리 시간 절반 실험

CREPE를 100분의 1초(hop=160) 간격으로 훑는데, 50분의 1초(hop=320)로 늘리면
스냅샷 횟수가 절반이라 시간도 절반이 될 것으로 보인다. 대가는 음 시작 위치
정밀도(10ms→20ms)와 아주 짧은 음의 누락이다. 16분음표가 200ms 수준이므로
20ms는 무해할 것으로 **보이지만 재본 적이 없다.**

## 2) 옥타브 오탐률

베이스 극저음역은 기음보다 2차 배음(한 옥타브 위)이 강하게 찍히는 일이 있어
E1을 E2로 잡을 수 있다. CREPE는 프레임당 피치를 하나만 내지만 그 하나가
배음일 수 있다. **이것을 한 번도 재지 않았다.**

온셋은 맞았는데 피치가 정확히 ±12·±24 반음 어긋난 경우를 따로 센다. 옥타브
오탐은 "그냥 틀린 음"과 성질이 다르다 — 운지가 통째로 엉뚱한 자리로 가고,
악보를 보고 따라 치면 원곡과 옥타브가 다르게 들린다.

사용:
    python eval/eval_hop_octave.py
    python eval/eval_hop_octave.py --hops 160 320 --limit 5
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

try:
    import defusedxml.ElementTree as ET
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as ET  # type: ignore[no-redef]

from pipeline import transcribe_crepe  # noqa: E402

IDMT = ROOT / "data" / "_datasets" / "idmt_single"

# 연습 관점 허용 오차. eval_practice.py와 같이 둔다 — 위치가 조금 어긋난 음은
# 악보상 같은 자리에 찍히므로 틀린 것으로 세지 않는다.
TOLERANCE_SEC = 0.15


def truth_events(xml_path: Path) -> list[tuple[float, int]]:
    root = ET.parse(xml_path).getroot()
    out = []
    for ev in root.iter("event"):
        onset, pitch = ev.findtext("onsetSec"), ev.findtext("pitch")
        if onset is None or pitch is None:
            continue
        out.append((float(onset), int(pitch)))
    return sorted(out)


def score(
    ref: list[tuple[float, int]], est: list[tuple[float, int]]
) -> dict:
    """정답과 추정을 맞춰보고 오류를 종류별로 센다.

    온셋만 맞은 짝을 먼저 만들고, 그 안에서 피치를 본다. 그래야 "위치는
    맞는데 옥타브가 틀린 음"을 "못 찾은 음"과 구분할 수 있다.
    """
    used: set[int] = set()
    pitch_ok = octave_err = other_err = 0
    missed = 0
    offsets: list[float] = []

    for onset, pitch in ref:
        best = None
        for i, (e_on, e_pitch) in enumerate(est):
            if i in used:
                continue
            d = abs(e_on - onset)
            if d <= TOLERANCE_SEC and (best is None or d < best[0]):
                best = (d, i, e_pitch)
        if best is None:
            missed += 1
            continue
        d, i, e_pitch = best
        used.add(i)
        offsets.append(d)
        diff = e_pitch - pitch
        if diff == 0:
            pitch_ok += 1
        elif abs(diff) in (12, 24):
            octave_err += 1
        else:
            other_err += 1

    false_notes = len(est) - len(used)
    return {
        "ref": len(ref),
        "est": len(est),
        "pitchOk": pitch_ok,
        "octaveErr": octave_err,
        "otherErr": other_err,
        "missed": missed,
        "falseNotes": false_notes,
        "meanOffsetMs": 1000 * statistics.fmean(offsets) if offsets else 0.0,
    }


def run(hop: int, xmls: list[Path]) -> dict:
    totals = {
        "ref": 0, "est": 0, "pitchOk": 0, "octaveErr": 0,
        "otherErr": 0, "missed": 0, "falseNotes": 0,
    }
    offsets: list[float] = []
    audio_sec = 0.0
    start = time.monotonic()

    for xml in xmls:
        audio = IDMT / "audio" / f"{xml.stem}.wav"
        if not audio.exists():
            continue
        events = transcribe_crepe.transcribe(audio, hop=hop)
        est = [(e[0], int(e[2])) for e in events]
        r = score(truth_events(xml), est)
        for k in totals:
            totals[k] += r[k]
        if r["meanOffsetMs"]:
            offsets.append(r["meanOffsetMs"])
        import soundfile as sf
        audio_sec += sf.info(str(audio)).duration

    elapsed = time.monotonic() - start
    totals["elapsedSec"] = elapsed
    totals["audioSec"] = audio_sec
    totals["realtimeFactor"] = elapsed / audio_sec if audio_sec else 0.0
    totals["meanOffsetMs"] = statistics.fmean(offsets) if offsets else 0.0
    return totals


def report(hop: int, t: dict) -> None:
    ref = max(t["ref"], 1)
    est = max(t["est"], 1)
    print(f"  hop={hop} ({1000 * hop / transcribe_crepe.SR:.0f}ms 간격)")
    print(f"    처리 {t['elapsedSec']:.0f}초 / 오디오 {t['audioSec']:.0f}초 "
          f"= 실시간 {t['realtimeFactor']:.2f}배")
    print(f"    정답 {t['ref']}음, 추정 {t['est']}음")
    print(f"    피치 정확   {t['pitchOk']:4d} ({100 * t['pitchOk'] / ref:5.1f}%)")
    print(f"    **옥타브 오탐** {t['octaveErr']:4d} ({100 * t['octaveErr'] / ref:5.1f}%)")
    print(f"    그 외 피치 오류 {t['otherErr']:4d} ({100 * t['otherErr'] / ref:5.1f}%)")
    print(f"    누락        {t['missed']:4d} ({100 * t['missed'] / ref:5.1f}%)")
    print(f"    거짓 음      {t['falseNotes']:4d} ({100 * t['falseNotes'] / est:5.1f}%)")
    print(f"    평균 온셋 오차 {t['meanOffsetMs']:.1f}ms")


def main() -> int:
    parser = argparse.ArgumentParser(description="hop 실험 + 옥타브 오탐률")
    parser.add_argument("--hops", type=int, nargs="+", default=[160, 320])
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    xmls = sorted((IDMT / "annotation").glob("*.xml"))
    if args.limit:
        xmls = xmls[: args.limit]
    if not xmls:
        print(f"[오류] IDMT 어노테이션이 없습니다: {IDMT / 'annotation'}")
        return 1

    print(f"=== hop 실험 + 옥타브 오탐 (IDMT {len(xmls)}곡, 허용 ±{TOLERANCE_SEC * 1000:.0f}ms) ===")
    results = {}
    for hop in args.hops:
        t = run(hop, xmls)
        results[hop] = t
        report(hop, t)
        print()

    if len(results) >= 2:
        base, alt = sorted(results)[0], sorted(results)[1]
        b, a = results[base], results[alt]
        print(f"=== hop {base} 대 {alt} ===")
        print(f"  처리 시간   {b['elapsedSec']:.0f}초 -> {a['elapsedSec']:.0f}초 "
              f"({100 * a['elapsedSec'] / max(b['elapsedSec'], 1e-9):.0f}%)")
        ref = max(b["ref"], 1)
        for key, label in (
            ("pitchOk", "피치 정확"), ("octaveErr", "옥타브 오탐"),
            ("missed", "누락"), ("falseNotes", "거짓 음"),
        ):
            print(f"  {label:10s} {b[key]:4d} -> {a[key]:4d} "
                  f"({100 * (a[key] - b[key]) / ref:+.1f}pp)")
        print(f"  온셋 오차   {b['meanOffsetMs']:.1f}ms -> {a['meanOffsetMs']:.1f}ms")
        print()
        print("  판정: 처리 시간이 절반 가까이 줄고 피치 정확·누락·거짓 음이")
        print("        거의 안 움직이면 hop을 올리는 것이 이득이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""정답 데이터셋(IDMT-SMT-BASS) 채보 채점 — 두 엔진을 같은 방식으로 잰다.

'악보 보고 연습할 수 있나'라는 관점으로 잰다. F 0.743 같은 값은 온셋 오차
50ms 기준의 연구용 지표다. 75BPM에서 8분음표가 400ms이므로 60ms 어긋난 음은
악보상 같은 자리에 찍히고 연주도 똑같다. 그런데 그 지표는 틀린 것으로 센다.
연습 관점에서 중요한 오류는 종류가 다르다.

  (1) 틀린 음을 배우게 되는가  → 우리 악보에 있는데 실제로는 없는 음 (거짓 음)
  (2) 빠진 음이 있는가          → 정답에 있는데 우리 악보에 없는 음
  (3) 위치만 살짝 어긋난 음     → 연주에는 지장 없음. 위 두 개와 구분해야 한다

사용:
    python eval/eval_idmt.py                      # 기본 crepe
    python eval/eval_idmt.py --engine basic-pitch
"""

from __future__ import annotations

import argparse
import glob
import statistics
import sys
from pathlib import Path

try:
    # 신뢰할 수 없는 XML에 표준 파서를 쓰면 엔티티 확장 공격에 노출된다.
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

DATASET = ROOT / "data" / "_datasets" / "idmt_single"

# 허용 오차. 위 (3)을 오류로 세지 않기 위한 값이다.
TOL = 0.15


def truth_of(stem: str) -> tuple[list[tuple[float, int]], str]:
    """어노테이션에서 (온셋초, MIDI) 목록과 주법 라벨을 뽑는다."""
    root = ET.parse(DATASET / "annotation" / (stem + ".xml")).getroot()
    out: list[tuple[float, int]] = []
    styles: set[str] = set()
    for ev in root.iter("event"):
        try:
            out.append((float(ev.findtext("onsetSec")), int(ev.findtext("pitch"))))
        except (TypeError, ValueError):
            continue
        style = ev.findtext("excitationStyle")
        if style:
            styles.add(style)
    return out, "/".join(sorted(styles))


def match(ref: list[tuple[float, int]], est: list[tuple[float, int]],
          tol: float = TOL) -> int:
    """온셋+피치가 tol 안에서 맞는 쌍의 개수. 한 추정음은 한 번만 쓰인다."""
    used: set[int] = set()
    tp = 0
    for t, p in ref:
        best, best_delta = None, tol
        for i, (et, ep) in enumerate(est):
            if i in used or ep != p:
                continue
            delta = abs(et - t)
            if delta <= best_delta:
                best, best_delta = i, delta
        if best is not None:
            used.add(best)
            tp += 1
    return tp


def transcribe_all(engine: str) -> list[tuple[str, str, list, list]]:
    """데이터셋 전체를 채보한다. 엔진에 따라 후처리 경로가 갈린다."""
    from pipeline import bassclean

    if engine == "crepe":
        from pipeline.transcribe_crepe import transcribe
        monophonic = True
    else:
        from pipeline.transcribe import transcribe
        monophonic = False

    data = []
    for path in sorted(glob.glob(str(DATASET / "audio" / "*.wav"))):
        wav = Path(path)
        ref, style = truth_of(wav.stem)
        notes, _ = bassclean.clean(
            transcribe(wav, verbose=False),
            monophonic_source=monophonic,
        )
        data.append((wav.stem, style, ref, [(n.start, n.pitch) for n in notes]))
        print(f"  {wav.stem} 완료 ({len(notes)}음)", flush=True)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="IDMT-SMT-BASS 정답 채점")
    parser.add_argument("--engine", default="crepe", choices=["crepe", "basic-pitch"])
    args = parser.parse_args()

    print(f"=== 엔진: {args.engine} — {DATASET.name} 채보 중 ===")
    data = transcribe_all(args.engine)

    print()
    print("=== 허용 오차별 정확도 — 오차 얼마가 '타이밍 미세오차'인가 ===")
    print()
    print("%-12s %8s %8s %8s   %s" % ("허용오차", "P", "R", "F", "의미"))
    print("-" * 68)
    meaning = {0.05: "연구 표준", 0.20: "75BPM 16분음표 = 200ms"}
    for tol in (0.05, 0.10, 0.15, 0.20, 0.30):
        ps, rs, fs = [], [], []
        for _, _, ref, est in data:
            tp = match(ref, est, tol)
            p = tp / len(est) if est else 0.0
            r = tp / len(ref) if ref else 0.0
            ps.append(p)
            rs.append(r)
            fs.append(2 * p * r / (p + r) if p + r else 0.0)
        print("%-12s %8.3f %8.3f %8.3f   %s"
              % ("±%dms" % int(tol * 1000), statistics.fmean(ps),
                 statistics.fmean(rs), statistics.fmean(fs), meaning.get(tol, "")))

    print()
    print(f"=== 오류를 종류별로 나눠 본다 (허용 ±{int(TOL * 1000)}ms 기준) ===")
    print("  '거짓 음' = 우리 악보에 있는데 그 근처에 그 음높이의 정답이 없는 것")
    print("            → 이게 틀린 음을 배우게 만드는 유일한 오류다")
    print()
    print("%-6s %6s | %-28s | %-24s" % ("트랙", "주법", "우리 악보", "정답 대비"))
    print("-" * 74)
    tot_est = tot_false = tot_ref = tot_missed = 0
    per_track: list[tuple[float, float]] = []
    for stem, style, ref, est in data:
        tp = match(ref, est)
        false_notes = len(est) - tp
        missed = len(ref) - tp
        tot_est += len(est)
        tot_false += false_notes
        tot_ref += len(ref)
        tot_missed += missed
        per_track.append((
            false_notes / len(est) if est else 0.0,
            missed / len(ref) if ref else 0.0,
        ))
        print("%-6s %6s | %3d음 중 거짓 %3d (%4.1f%%) | 정답 %3d 중 누락 %3d (%4.1f%%)"
              % (stem, style[:6], len(est), false_notes,
                 100 * false_notes / max(1, len(est)),
                 len(ref), missed, 100 * missed / max(1, len(ref))))

    print("-" * 74)
    print("합계: 우리 악보 %d음 중 거짓 %d음 (%.1f%%)  |  정답 %d음 중 누락 %d음 (%.1f%%)"
          % (tot_est, tot_false, 100 * tot_false / max(1, tot_est),
             tot_ref, tot_missed, 100 * tot_missed / max(1, tot_ref)))

    print()
    print("=== 주법별 (낮은 거짓 음 순. 낮을수록 믿고 연습 가능) ===")
    by: dict[str, list[int]] = {}
    for i, (_, style, _, _) in enumerate(data):
        by.setdefault(style or "?", []).append(i)
    rows = []
    for style, idxs in by.items():
        false_rate = statistics.fmean(per_track[i][0] for i in idxs)
        miss_rate = statistics.fmean(per_track[i][1] for i in idxs)
        fs = []
        for i in idxs:
            _, _, ref, est = data[i]
            tp = match(ref, est)
            p = tp / len(est) if est else 0.0
            r = tp / len(ref) if ref else 0.0
            fs.append(2 * p * r / (p + r) if p + r else 0.0)
        rows.append((false_rate, style, len(idxs), miss_rate, statistics.fmean(fs)))
    for false_rate, style, n, miss_rate, f in sorted(rows):
        print("  %-8s %2d곡  F %.3f  거짓 음 %5.1f%%  누락 %5.1f%%"
              % (style, n, f, 100 * false_rate, 100 * miss_rate))

    # 전체 합계 기준 P/R/F도 같이 낸다. 곡별 평균은 짧은 곡의 가중치가 커진다.
    tp_all = tot_est - tot_false
    p_all = tp_all / max(1, tot_est)
    r_all = tp_all / max(1, tot_ref)
    f_all = 2 * p_all * r_all / (p_all + r_all) if p_all + r_all else 0.0
    print()
    print("=== 음 단위 합계 기준 (±%dms) ===" % int(TOL * 1000))
    print("  P %.3f  R %.3f  F %.3f" % (p_all, r_all, f_all))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

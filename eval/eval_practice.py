"""'악보 보고 연습할 수 있나'라는 관점으로 다시 잰다.

F 0.743은 온셋 오차 50ms 기준 연구용 지표다. 75BPM에서 8분음표가 400ms이므로
60ms 어긋난 음은 악보상 같은 자리에 찍히고 연주도 똑같다. 그런데 그 지표는
틀린 것으로 센다. 연습 관점에서 중요한 것은 종류가 다르다.

  (1) 틀린 음을 배우게 되는가  → 우리 악보에 있는데 실제로는 없는 음 (거짓 음)
  (2) 빠진 음이 있는가          → 정답에 있는데 우리 악보에 없는 음
  (3) 위치만 살짝 어긋난 음     → 연주에는 지장 없음. 위 두 개와 구분해야 한다
"""
import glob
import statistics
import sys
from pathlib import Path

try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path("apps/worker").resolve()))
from pipeline.transcribe import transcribe
from pipeline import bassclean

ROOT = Path("data/_datasets/idmt_single")


def truth_of(stem):
    root = ET.parse(ROOT / "annotation" / (stem + ".xml")).getroot()
    out, styles = [], set()
    for ev in root.iter("event"):
        try:
            out.append((float(ev.findtext("onsetSec")), int(ev.findtext("pitch"))))
        except (TypeError, ValueError):
            continue
        s = ev.findtext("excitationStyle")
        if s:
            styles.add(s)
    return out, "/".join(sorted(styles))


data = []
for wav in sorted(glob.glob(str(ROOT / "audio" / "*.wav"))):
    wav = Path(wav)
    tr, style = truth_of(wav.stem)
    notes, _ = bassclean.clean(transcribe(wav, verbose=False))
    data.append((wav.stem, style, tr, [(n.start, n.pitch) for n in notes]))

print("=== 허용 오차별 정확도 — 오차 얼마가 '타이밍 미세오차'인가 ===")
print()
print("%-12s %8s %8s %8s   %s" % ("허용오차", "P", "R", "F", "의미"))
print("-" * 68)
meaning = {0.05: "연구 표준", 0.10: "", 0.15: "", 0.20: "75BPM 16분음표 = 200ms", 0.30: ""}
for tol in (0.05, 0.10, 0.15, 0.20, 0.30):
    ps, rs, fs = [], [], []
    for _, _, tr, est in data:
        used = set()
        tp = 0
        for t, p in tr:
            best, bd = None, tol
            for i, (et, ep) in enumerate(est):
                if i in used or ep != p:
                    continue
                d = abs(et - t)
                if d <= bd:
                    best, bd = i, d
            if best is not None:
                used.add(best); tp += 1
        P = tp / len(est) if est else 0
        R = tp / len(tr) if tr else 0
        F = 2 * P * R / (P + R) if P + R else 0
        ps.append(P); rs.append(R); fs.append(F)
    print("%-12s %8.3f %8.3f %8.3f   %s"
          % ("±%dms" % int(tol * 1000), statistics.fmean(ps), statistics.fmean(rs),
             statistics.fmean(fs), meaning.get(tol, "")))

print()
print("=== 오류를 종류별로 나눠 본다 (허용 ±150ms 기준) ===")
print("  '거짓 음' = 우리 악보에 있는데 그 근처에 그 음높이의 정답이 없는 것")
print("            → 이게 틀린 음을 배우게 만드는 유일한 오류다")
print()
TOL = 0.15
print("%-6s %6s | %-28s | %-24s" % ("트랙", "주법", "우리 악보", "정답 대비"))
print("-" * 74)
tot_est = tot_false = tot_ref = tot_missed = 0
false_rates = []
for stem, style, tr, est in data:
    used = set(); tp = 0
    for t, p in tr:
        best, bd = None, TOL
        for i, (et, ep) in enumerate(est):
            if i in used or ep != p:
                continue
            d = abs(et - t)
            if d <= bd:
                best, bd = i, d
        if best is not None:
            used.add(best); tp += 1
    false_notes = len(est) - tp
    missed = len(tr) - tp
    tot_est += len(est); tot_false += false_notes
    tot_ref += len(tr); tot_missed += missed
    false_rates.append(false_notes / len(est) if est else 0)
    print("%-6s %6s | %3d음 중 거짓 %3d (%4.1f%%) | 정답 %3d 중 누락 %3d (%4.1f%%)"
          % (stem, style[:6], len(est), false_notes, 100 * false_notes / max(1, len(est)),
             len(tr), missed, 100 * missed / max(1, len(tr))))

print("-" * 74)
print("합계: 우리 악보 %d음 중 거짓 %d음 (%.1f%%)  |  정답 %d음 중 누락 %d음 (%.1f%%)"
      % (tot_est, tot_false, 100 * tot_false / tot_est,
         tot_ref, tot_missed, 100 * tot_missed / tot_ref))
print()
print("=== 주법별 거짓 음 비율 (낮을수록 믿고 연습 가능) ===")
by = {}
for i, (stem, style, tr, est) in enumerate(data):
    by.setdefault(style or "?", []).append(false_rates[i])
for st, v in sorted(by.items(), key=lambda kv: statistics.fmean(kv[1])):
    print("  %-8s %d곡  거짓 음 %.1f%%" % (st, len(v), 100 * statistics.fmean(v)))

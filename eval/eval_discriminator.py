"""판별자 후보를 정답으로 채점한다.

문제: 같은 피치가 이어 나올 때 그것이
  (A) basic-pitch가 한 음을 쪼갠 '조각'      → 병합해야 함
  (B) 연주자가 다시 친 '재타격'              → 병합하면 안 됨
인지 가려야 한다. 간격만으로는 못 가른다는 것이 이미 확인됐다.

정답으로 라벨을 만든다: 뒤쪽 음의 온셋 근처(50ms)에 정답 온셋이 있으면 (B),
없으면 (A)다. 그러면 각 판별자 후보를 정확도로 채점할 수 있다.

후보
  1) 진폭 비율        amp(B) / amp(A)      — 재타격은 다시 오른다
  2) 온셋 간격        B.start - A.start    — 현재 쓰는 것
  3) 둘의 조합
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
from pipeline.bassclean import (
    Note, HARMONIC_INTERVALS, BASS_MIDI_MIN, BASS_MIDI_MAX,
    MIN_NOTE_SEC, MIN_AMPLITUDE, OVERLAP_TOLERANCE,
    LEAKAGE_CONFIDENT_AMPLITUDE, LEAKAGE_REGISTER_MARGIN, LEAKAGE_STRONG_AMPLITUDE,
)

ROOT = Path("data/_datasets/idmt_single")
TOL = 0.05


def truth_onsets(stem):
    root = ET.parse(ROOT / "annotation" / (stem + ".xml")).getroot()
    out = []
    for ev in root.iter("event"):
        try:
            out.append((float(ev.findtext("onsetSec")), int(ev.findtext("pitch"))))
        except (TypeError, ValueError):
            pass
    return out


def upto_mono(raw):
    """병합 직전까지의 파이프라인 (현재 코드와 동일 순서)."""
    notes = [Note(start=float(e[0]), end=float(e[1]), pitch=int(e[2]),
                  amplitude=float(e[3]), detected_end=float(e[1])) for e in raw]
    notes.sort(key=lambda n: (n.start, -n.amplitude))
    notes = [n for n in notes if not any(
        (n.pitch - b.pitch) in HARMONIC_INTERVALS and n.overlaps(b) and n.amplitude <= b.amplitude
        for b in notes if b is not n)]
    keep = []
    for n in notes:
        p = n.pitch
        while p > BASS_MIDI_MAX:
            p -= 12
        while p < BASS_MIDI_MIN and p + 12 <= BASS_MIDI_MAX:
            p += 12
        if BASS_MIDI_MIN <= p <= BASS_MIDI_MAX:
            n.pitch = p
            keep.append(n)
    notes = [n for n in keep if n.duration >= MIN_NOTE_SEC and n.amplitude >= MIN_AMPLITUDE]
    conf = [n.pitch for n in notes if n.amplitude >= LEAKAGE_CONFIDENT_AMPLITUDE]
    if conf:
        ceil_ = statistics.median(conf) + LEAKAGE_REGISTER_MARGIN
        notes = [n for n in notes
                 if not (n.pitch > ceil_ and n.amplitude < LEAKAGE_STRONG_AMPLITUDE)]
    notes.sort(key=lambda n: (n.start, -n.amplitude))
    mono = []
    for note in notes:
        if not mono:
            mono.append(note); continue
        prev = mono[-1]
        if note.start < prev.end - OVERLAP_TOLERANCE:
            if note.amplitude > prev.amplitude:
                prev.end = note.start
                if prev.duration < MIN_NOTE_SEC:
                    mono.pop()
                mono.append(note)
            continue
        if note.start < prev.end:
            prev.end = note.start
        mono.append(note)
    return mono


pairs = []   # (라벨, 진폭비, 온셋간격, 진폭A, 진폭B)
for wav in sorted(glob.glob(str(ROOT / "audio" / "*.wav"))):
    wav = Path(wav)
    tr = truth_onsets(wav.stem)
    notes = upto_mono(transcribe(wav, verbose=False))
    for a, b in zip(notes, notes[1:]):
        if a.pitch != b.pitch:
            continue
        # 뒤 음의 온셋 근처에 같은 피치 정답 온셋이 있나?
        is_attack = any(abs(t - b.start) <= TOL and p == b.pitch for t, p in tr)
        ratio = b.amplitude / (a.amplitude + 1e-9)
        pairs.append((("재타격" if is_attack else "조각"), ratio, b.start - a.start,
                      a.amplitude, b.amplitude))

atk = [p for p in pairs if p[0] == "재타격"]
frg = [p for p in pairs if p[0] == "조각"]
print("=== 같은 피치 인접쌍 %d개 (재타격 %d / 조각 %d) ===" % (len(pairs), len(atk), len(frg)))
print()


def dist(name, idx, arr):
    v = sorted(x[idx] for x in arr)
    if not v:
        return
    q = lambda f: v[min(len(v) - 1, int(len(v) * f))]
    print("  %-8s n=%3d  중앙값 %.3f  [10%% %.3f | 25%% %.3f | 75%% %.3f | 90%% %.3f]"
          % (name, len(v), statistics.median(v), q(.10), q(.25), q(.75), q(.90)))


print("진폭 비율 amp(B)/amp(A):")
dist("재타격", 1, atk); dist("조각", 1, frg)
print()
print("온셋 간격 (초):")
dist("재타격", 2, atk); dist("조각", 2, frg)
print()

print("=== 판별자별 정확도 (조각으로 맞히면 병합, 재타격이면 유지) ===")
print("%-34s %8s %8s %8s" % ("규칙", "정확도", "조각적발", "재타격보존"))
print("-" * 62)


def evaluate(name, is_fragment):
    tp = sum(1 for p in frg if is_fragment(p))       # 조각을 조각으로
    tn = sum(1 for p in atk if not is_fragment(p))   # 재타격을 재타격으로
    acc = (tp + tn) / len(pairs) if pairs else 0
    print("%-34s %7.1f%% %7.1f%% %7.1f%%"
          % (name, 100 * acc, 100 * tp / max(1, len(frg)), 100 * tn / max(1, len(atk))))
    return acc


evaluate("현재: 간격 < 0.15s", lambda p: p[2] < 0.15)
evaluate("간격 < 0.08s", lambda p: p[2] < 0.08)
for thr in (0.7, 0.8, 0.9, 1.0):
    evaluate("진폭비 < %.1f" % thr, lambda p, t=thr: p[1] < t)
for thr in (0.8, 0.9, 1.0):
    evaluate("간격<0.15 AND 진폭비<%.1f" % thr,
             lambda p, t=thr: p[2] < 0.15 and p[1] < t)
for thr in (0.8, 0.9):
    evaluate("간격<0.25 AND 진폭비<%.1f" % thr,
             lambda p, t=thr: p[2] < 0.25 and p[1] < t)
print()
print("참고: 전부 '재타격'이라 답하면 정확도 %.1f%%, 전부 '조각'이면 %.1f%%"
      % (100 * len(atk) / len(pairs), 100 * len(frg) / len(pairs)))

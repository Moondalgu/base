"""quantize가 마디를 넘는 음의 실제 길이를 보존하는지 확인한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("apps/worker").resolve()))
from pipeline.bassclean import Note
from pipeline.beats import BeatGrid
from pipeline.quantize import MAX_DURATION_BARS, quantize

# 120BPM 4/4 = 비트 0.5s, 마디 2.0s, 슬롯 0.125s
beats = [i * 0.5 for i in range(41)]
downbeats = [i * 2.0 for i in range(11)]
grid = BeatGrid(beats=beats, downbeats=downbeats, beats_per_bar=4,
                median_bpm=120.0, bpm_variance=0.0)

notes = [
    # 1마디 슬롯 12에서 시작해 2마디 슬롯 4까지 (8슬롯) — 마디를 4슬롯 넘는다
    Note(start=1.5, end=2.5, pitch=28, amplitude=0.9),
    # 3마디 슬롯 0에서 2.5마디 분량 (40슬롯)
    Note(start=4.0, end=9.0, pitch=31, amplitude=0.9),
    # 6마디 슬롯 0에서 터무니없이 긴 음 (상한 확인) — 10마디 분량
    Note(start=10.0, end=30.0, pitch=33, amplitude=0.9),
]

score = quantize(notes, grid)
spb = score.bars[0].slots_per_bar
print("slots_per_bar=%d, 상한=%d슬롯(%d마디)" % (spb, spb * MAX_DURATION_BARS, MAX_DURATION_BARS))
fails = []
for bar in score.bars:
    for n in bar.notes:
        crosses = n.slot + n.duration_slots > spb
        print("  %d마디 슬롯%-3d dur=%-3d pitch=%d %s"
              % (bar.index, n.slot, n.duration_slots, n.pitch,
                 "(마디 넘김)" if crosses else ""))

# 검증 대상은 **길이 보존과 상한**이다. 절대 위치(마디·슬롯)는 검증하지 않는다 —
# quantize.choose_phase가 "곡의 첫 음은 거의 항상 마디 1박"이라는 전제로 마디선을
# 첫 음에 다시 맞추기 때문에(PRD A.9), 입력 시각으로 위치를 예측할 수 없다.
# 위치까지 못 박으면 위상 교정 로직을 손댈 때마다 이 테스트가 깨진다.
durations = sorted(n.duration_slots for b in score.bars for n in b.notes)
want_durations = sorted([8, 40, spb * MAX_DURATION_BARS])
print()
print("기대 길이: %s" % (want_durations,))
print("실제 길이: %s" % (durations,))
if durations != want_durations:
    fails.append("길이 보존 실패 — 마디 경계로 잘리거나 상한이 안 걸렸다")

# 마디보다 긴 음은 **어느 슬롯에서 시작해도** 반드시 마디를 넘는다. 이건 위상과
# 무관하게 성립하는 조건이라 안전하게 검증할 수 있다. 반대로 마디보다 짧은 음은
# 위상에 따라 넘을 수도 안 넘을 수도 있으므로 조건에 넣지 않는다.
longer_than_bar = [
    (b.index, n.slot, n.duration_slots)
    for b in score.bars for n in b.notes
    if n.duration_slots > spb
]
not_crossing = [x for x in longer_than_bar if x[1] + x[2] <= spb]
print("마디보다 긴 음: %d개 %s" % (len(longer_than_bar), longer_than_bar))
if len(longer_than_bar) != 2:
    fails.append("마디보다 긴 음이 2개여야 한다 (40슬롯·64슬롯)")
if not_crossing:
    fails.append("마디보다 긴데 마디를 넘지 않는 음이 있다: %s" % (not_crossing,))

print("실패 %d건" % len(fails))
sys.exit(1 if fails else 0)

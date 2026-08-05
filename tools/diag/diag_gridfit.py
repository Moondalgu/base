"""위상 피팅 프로토타입: '단일 전역 템포 + 위상'을 베이스 스템 온셋에 맞춘다.

비교 대상
  A) 현재 방식 — beat_this가 준 개별 비트를 그대로 마디 경계로 사용 (불균일)
  B) 제안 방식 — 템포 하나 + 위상 하나로 균일 그리드를 만들고, 베이스 스템의
     온셋 에너지가 마디 시작에 가장 많이 걸리도록 둘을 함께 탐색

평가 지표(정답 악보 불필요): 각 마디 시작이 실제 소리의 강한 변화 지점에서
얼마나 떨어져 있는가. 중앙값과 표준편차가 낮을수록 그리드가 음악에 잠긴 것.
"""
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path("apps/worker").resolve()))
import librosa
from pipeline.beats import BeatGrid
from pipeline.quantize import _bar_beat_spans

WORK = Path("data/975e4e588d282666")
SR = 22050
HOP = 256
BPB = 4

m = json.loads((WORK / "manifest.json").read_text(encoding="utf-8"))
grid = BeatGrid.from_json(WORK / "beats.json")
spans = _bar_beat_spans(grid, m.get("phase") or 0)

y, sr = librosa.load(str(WORK / "stems" / "bass.wav"), sr=SR, mono=True)
env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
env = env / (env.max() + 1e-9)
t_env = librosa.frames_to_time(np.arange(len(env)), sr=sr, hop_length=HOP)

# 베이스가 실제로 울리는 구간만 평가 대상으로 (인트로 무연주 구간 제외)
active = t_env[env > 0.08]
T0, T1 = (float(active[0]), float(active[-1])) if active.size else (0.0, t_env[-1])
print("베이스 활동 구간: %.1f ~ %.1fs" % (T0, T1))
print()


def strong_onsets(min_strength=0.15):
    pk = librosa.util.peak_pick(env, pre_max=4, post_max=4, pre_avg=8, post_avg=8,
                                delta=min_strength, wait=6)
    return t_env[pk]


onsets = strong_onsets()
onsets = onsets[(onsets >= T0) & (onsets <= T1)]
print("강한 온셋 %d개 검출" % len(onsets))


def scatter(bar_starts, label):
    """각 마디 시작과 가장 가까운 강한 온셋 사이 거리."""
    ds = []
    for b in bar_starts:
        if b < T0 or b > T1:
            continue
        if onsets.size == 0:
            continue
        ds.append(float(np.min(np.abs(onsets - b))))
    if not ds:
        print("  %s: 평가 불가" % label)
        return None
    print("  %-34s 마디 %3d | 중앙값 %.3fs | 평균 %.3fs | 표준편차 %.3fs | 0.1s내 %d%%"
          % (label, len(ds), statistics.median(ds), statistics.fmean(ds),
             statistics.pstdev(ds), round(100 * sum(1 for d in ds if d <= 0.1) / len(ds))))
    return statistics.fmean(ds)


print()
print("=== A) 현재 방식 (개별 비트 그대로) ===")
cur_starts = [s[0] for s in spans]
scatter(cur_starts, "현재 그리드")

print()
print("=== B) 단일 템포 + 위상 피팅 ===")
# 온셋 에너지를 마디 시작에 최대한 걸리게 하는 (bpm, phase) 탐색
best = None
for bpm in np.arange(70.0, 80.01, 0.05):
    bar_len = BPB * 60.0 / bpm
    for ph in np.arange(0.0, bar_len, 0.01):
        starts = np.arange(T0 + ph, T1, bar_len)
        if starts.size < 8:
            continue
        idx = np.clip((starts / (HOP / sr)).astype(int), 0, len(env) - 1)
        sc = float(env[idx].sum()) / starts.size
        if best is None or sc > best[0]:
            best = (sc, float(bpm), float(ph), starts)
sc, bpm, ph, starts = best
print("  최적: %.2f BPM / 위상 %+.3fs / 마디길이 %.3fs / 점수 %.4f"
      % (bpm, ph, BPB * 60.0 / bpm, sc))
print("  (beat_this median = %.2f BPM)" % grid.median_bpm)
scatter(list(starts), "피팅된 균일 그리드")

print()
print("=== 참고: 현재 그리드의 마디 길이 편차 ===")
lens = [s[-1] - s[0] for s in spans if s[-1] > s[0]]
print("  마디 길이 중앙값 %.3fs / 최소 %.3f / 최대 %.3f / 표준편차 %.3f"
      % (statistics.median(lens), min(lens), max(lens), statistics.pstdev(lens)))

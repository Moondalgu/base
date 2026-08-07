"""재타현 분리 — 같은 음을 다시 뜯은 자리를 찾아 한 음을 여러 음으로 나눈다.

## 왜 필요한가 (측정으로 확정된 병목)

`transcribe_crepe._segment`는 **피치가 바뀌거나 무성이 될 때만** 음을 자른다.
CREPE는 프레임마다 피치 하나를 내므로, 같은 음(예: 4현 개방 E)을 세 번 뜯어도
피치가 안 바뀌어 **경계가 보이지 않는다.** 그래서 3타를 1타로 적는다.

실측(연습영상 정답 47마디, 전부 3타):

    검출: 2 3 4 2 2 3 4 3 4 3 4 1 5 3 2 2 4 3 3 3   <- 3타를 맞힌 마디 8/20
    1타로 적힌 마디(27·31·43·63·67·71)는 **엉뚱한 피치가 0개**다.
    즉 피치는 맞게 잡고 타현 횟수만 놓쳤다.

오차의 정체를 갈라보니:

| 정체 | 비율 |
|---|---|
| 음 쪼개짐(한 음이 여러 조각) | 1% — **원인 아니다** |
| 다른 피치 끼어듦 | 21% |
| **재타현 누락** | 마디의 34% |

IDMT 정답에서도 같은 방향이다: 948음 중 앞 음과 같은 피치가 211음(22%)이고,
우리가 놓친 136음 중 32음(24%)이 그 부류다.

## 무엇으로 찾는가 — 진폭만 보면 안 된다

`playing.json`의 `compressorPumping`이 경고하는 함정이 정확히 여기다. 베이스
녹음에는 컴프레서가 걸려 있어서 **한 번 뜯고 유지한 음도 볼륨이 줄었다 다시
오른다.** 진폭 재상승만 보면 그 출렁임을 재타현으로 세어 1타를 3~4타로 쪼갠다.

그래서 두 신호를 **함께** 본다.

1. **어택 트랜지언트** — 재타현에는 고주파 성분의 급상승(스펙트럼 플럭스 봉우리)이
   있고, 컴프레서 회복에는 없다. 이것이 주 신호다.
2. **구간 RMS 재상승** — 보조. 트랜지언트가 있어도 소리가 계속 작아지고만 있으면
   재타현으로 보지 않는다.

## 어디에 두는가

채보 직후, `bassclean` 전이다. bassclean의 필터들은 "음 하나"를 전제로 판단하므로
나눌 것은 먼저 나눠야 한다. 음량 게이트는 그 뒤에 온다 — 게이트는 나뉜 음 각각의
음량을 보고 판정해야 맞다.

## **이 모듈은 기본으로 꺼져 있다 — 측정에서 졌다** (2026-08-07)

만들어서 재봤고 **효과가 없었다.** `eval/eval_reattack.py --sweep` 결과:

| 설정 | IDMT F | 거짓음 | 재타현회복 | 실곡 반복 47마디 |
|---|---|---|---|---|
| 끄기(기준선) | 0.879 | 9.8% | **84.8%** | **40/47** |
| RMS 조건 강함(1.0) | 0.878 | 9.9% | 84.8% | 40/47 |
| RMS 허용 0.9 | 0.869 | 12.0% | 85.3% | **0/47** |
| RMS 조건 없음 | 0.858 | 14.1% | 85.3% | 0/47 |

**쓸 수 있는 중간값이 없다.**

- RMS 조건을 강하게 두면 분할이 거의 일어나지 않는다(IDMT 나눔 0건, 실곡 14건).
  후보의 대부분이 거부된다 — 실곡에서 841건이 "음량이 오르지 않았다"로 걸렸다.
  베이스는 감쇠하는 악기라 재타현 지점의 뒤 구간 평균이 앞 구간을 넘지 못한다.
- 조건을 조금만 풀면(0.9) 즉시 과분할로 넘어간다. 거짓음이 9.9% → 12.0%,
  실곡 반복 구간이 40/47에서 **0/47로 붕괴**한다.
- `PEAK_RATIO`를 0.20~0.60으로 훑어도 결과가 꿈쩍하지 않았다. 묶여 있는 것은
  플럭스 문턱이 아니라 RMS 조건이었다.

## 애초에 되찾을 여지가 작았다

진단 단계에서 "재타현 누락이 주범"이라고 봤는데, IDMT로 재보니 **같은 피치 재타현
회복률이 이미 84.8%**다. 정답 948음 중 같은 피치가 211음(22%)이므로 완벽히 고쳐도
전체 개선 상한이 22% × 15.2% = **3.3pp**다. 실곡 반복 구간의 "1타로 적힌 마디"가
눈에 띄어 크게 보였을 뿐이다.

**남은 더 큰 몫은 "다른 피치 끼어듦"(검출 음의 21%)이다.** 그쪽을 봐야 한다.

## 그래도 남겨두는 이유

`USE_REATTACK = False`로 껐고 지운 것은 아니다. 두 가지 때문이다.

1. **다른 신호로 다시 시도할 자리가 여기다.** 드럼 스템의 킥 위치(`playing.json`
   kickLock: 타격의 80% 이상이 킥과 일치)를 보조로 쓰면 "어택이 있어야 할 자리"를
   알 수 있다. 플럭스 봉우리 하나만으로 판정하는 지금 구조보다 근거가 강하다.
2. 이 측정 표가 **같은 것을 또 시도하지 않게 하는 기록**이다. 삭제하면 다음 세션이
   같은 가설로 다시 만든다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SR = 22050
# 5.8ms. 어택 봉우리를 놓치지 않을 해상도이고 스펙트럼 플럭스 온셋 검출의
# 통상 범위다. 여기를 늘리면 촘촘한 재타현(16분 간격 200ms)에서 봉우리 두 개가
# 한 프레임에 뭉친다.
HOP = 128

# 어택 트랜지언트를 볼 주파수 대역(Hz).
#
# 기음이 아니라 **뜯는 소리**를 본다. 베이스 기음은 41~200Hz이고 그 대역은
# 컴프레서 출렁임이 그대로 실려 재타현과 구분되지 않는다. 손가락·픽이 줄을
# 때리는 성분은 훨씬 위에 있다.
FLUX_FMIN, FLUX_FMAX = 800.0, 6000.0

# 이보다 짧은 음은 나누지 않는다. 나눌 여지가 없다.
MIN_SPLIT_SEC = 0.18

# 나눈 조각의 최소 길이. 이보다 짧게 잘리면 노이즈를 음으로 만드는 것이다.
# `bassclean.MIN_NOTE_SEC`(0.06)보다 넉넉하게 둔다 — 어차피 그쪽에서 한 번 더
# 걸러지므로 여기서 아슬아슬한 것을 만들 이유가 없다.
MIN_PIECE_SEC = 0.09

# 플럭스 봉우리를 재타현으로 인정하는 문턱. 그 음 **자신의 첫 어택**을 기준으로
# 한 상대값이다.
#
# 절대값을 쓰면 안 된다 — 곡마다 녹음 레벨이 다르고, 세게 뜯은 음과 약하게 뜯은
# 음의 어택 크기가 다르다. 자기 어택과 비교하면 그 둘이 자동으로 정규화된다.
PEAK_RATIO = 0.35

# 재타현 사이 최소 간격(초). 이보다 촘촘한 봉우리는 한 번의 어택이 만든
# 여러 봉우리로 본다(픽 어택은 두세 프레임에 걸쳐 흔들린다).
MIN_GAP_SEC = 0.09

# 이 모듈을 파이프라인에서 쓸 것인가.
#
# **False다. 측정에서 졌다.** 근거는 모듈 머리말의 표에 있다. 켜려면 그 표를
# 다시 만들어(`eval/eval_reattack.py --sweep`) 기준선을 이겼는지 확인해야 한다.
USE_REATTACK = False


@dataclass
class ReattackReport:
    notes_in: int = 0
    notes_out: int = 0
    candidates: int = 0        # 길이 조건을 넘어 검사한 음
    split_notes: int = 0       # 실제로 나뉜 음
    added: int = 0             # 늘어난 음 수
    rejected_short: int = 0    # 조각이 너무 짧아 버린 후보
    rejected_quiet: int = 0    # RMS가 오르지 않아 버린 후보

    def to_dict(self) -> dict:
        return {
            "notesIn": self.notes_in,
            "notesOut": self.notes_out,
            "candidates": self.candidates,
            "splitNotes": self.split_notes,
            "added": self.added,
            "rejectedShort": self.rejected_short,
            "rejectedQuiet": self.rejected_quiet,
        }


def split_reattacks(
    note_events: list[tuple],
    audio_path: Path,
    *,
    peak_ratio: float = PEAK_RATIO,
    min_split_sec: float = MIN_SPLIT_SEC,
    min_piece_sec: float = MIN_PIECE_SEC,
    min_gap_sec: float = MIN_GAP_SEC,
    require_rms_rise: bool = True,
    rms_tolerance: float = 1.0,
    verbose: bool = False,
) -> tuple[list[tuple], ReattackReport]:
    """긴 음 안에서 재타현 자리를 찾아 나눈다.

    note_events는 `transcribe*`의 반환 형식 그대로다
    (start, end, pitch, amplitude, pitch_bends).

    나눈 조각은 피치·amplitude를 원본에서 물려받는다. **amplitude는 CREPE
    확신도이므로 나눠도 그대로 유효하다** — 음량이 아니다.
    """
    import numpy as np

    report = ReattackReport(notes_in=len(note_events))
    if not note_events or not Path(audio_path).exists():
        report.notes_out = len(note_events)
        return note_events, report

    flux, rms, frame_sec = _analyse(audio_path)
    if flux is None:
        report.notes_out = len(note_events)
        return note_events, report

    out: list[tuple] = []
    for event in note_events:
        start, end = float(event[0]), float(event[1])
        if end - start < min_split_sec:
            out.append(event)
            continue

        report.candidates += 1
        a = int(start / frame_sec)
        b = min(len(flux), int(end / frame_sec))
        if b - a < 4:
            out.append(event)
            continue

        # 이 음 자신의 첫 어택 크기. 상대 문턱의 기준이다.
        head = flux[a : min(b, a + max(2, int(0.04 / frame_sec)))]
        reference = float(head.max()) if len(head) else 0.0
        if reference <= 1e-9:
            out.append(event)
            continue

        threshold = reference * peak_ratio
        min_gap_frames = max(1, int(min_gap_sec / frame_sec))
        # 첫 어택 직후 구간은 건너뛴다 — 자기 어택의 꼬리를 재타현으로 세지 않는다.
        cursor = a + min_gap_frames

        cuts: list[int] = []
        while cursor < b - 1:
            window = flux[cursor : min(b, cursor + min_gap_frames)]
            if not len(window):
                break
            local = int(np.argmax(window))
            idx = cursor + local
            value = float(flux[idx])
            if value >= threshold and 0 < idx < len(flux) - 1 \
                    and flux[idx] >= flux[idx - 1] and flux[idx] >= flux[idx + 1]:
                if require_rms_rise and not _rms_rises(
                    rms, idx, min_gap_frames, tolerance=rms_tolerance
                ):
                    report.rejected_quiet += 1
                else:
                    cuts.append(idx)
                    cursor = idx + min_gap_frames
                    continue
            cursor += min_gap_frames

        if not cuts:
            out.append(event)
            continue

        # 조각 경계를 시간으로 바꾸고 너무 짧은 것은 버린다.
        bounds = [start] + [idx * frame_sec for idx in cuts] + [end]
        pieces: list[tuple[float, float]] = []
        for lo, hi in zip(bounds, bounds[1:]):
            if hi - lo >= min_piece_sec:
                pieces.append((lo, hi))
            elif pieces:
                # 짧은 조각은 앞 조각에 붙인다. 버리면 라인에 구멍이 난다.
                pieces[-1] = (pieces[-1][0], hi)
                report.rejected_short += 1
            else:
                report.rejected_short += 1

        if len(pieces) <= 1:
            out.append(event)
            continue

        report.split_notes += 1
        report.added += len(pieces) - 1
        for lo, hi in pieces:
            out.append((lo, hi, int(event[2]), float(event[3]),
                        event[4] if len(event) > 4 else None))

    out.sort(key=lambda e: e[0])
    report.notes_out = len(out)
    if verbose:
        print(
            f"[reattack] {report.notes_in} -> {report.notes_out}음 "
            f"(후보 {report.candidates}, 나눔 {report.split_notes}, +{report.added}), "
            f"버림: 짧음 {report.rejected_short} / 음량 {report.rejected_quiet}"
        )
    return out, report


def _analyse(audio_path: Path):
    """오디오에서 (스펙트럼 플럭스, 프레임 RMS, 프레임 길이)를 만든다.

    플럭스는 `FLUX_FMIN~FLUX_FMAX` 대역에서만 계산한다. 기음 대역을 넣으면
    컴프레서 출렁임이 그대로 들어와 재타현과 섞인다.
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(str(audio_path), sr=SR, mono=True)
    if len(y) < 2048:
        return None, None, 1.0

    spec = np.abs(librosa.stft(y, n_fft=1024, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=1024)
    band = (freqs >= FLUX_FMIN) & (freqs <= FLUX_FMAX)

    # 양의 변화량만 합한다(감쇠는 어택이 아니다).
    energy = spec[band].sum(axis=0)
    flux = np.diff(energy, prepend=energy[:1])
    flux[flux < 0] = 0.0

    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=HOP)[0]
    return flux, rms, HOP / sr


def _rms_rises(rms, idx: int, span: int, *, tolerance: float = 1.0) -> bool:
    """봉우리 지점에서 음량이 실제로 올랐는가.

    트랜지언트가 있어도 소리가 계속 작아지고만 있으면 재타현으로 보지 않는다.
    감쇠 중에 스치는 잡음(줄 긁힘·손 이동)을 걸러내는 안전장치다
    (`playing.json` physicalRules.positionShiftNoise).
    """
    lo = max(0, idx - span)
    hi = min(len(rms), idx + span)
    if hi - idx < 2 or idx - lo < 2:
        return True
    before = float(rms[lo:idx].mean())
    after = float(rms[idx:hi].mean())
    # tolerance < 1.0이면 '조금 줄어드는 것'도 허용한다. 감쇠 중 재타현은
    # 이전 구간 평균을 넘지 못할 수 있다 — 뜯은 직후가 아니라 뜯기 전
    # 구간에 앞 음의 큰 소리가 남아 있기 때문이다.
    return after >= before * tolerance

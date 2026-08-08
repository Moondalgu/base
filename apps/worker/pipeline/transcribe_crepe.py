"""채보 — torchcrepe(단선율 피치 추적).

베이스는 단선율 악기다. 그래서 프레임당 피치를 하나만 내는 모델을 쓰면
배음을 별도 음으로 뱉는 일이 구조적으로 일어나지 않는다. 다성 모델은
한 음의 배음을 각각 독립된 음으로 검출하므로, 그것을 걷어내는 후처리가
필요해진다. CREPE는 그 후처리 자체가 필요 없는 지점에서 출발한다.

정답 데이터셋(IDMT-SMT-BASS, 실제 4현 일렉베이스 17곡·948음, 허용 ±150ms)
실측: 거짓 음 10.5% / 누락 14.0% / F 0.860. 후처리를 하나도 걸지 않은
수치다.

주법별 F(임계 0.6): 뮤트 0.938, 픽 0.913, 핑거 0.912, 슬랩 0.581.
슬랩은 어택이 타악기적이어서 피치가 뚜렷하지 않은 구간이 길고, 그래서
누락이 절반에 달한다. 슬랩 위주 곡은 이 엔진의 약점이라고 알고 써야 한다.

반환 형식은 transcribe.py와 동일하게 맞춘다. 파이프라인 뒷단(bassclean,
quality)이 어느 엔진을 썼는지 몰라도 되게 하려는 것이다.
"""

from __future__ import annotations

import time
from pathlib import Path

# CREPE는 16kHz 입력으로 학습됐다. 다른 샘플레이트를 넣으면 내부에서
# 리샘플링하므로 애초에 16k로 읽는 게 낭비가 없다.
SR = 16000
# **CREPE 자체 설계값이다.** 16kHz에서 160샘플(10ms)이 모델 표준이고,
# 피치 정확도와 연산량의 균형점으로 정해진 값이다. 바꾸면 hop=320 실험에서
# 겪은 것처럼 MIN_NOTE_SEC가 프레임 수 기준으로 흔들린다(누락 +10.4pp).
HOP = 160

# 베이스 최저음 E1 = 41.2Hz. torchcrepe 기본 fmin=50은 E1·F1을 아예
# 후보에서 빼버리므로 베이스에 그대로 쓸 수 없다. 32.7Hz(C1)까지 내린다.
FMIN, FMAX = 32.7, 500.0

# 보컬용 음역. 남성 저음 G2(98Hz)부터 여성 고음 C6(1047Hz)까지 덮는다.
# 베이스 음역을 그대로 쓰면 보컬의 실제 음이 상한에 걸려 옥타브 아래로
# 잘못 잡힌다.
VOCAL_FMIN, VOCAL_FMAX = 80.0, 1100.0

# tiny는 16배 빠르지만 핑거 누락이 2배로 늘고 슬랩은 사실상 붕괴한다.
# 속도를 위해 정확도를 내주는 거래가 성립하지 않는다.
MODEL = "full"

# 보컬 노트 필터. 이보다 짧은 음은 가사 자음·숨소리 조각으로 본다 —
# 베이스보다 길게 잡는다(보컬은 음절마다 음이 하나이고 음절이 이보다 짧기 어렵다).
VOCAL_MIN_SEC = 0.10
VOCAL_MIN_CONFIDENCE = 0.65

# periodicity 하한. 0.5~0.7 구간에서 거짓 음·누락 비율이 거의 움직이지
# 않았다. 즉 이 값에 결과가 민감하지 않다.
CONF_THRESHOLD = 0.6

# 이보다 짧은 덩어리는 음이 아니라 피치 흔들림으로 본다.
# 120BPM 16분음표가 125ms이므로 60ms는 실제 음을 자르지 않는다.
MIN_NOTE_SEC = 0.06

# CPU에서 오디오 길이의 약 1.26배가 걸린다(실측). 사용자에게 미리 알린다.
REALTIME_FACTOR = 1.26


def transcribe(
    stem_path: Path,
    *,
    verbose: bool = False,
    fmin: float = FMIN,
    fmax: float = FMAX,
    hop: int = HOP,
) -> list[tuple]:
    """스템에서 note_events를 뽑는다. 기본 음역은 베이스다.

    보컬 멜로디를 뽑을 때는 `fmin=VOCAL_FMIN, fmax=VOCAL_FMAX`를 준다. CREPE는
    단선율 추적기라 보컬이 원래 주 대상이고, 음역만 맞춰주면 그대로 쓸 수 있다.

    반환 튜플 구조는 transcribe.py와 같다:
        (start_sec, end_sec, pitch_midi, amplitude, pitch_bends)

    amplitude 자리에는 그 음 구간의 periodicity 평균을 넣는다. quality.py가
    이 값을 transcriptionConfidence로 쓰고 bassclean의 누출 필터도 진폭을
    신뢰도처럼 쓰기 때문에, 음량이 아니라 확신도가 들어가야 의미가 맞는다.

    pitch_bends는 None이다. CREPE는 연속 f0를 주므로 벤드를 뽑을 수는
    있지만, 뒷단에서 쓰는 곳이 없어 만들지 않는다.
    """
    import librosa
    import torch
    import torchcrepe

    y, _ = librosa.load(str(stem_path), sr=SR, mono=True)
    duration = len(y) / SR

    if verbose:
        print(
            f"[transcribe] CREPE({MODEL}) 오디오 {duration:.1f}s — "
            f"CPU 실시간 약 {REALTIME_FACTOR}배, {duration * REALTIME_FACTOR:.0f}s 예상"
        )

    start = time.monotonic()
    audio = torch.tensor(y, dtype=torch.float32).unsqueeze(0)
    f0, periodicity = torchcrepe.predict(
        audio,
        SR,
        hop_length=hop,
        fmin=fmin,
        fmax=fmax,
        model=MODEL,
        return_periodicity=True,
        batch_size=512,
        device="cpu",
    )
    elapsed = time.monotonic() - start

    f0 = f0.squeeze().numpy()
    periodicity = periodicity.squeeze().numpy()

    note_events = _segment(f0, periodicity, hop)

    if verbose:
        ratio = elapsed / duration if duration else 0.0
        print(
            f"[transcribe] {elapsed:.1f}s (실시간 {ratio:.2f}배): "
            f"{len(note_events)} note events"
        )
    return note_events


def transcribe_vocal(stem_path: Path, *, verbose: bool = False) -> list:
    """보컬 스템 채보 → Note 목록 (3단 악보의 위 단).

    베이스 후처리(bassclean.clean)는 걸지 않는다 — 배음 제거·누출 제거·음역
    접기가 전부 베이스 전제의 판정이라 보컬에 걸면 실제 음을 깎는다.
    짧음·약함만 여기서 거른다.
    """
    from .bassclean import Note

    events = transcribe(
        stem_path, verbose=verbose, fmin=VOCAL_FMIN, fmax=VOCAL_FMAX
    )
    return [
        Note(
            start=float(e[0]), end=float(e[1]), pitch=int(e[2]),
            amplitude=float(e[3]), detected_end=float(e[1]),
        )
        for e in events
        if e[1] - e[0] >= VOCAL_MIN_SEC and e[3] >= VOCAL_MIN_CONFIDENCE
    ]


def merge_vocal_fragments(notes: list, max_gap: float = 0.08) -> list:
    """같은 피치의 인접 보컬 조각을 병합한다.

    CREPE 분절은 반음 반올림 경계에서 음을 쪼갠다 — 비브라토가 있는 지속음이
    같은 피치의 짧은 조각 여럿으로 나온다. 악보에서는 16분 조각 + 쉼표의
    난수처럼 보이고, 가사 정렬에서는 조각마다 `-`가 붙어 지저분해진다.

    **같은 피치만** 병합한다. 다른 피치끼리 붙이면 실제 꾸밈음·경과음을
    먹는다. 간격 기준 80ms는 CREPE 프레임(10ms)의 흔들림과 무성 자음을
    덮는 수준이고, 같은 음절 안의 끊김이 이보다 길기는 어렵다.
    """
    import copy

    if not notes:
        return notes
    # 입력을 변조하지 않는다 — 호출자(jobs·CLI)가 같은 리스트를 다른 용도로
    # 다시 쓸 수 있고, 표기 폴백(build_from 재호출)에서 두 번 지나간다.
    merged = [copy.copy(notes[0])]
    for n in notes[1:]:
        prev = merged[-1]
        if n.pitch == prev.pitch and n.start - prev.end <= max_gap:
            prev.end = n.end
            prev.detected_end = n.detected_end
            # 확신도는 큰 쪽을 대표값으로 — 평균을 다시 내려면 길이 가중이
            # 필요한데 여기서 그 정밀도는 쓰이지 않는다.
            prev.amplitude = max(prev.amplitude, n.amplitude)
        else:
            merged.append(copy.copy(n))
    return merged


def _segment(f0, periodicity, hop: int = HOP) -> list[tuple]:
    """프레임 단위 f0를 음 단위로 묶는다.

    묶는 규칙은 두 개뿐이다: periodicity가 임계 이상이고, 반음으로 반올림한
    음높이가 앞 프레임과 같으면 같은 음. 다성 모델 출력이라면 동시 발음과
    조각을 가려내는 판단이 더 필요하지만, 프레임당 피치가 하나면 그 판단이
    성립할 여지가 없다.
    """
    import librosa
    import numpy as np

    voiced = (periodicity >= CONF_THRESHOLD) & (f0 > 0)

    # f0 <= 0 프레임에 hz_to_midi를 그대로 걸면 -inf가 나오므로 유성 프레임만 변환한다.
    semitone = np.zeros(len(f0), dtype=np.int64)
    if voiced.any():
        semitone[voiced] = np.rint(librosa.hz_to_midi(f0[voiced])).astype(np.int64)

    frame_sec = hop / SR
    events: list[tuple] = []
    run_start: int | None = None

    def flush(begin: int, end_exclusive: int) -> None:
        """[begin, end_exclusive) 프레임 구간을 한 음으로 확정한다."""
        start_sec = begin * frame_sec
        end_sec = end_exclusive * frame_sec
        if end_sec - start_sec < MIN_NOTE_SEC:
            return
        events.append((
            float(start_sec),
            float(end_sec),
            int(semitone[begin]),
            float(periodicity[begin:end_exclusive].mean()),
            None,
        ))

    for i in range(len(f0)):
        if not voiced[i]:
            if run_start is not None:
                flush(run_start, i)
                run_start = None
            continue
        if run_start is None:
            run_start = i
        elif semitone[i] != semitone[run_start]:
            flush(run_start, i)
            run_start = i
    if run_start is not None:
        flush(run_start, len(f0))

    return events

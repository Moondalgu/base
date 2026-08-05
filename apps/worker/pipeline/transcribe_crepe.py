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
HOP = 160              # 10ms

# 베이스 최저음 E1 = 41.2Hz. torchcrepe 기본 fmin=50은 E1·F1을 아예
# 후보에서 빼버리므로 베이스에 그대로 쓸 수 없다. 32.7Hz(C1)까지 내린다.
FMIN, FMAX = 32.7, 500.0

# tiny는 16배 빠르지만 핑거 누락이 2배로 늘고 슬랩은 사실상 붕괴한다.
# 속도를 위해 정확도를 내주는 거래가 성립하지 않는다.
MODEL = "full"

# periodicity 하한. 0.5~0.7 구간에서 거짓 음·누락 비율이 거의 움직이지
# 않았다. 즉 이 값에 결과가 민감하지 않다.
CONF_THRESHOLD = 0.6

# 이보다 짧은 덩어리는 음이 아니라 피치 흔들림으로 본다.
# 120BPM 16분음표가 125ms이므로 60ms는 실제 음을 자르지 않는다.
MIN_NOTE_SEC = 0.06

# CPU에서 오디오 길이의 약 1.26배가 걸린다(실측). 사용자에게 미리 알린다.
REALTIME_FACTOR = 1.26


def transcribe(stem_path: Path, *, verbose: bool = False) -> list[tuple]:
    """베이스 스템에서 note_events를 뽑는다.

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
        hop_length=HOP,
        fmin=FMIN,
        fmax=FMAX,
        model=MODEL,
        return_periodicity=True,
        batch_size=512,
        device="cpu",
    )
    elapsed = time.monotonic() - start

    f0 = f0.squeeze().numpy()
    periodicity = periodicity.squeeze().numpy()

    note_events = _segment(f0, periodicity)

    if verbose:
        ratio = elapsed / duration if duration else 0.0
        print(
            f"[transcribe] {elapsed:.1f}s (실시간 {ratio:.2f}배): "
            f"{len(note_events)} note events"
        )
    return note_events


def _segment(f0, periodicity) -> list[tuple]:
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

    frame_sec = HOP / SR
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

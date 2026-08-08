"""채보 엔진 자동 선택 — CREPE가 스템을 설명하지 못하면 basic-pitch로 폴백.

## 왜 필요한가 (2026-08-08 실측)

CREPE는 전반적으로 basic-pitch보다 낫지만(IDMT F 0.860 대 0.743) **곡 단위로
완전히 붕괴하는 케이스**가 있다. Virtual Insanity(뮤트 중심 저역 펑크):

- 스템에 베이스라인이 실재한다 — pyin 유성 36.8%, 저역 에너지 정상,
  피치도 E♭m 음계로 맞게 나온다
- 그런데 CREPE full은 같은 구간에서 periodicity 중앙값 0.002, 유성 9%.
  진폭 정규화·증폭 무관(내부 정규화 확인)
- basic-pitch는 같은 스템에서 771음을 내고 피치클래스 분포가 사람 채보
  (836타)와 일치한다

즉 "CREPE 하나로 간다"는 전제가 틀렸고, 곡마다 판정해야 한다.

## 판정 지표 — 노트 커버리지 / 스템 활동

검출된 노트가 스템의 소리 나는 시간을 얼마나 덮는가. 실측(6곡):

| 곡 | 비율 | basic-pitch로 바꾸면 (마디 피치클래스) |
|---|---|---|
| 예뻤어 0.83 · Champagne 0.80 · Drowning 0.68 | 정상 | (안 바꿈 — IDMT에서 CREPE 우위) |
| Queen **0.47** | 중립 | 62% → 60% (−2pp, 손해) |
| Come Together **0.44** | 개선 | 65% → **76%** (+11pp) |
| Virtual Insanity **0.27** | 붕괴→회복 | 22% → 25%, 타현 0→15% |

임계 0.45: 개선된 최고값(CT 0.44)과 손해 본 최저값(Queen 0.47) 사이 —
**간격이 3pp뿐이라 불안정한 경계다.** 골든셋이 늘어 이 사이 곡이 나오면
그 곡의 A/B로 다시 정한다. 절대 눈어림으로 올리지 말 것.
"""

from __future__ import annotations

from pathlib import Path

from . import transcribe, transcribe_crepe

# 스템 활동 판정 — diag 계열과 같은 기준 (16kHz, RMS 프레임 > 0.02)
SR = 16000
FRAME = 2048
HOP = 512
ACTIVE_RMS = 0.02

# 커버리지 폴백 임계. 근거는 모듈 머리말 표 (2026-08-08 A/B로 0.35→0.45).
MIN_COVERAGE = 0.45


def note_coverage(events: list[tuple], stem_path: Path) -> float:
    """검출 노트 총 길이 / 스템 활동 길이. 0이면 활동이 없거나 검출이 0."""
    import librosa
    import numpy as np

    note_sec = sum(e[1] - e[0] for e in events)
    y, _ = librosa.load(str(stem_path), sr=SR, mono=True)
    frames = librosa.feature.rms(y=y, frame_length=FRAME, hop_length=HOP)[0]
    active_sec = float((frames > ACTIVE_RMS).sum()) * HOP / SR
    if active_sec <= 0:
        return 0.0
    return note_sec / active_sec


def transcribe_auto(stem_path: Path, *, verbose: bool = False) -> tuple[list[tuple], str, float]:
    """(note_events, 사용한 엔진 이름, 커버리지) — 뒷단은 엔진 이름으로
    monophonic 여부를 정한다 (crepe만 단선율 출력).
    """
    events = transcribe_crepe.transcribe(stem_path, verbose=verbose)
    cov = note_coverage(events, stem_path)
    if cov >= MIN_COVERAGE:
        return events, "crepe", cov

    if verbose:
        print(
            f"[engine] CREPE 커버리지 {cov:.2f} < {MIN_COVERAGE} — "
            f"스템에 소리가 있는데 음을 못 잡고 있다. basic-pitch로 폴백"
        )
    events_bp = transcribe.transcribe(stem_path)
    cov_bp = note_coverage(events_bp, stem_path)
    if cov_bp <= cov:
        # 둘 다 못 잡으면 원래 엔진을 유지한다 (거짓 음이 적은 쪽)
        if verbose:
            print(f"[engine] basic-pitch도 {cov_bp:.2f} — CREPE 유지")
        return events, "crepe", cov
    if verbose:
        print(f"[engine] basic-pitch 채택 (커버리지 {cov_bp:.2f})")
    return events_bp, "basic-pitch", cov_bp

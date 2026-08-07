"""채보 — spotify/basic-pitch.

베이스 전용 파라미터를 여기서 고정한다.

주의: minimum_note_length 기본값 127.7ms는 베이스에 독이다.
120BPM 16분음표가 125ms라서 기본값 그대로 쓰면 빠른 라인이 통째로 잘린다.
"""

from __future__ import annotations

import time
from pathlib import Path

# 베이스 음역 (Hz). E1 = 41.2Hz, 4현 20프렛 상한 ≈ 415Hz
BASS_MIN_FREQ = 35.0
# 1현 20프렛 E4가 329.6Hz. 배음·슬랩 성분까지 덮는 상한.
BASS_MAX_FREQ = 450.0
# bassclean.MIN_NOTE_SEC와 같은 값·같은 등급(추측·위험, POLICY.md 4.1).
MIN_NOTE_LENGTH_MS = 60.0
# **추측(위험)이지만 우선순위가 낮다** — basic-pitch는 비교용 경로이고 기본
# 엔진이 아니다(CREPE가 IDMT F 0.861 대 0.815로 앞선다). POLICY.md 4.5.
ONSET_THRESHOLD = 0.5
# 위와 같다(POLICY.md 4.5).
FRAME_THRESHOLD = 0.3


def transcribe(stem_path: Path, *, verbose: bool = False) -> list[tuple]:
    """베이스 스템에서 note_events를 뽑는다.

    반환 튜플 구조 (실측 확인):
        (start_sec, end_sec, pitch_midi, amplitude, pitch_bends)
    """
    from basic_pitch.inference import predict

    start = time.monotonic()
    _, _, note_events = predict(
        str(stem_path),
        minimum_frequency=BASS_MIN_FREQ,
        maximum_frequency=BASS_MAX_FREQ,
        minimum_note_length=MIN_NOTE_LENGTH_MS,
        onset_threshold=ONSET_THRESHOLD,
        frame_threshold=FRAME_THRESHOLD,
    )
    elapsed = time.monotonic() - start

    if verbose:
        print(f"[transcribe] {elapsed:.1f}s: {len(note_events)} note events")
    return note_events

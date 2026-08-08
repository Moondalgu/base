"""가사 — faster-whisper ASR → 한국어 음절 분해 → 보컬 음 정렬.

## 정렬 원리 (프로브 실측, 2026-08-08)

alphaTex `\\lyrics`는 음절을 **음표 비트에만, 순서대로** 붙인다 — 쉼표는
음절을 소비하지 않는다(`tools/probe_vocal_pitch.mjs` + `lyric_rest.alphatex`).
그래서 표기 쪽은 "방출되는 보컬 음표 1개당 음절 토큰 1개"만 지키면 되고,
어려운 문제는 **어느 음에 어느 음절인가**뿐이다. 이것은 시간으로 푼다:
ASR이 낸 음절 타임스탬프와 보컬 음의 시각을 그리디로 짝짓는다.

- 음절이 없는 음(멜리스마·검출 조각) → `-` (이어짐 표기 관례)
- 음이 없는 음절(보컬 검출 누락) → 버린다. 억지로 뒤 음에 밀면 이후 전체가
  한 칸씩 밀린다 — 부분 정답이 전체 오답이 된다.

## 음절 단위

한국어는 글자 = 음절이라 분해가 자명하다("미치도록" → 미·치·도·록).
단어의 시간 구간을 음절 수로 등분해 각 음절에 시각을 준다. 영문 단어는
통째로 한 토큰(참조 악보도 "Oh", "yeah"를 통짜로 둔다).
"""

from __future__ import annotations

import json
from pathlib import Path

# small이 한국어 CPU 트레이드오프의 균형점. tiny는 한국어 오인식이 크고
# medium은 CPU에서 곡당 수십 분이다. 채점 도구가 생기면(골든셋 가사) 재평가.
MODEL_SIZE = "small"

# 음절-음 짝짓기 허용 오차(초). 보컬 온셋과 ASR 단어 타임스탬프는 서로
# 다른 체인에서 나오므로 정확히 겹치지 않는다. 8분음표(75BPM 기준 0.4s)
# 수준이면 이웃 음과 헷갈리지 않는 선이다.
ALIGN_TOLERANCE_SEC = 0.45


def transcribe_lyrics(vocals_path: Path, *, verbose: bool = False) -> list[dict]:
    """보컬 스템에서 음절 목록을 뽑는다. [{"start","end","text"}...] (시각순)."""
    from faster_whisper import WhisperModel

    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(vocals_path), language="ko", word_timestamps=True, vad_filter=True
    )
    syllables: list[dict] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if not text:
                continue
            hangul = [c for c in text if "가" <= c <= "힣"]
            if hangul and len(hangul) == len(text) and len(text) > 1:
                step = (w.end - w.start) / len(text)
                for k, ch in enumerate(text):
                    syllables.append({
                        "start": round(w.start + k * step, 3),
                        "end": round(w.start + (k + 1) * step, 3),
                        "text": ch,
                    })
            else:
                syllables.append({
                    "start": round(w.start, 3), "end": round(w.end, 3), "text": text,
                })
    if verbose:
        print(f"[lyrics] {len(syllables)}음절 (언어확률 {info.language_probability:.2f})")
    return syllables


def save_lyrics(syllables: list[dict], path: Path) -> None:
    path.write_text(json.dumps(syllables, ensure_ascii=False), encoding="utf-8")


def load_lyrics(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def align(note_times: list[float], syllables: list[dict]) -> list[str]:
    """음표 시각 열(방출 순서)에 음절을 그리디로 짝짓는다. 길이 = len(note_times).

    두 열 모두 시각순이므로 포인터 하나로 전진한다. 음보다 한참 앞의 음절은
    버리고(검출 누락), 허용 오차 안이면 붙이고, 아니면 `-`.
    """
    out: list[str] = []
    si = 0
    for t in note_times:
        while si < len(syllables) and syllables[si]["start"] < t - ALIGN_TOLERANCE_SEC:
            si += 1
        if si < len(syllables) and abs(syllables[si]["start"] - t) <= ALIGN_TOLERANCE_SEC:
            out.append(syllables[si]["text"])
            si += 1
        else:
            out.append("-")
    return out

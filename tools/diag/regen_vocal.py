"""보컬 멜로디를 채보해 vocal_notes.json으로 남긴다.

참조 악보(akbobada)는 3단이다 — 위에 보컬 멜로디 오선(가사·코드 심볼),
가운데 베이스 오선, 아래 베이스 TAB. 보컬 단을 그리려면 보컬 스템을 채보해야
한다. 보컬 스템은 Demucs가 이미 분리해 두었고, CREPE는 원래 단선율·보컬이
주 대상이므로 음역만 맞춰주면 그대로 쓸 수 있다.

베이스 후처리(bassclean)는 걸지 않는다. 배음 제거·누출 제거·음역 접기가 전부
베이스를 전제로 만든 판정이고, 보컬에 걸면 실제 음을 깎는다. 짧음·약함만
걸러낸다.

사용:
    python tools/diag/regen_vocal.py data/<hash>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import transcribe_crepe  # noqa: E402
from pipeline.bassclean import Note  # noqa: E402

# 보컬에서 이보다 짧은 음은 가사 자음·숨소리에서 온 조각으로 본다.
# 베이스보다 길게 잡는다 — 보컬은 음절마다 음이 하나이고 음절이 이보다 짧기 어렵다.
MIN_VOCAL_SEC = 0.10
MIN_CONFIDENCE = 0.65


def main() -> int:
    parser = argparse.ArgumentParser(description="보컬 멜로디 채보")
    parser.add_argument("workdir", type=Path, help="data/<hash>")
    args = parser.parse_args()

    stem = args.workdir / "stems" / "vocals.wav"
    if not stem.exists():
        print(f"[오류] 보컬 스템이 없습니다: {stem}")
        return 1

    t = time.monotonic()
    events = transcribe_crepe.transcribe(
        stem,
        verbose=True,
        fmin=transcribe_crepe.VOCAL_FMIN,
        fmax=transcribe_crepe.VOCAL_FMAX,
    )
    notes = [
        Note(
            start=float(e[0]), end=float(e[1]), pitch=int(e[2]),
            amplitude=float(e[3]), detected_end=float(e[1]),
        )
        for e in events
        if e[1] - e[0] >= MIN_VOCAL_SEC and e[3] >= MIN_CONFIDENCE
    ]

    out = args.workdir / "vocal_notes.json"
    out.write_text(
        json.dumps([asdict(n) for n in notes], ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"[vocal] {len(events)}이벤트 -> {len(notes)}음 (짧음·약함 제거) "
        f"-> {out} ({time.monotonic() - t:.1f}s)"
    )
    if notes:
        pitches = [n.pitch for n in notes]
        print(f"[vocal] 음역 MIDI {min(pitches)}~{max(pitches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

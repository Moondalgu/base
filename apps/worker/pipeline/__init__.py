"""베이스 자동 채보 파이프라인.

단계 순서:
    ingest -> separate -> encode -> beats -> transcribe -> bassclean -> quantize
           -> fretting -> alphatex

각 단계는 자기 산출물을 data/{contentHash}/ 아래에 캐시하므로
중간부터 다시 돌릴 수 있다.

`compose`는 뒷단(quantize -> fretting -> alphatex)을 한 덩어리로 묶은 것이다.
난이도 레벨·이조·튜닝을 바꿀 때 채보를 다시 돌리지 않고 여기부터 다시 돈다.
"""

from __future__ import annotations

__all__ = [
    "alphatex",
    "bassclean",
    "beats",
    "chords",
    "compose",
    "diagnose",
    "encode",
    "export",
    "fretting",
    "inertia",
    "ingest",
    "kicksync",
    "quality",
    "quantize",
    "reattack",
    "reduce",
    "sections",
    "separate",
    "transcribe",
    "transcribe_crepe",
]

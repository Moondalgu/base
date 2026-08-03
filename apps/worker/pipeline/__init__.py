"""베이스 자동 채보 파이프라인.

단계 순서:
    ingest -> separate -> beats -> transcribe -> bassclean -> quantize
           -> fretting -> alphatex

각 단계는 자기 산출물을 data/{contentHash}/ 아래에 캐시하므로
중간부터 다시 돌릴 수 있다.
"""

from __future__ import annotations

__all__ = [
    "alphatex",
    "bassclean",
    "beats",
    "fretting",
    "ingest",
    "quantize",
    "separate",
    "transcribe",
]

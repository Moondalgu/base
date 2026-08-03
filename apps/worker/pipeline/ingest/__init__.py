"""수집 어댑터 레지스트리.

새 소스를 지원하려면 어댑터를 만들어 ADAPTERS에 추가하기만 하면 된다.
"""

from __future__ import annotations

from pathlib import Path

from .base import IngestionAdapter, SourceInfo, content_hash_of, probe_duration, to_wav
from .upload import UploadAdapter
from .ytdlp import YoutubeAdapter

ADAPTERS: list[IngestionAdapter] = [
    YoutubeAdapter(),
    UploadAdapter(),
]


def resolve(source: str) -> IngestionAdapter:
    """입력에 맞는 어댑터를 고른다."""
    for adapter in ADAPTERS:
        if adapter.can_handle(source):
            return adapter
    raise ValueError(f"처리할 수 있는 어댑터가 없습니다: {source}")


def ingest(source: str, workdir: Path) -> SourceInfo:
    return resolve(source).fetch(source, workdir)


__all__ = [
    "ADAPTERS",
    "IngestionAdapter",
    "SourceInfo",
    "content_hash_of",
    "ingest",
    "probe_duration",
    "resolve",
    "to_wav",
]

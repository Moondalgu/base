"""수집 어댑터 인터페이스.

어떤 경로로 오디오가 들어오든(유튜브 링크, 파일 업로드, 향후 다른 소스)
파이프라인 이후 단계는 동일한 wav 파일 하나만 본다.
어댑터를 추가해도 separate/beats/transcribe 코드는 손대지 않는다.
"""

from __future__ import annotations

import hashlib
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

TARGET_SAMPLE_RATE = 44100
TARGET_CHANNELS = 2


@dataclass
class SourceInfo:
    """수집 결과. content_hash가 캐시 키가 된다."""

    content_hash: str
    wav_path: Path
    title: str
    duration_sec: float
    source_type: str  # "youtube" | "upload"
    source_id: str  # 영상 ID 또는 파일 해시


class IngestionAdapter(ABC):
    """모든 수집 경로가 구현하는 인터페이스."""

    source_type: str = ""

    @abstractmethod
    def can_handle(self, source: str) -> bool:
        """이 어댑터가 처리할 수 있는 입력인지."""

    @abstractmethod
    def fetch(self, source: str, workdir: Path) -> SourceInfo:
        """오디오를 확보해 44.1kHz 스테레오 wav로 workdir에 저장한다."""


def content_hash_of(value: str | bytes) -> str:
    """캐시 키 생성. 문자열(영상 ID) 또는 파일 바이트를 받는다."""
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()[:16]


def to_wav(src: Path, dst: Path) -> None:
    """ffmpeg으로 44.1kHz 스테레오 wav 변환.

    이후 모든 단계(Demucs, beat_this, basic-pitch)가 같은 샘플레이트를
    전제하므로 여기서 한 번만 정규화한다.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(src),
            "-ar", str(TARGET_SAMPLE_RATE),
            "-ac", str(TARGET_CHANNELS),
            "-c:a", "pcm_s16le",
            str(dst),
        ],
        check=True,
    )


def probe_duration(path: Path) -> float:
    """ffprobe로 길이(초)를 읽는다."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(out.stdout.strip())

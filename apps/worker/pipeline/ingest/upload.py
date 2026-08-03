"""파일 업로드 수집 어댑터.

로컬 오디오 파일을 받아 동일한 wav 규격으로 정규화한다.
캐시 키는 파일 내용 해시라 이름을 바꿔 올려도 재처리하지 않는다.
"""

from __future__ import annotations

from pathlib import Path

from .base import IngestionAdapter, SourceInfo, content_hash_of, probe_duration, to_wav

SUPPORTED_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac"}


class UploadAdapter(IngestionAdapter):
    source_type = "upload"

    def can_handle(self, source: str) -> bool:
        path = Path(source)
        return path.exists() and path.suffix.lower() in SUPPORTED_SUFFIXES

    def fetch(self, source: str, workdir: Path) -> SourceInfo:
        src = Path(source)
        if not src.exists():
            raise FileNotFoundError(f"파일이 없습니다: {source}")
        if src.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"지원하지 않는 형식입니다: {src.suffix}")

        chash = content_hash_of(src.read_bytes())
        workdir = workdir / chash
        workdir.mkdir(parents=True, exist_ok=True)
        wav_path = workdir / "source.wav"

        if not wav_path.exists():
            to_wav(src, wav_path)

        return SourceInfo(
            content_hash=chash,
            wav_path=wav_path,
            title=src.stem,
            duration_sec=probe_duration(wav_path),
            source_type=self.source_type,
            source_id=chash,
        )

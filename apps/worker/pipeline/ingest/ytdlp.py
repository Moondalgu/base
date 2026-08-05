"""유튜브 수집 어댑터.

개인 학습 목적. 추출한 오디오는 로컬에만 두고 재배포하지 않는다.
"""

from __future__ import annotations

import re
from pathlib import Path

import yt_dlp

from .base import IngestionAdapter, SourceInfo, content_hash_of, probe_duration, to_wav

_YOUTUBE_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})"),
]

# JS 런타임(deno 등)이 없으면 기본 클라이언트가 재생 URL을 못 받아 403이 난다.
# android 클라이언트는 JS 런타임 없이도 재생 URL을 내려주므로 폴백으로 둔다.
# None은 "기본 ydl_opts 그대로"를 의미한다. JS 런타임이 설치되면 기본이 더 좋은
# 포맷(오디오 전용 등)을 주므로 항상 기본을 먼저 시도한다.
PLAYER_CLIENT_FALLBACKS: tuple[str | None, ...] = (None, "android")


def extract_video_id(url: str) -> str | None:
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


class YoutubeAdapter(IngestionAdapter):
    source_type = "youtube"

    def can_handle(self, source: str) -> bool:
        return extract_video_id(source) is not None

    def fetch(self, source: str, workdir: Path) -> SourceInfo:
        video_id = extract_video_id(source)
        if video_id is None:
            raise ValueError(f"유튜브 URL이 아닙니다: {source}")

        # 캐시 키는 영상 ID 기반. 같은 영상은 URL 형태가 달라도 한 번만 처리한다.
        chash = content_hash_of(f"youtube:{video_id}")
        workdir = workdir / chash
        workdir.mkdir(parents=True, exist_ok=True)
        wav_path = workdir / "source.wav"

        if wav_path.exists():
            return SourceInfo(
                content_hash=chash,
                wav_path=wav_path,
                title=_read_title(workdir) or video_id,
                duration_sec=probe_duration(wav_path),
                source_type=self.source_type,
                source_id=video_id,
            )

        download_target = workdir / "download.%(ext)s"
        base_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(download_target),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        info = None
        downloaded = None
        for i, player_client in enumerate(PLAYER_CLIENT_FALLBACKS):
            opts = dict(base_opts)
            if player_client is not None:
                print(f"[ingest] 기본 클라이언트 실패, {player_client}로 재시도")
                opts["extractor_args"] = {"youtube": {"player_client": [player_client]}}
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(
                        f"https://www.youtube.com/watch?v={video_id}", download=True
                    )
                    downloaded = Path(ydl.prepare_filename(info))
                break
            except yt_dlp.utils.DownloadError:
                if i == len(PLAYER_CLIENT_FALLBACKS) - 1:
                    raise
                continue

        assert info is not None and downloaded is not None

        to_wav(downloaded, wav_path)
        downloaded.unlink(missing_ok=True)

        title = info.get("title") or video_id
        (workdir / "title.txt").write_text(title, encoding="utf-8")

        return SourceInfo(
            content_hash=chash,
            wav_path=wav_path,
            title=title,
            duration_sec=probe_duration(wav_path),
            source_type=self.source_type,
            source_id=video_id,
        )


def _read_title(workdir: Path) -> str | None:
    path = workdir / "title.txt"
    return path.read_text(encoding="utf-8") if path.exists() else None

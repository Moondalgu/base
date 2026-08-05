"""스템을 브라우저 전송용으로 인코딩한다.

Demucs는 wav로 뱉는다. 파이프라인 내부(basic-pitch)는 wav를 쓰지만,
브라우저에 wav를 그대로 보내면 안 된다.

실측: 5분 36초 곡 스템 4개가 wav로 227MB다. 브라우저는 이걸 내려받고
decodeAudioData로 Float32 PCM으로 펼치는데(스테레오 44.1kHz면 채널당
4바이트/샘플), 디코딩 결과만 474MB이고 addBuffers가 워크릿으로 복사하면서
다시 그만큼 더 든다. 재생 버튼이 아무 반응 없는 이유가 이것이다.

opus 96kbps로 바꾸면 같은 곡이 스템당 약 4MB, 합쳐서 16MB가 된다.

주의: 디코딩 후 PCM 크기는 포맷과 무관하게 곡 길이로 정해지므로, opus는
전송·디코드 입력만 줄인다. 메모리 쪽은 엔진이 워크릿에 버퍼를 넘긴 뒤
메인 스레드 사본을 해제하는 것으로 대응한다 (engine.ts ensureGraph).

Safari의 decodeAudioData는 ogg/opus를 못 푼다. 이 프로젝트는 로컬
Chrome 전용이라 감수한다. 필요해지면 여기서 aac로만 바꾸면 된다.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

BITRATE = "96k"


def encode_stems(stems: dict[str, Path], *, verbose: bool = True) -> dict[str, Path]:
    """wav 스템을 opus로 변환한다. 원본 wav는 파이프라인이 계속 쓰므로 남긴다."""
    start = time.monotonic()
    out: dict[str, Path] = {}
    encoded = 0

    for name, wav in stems.items():
        opus = wav.with_suffix(".opus")
        out[name] = opus
        if opus.exists() and opus.stat().st_mtime >= wav.stat().st_mtime:
            continue
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(wav),
                "-c:a", "libopus",
                "-b:a", BITRATE,
                # 커버아트 같은 비디오 스트림이 끼어들지 않게 한다
                "-vn",
                str(opus),
            ],
            check=True,
        )
        encoded += 1

    if verbose:
        wav_mb = sum(p.stat().st_size for p in stems.values()) / 1e6
        opus_mb = sum(p.stat().st_size for p in out.values()) / 1e6
        elapsed = time.monotonic() - start
        if encoded:
            print(
                f"[encode] {encoded}개 opus 변환 {elapsed:.1f}s: "
                f"{wav_mb:.0f}MB -> {opus_mb:.0f}MB ({wav_mb / max(opus_mb, 0.01):.0f}배 감소)"
            )
        else:
            print(f"[encode] 캐시 사용 ({opus_mb:.0f}MB)")
    return out

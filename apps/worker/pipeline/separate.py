"""스템 분리 — Demucs v4 (htdemucs).

4스템(drums/bass/other/vocals) 중 bass가 이 제품의 전제다.
htdemucs는 bass를 전용 스템으로 뽑아주는 반면 기타는 스템 자체가 없다.

demucs 4.1.0 기준으로 `demucs.api.Separator`가 정식 프로그래매틱 API다.
(`demucs.separate.load_track`은 4.x에 존재하지 않는다 — 실측 확인)
"""

from __future__ import annotations

import time
from pathlib import Path

STEM_NAMES = ("drums", "bass", "other", "vocals")
MODEL_NAME = "htdemucs"


def separate(
    wav_path: Path,
    outdir: Path,
    device: str | None = None,
    *,
    verbose: bool = True,
) -> dict[str, Path]:
    """wav를 4스템으로 분리해 stems/{name}.wav로 저장하고 경로를 반환한다.

    CPU 기준 처리 시간은 트랙 길이의 약 1.5배.
    """
    import torch
    from demucs.api import Separator, save_audio

    stems_dir = outdir / "stems"
    stems_dir.mkdir(parents=True, exist_ok=True)

    existing = {name: stems_dir / f"{name}.wav" for name in STEM_NAMES}
    if all(path.exists() for path in existing.values()):
        if verbose:
            print(f"[separate] 캐시 사용: {stems_dir}")
        return existing

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")

    start = time.monotonic()
    separator = Separator(
        model=MODEL_NAME,
        device=device,
        split=True,
        overlap=0.25,
        progress=verbose,
    )
    _origin, separated = separator.separate_audio_file(wav_path)
    elapsed = time.monotonic() - start

    result: dict[str, Path] = {}
    for name, source in separated.items():
        path = stems_dir / f"{name}.wav"
        save_audio(source, path, samplerate=separator.samplerate)
        result[name] = path

    if verbose:
        print(f"[separate] {MODEL_NAME} on {device}: {elapsed:.1f}s -> {sorted(result)}")
    return result

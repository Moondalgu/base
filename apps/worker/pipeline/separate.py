"""스템 분리 — Demucs v4 (htdemucs).

4스템(drums/bass/vocals/other) 중 bass가 이 제품의 전제다.
htdemucs는 bass를 전용 스템으로 뽑아주는 반면 기타는 스템 자체가 없다.
"""

from __future__ import annotations

import time
from pathlib import Path

import torch

STEM_NAMES = ("drums", "bass", "other", "vocals")  # Demucs 출력 순서
MODEL_NAME = "htdemucs"


def separate(wav_path: Path, outdir: Path, device: str | None = None) -> dict[str, Path]:
    """wav를 4스템으로 분리해 stems/{name}.wav로 저장하고 경로를 반환한다.

    CPU 기준 처리 시간은 트랙 길이의 약 1.5배.
    """
    from demucs.apply import apply_model
    from demucs.audio import save_audio
    from demucs.pretrained import get_model
    from demucs.separate import load_track

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    stems_dir = outdir / "stems"
    stems_dir.mkdir(parents=True, exist_ok=True)

    existing = {name: stems_dir / f"{name}.wav" for name in STEM_NAMES}
    if all(path.exists() for path in existing.values()):
        return existing

    model = get_model(MODEL_NAME)
    model.to(device)
    model.eval()

    wav = load_track(wav_path, model.audio_channels, model.samplerate)

    # Demucs는 정규화된 입력을 기대한다. 분리 후 되돌린다.
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std()
    wav_normalized = (wav - mean) / std

    start = time.monotonic()
    with torch.no_grad():
        sources = apply_model(
            model,
            wav_normalized[None],
            device=device,
            progress=True,
            split=True,
            overlap=0.25,
        )[0]
    sources = sources * std + mean
    elapsed = time.monotonic() - start

    result: dict[str, Path] = {}
    for name, source in zip(model.sources, sources):
        path = stems_dir / f"{name}.wav"
        save_audio(source, str(path), samplerate=model.samplerate)
        result[name] = path

    print(f"[separate] {MODEL_NAME} on {device}: {elapsed:.1f}s -> {list(result)}")
    return result

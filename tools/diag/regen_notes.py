"""이미 처리한 곡의 notes.json을 제자리에서 다시 만든다.

`notes.json`은 schemaVersion 2부터 저장된다. 그 이전 산출물에는 없어서 악보
변형(레벨·이조·튜닝)을 만들 수 없다. 파이프라인을 처음부터 다시 돌리면 새 hash
디렉토리가 생기고 분리(약 450초)까지 다시 도는데, 스템이 이미 있으므로 채보만
다시 하면 된다.

사용:
    python tools/diag/regen_notes.py data/<hash>
    python tools/diag/regen_notes.py data/<hash> --engine basic-pitch
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import bassclean, compose, fretting, transcribe, transcribe_crepe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="notes.json 제자리 재생성")
    parser.add_argument("workdir", type=Path, help="data/<hash> 디렉토리")
    parser.add_argument("--engine", choices=("crepe", "basic-pitch"), default="crepe")
    args = parser.parse_args()

    workdir: Path = args.workdir
    stem = workdir / "stems" / "bass.wav"
    if not stem.exists():
        print(f"[오류] 베이스 스템이 없습니다: {stem}")
        return 1
    if not (workdir / "beats.json").exists():
        print(f"[오류] beats.json이 없습니다. 비트 추적부터 다시 돌려야 합니다.")
        return 1

    monophonic = args.engine == "crepe"
    engine_fn = transcribe_crepe.transcribe if monophonic else transcribe.transcribe

    t = time.monotonic()
    events = engine_fn(stem)
    notes, report = bassclean.clean(
        events, verbose=True, monophonic_source=monophonic
    )
    bassclean.save_notes(notes, workdir / "notes.json")
    print(f"[regen] {len(notes)}음 -> {workdir / 'notes.json'} ({time.monotonic() - t:.1f}s)")

    # manifest도 맞춰준다. notes.json이 생겼는데 schemaVersion이 1로 남아 있으면
    # "변형을 만들 수 없다"는 잘못된 신호가 된다.
    manifest_path = workdir / "manifest.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["schemaVersion"] = 2
        data["scoreVariants"] = {
            "levels": [compose.ORIGINAL_LEVEL],
            "transposeRange": [-compose.TRANSPOSE_LIMIT, compose.TRANSPOSE_LIMIT],
            "tunings": sorted(fretting.TUNING_PRESETS),
        }
        manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("[regen] manifest schemaVersion 2 + scoreVariants 반영")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

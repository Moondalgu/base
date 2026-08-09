"""드럼 리듬(drums.json) 생성 — 저장된 곡의 드럼 스템에서.

사용: .venv/Scripts/python.exe tools/gen_drums.py <content_hash> [...]

마디 좌표는 워커 API의 ledger.json(barStarts/barEnds = 악보 좌표)에서
받는다 — beats.json 다운비트는 위상 보정 전이라 쓰면 안 된다(실측 3회).
워커(8000)가 떠 있어야 한다.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import drums  # noqa: E402


def main() -> None:
    hashes = sys.argv[1:]
    if not hashes:
        raise SystemExit("사용법: gen_drums.py <content_hash> [...]")
    for h in hashes:
        stem = ROOT / f"data/{h}/stems/drums.wav"
        if not stem.exists():
            print(f"[{h}] 드럼 스템 없음 — 건너뜀")
            continue
        workdir = ROOT / f"data/{h}"
        # 순서가 중요하다: 원시 온셋을 먼저 저장해야, 이어지는 ledger 요청이
        # 킥 단서로 위상을 심판한 **보정된** 마디 좌표를 돌려준다. 그 좌표로
        # 격자(drums.json)를 만들어야 드럼이 악보와 같은 마디에 앉는다.
        raw = drums.detect(stem)
        drums.save_onsets(raw, workdir)
        led = json.loads(urllib.request.urlopen(
            f"http://localhost:8000/api/scores/{h}/ledger.json?level=3",
            timeout=180).read())
        events = drums.to_grid(raw, led["barStarts"], led["barEnds"])
        drums.save(events, workdir)
        bars = len({e["bar"] for e in events})
        print(f"[{h}] drums.json 저장 — 이벤트 {len(events)}개, 마디 {bars}개")


if __name__ == "__main__":
    main()

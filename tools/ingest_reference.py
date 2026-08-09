"""참조 악보 적재 CLI — 워커 모듈(pipeline/reference.py)의 얇은 래퍼.

사용: .venv/Scripts/python.exe tools/ingest_reference.py <content_hash> <이미지...> [--votes 2]

--votes 2: 페이지를 두 번 판독해 어긋난 마디를 화성(코드 베이스 음) 기준으로
고른다 — 현 식별 흔들림 대응. 시간·비용 두 배.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import reference  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("content_hash")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--votes", type=int, default=1, choices=(1, 2))
    args = ap.parse_args()
    workdir = ROOT / "data" / args.content_hash
    if not workdir.exists():
        raise SystemExit(f"곡 디렉토리가 없습니다: {workdir}")
    out = reference.ingest_images(
        [Path(p) for p in args.images], workdir,
        votes=args.votes, verbose=True,
    )
    print(f"[완료] 마디 {len(out['bars'])}개 -> {workdir / reference.FILENAME}")


if __name__ == "__main__":
    main()

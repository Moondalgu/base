"""참조 악보 적재 — 악보 이미지들을 Gemini Vision으로 판독해 구조화 캐시로.

사용: .venv/Scripts/python.exe tools/ingest_reference.py <content_hash> <이미지1> [이미지2 ...]

산출:
  data/<hash>/reference.json   — 마디별 {chords, tab, lyrics} (참고용 캐시)

용도 둘:
  1) 대조 분석 — 우리 채보와 마디별 자동 대조(tools/diag/compare_reference.py)
  2) (예정) 악보 매칭 재생 — 사용자가 가진 악보를 넣으면 그 악보로
     인디케이터를 돌린다. 오픈소스 OMR(Audiveris·oemer)은 오선 전용이라
     TAB·코드·가사를 못 읽는다 — 베이스 악보는 Gemini 판독이 유일한 실선.

악보 이미지 자체는 저작물이므로 저장소에 넣지 않는다(기존 정책 유지).
판독 결과(코드 이름·프렛 숫자·마디 구조)는 사실 데이터다.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "vision"))

import gemini_vision as gv  # noqa: E402

PROMPT = (ROOT / "tools" / "vision" / "prompt_reference.txt").read_text(encoding="utf-8")


def parse_json(text: str) -> dict:
    """모델 응답에서 JSON을 꺼낸다. 펜스·메타 꼬리를 걷어낸다."""
    text = text.strip()
    text = re.sub(r"\n\n\[finishReason=.*$", "", text, flags=re.DOTALL)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
    start, end = text.index("{"), text.rindex("}") + 1
    return json.loads(text[start:end])


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    content_hash = sys.argv[1]
    images = [Path(p) for p in sys.argv[2:]]
    workdir = ROOT / "data" / content_hash
    if not workdir.exists():
        raise SystemExit(f"곡 디렉토리가 없습니다: {workdir}")

    key = gv.load_key()
    pages = []
    for img in images:
        print(f"[ingest] {img.name} 판독 중…")
        got = None
        for model in gv.MODELS:
            try:
                raw = gv.analyze(img, PROMPT, model, key)
                got = parse_json(raw)
                got["_source_image"] = img.name
                got["_model"] = model
                break
            except Exception as exc:  # noqa: BLE001
                print(f"  {model} 실패: {type(exc).__name__}: {exc}")
                time.sleep(2)
        if got is None:
            raise SystemExit(f"{img.name}: 모든 모델 실패")
        n_bars = len(got.get("bars", []))
        print(f"  -> {got.get('page_label')} 마디 {n_bars}개 "
              f"(first_bar={got.get('first_bar')}, {got['_model']})")
        pages.append(got)

    # 페이지 병합 — 마디 번호 기준. 겹치면 뒤 페이지가 이긴다(스캔 잘림 대비).
    bars: dict[int, dict] = {}
    for pg in pages:
        for b in pg.get("bars", []):
            if isinstance(b.get("bar"), int):
                bars[b["bar"]] = b
    out = {
        "contentHash": content_hash,
        "keySignature": next((p.get("key_signature") for p in pages
                              if p.get("key_signature")), None),
        "tempo": next((p.get("tempo") for p in pages if p.get("tempo")), None),
        "repeats": [p["repeats"] for p in pages if p.get("repeats")],
        "pages": [{k: p.get(k) for k in ("page_label", "first_bar", "_source_image", "_model")}
                  for p in pages],
        "bars": [bars[k] for k in sorted(bars)],
    }
    dest = workdir / "reference.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[완료] 마디 {len(out['bars'])}개 -> {dest}")


if __name__ == "__main__":
    main()

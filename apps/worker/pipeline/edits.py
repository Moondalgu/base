"""사용자 채보 보정(edits) — 검출 원본 위에 얹는 오버레이.

자동 채보는 틀린다(반음 오차·유령 음). 사용자가 화면에서 고친 것을
`data/<hash>/edits.json`에 남기고, 악보를 만들 때마다 **원본 노트를 로드한
직후** 적용한다. 원본 검출을 고치는 것이므로 하향(초급·중급)·이조·운지
전부에 자동으로 전파된다 — 레벨별로 따로 고칠 필요가 없다.

편집은 검출 음의 원래 시각(srcStart)으로 음을 특정한다. 슬롯·마디 번호는
격자 재계산 때 바뀔 수 있지만 검출 시각은 불변이다.

스키마: [{"srcStart": 18.05, "action": "pitch", "pitch": 44}]
        [{"srcStart": 20.11, "action": "delete"}]
"""

from __future__ import annotations

import json
from pathlib import Path

# srcStart 매칭 허용 오차(초). 검출 온셋은 10ms 해상도라 이보다 넉넉하면 된다.
MATCH_TOLERANCE_SEC = 0.03

FILENAME = "edits.json"


def load(workdir: Path) -> list[dict]:
    path = workdir / FILENAME
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save(workdir: Path, edits: list[dict]) -> None:
    (workdir / FILENAME).write_text(
        json.dumps(edits, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def validate(edits) -> list[dict]:
    """저장 전 검증 — 형식이 어긋난 항목은 통째로 거부한다(조용한 부분 적용은
    "고쳤는데 안 고쳐졌다"는 더 나쁜 상태를 만든다)."""
    if not isinstance(edits, list) or len(edits) > 2000:
        raise ValueError("edits는 2000개 이하의 배열이어야 합니다")
    out: list[dict] = []
    for e in edits:
        if not isinstance(e, dict):
            raise ValueError("edit 항목은 객체여야 합니다")
        src = e.get("srcStart")
        action = e.get("action")
        if not isinstance(src, (int, float)) or src < 0:
            raise ValueError(f"srcStart가 잘못됐습니다: {src!r}")
        if action == "pitch":
            p = e.get("pitch")
            if not isinstance(p, int) or not (10 <= p <= 90):
                raise ValueError(f"pitch가 잘못됐습니다: {p!r}")
            out.append({"srcStart": float(src), "action": "pitch", "pitch": p})
        elif action == "delete":
            out.append({"srcStart": float(src), "action": "delete"})
        else:
            raise ValueError(f"action이 잘못됐습니다: {action!r}")
    return out


def apply(notes: list, edits: list[dict]) -> list:
    """원본 노트 목록에 편집을 적용한 새 목록을 돌려준다.

    매칭 실패는 조용히 넘어간다 — 재채보로 검출이 달라져 대상이 사라진
    편집이 악보 생성을 막으면 안 된다(편집은 보너스, 원본이 본체).
    """
    if not edits:
        return notes
    from dataclasses import replace as _replace

    out = []
    for n in notes:
        matched = [e for e in edits
                   if abs(n.start - e["srcStart"]) <= MATCH_TOLERANCE_SEC]
        if not matched:
            out.append(n)
            continue
        e = min(matched, key=lambda e: abs(n.start - e["srcStart"]))
        if e["action"] == "delete":
            continue
        out.append(_replace(n, pitch=e["pitch"]))
    return out

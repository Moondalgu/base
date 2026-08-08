"""음표 배치 원장(ledger) — 악보의 모든 음이 어떻게 그 자리에 들어갔는지.

## 왜 있는가

"음표가 박자에 맞게 들어가고 있는가"를 눈이 아니라 데이터로 답하기 위해서다.
악보에 적힌 음 하나하나에 대해 아래를 한 행으로 남긴다:

| 열 | 뜻 | 어디서 오는가 |
|---|---|---|
| bar / slot | 마디(1-)와 마디 내 슬롯(0-) | quantize — 검출 온셋을 비트 격자의 최근접 슬롯에 스냅 |
| beat / beat_pos | 박(1-)과 박 내 위치("정박"·"+1/2"…) | slot을 subdivision으로 나눈 것 — **박자 맞춤의 실체** |
| duration_slots | 슬롯 단위 길이 | quantize — 듀레이션도 격자로 양자화 |
| pitch_detected | 검출 피치(MIDI) | CREPE/basic-pitch → bassclean |
| pitch_written | 악보에 적힌 피치 | reduce(근음 대체·옥타브 통일)·fretting(프렛 상한 접기) 이후 |
| string / fret | 현·프렛 | fretting Viterbi (W_* 비용, 실측 튜닝) |
| src_start_sec | 검출 온셋의 원래 시각 | transcribe. **-1 = 검출이 아니라 템플릿·보정이 만든 음** |
| snapped_sec | 스냅된 슬롯의 시각 | 마디 시각 × 슬롯 비율 |
| snap_ms | 스냅 이동량(ms) | snapped − src (검출이 격자에서 얼마나 벗어나 있었나) |
| residual | 스냅 잔차(격자 간격 비율) | quantize. SNAP_REJECT_RATIO 초과 = low_confidence |
| loudness / confidence | 실측 음량 / 검출 확신도 | bassclean.measure_loudness / 엔진 |
| source | 검출 / 템플릿·보정 | src_start 부호 |

즉 배치 규칙은: **검출 시각 → (비트 격자) 슬롯 스냅 → 마디·박 좌표 → 표기 토큰**
이고, 이 파일이 그 각 단계의 값을 전부 적재한다. 격자 위에 있지 않은 음은
구조적으로 존재할 수 없다(슬롯이 정수이므로) — 원장의 검증 절이 그걸 확인한다.

산출물: `data/<hash>/ledger.csv` (원본 레벨) + `/api/scores/{hash}/ledger.csv`
(레벨·이조·튜닝 변형 그대로).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pretty_midi

from .fretting import FrettedScore
from .quantize import QuantizedScore

# 사용자 표기: 현 인덱스 0 = 가장 얇은 현(G).
_STRING_NAMES = ["G", "D", "A", "E"]


def _beat_pos_label(slot: int, subdivision: int) -> str:
    """박 내 위치를 사람 말로. 정박 / +1/2(8분 뒤) / +1/4·+3/4(16분) / 셋잇단."""
    r = slot % subdivision
    if r == 0:
        return "정박"
    if subdivision == 2:
        return "+1/2"
    if subdivision == 4:
        return {1: "+1/4", 2: "+1/2", 3: "+3/4"}[r]
    if subdivision == 3:
        return {1: "+1/3", 2: "+2/3"}[r]
    return f"+{r}/{subdivision}"


def rows(qscore: QuantizedScore, fscore: FrettedScore) -> list[dict]:
    """양자화 결과와 운지 결과를 슬롯으로 짝지어 원장 행을 만든다.

    운지 단계가 음을 버릴 수 있으므로(연주불가 — 현재 0이지만 방어) 순서가
    아니라 **슬롯으로** 짝짓는다. 같은 마디에서 슬롯은 유일하다(quantize가
    겹침을 정리한다).
    """
    out: list[dict] = []
    sub = fscore.subdivision
    fbars = {b.index: b for b in fscore.bars}
    idx = 0
    for qbar in qscore.bars:
        fbar = fbars.get(qbar.index)
        fmap = {n.slot: n for n in (fbar.notes if fbar else [])}
        bar_len = qbar.end_sec - qbar.start_sec
        for qn in sorted(qbar.notes, key=lambda n: n.slot):
            fn = fmap.get(qn.slot)
            snapped = qbar.start_sec + bar_len * (qn.slot / max(1, qbar.slots_per_bar))
            detected = qn.src_start >= 0
            idx += 1
            out.append({
                "idx": idx,
                "bar": qbar.index + 1,
                "slot": qn.slot,
                "beat": qn.slot // sub + 1,
                "beat_pos": _beat_pos_label(qn.slot, sub),
                "duration_slots": qn.duration_slots,
                "pitch_detected": qn.pitch,
                "pitch_written": fn.pitch if fn else "",
                "pitch_name": pretty_midi.note_number_to_name(fn.pitch) if fn else "",
                "string": _STRING_NAMES[fn.string] if fn else "",
                "fret": fn.fret if fn else "",
                "src_start_sec": round(qn.src_start, 3) if detected else "",
                "snapped_sec": round(snapped, 3),
                "snap_ms": round((snapped - qn.src_start) * 1000) if detected else "",
                "residual": round(qn.residual, 3),
                "low_confidence": qn.low_confidence,
                "loudness": round(qn.loudness, 4),
                "confidence": round(qn.amplitude, 3),
                "source": "검출" if detected else "템플릿·보정",
            })
    return out


FIELDS = [
    "idx", "bar", "slot", "beat", "beat_pos", "duration_slots",
    "pitch_detected", "pitch_written", "pitch_name", "string", "fret",
    "src_start_sec", "snapped_sec", "snap_ms", "residual",
    "low_confidence", "loudness", "confidence", "source",
]


def to_csv(ledger_rows: list[dict]) -> str:
    """엑셀에서 바로 열리는 CSV(BOM 포함)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(ledger_rows)
    return "﻿" + buf.getvalue()


def write(ledger_rows: list[dict], path: Path) -> None:
    path.write_text(to_csv(ledger_rows), encoding="utf-8", newline="")


def summary(ledger_rows: list[dict]) -> dict:
    """배치 건전성 요약 — "박자에 맞게 들어갔는가"의 수치 답."""
    n = len(ledger_rows)
    if n == 0:
        return {"notes": 0}
    detected = [r for r in ledger_rows if r["source"] == "검출"]
    on_beat = sum(1 for r in ledger_rows if r["beat_pos"] == "정박")
    snaps = sorted(abs(r["snap_ms"]) for r in detected if r["snap_ms"] != "")
    return {
        "notes": n,
        "detected": len(detected),
        "generated": n - len(detected),
        "on_beat_ratio": round(on_beat / n, 3),
        "median_snap_ms": snaps[len(snaps) // 2] if snaps else None,
        "low_confidence": sum(1 for r in ledger_rows if r["low_confidence"]),
    }

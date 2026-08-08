"""악보 연주 이벤트 — 화면 악보를 소리로 재생하기 위한 음표 타임라인.

웹 플레이어의 베이스 샘플러가 이 목록을 받아, 원곡 반주(베이스 스템 뮤트)
위에 악보의 음을 실시간 스케줄로 연주한다("악보 연주" 모드).

시각은 전부 **입력 타임라인의 초**다 — 배속·이조는 플레이어가 자기 시계로
환산한다. 피치는 운지 이후의 표기 피치(fretting 결과)를 쓴다: 사용자가
보는 TAB과 들리는 소리가 같아야 하기 때문이다. 같은 이유로 이 목록은
`/api/scores`와 같은 `compose.build()` 산출물에서만 만든다.
"""

from __future__ import annotations

from .fretting import FrettedScore
from .quantize import QuantizedScore


def events(qscore: QuantizedScore, fscore: FrettedScore) -> list[dict]:
    """[{t, d, midi, v}] — 시작 초, 길이 초, MIDI 피치, 세기(0~1).

    운지 단계가 음을 버릴 수 있으므로 ledger와 같은 방식으로 **슬롯으로**
    짝짓는다. 운지에 없는 음은 소리도 내지 않는다(화면에 없는 음이므로).
    """
    # 검출 음량은 절대 스케일이 아니다(스템·마스터링에 따라 0.1~0.3 수준).
    # 그대로 세기로 쓰면 전곡이 모기 소리가 된다 — 곡 내 최대를 1로 보고
    # 0.6~1.0 대역으로 눌러 담는다: 다이내믹은 남기되 전부 또렷하게.
    peak = max(
        (n.loudness for b in qscore.bars for n in b.notes if n.loudness > 0),
        default=0.0,
    )

    def velocity(loudness: float) -> float:
        if peak <= 0 or loudness <= 0:
            return 0.85
        return 0.6 + 0.4 * min(1.0, loudness / peak)

    out: list[dict] = []
    fbars = {b.index: b for b in fscore.bars}
    for qbar in qscore.bars:
        fbar = fbars.get(qbar.index)
        if fbar is None:
            continue
        fmap = {n.slot: n for n in fbar.notes}
        bar_len = qbar.end_sec - qbar.start_sec
        spb = max(1, qbar.slots_per_bar)
        for qn in sorted(qbar.notes, key=lambda n: n.slot):
            fn = fmap.get(qn.slot)
            if fn is None:
                continue
            start = qbar.start_sec + bar_len * (qn.slot / spb)
            dur = bar_len * (qn.duration_slots / spb)
            out.append({
                "t": round(start, 4),
                "d": round(dur, 4),
                "midi": fn.pitch,
                "v": round(velocity(qn.loudness), 3),
            })
    return out

"""드럼 리듬 채보 — 드럼 스템 온셋을 킥/스네어/햇으로 분류해 격자에 놓는다.

밴드 악보(B-3)의 드럼 트랙용. 채점 근거: Queen AOBTD의 Songsterr 드럼 탭
(사람 채보)을 정답으로 F1 킥 0.785 / 스네어 0.775 / 햇 0.787
(eval/eval_drums.py, 2026-08-09). 임계값은 그 채점의 그리드 서치 최적.

좌표는 반드시 qscore(악보) 마디 시각 — beats.json 다운비트는 위상 보정
전이라 반 박 어긋난다(세 번째 실측 확인).

산출: data/<hash>/drums.json = [{"bar": 0-, "slot": 0-7, "labels": "KH"}...]
"""

from __future__ import annotations

import json
from pathlib import Path

FILENAME = "drums.json"

# 대역(Hz)과 임계 — eval_drums.py 그리드 서치 결과. 바꾸면 재채점할 것.
LO_BAND = (30, 120)
MID_BAND = (150, 800)
HI_BAND = (5000, 10000)
LO_RATIO = 0.6
MID_PCT = 65

# GM 퍼커션 번호 (alphaTex articulation)
GM = {"K": 36, "S": 38, "H": 42}


def detect(stem_path: Path) -> list[dict]:
    """드럼 스템 → 분류된 원시 온셋 [{"t": 시각, "labels": "KH"}...].

    격자와 무관한 **원시 좌표**다 — 위상 보정(quantize.choose_phase의 킥
    단서)이 이것을 쓰므로, 격자 산출물(drums.json)과 분리해 저장한다."""
    import librosa
    import numpy as np

    y, sr = librosa.load(str(stem_path), sr=22050, mono=True)
    env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=env, sr=sr,
                                        units="time", backtrack=False)
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    lo = (freqs >= LO_BAND[0]) & (freqs < LO_BAND[1])
    mid = (freqs >= MID_BAND[0]) & (freqs < MID_BAND[1])
    hi = (freqs >= HI_BAND[0]) & (freqs < HI_BAND[1])

    feats = []
    for t in onsets:
        f = int(t * sr / 512)
        if f + 2 >= S.shape[1]:
            continue
        seg = S[:, f:f + 3].mean(axis=1)
        feats.append((float(t), float(seg[lo].sum()),
                      float(seg[mid].sum()), float(seg[hi].sum())))
    if not feats:
        return []
    mid_thresh = float(np.percentile([m for _, _, m, _ in feats], MID_PCT))

    out = []
    for t, a, b, c in feats:
        labels = set()
        if a > (b + c) * 0.5 * LO_RATIO:
            labels.add("K")
        if b > mid_thresh and b > c * 0.7:
            labels.add("S")
        if c > a * 0.3 or not labels:
            labels.add("H")
        out.append({"t": round(t, 4), "labels": "".join(sorted(labels))})
    return out


def to_grid(raw: list[dict], bar_starts: list[float],
            bar_ends: list[float]) -> list[dict]:
    """원시 온셋 → 마디×8분 슬롯의 악기 집합.

    bar_starts/bar_ends는 **악보(양자화) 좌표**의 마디 시각 —
    ledger.json의 barStarts/barEnds 또는 qscore.bars에서 온다.
    슬롯 8개 = 4/4의 8분 격자(현재 라이브러리 전 곡이 4/4)."""
    import numpy as np

    starts, ends = list(bar_starts), list(bar_ends)
    grid: dict[tuple[int, int], set[str]] = {}
    for e in raw:
        t = e["t"]
        i = int(np.searchsorted(starts, t)) - 1
        if i < 0 or i >= len(starts):
            continue
        span = ends[i] - starts[i]
        if span <= 0:
            continue
        slot = round((t - starts[i]) / span * 8)
        if slot >= 8:
            i, slot = i + 1, 0
            if i >= len(starts):
                continue
        grid.setdefault((i, slot), set()).update(e["labels"])
    return [{"bar": k[0], "slot": k[1], "labels": "".join(sorted(v))}
            for k, v in sorted(grid.items())]


ONSETS_FILENAME = "drum_onsets.json"


def save_onsets(raw: list[dict], workdir: Path) -> None:
    (workdir / ONSETS_FILENAME).write_text(json.dumps(raw), encoding="utf-8")


def load_kicks(workdir: Path) -> list[float] | None:
    """저장된 원시 온셋에서 킥 시각만. 위상 보정 단서용."""
    p = workdir / ONSETS_FILENAME
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return [e["t"] for e in raw if "K" in e["labels"]]


def save(events: list[dict], workdir: Path) -> None:
    (workdir / FILENAME).write_text(json.dumps(events), encoding="utf-8")


def load(workdir: Path) -> list[dict] | None:
    p = workdir / FILENAME
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def render_track(events: list[dict], bar_count: int, beats_per_bar: int) -> list[str]:
    """alphaTex 드럼 트랙 줄들. 퍼커션 노트는 **괄호 필수**(프로브 실측):
    `(36 42).8` — 괄호 없으면 fret.string으로 오인돼 AT208/218."""
    by_bar: dict[int, dict[int, str]] = {}
    for e in events:
        by_bar.setdefault(e["bar"], {})[e["slot"]] = e["labels"]
    lines = ['\\track "Drums"',
             '\\staff{score} \\instrument "percussion"',
             f"\\ts {beats_per_bar} 4", ""]
    bars = []
    slots = beats_per_bar * 2
    for i in range(bar_count):
        row = by_bar.get(i)
        if not row:
            bars.append("r.1")
            continue
        toks = []
        for s in range(slots):
            labels = row.get(s)
            if labels:
                nums = " ".join(str(GM[c]) for c in labels if c in GM)
                toks.append(f"({nums}).8")
            else:
                toks.append("r.8")
        bars.append(" ".join(toks))
    lines.append(" |\n".join(bars))
    return lines

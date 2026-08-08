"""사용자 악보(참조 악보) — 적재·오디오 매핑·표시용 alphaTex 생성.

"악보가 있으면 그 악보로 연습한다": 사용자가 가진 악보 이미지를 Gemini
Vision으로 판독해 `data/<hash>/reference.json`에 적재하고, 그 악보를 우리
플레이어에서 **오디오와 마디가 맞물린 채** 보여준다.

## 왜 '펼쳐서' 그리는가

출판 악보는 반복 기호로 접혀 있고(드라우닝 93마디) 오디오는 펼쳐져
있다(112마디). 접힌 악보를 그대로 그리면 커서가 반복 지점에서 길을 잃는다.
그래서 **근음 진행 DP 정렬**로 악보 마디 ↔ 오디오 마디 매핑을 만들고,
오디오 마디 순서대로 악보 내용을 다시 배열해 그린다 — 마디 수가 오디오와
같아지므로 기존 커서·시크·자동넘김 장치가 수정 없이 작동한다.

## 리듬 단순화

판독된 TAB은 온셋 열(순서)이고 정밀 리듬은 없다. 마디 안에서 균등 배치한다
— 참조 악보류(akbobada)는 균일 8분이 지배적이라 실질 손실이 작고, 인디케이터
목적(어느 마디의 몇 번째 음인가)에는 충분하다. 정밀 리듬 판독은 후속 과제.

OMR 오픈소스(Audiveris·oemer)를 쓰지 않는 이유: 오선 전용이라 TAB·코드
심볼을 못 읽는다. 베이스 악보는 TAB이 본체다.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import urllib.error
import urllib.request
from pathlib import Path

GEMINI_MODELS = ["gemini-3.1-pro-preview", "gemini-2.5-pro"]

FILENAME = "reference.json"

_PROMPT_PATH = Path(__file__).with_name("reference_prompt.txt")

# TAB 현 이름 → alphaTex 현 번호 (우리 표기: 4=E(굵은 현) ... 1=G)
_STRING_NO = {"E": 4, "A": 3, "D": 2, "G": 1}

PC = {"C": 0, "Db": 1, "C#": 1, "D": 2, "Eb": 3, "D#": 3, "E": 4, "F": 5,
      "Gb": 6, "F#": 6, "G": 7, "Ab": 8, "G#": 8, "A": 9, "Bb": 10, "A#": 10,
      "B": 11, "Cb": 11}


def load(workdir: Path) -> dict | None:
    path = workdir / FILENAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ─── 적재 (이미지 → 구조화 판독) ─────────────────────────────────────────────

def _gemini_key() -> str | None:
    from .lyrics import _gemini_key as k

    return k()


def _analyze_image(img_path: Path, prompt: str, model: str, key: str) -> str:
    mime = mimetypes.guess_type(str(img_path))[0] or "image/png"
    payload = json.dumps({
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {
                    "mime_type": mime,
                    "data": base64.b64encode(img_path.read_bytes()).decode("ascii"),
                }},
            ]
        }],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 40000},
    }).encode("utf-8")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    parts = body["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts if "text" in p)


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


def ingest_images(image_paths: list[Path], workdir: Path, *, verbose: bool = False) -> dict:
    """악보 이미지들을 판독해 reference.json으로 적재한다. 반환 = 적재 결과.

    페이지 순서는 호출자가 준 순서다(첫 마디 번호로 재정렬하므로 뒤섞여도
    된다). 판독 실패 페이지는 건너뛰고 남은 것으로 만든다 — 부분 악보도
    없는 것보다 낫다(못 읽은 페이지는 결과에 명시).
    """
    key = _gemini_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY가 없어 악보를 판독할 수 없습니다")
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")

    pages, failed = [], []
    for img in image_paths:
        got = None
        for model in GEMINI_MODELS:
            try:
                got = _parse_json(_analyze_image(img, prompt, model, key))
                got["_source_image"] = img.name
                got["_model"] = model
                break
            except Exception as exc:  # noqa: BLE001
                if verbose:
                    print(f"[reference] {img.name} {model} 실패: {exc}")
        if got is None:
            failed.append(img.name)
        else:
            pages.append(got)
            if verbose:
                print(f"[reference] {img.name}: {got.get('page_label')} "
                      f"마디 {len(got.get('bars', []))}개")
    if not pages:
        raise RuntimeError("모든 페이지 판독에 실패했습니다")

    bars: dict[int, dict] = {}
    for pg in sorted(pages, key=lambda p: p.get("first_bar") or 0):
        for b in pg.get("bars", []):
            if isinstance(b.get("bar"), int):
                bars[b["bar"]] = b
    out = {
        "keySignature": next((p.get("key_signature") for p in pages
                              if p.get("key_signature")), None),
        "tempo": next((p.get("tempo") for p in pages if p.get("tempo")), None),
        "repeats": [p["repeats"] for p in pages if p.get("repeats")],
        "pages": [{k: p.get(k) for k in ("page_label", "first_bar",
                                         "_source_image", "_model")}
                  for p in pages],
        "failedPages": failed,
        "bars": [bars[k] for k in sorted(bars)],
    }
    (workdir / FILENAME).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ─── 오디오 마디 매핑 (근음 DP 정렬) ────────────────────────────────────────

def chord_root_pc(symbol: str) -> int | None:
    if not symbol:
        return None
    head = symbol.split("/")[0].strip()
    for ln in (2, 1):
        if head[:ln] in PC:
            return PC[head[:ln]]
    return None


def _ref_roots(ref: dict) -> list[int | None]:
    """참조 마디별 근음 pc. 코드 심볼 승계, 연주(tab) 없는 마디는 None."""
    out, cur = [], None
    for b in ref["bars"]:
        chords = b.get("chords") or []
        if chords:
            cur = chord_root_pc(chords[0])
        out.append(cur if (b.get("tab") or []) else None)
    return out


def _tab_root_pc(bar: dict) -> int | None:
    """TAB 첫 온셋의 피치클래스 — 코드 심볼이 없거나 못 읽었을 때의 근음."""
    tab = bar.get("tab") or []
    if not tab:
        return None
    t = tab[0]
    open_pc = {"E": 4, "A": 9, "D": 2, "G": 7}.get(str(t.get("string", "")).upper())
    fret = t.get("fret")
    if open_pc is None or not isinstance(fret, int):
        return None
    return (open_pc + fret) % 12


def align_bars(ref: dict, our_roots: list[int | None]) -> list[int | None]:
    """오디오 마디 i(0-) → 참조 bars 인덱스(0-) 또는 None. 단조 DP 정렬.

    비용: 근음 pc 일치 0 / 불일치 2 / 스킵 1. 참조 근음은 코드 심볼 우선,
    없으면 TAB 첫 온셋 pc. 반복(오디오가 더 긺)은 참조 쪽 되감기가 아니라
    스킵 누적으로는 못 잡는다 — 그래서 **오디오를 참조에 정렬한 뒤, 매칭이
    끊긴 오디오 구간을 같은 근음 열이 다시 나오는 참조 구간에 재정렬**하는
    2패스로 푼다.
    """
    ref_roots = _ref_roots(ref)
    for i, b in enumerate(ref["bars"]):
        if ref_roots[i] is None:
            ref_roots[i] = _tab_root_pc(b)

    def dp_align(rs: list, os_: list) -> list[tuple[int | None, int | None]]:
        R, O = len(rs), len(os_)
        INF = float("inf")
        MATCH, MIS, SKIP = 0.0, 2.0, 1.0
        dp = [[INF] * (O + 1) for _ in range(R + 1)]
        back = [[None] * (O + 1) for _ in range(R + 1)]
        dp[0][0] = 0.0
        for i in range(R + 1):
            for j in range(O + 1):
                if dp[i][j] == INF:
                    continue
                base = dp[i][j]
                if i < R and j < O:
                    cost = MATCH if rs[i] == os_[j] else MIS
                    if base + cost < dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = base + cost
                        back[i + 1][j + 1] = "d"
                if i < R and base + SKIP < dp[i + 1][j]:
                    dp[i + 1][j] = base + SKIP
                    back[i + 1][j] = "u"
                if j < O and base + SKIP < dp[i][j + 1]:
                    dp[i][j + 1] = base + SKIP
                    back[i][j + 1] = "l"
        pairs = []
        i, j = R, O
        while i > 0 or j > 0:
            m = back[i][j]
            if m == "d":
                pairs.append((i - 1, j - 1)); i -= 1; j -= 1
            elif m == "u":
                pairs.append((i - 1, None)); i -= 1
            else:
                pairs.append((None, j - 1)); j -= 1
        return list(reversed(pairs))

    mapping: list[int | None] = [None] * len(our_roots)
    for ri, oi in dp_align(ref_roots, our_roots):
        if ri is not None and oi is not None:
            mapping[oi] = ri

    # 2패스 — 반복 구간: 1패스에서 못 붙은 오디오 꼬리 구간(연주 있음)을
    # 참조 전체에 다시 정렬한다. 드라우닝: 2절(우리 61~96)이 참조 25~60에
    # 다시 붙는다.
    unmatched = [j for j in range(len(our_roots))
                 if mapping[j] is None and our_roots[j] is not None]
    if unmatched:
        # 연속 구간 단위로
        runs: list[list[int]] = [[unmatched[0]]]
        for j in unmatched[1:]:
            if j == runs[-1][-1] + 1:
                runs[-1].append(j)
            else:
                runs.append([j])
        for run in runs:
            if len(run) < 4:
                continue  # 짧은 구멍은 억지로 붙이지 않는다
            sub = [our_roots[j] for j in run]
            for ri, oi in dp_align(ref_roots, sub):
                if ri is not None and oi is not None:
                    mapping[run[oi]] = ri
    return mapping


# ─── 표시용 alphaTex (오디오 마디 순서로 펼침) ──────────────────────────────

def _bar_tokens(bar: dict | None, beats_per_bar: int) -> str:
    """참조 마디 하나 → alphaTex 토큰. 온셋을 균등 배치한다."""
    if bar is None:
        return "r.1"
    tab = bar.get("tab") or []
    onsets = []
    for t in tab:
        s = _STRING_NO.get(str(t.get("string", "")).upper())
        f = t.get("fret")
        if s is not None and isinstance(f, int) and 0 <= f <= 24:
            onsets.append((f, s))
    if not onsets:
        return "r.1"
    n = len(onsets)
    # 균등 배치 — 온셋을 다 담는 가장 성긴 격자를 고른다(굵을수록 읽기 쉽다).
    # 격자보다 온셋이 많으면(판독 과잉) 16분까지 늘리고 그래도 넘치면 자른다.
    for slots, duration in ((beats_per_bar, 4), (beats_per_bar * 2, 8),
                            (beats_per_bar * 4, 16)):
        if n <= slots:
            break
    else:
        slots, duration = beats_per_bar * 4, 16
        onsets = onsets[:slots]
    toks = [f"{f}.{s}.{duration}" for f, s in onsets]
    toks.extend([f"r.{duration}"] * (slots - len(toks)))
    return " ".join(toks)


def _with_chord(token_line: str, chord: str | None) -> str:
    if not chord:
        return token_line
    head, *rest = token_line.split(" ", 1)
    safe = chord.replace('"', "'")
    head = f'{head}{{ch "{safe}"}}'
    return " ".join([head] + rest)


def build_tex(ref: dict, qscore, mapping: list[int | None], title: str) -> str:
    """참조 악보를 오디오 마디 순서로 펼친 alphaTex."""
    lines = [f'\\title "{title.replace(chr(34), chr(39))}"',
             f"\\tempo {qscore.median_bpm:.0f}"]
    ks = ref.get("keySignature")
    if ks:
        lines.append(f"\\ks {ks}")
    lines.append(".")
    lines.append("")
    lines.append('\\track "Bass"')
    lines.append("\\staff{score tabs} \\clef bass")
    if ks:
        lines.append(f"\\ks {ks}")
    lines.append(f"\\ts {qscore.beats_per_bar} 4")
    lines.append("")

    bar_texts = []
    last_chord = None
    for i in range(len(qscore.bars)):
        ri = mapping[i] if i < len(mapping) else None
        rb = ref["bars"][ri] if ri is not None else None
        text = _bar_tokens(rb, qscore.beats_per_bar)
        chord = None
        if rb:
            chords = rb.get("chords") or []
            if chords and chords[0] != last_chord:
                chord = chords[0]
                last_chord = chords[0]
        bar_texts.append(_with_chord(text, chord) if text != "r.1" else text)
    lines.append(" |\n".join(bar_texts))
    return "\n".join(lines) + "\n"

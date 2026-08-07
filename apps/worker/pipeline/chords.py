"""코드 심볼 — 마디별 코드 이름을 뽑는다.

참조 악보(akbobada)는 오선 위에 코드 심볼이 붙는다(A♭, Cm7, D♭m6/E …).
그것을 내려면 마디마다 코드를 알아야 한다.

## 베이스 음은 코드의 **맨 아래 음**이지 루트가 아니다

일반적인 코드 인식은 24개(장·단 12개) 이상의 후보를 크로마와 매칭한다. 우리는
베이스 채보에서 **마디의 최저음을 이미 안다**(`reduce.bar_root`). 그것이 후보를
크게 줄여준다 — 다만 **그 음을 루트로 단정하면 분수 코드에서 틀린다.**

베이시스트가 E를 짚었다고 코드가 E는 아니다. C 코드의 3음일 수도 있고(C/E)
A 코드의 5음일 수도 있다(A/E). 참조 악보에 `Eb/G`·`Ebm/Gb`·`Fdim/Ab` 같은
분수 코드가 즐비하므로 이것을 구분하지 못하면 참조 악보를 재현할 수 없다.

그래서 후보를 이렇게 잡는다: **베이스 음이 코드 구성음 중 하나**라는 전제만
쓴다. 루트 R의 후보는 `베이스음 - R`이 유니슨·3도·5도인 것들뿐이다. 24개가
5개 안쪽으로 줄면서도 루트를 단정하지 않는다. 루트가 베이스 음과 같으면 그냥
코드 이름, 다르면 분수 코드로 적는다.

## 어느 스템의 크로마를 보는가

베이스가 아니라 **other 스템**(기타·건반 등 화성 악기)을 본다. 베이스 스템에는
근음만 있어서 3도가 들어 있지 않다. other가 없으면 원본 믹스를 쓴다.

## 확신 없으면 이름을 붙이지 않는다

3도 근거가 약한 마디는 코드를 비운다. 틀린 코드는 없는 코드보다 나쁘다 —
연습자가 그 코드를 믿고 다른 악기와 맞춰보면 어긋난다.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

HARMONY_PATH = Path(__file__).with_name("harmony.json")


@lru_cache(maxsize=1)
def harmony() -> dict:
    """화성학 지식 데이터. 조회가 잦으므로 한 번만 읽는다."""
    return json.loads(HARMONY_PATH.read_text(encoding="utf-8"))


# 근음 대비 반음 거리
MINOR_THIRD = 3
MAJOR_THIRD = 4
PERFECT_FIFTH = 7
MINOR_SEVENTH = 10   # 표기하지 않지만 도수 정의는 남긴다
MAJOR_SEVENTH = 11

# 판정에 쓸 코드 품질. **7도 계열은 넣지 않는다** — 아래 주석의 실측 근거 참조.
# harmony.json에는 정의가 다 들어 있으므로 골든셋으로 채점한 뒤 늘리면 된다.
ALLOWED_QUALITIES = ("major", "minor")

# 근음 자리(분수 코드가 아닌 것)에 주는 가산점. 크로마에는 인접 화음과 배음이
# 새어 들어오므로, 분수 코드는 **분명히 더 잘 맞을 때만** 이기게 한다.
# 실제 음악에서도 근음 자리가 압도적으로 흔하다.
ROOT_POSITION_BONUS = 1.20

# 3도 판정을 신뢰하는 최소 우세도. 장3도와 단3도 에너지 중 큰 쪽이 작은 쪽의
# 이 배수를 넘어야 이름을 붙인다. 두 값이 거의 같은 경우(3도가 연주되지 않은
# 구간)를 걸러내는 것이 목적이다.
THIRD_MARGIN = 1.15

# **7도는 표기하지 않는다.** 실측 근거: Champagne Supernova(삼화음 E·D·C#m·B
# 진행, 참조 악보로 확인)에서 7도 문턱 0.55로 재보니 거의 모든 마디에 7이
# 붙었고(E7·D7·Dbm7·B7), 같은 D 마디가 D7과 DM7로 갈리기까지 했다. 크로마의
# 7도 성분은 배음과 인접 화음에서 새어 들어오기 때문이다. 문턱을 올려 맞추는
# 것은 곡마다 다른 값을 추측하는 것이므로 하지 않는다. 없는 텐션을 알려주는
# 것보다 삼화음으로 적는 편이 정직하다.
#
# 7도를 되살리려면 골든셋(코드 진행 정답)으로 문턱을 채점해야 한다.

PITCH_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


@dataclass
class BarChord:
    bar_index: int
    # 베이스가 짚은 음(코드의 맨 아래 음). 루트와 다를 수 있다.
    bass_pitch_class: int
    # 판정된 코드 루트. 판정 불가면 베이스 음과 같게 둔다.
    root_pitch_class: int
    # "Ab", "Cm", "C/E" 같은 표기. 확신이 없으면 빈 문자열.
    name: str
    quality: str | None     # "major" / "minor" / None(판정 불가)
    # 베이스가 루트가 아니면 True (분수 코드)
    inverted: bool
    confidence: float       # 최선 후보 대 차선 후보 비율 (1.0 = 구분 없음)

    def to_dict(self) -> dict:
        return {
            "bar": self.bar_index,
            # 피치클래스를 숫자로 남긴다. 이조할 때 이름을 파싱하는 것보다
            # 안전하다(Db/C# 같은 이명동음 표기 문제가 없다).
            "bassPitchClass": self.bass_pitch_class,
            "rootPitchClass": self.root_pitch_class,
            "name": self.name,
            "quality": self.quality,
            "inverted": self.inverted,
            "confidence": round(self.confidence, 3),
        }


def name_of(root_pc: int, quality: str | None, bass_pc: int | None = None) -> str:
    """코드 이름을 만든다.

    품질을 모르면 근음만 적는다 — 틀린 장/단을 붙이는 것보다 낫다.
    베이스 음이 루트와 다르면 분수 코드로 적는다(`C/E`).
    """
    name = PITCH_NAMES[root_pc]
    if quality is not None:
        name += harmony()["chordQualities"][quality]["suffix"]
    if bass_pc is not None and bass_pc % 12 != root_pc % 12:
        name += "/" + PITCH_NAMES[bass_pc % 12]
    return name


def _candidates(bass_pc: int) -> list[tuple[int, str, bool]]:
    """베이스 음이 구성음 중 하나라는 전제로 (루트, 품질, 근음자리인가)를 만든다.

    베이스 음을 루트로 단정하지 않는 것이 핵심이다. 루트 R의 후보는
    `베이스음 - 역할반음`이고, 역할은 근음·3도·5도만 본다(7도를 베이스가
    짚는 경우는 드물고 오검출 위험이 크다 — harmony.json bassRoles 주석).
    """
    qualities = harmony()["chordQualities"]
    out: list[tuple[int, str, bool]] = []
    seen: set[tuple[int, str]] = set()
    for quality in ALLOWED_QUALITIES:
        for tone in qualities[quality]["tones"]:
            if tone not in (0, MINOR_THIRD, MAJOR_THIRD, PERFECT_FIFTH):
                continue
            root = (bass_pc - tone) % 12
            key = (root, quality)
            if key in seen:
                continue
            seen.add(key)
            out.append((root, quality, tone == 0))
    return out


def _score(chroma_profile, root: int, quality: str) -> float:
    """코드 적합도 = 구성음 평균 − 비구성음 평균.

    **비구성음 감점이 없으면 분수 코드를 가릴 수 없다.** 실측 사례: C 장3화음
    (C·E·G) 위에 베이스 E를 놓고 구성음만 보면 Em(E·G·B)이 B 없이도 만점을
    받아 C/E를 이긴다. 두 코드를 가르는 것은 정확히 "C가 있나 B가 있나"이므로
    화음 밖 에너지를 벌점으로 봐야 한다.

    5도를 빼서도 안 된다. C major와 Em을 가르는 음이 각각 C(근음)와 B(5도)라서,
    5도를 제외하면 Em이 결정적 음을 보지 않고 통과한다.
    """
    tones = {(root + t) % 12 for t in harmony()["chordQualities"][quality]["tones"]}
    inside = [float(chroma_profile[pc]) for pc in tones]
    outside = [float(chroma_profile[pc]) for pc in range(12) if pc not in tones]
    return sum(inside) / len(inside) - (sum(outside) / len(outside) if outside else 0.0)


def decide(profile, bass_pc: int) -> tuple[int, str | None, bool, float]:
    """크로마 한 벌과 베이스 음으로 코드를 정한다.

    반환 (루트 피치클래스, 품질 또는 None, 분수 코드인가, 확신도).

    오디오와 분리해 둔 이유는 **합성 화음으로 채점할 수 있게** 하려는 것이다.
    실곡에 분수 코드가 없으면 이 판정을 검증할 방법이 없다.

    판별이 두 개이고 지표가 다르다. 하나로 합치면 안 된다.
      (1) 장/단 — 3도 자리 크로마 직접 비교
      (2) 근음 자리 대 분수 코드 — 구성음 평균 점수 비교
    """
    minor_third = float(profile[(bass_pc + MINOR_THIRD) % 12])
    major_third = float(profile[(bass_pc + MAJOR_THIRD) % 12])
    best_quality = "minor" if minor_third > major_third else "major"
    strong, weak = max(minor_third, major_third), min(minor_third, major_third)
    quality_ratio = strong / weak if weak > 1e-6 else float("inf")

    root_scores = {
        quality: _score(profile, bass_pc, quality) for quality in ALLOWED_QUALITIES
    }
    slash = [
        (_score(profile, root, quality), root, quality)
        for root, quality, is_root in _candidates(bass_pc)
        if not is_root
    ]
    best_slash = max(slash) if slash else None

    # 분수 코드는 근음 자리를 ROOT_POSITION_BONUS만큼 이겨야 채택된다. 크로마에
    # 인접 화음과 배음이 새어 들어오고, 실제 음악에서 근음 자리가 훨씬 흔하다.
    baseline = root_scores[best_quality]
    if best_slash and best_slash[0] > baseline * ROOT_POSITION_BONUS:
        score, root, quality = best_slash
        return root, quality, True, min(score / max(baseline, 1e-6), 99.0)

    if quality_ratio < THIRD_MARGIN:
        # 장3도와 단3도가 구분되지 않는다. 품질을 찍지 않고 베이스 음만 적는다.
        return bass_pc, None, False, min(quality_ratio, 99.0)
    return bass_pc, best_quality, False, min(quality_ratio, 99.0)


# ─── 조성 검출 ──────────────────────────────────────────────────────────────
#
# 코드 진행이 나오면 조성은 계산으로 떨어진다. 오디오를 다시 볼 필요가 없다.
#
# 조성을 아는 것은 두 가지에 쓰인다.
#   1) 조표 표기 — 참조 악보에 조표가 있다(SCR-16)
#   2) **코드 판정의 안전장치** — 조성 밖 코드는 의심하고 표시할 수 있다

# 장조의 다이어토닉 3화음: I ii iii IV V vi vii°
MAJOR_TRIADS = ((0, "major"), (2, "minor"), (4, "minor"), (5, "major"),
                (7, "major"), (9, "minor"), (11, "diminished"))
# 자연단조: i ii° III iv v VI VII. 화성단조의 V(장조)도 흔하므로 함께 인정한다.
MINOR_TRIADS = ((0, "minor"), (2, "diminished"), (3, "major"), (5, "minor"),
                (7, "minor"), (7, "major"), (8, "major"), (10, "major"))

# 토닉 화음이 등장하면 주는 가산점(마디 수에 비례). 다이어토닉 일치만으로는
# 나란한조·딸림조가 자주 동점이 된다 — 실측: Champagne Supernova에서 E장조와
# A장조가 3대3으로 갈렸다. 토닉이 실제로 울리는지가 결정적 단서다.
TONIC_WEIGHT = 1.5


@dataclass
class KeyEstimate:
    tonic_pitch_class: int
    mode: str               # "major" / "minor"
    name: str               # "E", "Am" 같은 표기
    # alphaTab `\ks`에 넣을 조표 이름(장조 이름). 단조는 나란한장조를 쓴다.
    signature_name: str
    flats: int              # 음수면 샾
    confidence: float       # 최선 대 차선 비율
    diatonic_ratio: float   # 조성 안에 든 마디 비율
    # 조성 밖 코드가 쓰인 마디. 코드 판정을 의심할 자리다.
    outside_bars: list[int] = field(default_factory=list)
    # **조표를 찍어도 되는가.** False면 이름은 참고로 보여줄 수 있지만 악보에
    # 조표를 넣지 않는다. 틀린 조표는 임시표를 전부 어긋나게 해서 조표가
    # 없는 것보다 나쁘다.
    trusted: bool = True
    # trusted가 False인 이유. 사용자에게 그대로 보여줄 수 있는 문장이다.
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "tonicPitchClass": self.tonic_pitch_class,
            "mode": self.mode,
            "name": self.name,
            "signatureName": self.signature_name,
            "flats": self.flats,
            "confidence": round(self.confidence, 3),
            "diatonicRatio": round(self.diatonic_ratio, 3),
            "outsideBars": self.outside_bars,
            "trusted": self.trusted,
            "reason": self.reason,
        }


def _triads_of(tonic: int, mode: str) -> set[tuple[int, str]]:
    table = MAJOR_TRIADS if mode == "major" else MINOR_TRIADS
    return {((tonic + step) % 12, quality) for step, quality in table}


def signature_for(tonic: int, mode: str) -> tuple[str, int]:
    """조표 이름과 플랫 수. 단조는 나란한장조의 조표를 쓴다."""
    data = harmony()["keySignatures"]
    if mode == "major":
        for name, info in data["major"].items():
            if info["tonic"] == tonic:
                return name, info["flats"]
        return PITCH_NAMES[tonic], 0
    for major_name, minor_tonic in data["relativeMinorOf"].items():
        if minor_tonic == tonic:
            return major_name, data["major"][major_name]["flats"]
    return PITCH_NAMES[tonic], 0


# 조표를 찍을 최소 다이어토닉 비율.
#
# **이 값은 추측이 아니라 상한이 정해져 있다.** 실곡(Champagne Supernova 커버)에서
# 우리 검출이 E major를 냈고 다이어토닉 비율이 **0.707**이었다. 그 답은 나중에
# Songsterr 사람 채보로 검증됐다 — 원곡이 A major이고 커버가 완전4도 아래이므로
# E major가 맞다(`MARKET.md` 벤치마크).
#
# 즉 **0.707은 맞는 답의 값이다.** 임계를 그보다 높게 두면 정답을 버린다.
# 0.60은 그 아래에서 "명백히 안 맞는 경우"만 걸러내는 자리다.
#
# 더 조이려면 골든셋에 조표 정답이 있는 곡을 모아야 한다 — Songsterr 채보 중
# `keySignature`를 담은 것이 있다(Come Together = 2샵 major). 지금 검증된 표본이
# 한 곡이라 이 값을 좁힐 근거가 없다.
MIN_DIATONIC_RATIO = 0.60

# 최선 대 차선 점수 비율의 하한.
#
# 실곡의 이 값이 **1.065**였고 그 답이 맞았다. 나란한조·딸림조는 구성음이 6개
# 겹쳐서 정답이라도 이 비율이 1에 가깝다 — 즉 **이 지표로는 못 가른다.**
# 1.0(동점)만 배제하는 자리에 둔다.
MIN_KEY_CONFIDENCE = 1.02


def detect_key(
    bar_chords: list[BarChord], *, verbose: bool = False
) -> KeyEstimate | None:
    """코드 진행에서 조성을 추정한다. 판정할 코드가 없으면 None.

    24조 후보를 다이어토닉 일치로 채점하고 토닉 등장에 가산점을 준다.
    가산점이 없으면 나란한조·딸림조가 동점이 되어 갈리지 않는다.

    **확신이 없으면 `trusted=False`로 표시한다.** 조표를 찍는 쪽이 안 찍는 쪽보다
    나쁠 수 있다 — 조표가 틀리면 임시표가 전부 어긋나 악보가 오히려 읽기 어려워진다.
    조표를 쓸지 말지는 부르는 쪽이 `trusted`를 보고 정한다(`jobs._load_key_signature`).
    """
    usable = [c for c in bar_chords if c.name and c.quality is not None]
    if len(usable) < 4:
        return None

    counts: dict[tuple[int, str], int] = defaultdict(int)
    for c in usable:
        counts[(c.root_pitch_class, c.quality)] += 1
    total = sum(counts.values())

    scored: list[tuple[float, int, str]] = []
    for tonic in range(12):
        for mode in ("major", "minor"):
            triads = _triads_of(tonic, mode)
            inside = sum(n for chord, n in counts.items() if chord in triads)
            tonic_quality = "major" if mode == "major" else "minor"
            tonic_hits = counts.get((tonic, tonic_quality), 0)
            scored.append((inside + TONIC_WEIGHT * tonic_hits, tonic, mode))

    scored.sort(reverse=True)
    best_score, tonic, mode = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0
    confidence = best_score / runner if runner > 1e-6 else float("inf")

    triads = _triads_of(tonic, mode)
    outside = [
        c.bar_index for c in usable
        if (c.root_pitch_class, c.quality) not in triads
    ]
    inside_count = total - sum(
        n for chord, n in counts.items() if chord not in triads
    )

    signature_name, flats = signature_for(tonic, mode)
    diatonic_ratio = inside_count / total if total else 0.0

    # 조표를 찍어도 되는지 판정한다. 두 조건을 모두 넘어야 한다.
    reasons: list[str] = []
    if diatonic_ratio < MIN_DIATONIC_RATIO:
        reasons.append(
            f"코드 진행의 {100 * diatonic_ratio:.0f}%만 이 조성에 들어맞습니다"
            f" (기준 {100 * MIN_DIATONIC_RATIO:.0f}%)"
        )
    if confidence < MIN_KEY_CONFIDENCE:
        reasons.append("다른 조성과 점수가 거의 같아 하나를 고를 근거가 부족합니다")
    trusted = not reasons

    estimate = KeyEstimate(
        tonic_pitch_class=tonic,
        mode=mode,
        name=PITCH_NAMES[tonic] + ("m" if mode == "minor" else ""),
        signature_name=signature_name,
        flats=flats,
        confidence=min(confidence, 99.0),
        diatonic_ratio=diatonic_ratio,
        outside_bars=outside,
        trusted=trusted,
        reason=(
            "" if trusted
            else "조표를 표시하지 않습니다 — " + ", ".join(reasons)
            + ". 틀린 조표는 임시표를 어긋나게 해서 없는 것보다 나쁩니다."
        ),
    )
    if verbose:
        print(
            f"[key] {estimate.name} (조표 {signature_name}, "
            f"플랫 {flats}), 다이어토닉 {100 * estimate.diatonic_ratio:.0f}%, "
            f"확신도 {estimate.confidence:.2f}, 조성 밖 {len(outside)}마디"
            + ("" if trusted else "  <- 조표 미표시")
        )
        if not trusted:
            print(f"[key] {estimate.reason}")
    return estimate


def detect(
    audio_path: Path,
    bars: list[tuple[int, float, float, int | None]],
    *,
    verbose: bool = False,
) -> list[BarChord]:
    """마디별 코드를 판정한다.

    bars는 (마디 인덱스, 시작초, 끝초, **베이스 최저음** MIDI 또는 None) 목록이다.
    음이 없는 마디는 코드도 비운다.
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    # CQT 크로마가 화성 분석에 STFT 크로마보다 안정적이다(저음역 해상도).
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    times = librosa.times_like(chroma, sr=sr)

    # 코드는 마디마다 따로 판정하지 않고 **같은 베이스 음의 마디를 전곡에서
    # 모아** 한 번 판정한다. 마디 단위로는 결과가 흔들린다 — 실측 사례: 같은
    # B 코드가 마디에 따라 B / B7 / 판정불가로 갈렸다. 한 곡 안에서 같은 베이스
    # 음 위 코드가 바뀌는 일은 드물어 모아서 보는 편이 음악적으로도 맞다.
    accum: dict[int, list] = {}   # bass_pc -> [크로마 합, 마디 수]
    for index, start, end, bass in bars:
        if bass is None:
            continue
        mask = (times >= start) & (times < end)
        if not mask.any():
            continue
        profile = chroma[:, mask].mean(axis=1)
        acc = accum.setdefault(bass % 12, [np.zeros(12), 0])
        acc[0] = acc[0] + profile
        acc[1] += 1

    # 베이스 음별로 판정한다. 판정 규칙은 `decide()`에 있다 — 오디오와 분리해
    # 합성 화음으로 채점할 수 있게 뺐다.
    decided = {
        bass_pc: decide(total / max(count, 1), bass_pc)
        for bass_pc, (total, count) in accum.items()
    }

    out: list[BarChord] = []
    for index, start, end, bass in bars:
        if bass is None:
            out.append(BarChord(index, 0, 0, "", None, False, 1.0))
            continue
        bass_pc = bass % 12
        root_pc, quality, inverted, ratio = decided.get(
            bass_pc, (bass_pc, None, False, 1.0)
        )
        out.append(
            BarChord(
                bar_index=index,
                bass_pitch_class=bass_pc,
                root_pitch_class=root_pc,
                name=name_of(root_pc, quality, bass_pc if inverted else None),
                quality=quality,
                inverted=inverted,
                confidence=ratio,
            )
        )

    if verbose:
        named = sum(1 for c in out if c.name)
        judged = sum(1 for c in out if c.quality is not None)
        slashes = sum(1 for c in out if c.inverted)
        detail = ", ".join(
            f"{PITCH_NAMES[pc]}베이스→"
            f"{name_of(r, q, pc if inv else None)}({conf:.2f})"
            for pc, (r, q, inv, conf) in sorted(decided.items())
        )
        print(
            f"[chords] {len(out)}마디: 이름 있음 {named}, 품질 판정 {judged}, "
            f"분수 코드 {slashes}마디"
        )
        print(f"[chords] 베이스음별 판정: {detail}")
    return out

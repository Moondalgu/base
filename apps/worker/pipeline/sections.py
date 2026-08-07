"""곡 구조 분할 — 베이스 노트만 보고 섹션 경계를 찾는다.

## 왜 필요한가

패턴 관성(`inertia.py`)은 "섹션 안에서 리듬이 반복된다"는 사실을 쓴다. 그런데
섹션을 몰라서 **12마디 고정 창**으로 잘랐다. 그 창은 곡 구조와 아무 관계가
없고, 벌스 8마디와 코러스 4마디를 한 창에 묶으면 조용한 리듬이 격한 리듬을
오염시킨다(또는 반대로). 벌스는 마디당 1~3타, 코러스는 8~16타인데
(`playing.json` songSections) 그 둘의 최빈 패턴을 하나로 뽑는 것은 무의미하다.

## 어떻게 하는가

오디오를 다시 보지 않는다. **양자화된 노트에서 마디별 특징벡터**를 만들고
자기유사도 행렬(SSM)의 대각선에서 변화가 큰 지점을 경계로 잡는다.

특징벡터 (마디마다):
    - 음높이 클래스 히스토그램 12차 — 화성이 바뀌면 여기가 바뀐다
    - 타현 수 (정규화) — 밀도가 바뀌면 섹션이 바뀐다
    - 음역 중심·폭 (정규화) — 코러스는 위로 올라간다
    - 리듬 슬롯 히스토그램 — 어디를 치는가

## 4의 배수로 스냅한다

대중음악의 섹션은 4·8·16마디로 떨어진다. SSM이 낸 후보를 가장 가까운 4의
배수 자리로 옮긴다. **원 후보를 버리지 않고 옮기는** 것이 요점이다 — 4의
배수를 강제로 자르기만 하면 12마디 고정 창과 다를 게 없다.

## 못 찾으면 정직하게 못 찾았다고 한다

경계가 하나도 안 나오면 곡 전체를 한 섹션으로 돌려준다. 그것이 "구조가
단조롭다"는 정보이고, 억지 경계를 만드는 것보다 낫다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .quantize import Bar, QuantizedScore

# 경계 후보를 볼 때 앞뒤로 몇 마디를 비교하는가.
#
# 4마디: 대중음악에서 가장 짧은 구조 단위다. 2마디로 좁히면 필인 한 마디에
# 반응해 경계가 남발되고, 8마디로 넓히면 8마디 섹션의 경계를 자기 창 안에
# 삼켜 못 찾는다.
KERNEL_BARS = 4

# 노벨티가 이 값을 넘으면 경계 후보로 본다. 특징벡터를 L1 정규화해서
# 거리가 0~2 범위이므로 0.5는 "앞뒤 4마디가 절반 이상 다르다"는 뜻이다.
NOVELTY_THRESHOLD = 0.5

# 경계를 4의 배수 자리로 옮길 때 허용하는 이동 폭(마디).
# 2를 넘게 옮기면 원래 후보와 다른 곳을 가리키게 된다.
SNAP_TOLERANCE = 2

# 섹션 하한(마디).
#
# **8이다. 4가 아니다.** 실측: 4로 두었을 때 4마디 섹션이 나왔고, 그 안에서
# 최빈 패턴을 뽑으려면 슬롯 하나가 4마디 중 2마디에만 나와도 인정된다. 우리
# 검출이 흔들리는 상황에서 이 투표는 불안정해서 정답 3타 마디를 2타로 통일했다
# (영상 25마디, 16마디 대조에서 유일한 실패).
#
# 관성이 창을 12마디로 넓힌 것과 같은 이유다 — 반복되는 축을 뽑으려면 표본이
# 필요하다. 8마디는 대중음악의 가장 흔한 섹션 길이이면서 투표가 견디는 하한이다.
MIN_SECTION_BARS = 8

# 섹션 상한(마디). 이보다 길면 절반으로 쪼갠다. 구조가 단조로운 곡에서
# 섹션 하나가 60마디가 되면 관성 창의 의미가 없어진다 — 그 안에서 리듬이
# 바뀌었는데도 하나로 통일해 버린다.
MAX_SECTION_BARS = 16

# 관성 모듈이 쓰는 특징 집합.
#
# **리듬만 본다.** 관성이 통일하는 것은 리듬이고 음높이는 건드리지 않는다.
# 그러니 경계도 리듬이 바뀌는 자리여야 한다. 화성까지 넣으면 **코드가 바뀔
# 때마다 경계가 생긴다** — 실측: 같은 그루브를 4마디씩 네 조각으로 잘랐고,
# 조각이 짧아 최빈 패턴 투표가 무너졌다.
#
# 베이시스트는 코드가 바뀌어도 리듬을 유지한다(`playing.json` patternInertia:
# "코드 근음만 바뀐다"). 그 사실이 곧 "화성 변화는 리듬 경계가 아니다"다.
FEATURES_RHYTHM = "rhythm"
FEATURES_FULL = "full"


@dataclass
class SectionReport:
    boundaries: list[int] = field(default_factory=list)
    novelty_peaks: int = 0
    snapped: int = 0
    merged_short: int = 0
    split_long: int = 0
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "boundaries": self.boundaries,
            "noveltyPeaks": self.novelty_peaks,
            "snapped": self.snapped,
            "mergedShort": self.merged_short,
            "splitLong": self.split_long,
            "reason": self.reason,
        }


def _features(bar: Bar, max_attacks: int, *, rhythm_only: bool) -> list[float]:
    """마디 하나의 특징벡터. 각 블록을 따로 L1 정규화한다.

    블록마다 정규화하는 이유: 12차 피치 히스토그램과 1차 밀도를 한 번에
    정규화하면 차원 수가 많은 쪽이 거리를 지배한다. 화성 변화와 밀도 변화가
    같은 무게를 갖게 해야 벌스→코러스(밀도 변화)와 코드 전환(화성 변화)이
    둘 다 잡힌다.

    `rhythm_only`면 음높이에 관한 블록(피치 히스토그램·음역)을 뺀다. 왜
    필요한가는 `FEATURES_RHYTHM` 주석에 있다.
    """
    density = [min(1.0, len(bar.notes) / max(1, max_attacks))] if bar.notes else [0.0]

    # 박 단위 4분할 — 어느 박에 치는가. 슬롯 수가 곡마다 달라도 비교된다.
    beats = [0.0] * 4
    if bar.notes:
        for n in bar.notes:
            idx = min(3, int(4 * n.slot / max(1, bar.slots_per_bar)))
            beats[idx] += 1
        bt = sum(beats)
        beats = [v / bt for v in beats]

    if rhythm_only:
        return density + beats

    if not bar.notes:
        return [0.0] * 12 + density + [0.0, 0.0] + beats

    pcs = [0.0] * 12
    for n in bar.notes:
        pcs[n.pitch % 12] += 1
    total = sum(pcs)
    pcs = [v / total for v in pcs]

    pitches = [n.pitch for n in bar.notes]
    # 4현 베이스 음역(28~63) 안에서의 상대 위치·폭.
    centre = (sum(pitches) / len(pitches) - 28) / 35
    width = (max(pitches) - min(pitches)) / 35
    register = [max(0.0, min(1.0, centre)), max(0.0, min(1.0, width))]

    return pcs + density + register + beats


def _novelty(feats: list[list[float]], kernel: int) -> list[float]:
    """마디 i의 앞 kernel마디와 뒤 kernel마디 사이의 평균 L1 거리."""
    n = len(feats)
    out = [0.0] * n
    for i in range(n):
        before = feats[max(0, i - kernel) : i]
        after = feats[i : i + kernel]
        if not before or not after:
            continue
        pairs = 0
        acc = 0.0
        for a in before:
            for b in after:
                acc += sum(abs(x - y) for x, y in zip(a, b))
                pairs += 1
        out[i] = acc / pairs if pairs else 0.0
    return out


def detect(
    score: QuantizedScore,
    *,
    kernel: int = KERNEL_BARS,
    features: str = FEATURES_RHYTHM,
    verbose: bool = False,
) -> tuple[list[tuple[int, int]], SectionReport]:
    """섹션을 [(시작마디index, 끝마디index+1), ...]로 돌려준다.

    항상 곡 전체를 덮는다 — 빈틈이 생기면 관성 모듈이 그 마디를 건드리지
    않아 조용히 통일에서 빠진다.
    """
    bars = list(score.bars)
    report = SectionReport()
    if len(bars) < MIN_SECTION_BARS * 2:
        report.reason = "마디가 너무 적어 구조를 나누지 않는다"
        report.boundaries = [0]
        return [(0, len(bars))], report

    max_attacks = max((len(b.notes) for b in bars), default=1)
    rhythm_only = features == FEATURES_RHYTHM
    feats = [_features(b, max_attacks, rhythm_only=rhythm_only) for b in bars]
    novelty = _novelty(feats, kernel)

    # 국소 최대만 후보로 삼는다. 문턱만 쓰면 한 경계 주변 여러 마디가
    # 다 후보가 되어 섹션이 잘게 부서진다.
    raw: list[int] = []
    for i in range(1, len(novelty) - 1):
        if (novelty[i] >= NOVELTY_THRESHOLD
                and novelty[i] >= novelty[i - 1]
                and novelty[i] > novelty[i + 1]):
            raw.append(i)
    report.novelty_peaks = len(raw)

    # 4의 배수 자리로 옮긴다.
    snapped: list[int] = []
    for i in raw:
        target = round(i / 4) * 4
        if target != i and abs(target - i) <= SNAP_TOLERANCE:
            report.snapped += 1
            i = target
        if 0 < i < len(bars) and i not in snapped:
            snapped.append(i)
    snapped.sort()

    # 너무 짧은 섹션은 앞에 붙이고, 너무 긴 섹션은 4의 배수 자리에서 쪼갠다.
    bounds = [0]
    for i in snapped:
        if i - bounds[-1] < MIN_SECTION_BARS:
            report.merged_short += 1
            continue
        bounds.append(i)
    bounds.append(len(bars))

    final: list[int] = [0]
    for a, b in zip(bounds, bounds[1:]):
        span = b - a
        if span > MAX_SECTION_BARS:
            step = MAX_SECTION_BARS - (MAX_SECTION_BARS % 4)
            cut = a + step
            while cut < b and b - cut >= MIN_SECTION_BARS:
                final.append(cut)
                report.split_long += 1
                cut += step
        if b < len(bars):
            final.append(b)
    final = sorted(set(final))

    sections = [
        (a, b) for a, b in zip(final, final[1:] + [len(bars)]) if b > a
    ]
    report.boundaries = final
    report.reason = (
        f"노벨티 봉우리 {report.novelty_peaks}개 -> 섹션 {len(sections)}개"
        if report.novelty_peaks else "구조 변화가 없어 길이로만 나눴다"
    )
    if verbose:
        print(
            f"[sections] 섹션 {len(sections)}개 "
            f"(봉우리 {report.novelty_peaks}, 4배수 스냅 {report.snapped}, "
            f"짧아서 합침 {report.merged_short}, 길어서 쪼갬 {report.split_long}, "
            f"특징={features})"
        )
        print("[sections] 경계 마디: " + ", ".join(str(b + 1) for b in final))
    return sections, report

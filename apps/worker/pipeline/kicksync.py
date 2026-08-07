"""킥 동기화 — 드럼 스템의 킥 위치로 베이스 타현 판정을 보강한다.

## 왜 킥인가

`playing.json` kickLock: **베이스 오른손 타격의 80% 이상이 드럼 킥과 정확히
일치한다.** 리듬 섹션이 하는 일이 그것이다.

그리고 킥은 우리가 검출하기 **쉽다.** 저역(50~120Hz)에 에너지가 몰린 짧고 명확한
트랜지언트다. 베이스는 지속음이라 어디서 다시 뜯었는지가 흐릿한데(그래서 재타현
분리가 실패했다 — `reattack.py`), 킥은 매번 새로 때린다.

즉 **검출이 쉬운 신호로 검출이 어려운 신호의 자리를 알려주는** 구조다.

## 무엇을 하고 무엇을 하지 않는가

- **한다**: 킥이 있는데 우리 음이 없는 자리를 **후보로 표시**한다. 그 자리에
  베이스 스템의 에너지가 있으면 음을 되살린다.
- **하지 않는다**: 킥이 없는 자리의 음을 지우지 않는다. 베이스는 킥과 무관한
  당김음·경과음을 치고, 지우는 쪽은 되살리는 쪽보다 훨씬 위험하다.

## 절대 하지 말 것 — 누출 판정에 쓰기

이미 한 번 그렇게 틀렸다. "킥 근처에 우리 음이 2.35배 몰려 있다"를 보고 킥이
베이스 스템에 누출됐다고 판단했는데, **베이스가 킥과 락을 맞추기 때문**이었다.
결정적 검사(킥은 때리는데 베이스는 조용한 5지점)에서 우리 검출은 0음이었다 —
누출은 없었다.

**킥 동기화는 "여기에 타현이 있을 만하다"에만 쓴다.** 상관관계를 인과로 읽는
자리가 정확히 여기다(`playing.json` kickLock.howToUse 주의 항목).

## 첫 곡에서는 발동하지 않는다 — 그것이 맞는 동작이다 (2026-08-07 실측)

기존 실곡(Champagne Supernova 커버 영상)에서 재보니:

| | 값 |
|---|---|
| 킥 검출 | 205개 = 마디당 1.99 (상식 범위) |
| 킥 위치 | **1박끝 27.3% + 3박끝 27.8% = 55%** — 두 자리에 몰린다 |
| **락 비율(베이스 기준)** | **6.1%** (문헌값 80%) |
| 베이스 온셋에서 가장 가까운 킥까지 | 중앙 **449ms** (≈8분음표) |
| 드럼 스템 RMS | 중앙 0.003 (베이스 0.139의 **1/46**) |

**킥 검출은 맞다** — 12개 자리 중 두 자리에 55%가 몰리는 것은 무작위가 아니다.
그런데 베이스와 안 맞는다. 여유를 30ms에서 150ms로 늘려도 락이 17%까지만 오른다.
거리 중앙값이 449ms이므로 **여유를 늘려서 되는 문제가 아니다.**

이유는 입력의 성질이다. 이 곡은 연습 영상이라 **드럼이 스피커로 재생된 반주**이고
베이스는 마이크 앞 직접 연주다. 드럼 스템이 46배 조용하고, 커버 연주자는 원곡
드럼과 정확히 맞추지 않았다.

`min_lock` 게이트가 이것을 잡아 **아무것도 하지 않는다.** 되살린 음 0개, 정확도
변화 0. 발동하지 않는 것이 옳은 동작이다 — 전제가 없는 곳에서 음을 만들면
거짓음만 늘어난다.

**판정은 골든셋으로 미룬다.** Queen "Another One Bites the Dust"는 킥과 베이스가
맞물리는 대표적인 곡이고(`eval/golden/SET.md`), 그 곡에서 락 비율이 문헌값에
가까이 나오면 이 모듈의 효과를 처음으로 잴 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SR = 22050
HOP = 256                    # 11.6ms. beats.py와 같은 홉을 쓴다.

# 킥을 볼 주파수 대역(Hz).
#
# 킥 드럼의 기본 성분은 50~100Hz에 몰린다. 상한을 200Hz까지 올리면 베이스 기음이
# 섞여 들어와 "킥이 있다"가 "베이스가 있다"와 같은 말이 된다 — 그러면 아무것도
# 알려주지 않는다.
KICK_FMIN, KICK_FMAX = 40.0, 120.0

# 킥 사이 최소 간격(초). 이보다 촘촘한 봉우리는 한 번의 타격으로 본다.
#
# **0.07초는 너무 짧았다.** 직접 만든 플럭스 봉우리 찾기 + 이 간격으로 재보니
# 336초 곡에서 킥 2017개(초당 6개)가 나왔다. 4/4 75BPM 103마디에서 킥은 많아도
# 마디당 4개, 즉 400개가 상한이다. 5배 과검출이었다.
#
# 0.12초는 16분음표(75BPM에서 200ms)보다 짧아 빠른 더블 킥을 살리면서
# 한 타격이 만드는 여러 봉우리는 묶는다.
KICK_MIN_GAP_SEC = 0.12

# 온셋 검출 민감도(`librosa.onset.onset_detect`의 delta).
#
# **플럭스 봉우리를 직접 찾지 않고 librosa를 쓴다.** 직접 만든 것은 "중앙값 대비
# 배수" 문턱이었는데, 플럭스 대부분이 0에 가까운 신호에서는 중앙값이 매우 작아
# 문턱이 무의미해진다. librosa의 peak_pick은 이동 평균 기준이라 그 함정이 없고
# 이미 검증된 구현이다(`beats.py`도 같은 계열을 쓴다).
KICK_DELTA = 0.12

# 검출된 킥 수가 마디당 이 범위를 벗어나면 **검출을 믿지 않는다.**
#
# 킥이 마디당 8개를 넘거나 0.5개도 안 되면 그것은 킥이 아니라 다른 것을 세고
# 있다는 뜻이다. 위의 2017개 사고를 다시 겪지 않기 위한 안전장치다.
KICKS_PER_BAR_RANGE = (0.5, 8.0)

# 킥과 베이스 음이 "같은 자리"라고 볼 시간 여유(초).
#
# 베이스는 킥보다 살짝 늦거나 이르게 들어온다. 30ms는 사람이 동시로 듣는 범위이고
# 16분음표(125ms)보다 훨씬 작아 인접 슬롯을 삼키지 않는다.
MATCH_TOLERANCE_SEC = 0.03


@dataclass
class KickReport:
    kicks: int = 0
    matched: int = 0            # 우리 음이 이미 있던 킥
    orphan: int = 0             # 우리 음이 없던 킥
    revived: int = 0            # 그중 베이스 에너지가 있어 되살린 것
    rejected_quiet: int = 0     # 베이스가 조용해서 되살리지 않은 것
    lock_ratio: float = 0.0     # 킥 중 우리 음이 있던 비율

    def to_dict(self) -> dict:
        return {
            "kicks": self.kicks,
            "matched": self.matched,
            "orphan": self.orphan,
            "revived": self.revived,
            "rejectedQuiet": self.rejected_quiet,
            "lockRatio": round(self.lock_ratio, 4),
        }


def detect_kicks(
    drums_path: Path, *, delta: float = KICK_DELTA, verbose: bool = False
) -> list[float]:
    """드럼 스템에서 킥 온셋 시각을 뽑는다. 스템이 없으면 빈 목록.

    저역(`KICK_FMIN~KICK_FMAX`)만 남긴 온셋 강도 곡선에 `librosa`의 peak_pick을
    걸어 봉우리를 찾는다. 대역을 좁게 두는 것이 요점이다 — 상한을 200Hz까지
    올리면 베이스 기음이 섞여 "킥이 있다"가 "베이스가 있다"와 같은 말이 된다.
    """
    import librosa
    import numpy as np

    if not Path(drums_path).exists():
        return []

    y, sr = librosa.load(str(drums_path), sr=SR, mono=True)
    if len(y) < 2048:
        return []

    # 킥 대역만 남긴 온셋 강도.
    #
    # **`onset_strength(fmin=, fmax=)`를 쓰면 안 된다.** 기본 n_mels=128을
    # 40~120Hz에 밀어넣으면 대부분의 멜 밴드가 비어
    # `UserWarning: Empty filters detected in mel frequency basis`가 나고
    # 강도 곡선이 쓰레기가 된다. 경고를 무시하고 그 위에서 문턱을 훑으면
    # 무효한 값을 고르게 된다.
    #
    # 대신 STFT에서 대역만 잘라 직접 만든다. n_mels 문제가 없다.
    spec = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    band = (freqs >= KICK_FMIN) & (freqs <= KICK_FMAX)
    if not band.any():
        return []
    energy = spec[band].sum(axis=0)
    strength = np.diff(energy, prepend=energy[:1])
    strength[strength < 0] = 0.0
    if not len(strength):
        return []

    frame_sec = HOP / sr
    wait = max(1, int(KICK_MIN_GAP_SEC / frame_sec))
    peaks = librosa.util.peak_pick(
        strength,
        pre_max=wait, post_max=wait,
        pre_avg=wait * 3, post_avg=wait * 3,
        delta=delta * float(np.max(strength)),
        wait=wait,
    )
    out = [float(p) * frame_sec for p in peaks]
    if verbose:
        print(f"[kicksync] 킥 {len(out)}개 (delta {delta})")
    return out


def plausible(kicks: list[float], bar_count: int) -> bool:
    """검출된 킥 수가 마디당 상식 범위에 드는가.

    범위를 벗어나면 킥이 아니라 다른 것을 세고 있다. 실제로 한 번 그랬다 —
    336초 곡에서 2017개(초당 6개)가 나왔고 락 비율 11.6%로 읽혔는데, 그것은
    "킥과 베이스가 안 맞는다"가 아니라 **검출이 틀렸다**는 뜻이었다.
    """
    if not bar_count:
        return False
    per_bar = len(kicks) / bar_count
    lo, hi = KICKS_PER_BAR_RANGE
    return lo <= per_bar <= hi


def measure_lock(onsets: list[float], kicks: list[float]) -> float:
    """**베이스 온셋 중 킥이 함께 있는 비율.** `playing.json` kickLock의 실측값.

    방향을 틀리지 마라. 문헌값은 "베이스 오른손 타격의 80% 이상이 킥과 일치"이고
    분모가 **베이스**다. 처음에 분모를 킥으로 두고 재서 11~23%가 나왔는데, 그것은
    다른 질문(킥 중 베이스가 있는 비율)의 답이었다. 킥은 베이스보다 훨씬 많으니
    당연히 낮게 나온다.

    이 값이 낮으면 그 곡은 킥과 베이스가 안 맞는 곡이고 킥 동기화를 걸 근거가
    없다. **판정 전에 이것부터 본다.**
    """
    import bisect

    if not kicks or not onsets:
        return 0.0
    ordered = sorted(kicks)
    hit = 0
    for t in onsets:
        i = bisect.bisect_left(ordered, t)
        for j in (i - 1, i):
            if 0 <= j < len(ordered) and abs(ordered[j] - t) <= MATCH_TOLERANCE_SEC:
                hit += 1
                break
    return hit / len(onsets)


def revive_missing(
    notes: list,
    drums_path: Path,
    bass_path: Path,
    *,
    min_lock: float = 0.5,
    energy_ratio: float = 0.5,
    min_note_sec: float = 0.09,
    verbose: bool = False,
) -> tuple[list, KickReport]:
    """킥이 있는데 우리 음이 없는 자리에 음을 되살린다.

    되살리는 음의 피치는 **직전 음의 피치를 물려받는다.** 킥은 음정을 알려주지
    않고, 베이스는 같은 근음을 반복하는 경우가 압도적이다(그래서 재타현 누락이
    문제가 됐다). 직전 음이 없으면 되살리지 않는다 — 음정을 지어낼 수는 없다.

    `min_lock`: 킥과 베이스가 이만큼 맞물리지 않는 곡에는 아무것도 하지 않는다.
    킥 동기화를 걸 전제가 성립하지 않기 때문이다.

    `energy_ratio`: 그 자리 베이스 스템 에너지가 곡 중앙값의 이 배수를 넘어야
    되살린다. 킥만 있고 베이스는 쉬는 자리에 음을 만들지 않기 위한 조건이다.
    """
    import bisect

    import librosa
    import numpy as np

    report = KickReport()
    kicks = detect_kicks(drums_path)
    report.kicks = len(kicks)
    if not kicks or not notes:
        return notes, report

    onsets = sorted(n.start for n in notes)
    report.lock_ratio = measure_lock(onsets, kicks)
    if report.lock_ratio < min_lock:
        if verbose:
            print(
                f"[kicksync] 킥 {len(kicks)}개, 락 비율 "
                f"{100 * report.lock_ratio:.0f}% — 기준({100 * min_lock:.0f}%) 미달로 "
                f"아무것도 하지 않는다"
            )
        return notes, report

    if not Path(bass_path).exists():
        return notes, report
    y, sr = librosa.load(str(bass_path), sr=SR, mono=True)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=HOP)[0]
    frame_sec = HOP / sr
    active = rms[rms > 0]
    floor = float(np.median(active)) * energy_ratio if len(active) else 0.0

    revived: list = []
    for k in kicks:
        i = bisect.bisect_left(onsets, k)
        near = any(
            0 <= j < len(onsets) and abs(onsets[j] - k) <= MATCH_TOLERANCE_SEC
            for j in (i - 1, i)
        )
        if near:
            report.matched += 1
            continue
        report.orphan += 1

        frame = int(k / frame_sec)
        if frame >= len(rms) or float(rms[frame]) < floor:
            report.rejected_quiet += 1
            continue

        # 직전 음에서 피치를 물려받는다. 없으면 만들지 않는다.
        previous = [n for n in notes if n.start <= k]
        if not previous:
            report.rejected_quiet += 1
            continue
        source = max(previous, key=lambda n: n.start)

        # 다음 음까지, 또는 최소 길이만큼.
        following = [n.start for n in notes if n.start > k]
        end = min(following) if following else k + min_note_sec
        if end - k < min_note_sec:
            report.rejected_quiet += 1
            continue

        clone = type(source)(
            start=k,
            end=end,
            pitch=source.pitch,
            amplitude=source.amplitude,
            detected_end=end,
            loudness=float(rms[frame]),
        )
        revived.append(clone)
        report.revived += 1

    if not revived:
        if verbose:
            print(
                f"[kicksync] 킥 {report.kicks}개 (락 {100 * report.lock_ratio:.0f}%), "
                f"짝 없는 킥 {report.orphan}개 — 되살린 음 없음"
            )
        return notes, report

    # 되살린 음이 앞 음의 끝을 넘어가면 앞 음을 잘라 맞닿게 한다. 단선율
    # 전제를 깨면 뒷단(운지·표기)이 겹친 음을 만난다.
    merged = sorted(list(notes) + revived, key=lambda n: n.start)
    for a, b in zip(merged, merged[1:]):
        if a.end > b.start:
            a.end = b.start

    if verbose:
        print(
            f"[kicksync] 킥 {report.kicks}개 (락 {100 * report.lock_ratio:.0f}%), "
            f"짝 없는 킥 {report.orphan}개 -> {report.revived}음 되살림 "
            f"(베이스 조용해서 건너뜀 {report.rejected_quiet})"
        )
    return merged, report

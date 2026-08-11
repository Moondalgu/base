# 골든셋 — 정답이 있는 곡 목록

## 골든셋이 무엇인가

**"정답을 아는 곡 묶음"**이다. 파이프라인을 고칠 때마다 이 곡들을 돌려서 좋아졌는지
나빠졌는지 숫자로 확인한다. 없으면 "고친 것 같다"밖에 말할 수 없다.

이번 세션에서 정답이 한 곡뿐이라 두 번 크게 틀렸다.

- 16마디에서 타현 100%였는데 59마디로 늘리니 63%로 드러났다 (과적합)
- 구조 분할이 좋은지 나쁜지 **판정 자체가 불가능**했다 — 그 한 곡이 100마디 넘게
  같은 그루브를 반복해서 나눌 구조가 없었다

## 골든셋에 필요한 두 가지

1. **정답** — 마디별로 무엇을 몇 번 짚는지
2. **그 정답과 같은 녹음의 오디오** — 이것이 핵심이다

기존 정답(`champagne_video_*.json`)은 유튜브 커버 영상 화면 TAB이라 (1)과 (2)가
같은 녹음이었지만, 커버 연주자 본인의 채보라 원곡과 다르고 속주 구간이 맞는지
확인하지 못했다. `songsterr_champagne_bass.json`은 사람이 만든 정확한 채보지만
**Oasis 원곡 기준**이고 우리 오디오는 백예린 커버다 — 녹음이 다르다.

그래서 아래 3곡은 **Songsterr 채보와 같은 스튜디오 녹음**을 오디오로 쓴다.

## 곡 목록 — 클론 직후 이대로 만들면 골든셋이 선다

`data/`는 gitignore라 **저장소에는 산출물이 없다.** 아래 명령을 순서대로 돌리면
`eval/run_goldenset.py`가 읽는 9행이 전부 만들어진다. 곡당 8~15분(CPU).

```bash
P=.venv/Scripts/python.exe
$P scripts/run_pipeline.py https://www.youtube.com/watch?v=rY0WxgSXdEE   # Queen
$P scripts/run_pipeline.py https://www.youtube.com/watch?v=b9Y4TACmvE8   # Virtual Insanity
$P scripts/run_pipeline.py https://www.youtube.com/watch?v=l3SBBWIxGZA   # Come Together
$P scripts/run_pipeline.py https://www.youtube.com/watch?v=NbKH4iZqq1Y   # Drowning
$P scripts/run_pipeline.py https://www.youtube.com/watch?v=BS7tz2rAOSA   # 예뻤어
$P scripts/run_pipeline.py https://www.youtube.com/watch?v=zaHO35c0NPk   # Highway to Hell
$P scripts/run_pipeline.py https://www.youtube.com/watch?v=mLU3XOaraqs   # HTH 커버(F2E)
$P scripts/run_pipeline.py https://www.youtube.com/watch?v=Kr4EQDVETuA   # Billie Jean
# Champagne 커버 영상만 --cover-overlay를 준다 (아래 표 참조)
$P scripts/run_pipeline.py https://www.youtube.com/watch?v=AYKkRsrEpX8 --cover-overlay
$P eval/run_goldenset.py
```

**`--cover-overlay`는 Champagne에만 준다.** 원곡 음원을 반주로 틀고 그 위에
연주한 영상이라 베이스가 둘 섞여 있고, 화면 악보 정답은 큰 쪽(커버 연주)을
가리킨다. 스튜디오 원곡에 이 플래그를 주면 멀쩡한 음을 버려서 타현 정확도가
곡마다 10~32pp 떨어진다(실측).

| 곡 | 해시 | 유튜브 | 정답 | 왜 이 곡인가 |
|---|---|---|---|---|
| Queen — Another One Bites the Dust | `528aa2e6986aa42a` | [rY0WxgSXdEE](https://www.youtube.com/watch?v=rY0WxgSXdEE) 공식 뮤비 **(음원이 악보보다 +1반음)** | `songsterr_queen_aobtd.json` (98마디) | **베이스가 곡의 주역**이고 리프가 명확하다. 8분 중심. 우리가 가장 잘해야 하는 유형 |
| Jamiroquai — Virtual Insanity | `d4fd7b689b9db1bb` | [b9Y4TACmvE8](https://www.youtube.com/watch?v=b9Y4TACmvE8) 공식 Visualiser(앨범 5:41) — **MV(4JkIs37a2JE)는 축약 편집판이라 쓰면 안 된다** | `songsterr_jamiroquai_virtual_insanity.json` (130마디) | **16비트 펑크, 난이도 5.** 우리가 가장 못하는 유형. CREPE가 붕괴해 엔진 폴백(engine_select)이 생겼다 |
| The Beatles — Come Together | `78d6e3fc12388629` | [l3SBBWIxGZA](https://www.youtube.com/watch?v=l3SBBWIxGZA) 2019 믹스 | `songsterr_beatles_come_together.json` (89마디) | **픽 연주, 구간이 잘게 나뉜다**(16섹션, 2~8마디). 구조 분할을 판정할 수 있는 첫 곡 |
| WOODZ — Drowning | `65ef1cf020561a5c` | [NbKH4iZqq1Y](https://www.youtube.com/watch?v=NbKH4iZqq1Y) 공식 | `songsterr_woodz_drowning.json` (113마디) + 참조 악보 PNG(저장소 밖) | **K-pop + 목표 악보 원곡.** akbobada 3단 악보(Lv2)와 Songsterr 정답이 둘 다 있는 유일한 곡 |
| DAY6 — 예뻤어 | `8181e1aa7d7a0be1` | [BS7tz2rAOSA](https://www.youtube.com/watch?v=BS7tz2rAOSA) 공식 MV | `songsterr_day6_ywb.json` (98마디) · `..._encover.json` (99마디) | **하드 케이스**: 셋잇단·고스트노트·D.S. 반복. 셋잇단 격자 경로 실전 검증 |
| AC/DC — Highway to Hell | `a7b3735a1e06ccde` | [zaHO35c0NPk](https://www.youtube.com/watch?v=zaHO35c0NPk) 스튜디오 원곡(튜닝 편차 −5센트, 변조 없음) | `songsterr_acdc_hth_estandard.json` (표준튜닝, **자리 비교 가능**) · `songsterr_acdc_hth_bass.json` (E♭탭, 이조 탐색 시험용) | **개방현 중심 록.** 자리 정답 45마디 중 39가 개방현이라 운지 가중치가 여기서 갈린다 |
| AC/DC — HTH 커버 (First To Eleven) | `2c80d86eb66dd69a` | [mLU3XOaraqs](https://www.youtube.com/watch?v=mLU3XOaraqs) | `songsterr_acdc_hth_bass.json` | 같은 곡 다른 녹음(원곡 −1반음). **정답 탭이 E♭튜닝이라 자리 비교는 성립하지 않는다**(`n/a`) |
| Michael Jackson — Billie Jean | `752cc5fcb58d957a` | [Kr4EQDVETuA](https://www.youtube.com/watch?v=Kr4EQDVETuA) | `songsterr_mj_billie_jean.json` (144마디) | **표준튜닝 + 144마디 중 142마디에 베이스.** 자리 대조 표본이 가장 크다 |
| Oasis/백예린 — Champagne Supernova (커버 영상) | `975e4e588d282666` | [AYKkRsrEpX8](https://www.youtube.com/watch?v=AYKkRsrEpX8) **`--cover-overlay` 필수** | `champagne_video_bars25_40.json` · `champagne_video_bars41_99.json` (화면 TAB) | **실사용 하드 케이스** — 원곡 반주 위 커버 연주. 화면 악보라 정답과 오디오가 같은 녹음이다 |

**리마스터·리믹스는 같은 연주다.** 2011 리마스터와 2019 믹스는 같은 테이프에서
나온 것이므로 마디 구조와 연주 내용이 채보와 일치한다. 라이브 버전은 쓸 수 없다.

**같은 곡에 Songsterr 탭이 여럿이고 튜닝이 다르다.** 탭을 받을 때 `tuning`을
먼저 확인해라 — 튜닝이 다르면 같은 음도 프렛 번호가 통째로 달라져 자리 비교가
성립하지 않는다. `eval_songsterr.comparable_tuning`이 그런 정답을 `n/a`로 뺀다.
빼지 않으면 0%로 찍혀 "우리가 다 틀렸다"로 읽힌다(실제로 그랬다).

## 기준선 (2026-08-11, 전곡 현재 코드로 재생성 후)

| 곡 | 피치클래스 | 자리 | 타현 |
|---|---|---|---|
| 예뻤어 | 98% | 60% | 49% |
| Champagne(커버영상) | 94% | n/a | 3% |
| Come Together | 89% | 14% | 36% |
| Highway to Hell | 87% | 70% | 20% |
| Drowning | 81% | 63% | 83% |
| Queen | 66% | n/a | 18% |
| Virtual Insanity | 25% | 14% | 15% |

**피치클래스가 3pp 이상 떨어지면 회귀다.** 자리는 운지 가중치를 건드렸을 때만
움직이고, `eval/eval_fretting.py --sweep-songs`가 이 목록을 그대로 쓴다.

## 성격이 갈리는 것이 요점이다

한 유형만 모으면 그 유형에 과적합한다. 세 곡의 성격:

| | 반복성 | 최소 리듬 단위 | 섹션 길이 | 주법 |
|---|---|---|---|---|
| Champagne Supernova (기존) | 매우 높음 | 8분 | 4·8·12·18·26 | 핑거 |
| Another One Bites the Dust | 높음 | 8분 | 4·8·9·11·26 | 핑거 |
| Virtual Insanity | 중간 | **16분** | 4·8·16·24·28 | 핑거·고스트 |
| Come Together | 중간 | 8분 + 당김음 | **2·4·8·23 (잘다)** | 픽 |

## 음원이 악보와 다른 키일 수 있다 — 이것부터 확인한다

**Queen 공식 뮤비 음원은 악보(Em)보다 정확히 반음 높다**(Fm). 이조를 모르고
대조하면 자리 일치가 5%로 나오고 **파이프라인 실패로 오해한다.** 실제로 그렇게
오해했다가 피치클래스 분포 상관으로 잡아냈다(+1반음 0.905 대 0반음 −0.192).

`eval_songsterr.py`가 12개 이조를 다 대보고 상관이 가장 높은 값을 먼저 찾는다.
이조가 있으면 **자리(현·프렛) 대신 피치클래스로 비교**한다 — 이조되면 같은 음도
다른 자리에서 나기 때문이다.

원인은 확인하지 않았다. 레이블이 Content ID를 피하려 살짝 올려 올리는 경우가
있다고 알려져 있지만 **확인한 사실이 아니다.** 우리에게 중요한 것은 원인이 아니라
"음원과 악보의 키가 다를 수 있다"는 사실 자체다.

## 마디 정렬을 맞춰야 한다

Songsterr의 1마디와 우리 1마디가 같은 자리라는 보장이 없다. 인트로 무음 길이,
비트 추적의 위상, 픽업 마디가 다 영향을 준다. `eval/eval_songsterr.py`가
**최적 마디 오프셋을 찾아 함께 보고한다** — 오프셋이 안 맞으면 정확도가 아니라
정렬을 먼저 봐야 한다.

## 한계 — 이 자료로 못 하는 것

- **사람 채보도 해석이다.** Songsterr 채보자가 적은 타현 수가 실제 녹음과 다를 수
  있다. 특히 고스트 노트는 적는 사람마다 다르다
- **믹스 차이.** 리마스터는 같은 연주지만 음량 균형이 다르다. 분리 품질에 영향을
  줄 수 있다
- **저작권.** 이 곡들은 개인 학습·평가 목적으로만 쓴다. `data/`는 gitignore이고
  오디오를 저장소에 넣지 않는다. 정답 JSON(마디별 숫자)만 커밋한다

## 곡을 더 붙이는 방법

```bash
# 1) Songsterr에서 곡을 찾는다 (베이스 트랙 = tuning 길이 4)
curl -s "https://www.songsterr.com/api/search?pattern=<제목>&inst=bass&size=8&from=0"

# 2) 정답을 받는다 (songId만 있으면 된다)
.venv/Scripts/python.exe tools/fetch_songsterr.py <songId> --auto \
    --out eval/golden/songsterr_<이름>.json

# 3) 같은 녹음의 오디오로 파이프라인을 돌린다 (5분 곡에 약 15분)
.venv/Scripts/python.exe scripts/run_pipeline.py "<유튜브 URL>"

# 4) 대조
.venv/Scripts/python.exe eval/eval_songsterr.py data/<hash> \
    eval/golden/songsterr_<이름>.json
```


## 첫 측정 결과 (2026-08-07)

| 곡 | 음(피치클래스) | 타현 | 평균오차 | 이조 |
|---|---|---|---|---|
| Champagne Supernova (기존) | 93% | 63% | 0.51 | 0 |
| Another One Bites the Dust | 62% | 4% | 2.50 | +1반음 |
| Come Together | 28% | 3% | 3.50 | +7(불확실) |
| Virtual Insanity | 16% | 0% | 6.62 | 0 |

**한 곡에서만 동작하고 나머지에서 무너진다.** 찾아낸 결함은 `NEXT.md`
"골든셋이 즉시 찾아낸 것" 절에 있다 — 16비트 붕괴, 배음 오인, 연습영상 오판.

## 이조·조성 판정은 **베이스 스템 근음**으로 한다 (2026-08-10 실측)

AC/DC "Highway to Hell" 원곡과 First To Eleven 커버의 키 차이를 재면서
세 방법이 서로 다른 답을 냈다. 정답은 베이스 스템이 가리키는 쪽이었다.

| 방법 | 답 | 판정 |
|---|---|---|
| 전체 믹스 크로마 + Krumhansl 조성 추정 | 커버 C#장조 | **틀림** (실제 G#) |
| 전체 믹스 CQT 피치축 교차상관 | +1반음 | **틀림** |
| **베이스 스템 근음 분포 상관** | **−1반음 (0.992)** | 맞음 |
| **베이스 진입 구간 최빈 근음** | 원곡 A / 커버 G# | 맞음 |

- **전체 믹스 크로마는 IV·V도와 으뜸음을 혼동한다.** 커버의 진짜 키는 G#인데
  IV도인 C#가 1위로 나왔다(0.591 대 0.571로 종이 한 장). 기타 파워코드는
  근음+5도라 5도 성분을 부풀리고, 심벌·보컬 배음까지 크로마에 섞인다.
- **베이스는 정의상 근음을 친다.** 원곡 A 48.9%/D 20.8%/E 12.3%/G 7.9%,
  커버 G# 43.4%/C# 22.2%/D# 9.6%/F# 10.4% — I·IV·V·♭VII이 그대로 보이고
  두 분포의 상관이 −1반음에서 0.992로 압도적이다.
- 유튜브 비공식 업로드는 **저작권 회피 피치 변조**가 흔하다(실측 −50센트).
  기준 음원은 공식 업로드로 잡고, `librosa.estimate_tuning`으로 먼저 검증한다.

**이 탭(songsterr_acdc_hth_bass.json)은 E♭튜닝([42,37,32,27])이라 사운딩이
A♭ — 원곡 스튜디오 녹음(A장조)보다 반음 낮다.** 대조 시 이조 자동 탐색이
−1을 찾아내야 정상이다.

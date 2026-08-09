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

## 곡 목록

| 곡 | 정답 | 오디오 | 왜 이 곡인가 |
|---|---|---|---|
| Queen — Another One Bites the Dust | `songsterr_queen_aobtd.json` (98마디) | [rY0WxgSXdEE](https://www.youtube.com/watch?v=rY0WxgSXdEE) 공식 뮤비 **(음원이 악보보다 +1반음)** | **베이스가 곡의 주역**이고 리프가 명확하다. 8분 중심. 우리가 가장 잘해야 하는 유형 |
| Jamiroquai — Virtual Insanity | `songsterr_jamiroquai_virtual_insanity.json` (130마디) | [b9Y4TACmvE8](https://www.youtube.com/watch?v=b9Y4TACmvE8) 공식 Visualiser(앨범 5:41) — **MV(4JkIs37a2JE)는 축약 편집판이라 쓰면 안 된다**(2026-08-08 발견, 구간이 잘려 마디 정렬 불가) | **16비트 펑크, 난이도 5.** 우리가 가장 못하는 유형(고스트 노트·16분). CREPE가 이 곡에서 붕괴해 엔진 폴백(engine_select)이 생겼다 |
| The Beatles — Come Together | `songsterr_beatles_come_together.json` (89마디) | [l3SBBWIxGZA](https://www.youtube.com/watch?v=l3SBBWIxGZA) 2019 믹스 | **픽 연주, 구간이 잘게 나뉜다**(16섹션, 2~8마디). 구조 분할을 판정할 수 있는 첫 곡 |
| WOODZ — Drowning (드라우닝) | `songsterr_woodz_drowning.json` (113마디) + 참조 악보 PNG(`Desktop\악보\드라우닝\`) | [NbKH4iZqq1Y](https://www.youtube.com/watch?v=NbKH4iZqq1Y) 공식 | **K-pop + 목표 악보 원곡.** akbobada 3단 악보(Lv2)와 Songsterr(원곡 난이도) 정답이 둘 다 있는 유일한 곡 — 하향 품질을 처음으로 정답 대조할 수 있다 |
| DAY6 — 예뻤어 (You Were Beautiful) | `songsterr_day6_ywb.json` (98마디, 원곡) · `songsterr_day6_ywb_encover.json` (99마디, 뷰 많음) + 참조 악보 PNG(`Desktop\악보\예뻤어\`) | [BS7tz2rAOSA](https://www.youtube.com/watch?v=BS7tz2rAOSA) 공식 MV | **하드 케이스**: 셋잇단·고스트노트(×)·D.S. 반복 — 셋잇단 격자 경로 실전 첫 검증. Songsterr 원곡판(4뷰)은 신뢰도 낮음 — 두 판 대조 후 채택 |

**리마스터·리믹스는 같은 연주다.** 2011 리마스터와 2019 믹스는 같은 테이프에서
나온 것이므로 마디 구조와 연주 내용이 채보와 일치한다. 라이브 버전은 쓸 수 없다 —
Songsterr가 라이브를 별도 항목으로 두는 이유가 그것이다(`(Live At The Budokan 1998)`).

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

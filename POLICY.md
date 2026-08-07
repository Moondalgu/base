# 규칙·정책값 카탈로그 (2026-08-07)

이 프로젝트의 판단은 대부분 **상수 하나**에 들어 있다. 게이트 문턱 0.95, 관성 창
12마디, 운지 가중치 0.2 — 이 값들이 산출물을 결정한다. 그런데 값이 어디서 왔는지가
코드 주석에만 흩어져 있어서 **근거 없는 값이 몇 개인지 아무도 몰랐다.**

`python tools/audit_constants.py`가 AST로 전수 조사한다. 지금 **110개** 중
근거 주석 65 / 자명 15 / **근거 없음 30**이다. 이 문서는 그 30개에 등급을 붙인 것이다.

Gemini(세션 베이시스트·MIR 연구자 관점)와 교차 검토했고, **그 판정 중 틀린 것은
아래에 따로 적었다.**

## 등급

| 등급 | 뜻 |
|---|---|
| **실측** | 정답 데이터로 재서 정했다. 재현 명령이 있다 |
| **차용** | 문헌·표준·라이브러리 기본값·도메인 관습 |
| **자명** | 악기 사양·음악 이론상 정해진 값 |
| **추측(위험)** | 감이고, 틀리면 산출물이 나빠진다. **줄여야 할 대상** |
| **추측(무해)** | 감이지만 넓은 범위에서 결과가 안 바뀐다 |

---

## 1. 실측으로 정한 값 (재현 명령 있음)

이미 코드 주석에 근거와 수치가 있다. 바꾸려면 같은 명령으로 다시 재야 한다.

| 상수 | 값 | 근거 | 재현 |
|---|---|---|---|
| `fretting.W_MOVE` | 0.2 | IDMT 77.8% / 영상 100%. IDMT만으로 튜닝하면 모든 음이 E현에 갇힌다 | `eval/eval_fretting.py --sweep` |
| `fretting.W_STRING_CHANGE` | 0.2 | 같은 스윕 | 〃 |
| `fretting.W_POSITION` | 0.03 | 같은 스윕 | 〃 |
| `fretting.W_OPEN_PENALTY` | 0.4 | 같은 스윕. **보너스에서 벌점으로 부호가 뒤집혔다** | 〃 |
| `bassclean.GATE_TARGET_GRID_RATIO` | 0.95 | 정상 곡 오발동 6/17(35%) → 2/17(12%). **IDMT 정답 온셋 기준** | 아래 "게이트 재측정" |
| `diagnose.TRUSTED_GRID_RATIO` | 0.85 | **우리 검출 온셋 기준.** 격자정렬↔타현정확도 상관 0.861, 0.875(63%)와 0.777(7%) 사이에서 갈린다 | `eval_songsterr.py` + `eval_video_bars.py`로 표 재작성 |
| `bassclean.GATE_GRID_DIVISORS` | (4,3,6) | 스윙 곡을 16분 격자로만 재면 정상 연주가 어긋나 보인다 | 〃 |
| `bassclean.GATE_GRID_TOLERANCE` | 0.0625 | 격자 간격에 비례시키면 거친 격자가 박 전체를 덮는다 | 〃 |
| `bassclean.GATE_MAX_DROP_RATIO` | 0.45 | 절반 넘게 버리면 남는 것이 라인이 아니라 파편 | — |
| `quantize.SIXTEENTH_REQUIRED_RATIO` | 0.05 | IDMT 17곡 격자 해상도 측정 | `eval/eval_grid_resolution.py` |
| `inertia.WINDOW_BARS` | 12 | 4마디는 21창 중 대부분을 건너뜀. 12에서 최빈 {0,7,10}이 정확히 나옴 | `eval/eval_video_bars.py` |
| `inertia.FILL_ATTACK_RATIO` | 2.0 | 1.6에서 5타 마디가 필인으로 오분류 | 〃 |
| `inertia.USE_SECTIONS` | False | 구조 분할을 켜면 타현 63%→53% | 〃 |
| `chords.ALLOWED_QUALITIES` | major/minor | 7화음은 오검출 실측 | `tools/diag/test_chords.py` |
| `chords.ROOT_POSITION_BONUS` | 1.20 | 분수 코드 5/5 실패 → 통과 | 〃 |
| `chords.THIRD_MARGIN` | 1.15 | 근음 성분이 공통이라 비율이 희석됨 | 〃 |
| `reduce.EASY_MAX_*` | 2.0 / 0.05 / 9.0 | 원곡이 이미 쉬우면 단계를 만들지 않는다 | `tools/diag/test_reduce.py` |
| `transcribe_crepe.MODEL` | "full" | tiny는 16배 빠르지만 핑거 누락 2배·슬랩 붕괴 | `eval/eval_idmt.py` |
| `transcribe_crepe.CONF_THRESHOLD` | 0.6 | 0.5~0.7에서 결과가 거의 안 움직인다 | 〃 |

### 게이트 재측정 명령

```bash
.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'apps/worker'); sys.path.insert(0,'eval')
from pipeline import bassclean as bc
from eval_grid_resolution import truth_onsets, truth_beats, IDMT
class N:
    def __init__(s,t): s.start=t
fire=tot=0
for xml in sorted((IDMT/'annotation').glob('*.xml')):
    csv=IDMT/'misc'/'beats_csv'/f'{xml.stem}_beats.csv'
    if not csv.exists(): continue
    tot+=1
    if bc._grid_ratio([N(t) for t in truth_onsets(xml)], truth_beats(csv)[0]) < bc.GATE_TARGET_GRID_RATIO: fire+=1
print(f'정상 {tot}곡 중 {fire}곡 오발동')"
```

---

## 2. 차용 — 출처가 있는 값

| 상수 | 값 | 출처 |
|---|---|---|
| `transcribe_crepe.HOP` | 160 (10ms) | **CREPE 자체 설계값.** 16kHz에서 160샘플이 모델 표준이다 |
| `beats.HOP` | 256 (11.6ms) | librosa 계열 온셋 분석의 통상 홉 |
| `reattack.HOP` | 128 (5.8ms) | 어택 봉우리를 놓치지 않을 해상도. 스펙트럼 플럭스 온셋 검출의 통상 범위 |
| `bassclean.GATE_CONVERGE_TOLERANCE` | 0.125박 | 32분음표의 절반. 퀀타이즈 허용 오차의 통상값이고 사람의 리듬 인지 오차 안에 있다 |
| `quantize.DEFAULT_SUBDIVISION` | 4 (16분) | 대중음악의 통상 최소 단위. **격자 자동 선택이 실패할 때만 쓰는 폴백**이다 |
| `quantize.SNAP_REJECT_RATIO` | 0.5 | 격자 간격의 절반보다 멀면 그 격자 자리가 아니다 — 퀀타이즈의 논리적 기준 |
| `separate.MODEL_NAME` | htdemucs | Demucs v4 기본 모델 |
| `encode.BITRATE` | 96k | opus 96kbps는 베이스 대역에서 채보에 영향을 줄 만한 손실이 없다 |

---

## 3. 자명 — 악기 사양·음악 이론

| 상수 | 값 | 근거 |
|---|---|---|
| `bassclean.BASS_MIDI_MIN` | 28 | 개방 4현 E1 |
| `bassclean.BASS_MIDI_MAX` | 63 | 20프렛 4현 베이스의 1현 20프렛이 E4(64). 63은 그 바로 아래 실용 상한 |
| `fretting.NFRETS` | 20 | 4현 베이스의 가장 보편적인 프렛 수 |
| `quantize.SWING_SUBDIVISION` | 3 | 스윙은 8분 셋잇단 구조다 |
| `quantize.MIN_DURATION_SLOTS` | 1 | 양자화된 음은 최소 한 슬롯 |
| `transcribe.BASS_MAX_FREQ` | 450Hz | 1현 20프렛 E4가 329.6Hz. 배음·슬랩 성분까지 덮는다 |
| `chords.MINOR_THIRD` 등 | 3/4/7/10/11 | 음정의 반음 수 |
| `reduce.BEGINNER/INTERMEDIATE/ORIGINAL_LEVEL` | 1/2/3 | 레벨 번호 |

---

## 4. 추측(위험) — 줄여야 할 대상

**이것이 이 문서의 요점이다.** 아래 값들은 감으로 정했고 틀리면 산출물이 나빠진다.
재는 방법을 함께 적었다.

### 4.1 최소 음 길이 — `MIN_NOTE_SEC = 0.06` / `MIN_NOTE_LENGTH_MS = 60.0`

60ms보다 짧으면 버린다. 그런데 **슬랩의 고스트 노트와 16비트 펑크의 뮤트 타격은
그보다 짧을 수 있다.** 우리 슬랩 누락률이 51.7%인 것과 무관하지 않을 가능성이 있다.

재는 법: IDMT 어노테이션에 `excitationStyle`이 있다. **주법별로 정답 음 길이 분포를
뽑으면** 이 문턱이 실제로 무엇을 자르고 있는지 바로 나온다. 아직 안 했다.

### 4.2 누출 판정 — `LEAKAGE_REGISTER_MARGIN = 14` / `LEAKAGE_STRONG_AMPLITUDE = 0.85`

곡의 베이스 음역 중앙값보다 14반음 위이면서 약하면 다른 악기 누출로 보고 버린다.

**문제**: 14반음은 장9도이고, 베이스가 필인·코러스에서 **옥타브 위(12반음) 이상으로
도약하는 것은 정상**이다. 약하게 연주한 고음역 멜로디나 하모닉스가 누출로 오인될 수
있다. 12는 확실히 살려야 하고 그 위는 판단이 필요하다.

재는 법: IDMT 정답으로 "곡의 중앙값 대비 최고 음정 분포"를 뽑는다. 실곡에서는
Songsterr 사람 채보(`eval/golden/songsterr_champagne_bass.json`)에 고음역 필인이
있다 — 원곡 52마디가 3현 14프렛(MIDI 47)이고 그 곡 중앙값보다 한참 위다.

### 4.3 게이트 수렴 목표 — `GATE_CONVERGE_TARGET = 0.85`

발동 판정(0.95, 16분 격자)은 실측으로 정했지만 **수렴 목표는 옛 값을 물려받았다.**
8분 격자에 85%를 맞추려는 것은 공격적이고, 스윙·레이백 그루브를 훼손할 수 있다.

재는 법: 이 값만 바꿔 `eval/eval_video_bars.py`를 다시 돌린다. 단 지금 정답이
연습영상 한 곡뿐이라 과적합 위험이 있다 — 골든셋 확대와 함께 해야 한다.

### 4.4 품질 문턱 — `GOOD_THRESHOLD = 70` / `REFERENCE_THRESHOLD = 40`

100점 만점 품질 점수를 good/reference/failed로 가르는 선인데 **순전히 감이다.**
사용자에게 "이 악보는 쓸 수 있다"고 말하는 값이므로 근거가 없으면 안 된다.

재는 법(교차 검토에서 나온 것):
1. **사용자 평가와의 상관** — 여러 품질의 악보를 연주자에게 보여 "연습에 쓸 수
   있는가"를 받고 우리 점수와의 상관을 본다
2. **오류 비용 가중** — 거짓음·누락·리듬 오차의 비용을 다르게 매긴다. 우리는 이미
   "거짓음이 누락보다 치명적"이라고 판단했는데 점수에는 반영돼 있지 않다

참고 기준: 교차 검토에서 **타현 정확도 90%가 "연습 보조로 쓸 수 있는 선"**,
85%가 "참고용"이라고 나왔다. 우리 실측은 반복 구간 85% / 비반복 25%다.

### 4.5 basic-pitch 임계 — `ONSET_THRESHOLD = 0.5` / `FRAME_THRESHOLD = 0.3`

감으로 정했다. **다만 basic-pitch는 비교용 경로이고 기본 엔진이 아니다**(CREPE가
IDMT F 0.861 대 0.815로 앞선다). 우선순위가 낮다.

### 4.6 분리 모델 — `MODEL_NAME = "htdemucs"`

`htdemucs_ft`(4배 느림)·`mdx_extra` 등 대안이 있고 **베이스 스템 품질을 비교한
적이 없다.** 분리 품질은 채보 정확도의 상한을 정하므로 이것이 병목일 수 있다.

재는 법: 같은 곡에 세 모델을 돌려 각각 채보하고 `eval/eval_video_bars.py`로 잰다.
분리 자체의 SDR을 재려면 멀티트랙 정답이 필요한데 우리에게 없다 — **최종 채보
정확도로 대신 재는 것이 우리 목적에 더 맞다.**

---

## 5. 추측(무해)

| 상수 | 값 | 왜 무해한가 |
|---|---|---|
| `beats.BPM_SEARCH_STEP` | 0.05 | 탐색 해상도. 더 줄여도 결과가 안 바뀐다 |
| `beats.PHASE_SEARCH_STEP` | 0.01 | 10ms 해상도는 리듬 인지 임계 안에 있다 |
| `bassclean.MIN_AMPLITUDE` | 0.25 | basic-pitch 경로 전용. 기본 엔진에서 안 쓴다 |
| `bassclean.MERGE_GAP_SEC` | 0.04 | 같음 — 아래 참조 |
| `bassclean.OVERLAP_TOLERANCE` | 0.05 | 같음 |

---

## 6. 교차 검토에서 **틀린** 판정

Gemini 판정 중 코드를 확인해 보니 사실과 다른 것들이다. 같은 지적이 다시 올 때
여기를 보면 된다.

### "`MERGE_GAP_SEC`와 재타현 분리가 서로 싸운다" — **아니다**

병합은 "같은 피치가 40ms 이내면 한 음", 재타현 분리는 "한 음 안에서 어택을 찾아
나눈다"로 방향이 반대인 것은 맞다. 그런데 **기본 경로에서는 병합이 아예 돌지
않는다.** `bassclean.clean(monophonic_source=True)`가 배음 제거·단선율 강제·병합을
모두 건너뛰고, CREPE 경로는 항상 그 인자로 부른다(`bassclean.py` 머리말).

병합은 basic-pitch(다성 모델) 경로 전용이고, 그 경로에는 재타현 분리를 붙이지
않았다. 충돌 지점이 없다. **단 basic-pitch 경로에 재타현 분리를 붙인다면 그때는
이 지적이 유효해진다.**

### "`MIN_AMPLITUDE`·`OVERLAP_TOLERANCE`가 위험하다" — 기본 경로에서는 무해

둘 다 basic-pitch 전용 단계에서만 쓰인다. 위와 같은 이유다.

### 시장 조사에서 틀렸던 것

`MARKET.md`의 "Gemini 답변에서 확인해보니 틀렸던 것" 절 참조 (4건).

---

## 6.5 같은 숫자를 다른 모집단에 쓰지 마라

`diagnose.TRUSTED_GRID_RATIO`를 `bassclean.GATE_TARGET_GRID_RATIO`와 **같게
두라고 코드에 적어놨었다.** "같은 질문이니 같은 값이어야 한다"는 이유였는데
틀렸다. 지표는 같아도 **재는 대상이 달랐다.**

| | 무엇에 대해 재는가 | 0.95를 적용하면 |
|---|---|---|
| 게이트 발동 | IDMT **정답 온셋** | 정상 곡 2/17 제외 (적절) |
| 리듬 신뢰 | **우리 검출 온셋** | 실곡 4/4 제외 (전부 불신) |

우리 검출은 정답보다 흔들리므로 같은 자를 댈 수 없다. 결과적으로 **하향 기능이
어느 곡에서도 안 열렸다** — 우리 유일한 차별점인데.

문턱을 옮겨 쓰기 전에 **그 값이 어떤 모집단에서 나왔는지** 확인한다.

## 7. 이 문서를 유지하는 방법

1. 상수를 새로 추가하면 `python tools/audit_constants.py --undocumented`가 잡는다
2. 값을 실측으로 정했으면 **코드 주석에 수치와 재현 명령을 적는다.** 이 문서가
   아니라 코드가 정본이다 — 문서는 목록과 등급만 갖는다
3. 4장(추측·위험)에서 하나를 재서 옮기면 1장에 추가하고 4장에서 지운다.
   **4장이 줄어드는 것이 이 문서의 목적이다**

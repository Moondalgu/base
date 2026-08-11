# 다음 세션 시작 지점

이 파일 하나만 읽고 바로 작업을 시작할 수 있게 만든 것이다.
배경이 필요하면 `HANDOFF.md` → `NEXT.md` 순서로 간다.

## 무엇을 할지는 GitHub 이슈에 있다

각 이슈에 증상·재현 명령·이미 진 시도·완료 기준이 자기완결로 들어 있다.

| # | 과업 |
|---|---|
| [#1](https://github.com/Moondalgu/base/issues/1) | **채보 누락** — HTH 타현 20%(마디당 3.2음, 필요 8음). VI 25%와 같은 뿌리 |
| [#2](https://github.com/Moondalgu/base/issues/2) | **음량 게이트 존재 이유 판정** — 통제 실험 준비 완료, 실행만 남음 |
| [#3](https://github.com/Moondalgu/base/issues/3) | 운지 가중치 되돌리기(HTH 우선순위 종료 후). 상수를 세 번 잘못 정한 경위 포함 |

**클론 직후에는 `data/`가 비어 있다.** `eval/golden/SET.md`의 명령을 그대로
돌리면 골든셋 9행이 만들어진다(곡당 8~15분).

## 전체 점검을 하려면 — **"베이스 서비스 읽어줘"**

그 말을 하면 `lowend-review` 스킬이 뜬다(`.claude/skills/lowend-review/`).
4페이즈로 돈다:

| 페이즈 | 무엇을 | 어떻게 |
|---|---|---|
| 0~1 | 상태 파악 + 기계 검사 | 직접. `check_consistency.py --measure` |
| 2 | 정합성 3갈래 | **Fable 3개 병렬** — 요구사항 대비 / 내부 / 주장·근거·설계 |
| 3 | 오픈소스 비교 2갈래 | **Fable 2개 병렬** — 채보 엔진 / 표기·렌더 |
| 4 | 종합 | 직접 검증 후 보고. 에이전트 보고를 그대로 옮기지 않는다 |

에이전트에는 **제품 정의·핵심 가치·아직 없는 기능·골든셋 점수**를 함께 넘긴다.
그게 없으면 내부 일관성만 보고 "무엇을 위한 물건인지"를 모른 채 판단한다.
기준은 최고 수준이되, **관점은 체크리스트가 아니라 출발점**으로 주고 확장성·
설계 규칙은 에이전트 주관으로 판단하게 한다.

**작업을 이어서 하려면** 이 문서를 그대로 따라간다(아래 0번부터).

---

## 0. 환경 확인 (2분)

```bash
cd C:/Users/admin/Desktop/lowend
git log --oneline -1        # 9e5e8d4 docs: 점검 스킬을 지시 대신 판단 중심으로 다시 씀
git branch --show-current   # master
```

**`data/`는 gitignore이므로 산출물이 없으면 다시 만들어야 한다.** 확인:

```bash
ls data/975e4e588d282666/manifest.json   # 커버 영상 (정답 59마디)
ls data/528aa2e6986aa42a/manifest.json   # Queen
ls data/78d6e3fc12388629/manifest.json   # Come Together
ls data/c54d965e0a8fda45/manifest.json   # Virtual Insanity
```

없으면 `eval/golden/SET.md`의 URL로 `scripts/run_pipeline.py`를 돌린다(곡당 8~11분).

## 1. 현재 점수 재현 (5분)

```bash
.venv/Scripts/python.exe eval/eval_video_bars.py data/975e4e588d282666 \
    eval/golden/champagne_video_bars41_99.json
# 기대: 자리 36/43 (84%)  타현수 27/43 (63%)

.venv/Scripts/python.exe eval/eval_songsterr.py data/528aa2e6986aa42a \
    eval/golden/songsterr_queen_aobtd.json
# 기대: +1반음 이조, 음 50/76 (66%), 타현 14/76 (18%)

# 전곡을 한 번에 (자리 비교가 성립하지 않는 곡은 n/a로 빠진다)
.venv/Scripts/python.exe eval/run_goldenset.py
```

숫자가 다르면 **파이프라인이 아니라 산출물이 낡은 것**일 수 있다.
`tools/diag/refresh_manifest.py`로 뒷단만 다시 돈다.

---

## 2. 오늘 할 일 — 하나만 고르면 이것

### 배음을 기음으로 잡는 것 (`pipeline/transcribe_crepe.py`)

> 앞 세션 1순위였던 **연습영상 오판은 고쳤다**(아래 "직전에 고친 것" 참조).

**증상**: Come Together에서 박자 4/4 ✓, 마디 89/89 ✓, BPM 83.3 ✓로 **시간축은
정확한데 음이 틀린다.** 최적 이조가 +7반음(완전5도), 상관 0.727 / 0반음 0.642로
애매하다 — 일정한 이조가 아니라 **일부 음에서 3배음을 f0로 잡는** 모습이다.

**왜 그런가**: 리켄배커 + 피크 연주는 기음보다 배음이 강하게 녹음되는 전형적
경우다. CREPE는 단선율이라 배음을 별도 음으로 만들지 않지만, **기음보다 배음이
강하면 그쪽을 f0로 고른다.** `bassclean`의 배음 제거는 CREPE 경로에서 꺼져
있다(다성 모델용이라 걸러낼 대상이 없다고 판단했는데, 이 경우는 다르다).

**확인 명령**:

```bash
.venv/Scripts/python.exe eval/eval_songsterr.py data/78d6e3fc12388629     eval/golden/songsterr_beatles_come_together.json
# 기대(현재): +7반음 이조, 음 19/68 (28%)
```

**방향**: f0 후보의 1/2·1/3 지점 에너지를 확인해 기음을 되찾는다. `fmax=500`을
낮추는 것도 후보지만 슬랩 고음을 잃는다 — 재고 정한다.

**주의**: 고친 뒤 **IDMT와 골든셋을 둘 다** 돌려라. IDMT는 베이스 단독 클린
녹음이라 이 문제가 없어서, IDMT만 보면 "변화 없음"으로 보이고 실곡에서만
갈린다.

### 그다음 (순서대로)

2. **16비트 붕괴** — Virtual Insanity. 박자 3/4 오검출부터 규명
3. **A-B 루프 + 메트로놈** — 정확도와 무관하게 값이 있다. 없으면 연습 도구가 아니다
4. `POLICY.md` 4장 추측(위험) 6건 중 하나 재기

## 직전에 고친 것 — 연습영상 오판 (2026-08-07)

**판정을 고친 게 아니라 버렸다.** 골든셋 4곡에서 세 신호가 전부 안 갈렸고
하나는 방향이 반대였다.

| 곡 | 실제 | 격자 정렬 | 어택 CV |
|---|---|---|---|
| Queen | 원곡 | 0.777 | 1.480 |
| Come Together | 원곡 | 0.751 | 1.389 |
| **Champagne 커버** | **연습 영상** | **0.730** | **1.096** |
| Virtual Insanity | 원곡 | 0.674 | 1.496 |

진짜 연습 영상이 격자 정렬 3위, **어택 CV는 가장 낮다**(문서에는 "겹치면 크게
흔들린다"고 적혀 있었는데 정반대).

**바꾼 것**: 원인("베이스가 둘 섞였다")을 단정하지 않고 관측("리듬 검출 신뢰도가
낮다")만 보고한다. `practice_video`는 항상 False로 두고 `rhythm_confident`로
판단한다.

**임계도 틀려 있었다.** `TRUSTED_GRID_RATIO`를 `bassclean`의 게이트 문턱(0.95)과
같게 두라고 적어놨었는데, **재는 대상이 다르다** — 게이트는 IDMT **정답 온셋**에
대해, 이쪽은 **우리 검출 온셋**에 대해 잰다. 우리 검출은 더 흔들리므로 같은 자를
대면 실곡 4/4가 전부 불신으로 떨어진다.

실측으로 다시 잡았다(격자 정렬률과 타현 정확도의 상관 **0.861**):

| 곡 | 격자 정렬 | 타현 정확도 |
|---|---|---|
| **Champagne (커버, 게이트 동작)** | **0.875** | **63%** |
| Queen | 0.777 | 7% |
| Come Together | 0.751 | 7% |
| Virtual Insanity | 0.674 | 6% |

0.875와 0.777 사이에서 63%와 7%로 갈린다 → **0.85**. 이제 Champagne이
`rhythm_confident=True`로 3단계 전부(`[1,2,3]`) 열린다.

**그 과정에서 거꾸로였던 것 하나를 더 잡았다**: 리듬을 못 믿을 때 원본만
주고 있었는데, **초급이야말로 남겨야 할 단계**다. 초급은 `uniform_rhythm=True`로
검출 리듬을 버리고 균일 템플릿을 씌우므로 리듬 검출 품질과 무관하다. UI는
이미 그렇게 판단하고 있었고(`MAX_TRUSTED_LEVEL_WHEN_MIXED = 1`)
`reduce.available_levels`만 어긋나 있었다. 이제 `[1, 3]`을 준다.

## 3. 회귀 (변경 후 반드시)

```bash
H=975e4e588d282666
.venv/Scripts/python.exe eval/eval_video_bars.py data/$H eval/golden/champagne_video_bars41_99.json
.venv/Scripts/python.exe tools/diag/test_export.py data/$H
.venv/Scripts/python.exe tools/diag/test_reduce.py data/$H
.venv/Scripts/python.exe tools/diag/test_variants.py data/$H
.venv/Scripts/python.exe tools/diag/test_carry.py
.venv/Scripts/python.exe tools/diag/test_quantize_cross.py
.venv/Scripts/python.exe tools/diag/test_chords.py
.venv/Scripts/python.exe tools/audit_constants.py --undocumented
cd apps/web && npm run build
```

기준선: 정답 43마디에서 **자리 84% / 타현 63%**, 나머지 전부 실패 0건.

---

## 4. 다시 하지 말 것 (측정에서 진 것들)

| 시도 | 결과 |
|---|---|
| 재타현 분리(스펙트럼 플럭스) | 중간값 없음. 40/47 유지 아니면 0/47 붕괴 |
| 관성 창을 구조 분할 경계로 | 타현 63% → 53% |
| 게이트 마디 보호에 16분 조건 | 73% → 53% |
| 겹침을 "일정 시간차 짝"으로 판정 | 신호가 전체의 8%뿐 |
| 커버/반주를 음량·어택 선명도로 가르기 | 둘 다 실패 |
| 음 쪼개짐 병합 | 26% → 30%. 쪼개짐은 원인이 아니다 |

`reattack.py`·`sections.py`·`kicksync.py`는 **만들어서 끈 것**이다. 각 모듈
머리말에 반증 표가 있다. 켜려면 그 표를 다시 만들어 기준선을 이겼는지 봐야 한다.

## 5. 함정 — 시간 날리는 자리

- **측정 도구를 먼저 의심하라.** 이번 세션에 두 번 당했다. `bassclean._bar_of`는
  근사 함수라 분석에 쓰면 없는 문제를 만든다. 대조 도구가 이조를 못 찾으면
  정상 결과가 5%로 보인다
- **워커를 재시작할 때** `taskkill //F //PID`가 안 먹는 경우가 있다.
  `Get-NetTCPConnection -LocalPort 8000` → `Get-Process python` → `Stop-Process`.
  놓치면 옛 코드가 응답해서 새 라우트가 404로 보인다
- **이름을 바꾸면 부르는 쪽을 전부 찾아라.** 이번에 네 군데를 놓쳤다
  (웹 라우트 상수, UI 게이트 필드, `slots_of`, CLI). 전부 "값이 없으면 안전해
  보이는 기본값으로 흐르는" 형태라 조용히 틀린다
- 나머지는 `CLAUDE.md` 함정 모음

---

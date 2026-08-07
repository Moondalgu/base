---
name: lowend-review
description: Lowend 베이스 자동채보 서비스의 전체 점검 — 상태 파악, 문서·코드·실측 정합성 검토, 오픈소스 대안과의 비교. "베이스 서비스 읽어줘", "베이스 서비스 점검", "lowend 점검", "베이스 채보 전체 검토", "베이스 오픈소스 비교" 맥락에서 호출한다.
---

# Lowend 전체 점검

유튜브 링크 → 베이스 자동 채보 + 연습 웹앱. 저장소는 `C:\Users\admin\Desktop\lowend`.

**이 스킬의 목적은 "잘 돌아간다"를 확인하는 것이 아니라 어긋난 곳을 찾는 것이다.**
이 프로젝트에서 실제로 난 사고는 전부 "맞는 줄 알았는데 아니었던 것"이다.

## 페이즈 0 — 무엇을 읽는가 (직접, 위임 없이)

```bash
cd C:/Users/admin/Desktop/lowend
git log --oneline -5
git status --short
```

읽는 순서: `START_HERE.md` → `HANDOFF.md` → `NEXT.md`.
`POLICY.md`·`MARKET.md`·`eval/golden/SET.md`는 페이즈에서 필요할 때 연다.

**`data/`는 gitignore이므로 산출물이 없을 수 있다.** 없으면 페이즈 1의 측정을
건너뛰고 그 사실을 보고에 적는다 — 없는 수치를 추정하지 않는다.

## 페이즈 1 — 기계가 잡을 수 있는 것부터 (직접)

```bash
.venv/Scripts/python.exe tools/check_consistency.py --measure
.venv/Scripts/python.exe tools/audit_constants.py --undocumented
```

`check_consistency.py`는 상수 삼자 일치·폐기된 이름 잔존·문서가 인용한 값·
문서가 주장하는 점수를 검사한다. **실패가 나오면 그것부터 고친다** — 그 위에
쌓은 판단이 전부 흔들린다.

## 페이즈 2 — 정합성 검토 (Fable 에이전트 3개, 병렬)

`Agent` 도구로 `model: "fable"`, `subagent_type: "general-purpose"`를 써서
셋을 **한 메시지에 동시에** 띄운다. 각 에이전트에 "저장소 경로"와
"읽어야 할 문서"를 명시하고, **파일을 고치지 말고 찾기만 하라**고 지시한다.

### 2-A. 코드끼리 어긋난 곳

찾을 것:
- 같은 개념을 두 곳에 적어둔 상수·필드명이 갈라진 곳
  (워커/웹/UI, manifest 키 ↔ 읽는 쪽)
- 이름을 바꾸고 호출부를 놓친 흔적. **특히 "값이 없으면 안전해 보이는 기본값으로
  흐르는" 형태** — `?? 1`, `or 기본값`, `.get(x, True)`
- 파이프라인 단계 순서 전제가 깨진 곳 (`compose.build`의 이조→양자화→관성→하향)

이 프로젝트에서 실제로 네 번 났다. 근거는 `CLAUDE.md` 함정 모음.

### 2-B. 문서가 코드와 어긋난 곳

찾을 것:
- `NEXT.md`·`HANDOFF.md`·`PLAN.md`가 "고쳤다"고 한 것이 코드에 실제로 있는가
- `POLICY.md` 등급이 코드 주석과 맞는가
- **꺼둔 모듈**(`reattack.USE_REATTACK`, `inertia.USE_SECTIONS`)이 문서 설명대로
  꺼져 있는가
- 문서에 있는 재현 명령이 실제로 도는가 (돌려본다)

### 2-C. 주장과 근거가 어긋난 곳 — 가장 중요하다

찾을 것:
- 코드 주석이 "실측"이라고 하는데 재현 명령이 없는 것
- **다른 모집단에서 나온 수치를 옮겨 쓴 곳.** 이 프로젝트에서 두 번 났다:
  IDMT 정답 온셋 기준 문턱을 우리 검출에 적용(`POLICY.md` 6.5),
  근사 함수(`bassclean._bar_of`)로 정밀 분석
- 상관을 인과로 읽은 곳 (킥 근처에 음이 몰린다 → 누출이다, 로 틀린 전례)
- 한 곡에서만 검증하고 일반화한 곳

## 페이즈 3 — 오픈소스 비교 (Fable 에이전트 2개, 병렬)

**우리가 지금 하는 방식이 최선인지**를 묻는 것이지 기능 목록 비교가 아니다.
`MARKET.md`는 상용 서비스 조사이고 **이쪽은 기술 대안 조사**다.

### 3-A. 채보 엔진 대안

우리는 **Demucs(htdemucs) → torchcrepe(단선율 f0) → 자체 후처리**다.
`POLICY.md` 4.6에 "분리 모델을 비교한 적이 없다"고 적혀 있다.

비교 대상:

| 대상 | 왜 |
|---|---|
| [spotify/basic-pitch](https://github.com/spotify/basic-pitch) | 이미 저장소에 비교 경로가 있다(`transcribe.py`, IDMT F 0.815 대 CREPE 0.861) |
| [magenta/mt3](https://github.com/magenta/mt3) | 다중악기 동시 채보. 분리 없이 베이스를 뽑을 수 있는지 |
| [omnizart](https://github.com/Music-and-Culture-Technology-Lab/omnizart) | 보컬·드럼·코드·비트까지 한 프레임워크. 3단 악보에 쓸 수 있는지 |
| [lucasgris/awesome-agt](https://github.com/lucasgris/awesome-agt) | 기타 채보 자료 모음. 베이스 특화는 적다 |
| Demucs 변종 (`htdemucs_ft`, `mdx_extra`) | 베이스 스템 품질 미비교 (POLICY.md 4.6) |

각각에 대해 답할 것:
1. **베이스를 지원하는가**, 아니면 기타·피아노 중심인가
2. 우리가 못 하는 것을 하는가 — **16비트 붕괴·배음 오인**이 우리 실측 결함이다
3. 붙이는 비용 (의존성 충돌 이력이 있다 — `CLAUDE.md` 새 환경 준비 절)
4. **우리 골든셋으로 채점할 수 있는가.** 못 재면 채택 근거가 없다

### 3-B. 표기·렌더 대안

우리는 **AlphaTex 생성 → alphaTab 렌더**다. 확정된 문법과 함정이
`CLAUDE.md`에 있다.

비교 대상: VexFlow, OpenSheetMusicDisplay(MusicXML 직접 렌더), Verovio,
그리고 MuseScore CLI(PDF 경로).

물을 것: **PDF·자동 넘김 뷰·3단 악보(보컬+가사)**가 지금 스택에서 되는가,
아니면 렌더러를 바꿔야 하는가. 우리는 MusicXML 내보내기가 이미 있으므로
(`pipeline/export.py`) 다른 렌더러로 가는 문이 열려 있다.

## 페이즈 4 — 종합 (직접)

에이전트 결과를 받아 **직접 검증한 뒤** 보고한다. 에이전트 보고를 그대로
옮기지 않는다 — 이 세션에서 교차 검토가 사실을 틀린 적이 여러 번 있다
(`MARKET.md` "Gemini 답변에서 확인해보니 틀렸던 것", `POLICY.md` 6장).

보고 형식:

1. **지금 상태** — 골든셋 4곡 점수와 재현 여부
2. **어긋난 곳** — 심각도 순. 각 항목에 (파일:줄) + (왜 문제인가) + (고치는 법)
3. **오픈소스 비교 결론** — 바꿀 것 / 안 바꿀 것, 각각 근거
4. **다음 한 가지** — 여러 개 나열하지 말고 하나를 고른다

## 이 프로젝트에서 지켜야 할 것

- **측정 도구를 먼저 의심하라.** 예상 밖으로 나쁜 숫자는 파이프라인이 아니라
  측정이 틀린 경우가 있었다(두 번)
- **IDMT와 실곡 골든셋을 둘 다 돌린다.** 반대를 가리키면 더 나쁜 쪽을 따른다.
  IDMT는 베이스 단독 21초 리프라 실사용을 대표하지 않는다
- **이미 진 시도를 다시 하지 않는다.** `START_HERE.md` 4절과
  `reattack.py`·`sections.py`·`kicksync.py` 머리말의 반증 표
- **꺼둔 모듈을 켜려면 반증 표를 다시 만들어 기준선을 이겨야 한다**
- 회귀 명령은 `START_HERE.md` 3절

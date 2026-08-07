# 다음 세션 시작 지점

이 파일 하나만 읽고 바로 작업을 시작할 수 있게 만든 것이다.
배경이 필요하면 `HANDOFF.md` → `NEXT.md` 순서로 간다.

---

## 0. 환경 확인 (2분)

```bash
cd C:/Users/admin/Desktop/lowend
git log --oneline -1        # 4f68999 feat: 골든셋 4곡 + 내보내기 + 규칙값 카탈로그
git branch --show-current   # feat/golden-set-and-export
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
# 기대: 자리 40/43 (93%)  타현수 27/43 (63%)

.venv/Scripts/python.exe eval/eval_songsterr.py data/528aa2e6986aa42a \
    eval/golden/songsterr_queen_aobtd.json
# 기대: +1반음 이조, 음 47/76 (62%), 타현 3/76 (4%)
```

숫자가 다르면 **파이프라인이 아니라 산출물이 낡은 것**일 수 있다.
`tools/diag/refresh_manifest.py`로 뒷단만 다시 돈다.

---

## 2. 오늘 할 일 — 하나만 고르면 이것

### 연습영상 오판 고치기 (`pipeline/diagnose.py`)

**왜 이것부터**: 지금 **사용자에게 틀린 정보를 보여주고 있다.** 공식 스튜디오
음원 3곡을 전부 "베이스가 둘 섞인 연습 영상"으로 판정해서, 하향 단계를 막고
없는 문제를 경고한다. 정확도 개선보다 우선한다.

**현재 상태 확인**:

```bash
.venv/Scripts/python.exe -c "
import json, glob, os
for d in sorted(glob.glob('data/*/manifest.json')):
    m = json.load(open(d, encoding='utf-8'))
    t = (m.get('source') or {}).get('title', '?')[:38]
    dg = m.get('inputDiagnosis') or {}
    print(f\"{os.path.basename(os.path.dirname(d))} {t:38} practice={dg.get('practiceVideo')} 격자={dg.get('gridRatio')} 어택CV={dg.get('attackCv')}\")"
```

**정답**: 커버 영상(975e...) 하나만 `practice=True`여야 한다.

**무엇이 문제인가**: `diagnose.py`가 게이트 후 격자 정렬률만 본다. 정렬이 나쁜
이유가 둘인데(베이스가 둘 / 우리 검출이 나쁨) 하나로만 해석한다. 보조 신호인
어택 편차도 세 곡에서 1.39~1.50으로 커버 영상보다 오히려 높아 못 가른다.

**방향**: 보수적으로 바꾼다 — 확신 없으면 원곡으로 본다. 틀린 경고는 없는
경고보다 나쁘다. 판정을 느슨하게 하면 실제 연습 영상에서 하향 단계가 다시
열리는데, 그 하향 품질이 낮다는 근거는 `diagnose.py` 머리말에 있다.

**검증**: 위 명령으로 4곡의 `practice` 값을 보고, 그다음 회귀(아래 3번).

### 그다음 (순서대로)

2. **배음을 기음으로 잡는 것** — Come Together. f0 후보의 1/2·1/3 에너지 확인
3. **16비트 붕괴** — Virtual Insanity. 박자 3/4 오검출부터 규명
4. **A-B 루프 + 메트로놈** — 정확도와 무관하게 값이 있다. 없으면 연습 도구가 아니다

---

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

기준선: 정답 59마디에서 **자리 93% / 타현 63%**, 나머지 전부 실패 0건.

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

## 6. 브랜치 정리

작업은 `feat/golden-set-and-export`에 있다. master로 합치려면:

```bash
git checkout master && git merge feat/golden-set-and-export
```

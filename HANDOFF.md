# HANDOFF — 다음 세션 재개용 (2026-08-08 심야 갱신)

유튜브 링크 → 베이스 자동 채보 + 연습 플레이어 (Lowend).
**재개 시 이 파일부터 읽고, 그다음 `NEXT.md`로 간다.** 계획 v2(B·Q·X·F·V 트랙)의
실행 기록·수치는 전부 `PLAN.md` 2026-08-08 절들에 있다.

---

## 한 문장 요약

**3단 악보(보컬 오선+가사+조표 / 베이스 오선 / TAB)가 브라우저에 실물로 떴고**
(드라우닝 — 참조 악보와 동일 구성), 골든셋 6곡 체제에서 K-pop 두 곡이
피치 98%(예뻤어)·81%/타현 83%(드라우닝)로 최상위다. A-B 루프·메트로놈·자동
넘김 뷰·인쇄까지 붙었다. 남은 것은 소리 귀 검증, Lv2 참조 악보 대조(V),
조판·UX 폴리싱(F7·F8)이다.

## 골든셋 현황 (마디 피치클래스, `eval/run_goldenset.py`)

| 곡 | 피치 | 타현 | 엔진 | 비고 |
|---|---|---|---|---|
| 예뻤어 | **98%** | 49% | crepe | 조표 E♭ 발행 |
| Champagne | 94% | (영상 정답 63%) | crepe | Songsterr 대조는 커버라 +7 이조 |
| Drowning | **81%** | **83%** | crepe | 조표 A♭·코드 근음 진행 참조와 일치 |
| Come Together | 76% | 5% | **basic-pitch** | 이번에 65→76 (엔진 폴백) |
| Queen | 62% | 4% | crepe | 음원이 악보보다 +1반음 (진짜 이조) |
| Virtual Insanity | 25% | 15% | **basic-pitch** | 의도된 하드 케이스. 앨범 음원(b9Y4TACmvE8)으로 교체됨 |

## 이번 세션의 구조적 변화 (2026-08-08)

1. **엔진 자동 폴백** `pipeline/engine_select.py` — CREPE 커버리지 < 0.45면
   basic-pitch. 임계는 CT(0.44, +11pp)와 Queen(0.47, −2pp) 사이 — **간격 3pp뿐인
   불안정 경계**, 새 곡으로만 재조정.
2. **박자 추론 수정** — beat_this 다운비트가 마디/반마디 혼합(쌍봉)일 때 중앙값이
   3/4로 떨어지던 버그. 정규화(2→4)를 집계 전으로.
3. **3단 악보 전 경로 배선** — `compose.build(vocal_notes, vocal_syllables)`,
   quantize `force_phase`(트랙 간 마디 공유), alphaTab은 **트랙 미지정 시 첫
   트랙만 그린다** → ScoreView가 `renderTracks(전체)`.
4. **가사** `pipeline/lyrics.py` — faster-whisper ASR, 음절 시각 그리디 정렬,
   `\lyrics`는 쉼표를 소비하지 않는다(프로브 실측).
5. **자기 채점** `eval/eval_selfscore.py` — 크로마 일치·커버리지, 골든셋 상관
   0.807 유효. quality.py 편입은 임계 재보정이 걸려 이월.
6. **측정 도구 수정** — eval_songsterr 이조 마진(가짜 +7 차단)·피치클래스 지표
   상시 보고, review_score·our_bars 멀티트랙 대응.
7. 프론트: A-B 루프(입력 타임라인이라 배속 무관)·메트로놈(lookahead)·자동 넘김
   뷰(startBar/barCount)·인쇄(api.print).

## 바로 다음에 할 일

1. **소리 귀 검증** — 루프 경계·메트로놈 클릭(배속·되감기)·3단 재생 커서.
   PLAN.md 마지막 절의 체크리스트 11항목 중 소리 항목.
2. **V 최종 검증** — 드라우닝·예뻤어 **Lv2** 3단 악보를 참조 악보 PNG
   (`Desktop\악보\`)와 눈 대조(근음 진행·리듬 분포·가사 마디 정렬).
3. **F7 조판** — 보컬 조각화(비브라토가 반음 경계에서 쪼갬 — 같은 음 인접 병합),
   stretchForce 튜닝, SVG 좌표 실측.
4. **F8 UX/UI** — impeccable 계열 스킬로 전면 검토.
5. NEXT.md 이월 목록(코드 3도 단조 판정, 고스트노트 측정, 위상 채점 등).

## 서버·환경 메모

- 웹 dev는 **Turbopack이 패닉한다**(자식 프로세스 0xc0000142) —
  `npx next dev --webpack`으로 켠다. 워커는 `cd apps/worker &&
  ../../.venv/Scripts/python -m uvicorn main:app --port 8000`.
- alphaTab은 행을 뷰포트 진입 시 지연 렌더 — 전곡 검사는 스크롤 박스를 실제로 내려야 한다.
- 설치: faster-whisper·synctoolbox·music21(본 venv), audio-separator(`.venv-sep`).
  its-mytabs 클론 = `Desktop/lowend-refs/its-mytabs`(커서 3모드 참고).
- 골든셋 신규 해시: 드라우닝 65ef1cf020561a5c · 예뻤어 8181e1aa7d7a0be1 ·
  VI 앨범 d4fd7b689b9db1bb (MV c54d965e0a8fda45는 축약판 — 평가에 쓰지 말 것).

## 문서 지도

| 파일 | 무엇이 있나 |
|---|---|
| `NEXT.md` | **계획 v2 순서 + 이월 목록.** 이 파일 다음에 읽는다 |
| `PLAN.md` | 실행 기록·측정치 정본 (2026-08-08 절 다수 추가) |
| `POLICY.md` | 규칙·정책 상수의 근거 등급 (08-08 상수 8건 추가) |
| `MARKET.md` | 경쟁 조사 + 08-08 보강(alphaTab API 발견·Klangio 실물) |
| `eval/golden/SET.md` | 골든셋 6곡·URL·재생성 절차 |
| `PRD.md` | 서비스 정의·요구사항 (2.0.0) |
| `CLAUDE.md` | 재발견 금지 사실·함정 모음 |

## 측정에서 진 시도 — 다시 하지 마라 (08-08 추가분)

- 배음→기음 복구(서브하모닉): **문제 자체가 허구** — f/2·f/3 에너지 0%
- 드럼 스템 위상 소스: 정렬 수치는 좋아 보였지만 재조립 결과 붕괴(타현 15%→3%)
- kicksync: 스튜디오 원곡에서도 락 비율 최대 35.9%(문헌 80%) — 전제 불성립
- htdemucs_ft 분리: VI에서 이득 없음, 시간 4배

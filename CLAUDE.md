# Lowend — Claude용 프로젝트 규칙

유튜브 링크나 오디오 파일에서 **베이스 파트를 자동 채보하고 연습 도구를 붙인** 웹앱.
개인 학습 목적. 상업화 계획 없음.

**작업 시작 전 이 순서로 읽어라**
0. `START_HERE.md` — **다음 세션 진입점.** 환경 확인 → 점수 재현 → 오늘 할 일 → 회귀. 이것만 읽고 시작할 수 있다.
1. `HANDOFF.md` — 현재 상태·실측 수치·미해결 과제.
2. `PRD.md` (2.0.0) — 서비스 정의, 기능 요구사항, 11장 구현 프로세스, 12장 누락 검토 시나리오, **13장 과제 나래비(할 일 순서의 정본)**. 부록 A에 실측 확인된 API.
3. `PLAN.md` — P0~P8 실행 기록과 확정 원칙(난이도 하향·KEY·악보 구성)의 근거·측정치.
4. `POLICY.md` — **규칙·정책 상수 110개의 근거 등급.** 값을 바꾸려면 여기를 먼저 본다. `python tools/audit_constants.py`가 전수 조사한다.
5. `MARKET.md` — 경쟁 서비스 조사와 벤치마크. 무엇이 차별점이고 무엇이 아닌지.
6. 이 파일 — 재발견하지 말아야 할 확정 사실들

**할 일을 고를 때는 `PRD.md` 13장을 본다.** 프로세스 순서로 정렬돼 있고, 앞 단계를 고치지 않고 뒤 단계를 고치면 헛수고가 되는 구조다.

---

## 새 환경 준비 (클론 직후)

`data/`는 gitignore 대상이라 비어 있다. 오디오·산출물·데이터셋은 직접 만들거나 받아야 한다.

```bash
# 1) Python 3.12 가상환경. 설치 순서가 중요하다 — apps/worker/requirements.txt 머리말 참조.
python -m venv .venv
.venv/Scripts/python.exe -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/python.exe -m pip install -r apps/worker/requirements.txt
.venv/Scripts/python.exe -m pip install basic-pitch==0.4.0 --no-deps
.venv/Scripts/python.exe -m pip install tuttut==0.0.6 --no-deps

# 2) 웹
cd apps/web && npm install && cd ../..
cd tools && npm install && cd ..        # 검증기용

# 3) 합성 픽스처 생성 (스모크 테스트용, 16초). 스윙판은 플래그가 따로 있다.
.venv/Scripts/python.exe scripts/make_fixture.py
.venv/Scripts/python.exe scripts/make_fixture.py --swing

# 4) 정답 데이터셋 — 정확도를 재려면 필수. 아래 "측정" 절 참조.
```

`basic-pitch`와 `tuttut`을 `--no-deps`로 넣는 이유는 PRD 부록 A.1에 있다. Python 3.12에서 옛 numpy 핀을 소스 빌드하려다 깨진다.

## 실행

```bash
# 파이프라인 (CLI)
.venv/Scripts/python.exe scripts/run_pipeline.py <오디오파일|유튜브URL>
.venv/Scripts/python.exe scripts/run_pipeline.py <베이스단독파일> --skip-separate --beat-source <원본>
.venv/Scripts/python.exe scripts/run_pipeline.py <파일> --engine basic-pitch   # 비교용

# 워커 (웹 백엔드)
cd apps/worker && ../../.venv/Scripts/python -m uvicorn main:app --port 8000

# 웹
cd apps/web && npm run dev        # predev가 sync-vendor 자동 실행
cd apps/web && npm run build && npm start

# 검증
.venv/Scripts/python.exe eval/run_eval.py data/<hash> data/_fixture/truth.json
.venv/Scripts/python.exe eval/eval_idmt.py --engine crepe        # 정답 데이터셋
.venv/Scripts/python.exe eval/eval_practice.py                   # 연습 관점(거짓음·누락)
cd apps/web && node ../../tools/validate_alphatex.mjs <file.alphatex>
cd apps/web && node ../../tools/probe_clef.mjs <file.alphatex>

# 표기 검토 — 표기 로직을 건드렸으면 이것부터
.venv/Scripts/python.exe tools/diag/review_score.py data/<hash>/score.alphatex
.venv/Scripts/python.exe tools/diag/review_shortnotes.py data/<hash>/score.alphatex
.venv/Scripts/python.exe tools/diag/test_carry.py            # 마디 넘김 타이
.venv/Scripts/python.exe tools/diag/test_quantize_cross.py   # 길이 보존·상한

# 이미지·PDF 판독은 Gemini로 (base64가 컨텍스트에 안 들어간다)
.venv/Scripts/python.exe tools/vision/gemini_vision.py <이미지|PDF> tools/vision/prompt_score.txt
```

도구 설명은 `tools/diag/README.md`, `tools/vision/README.md`에 있다.

CPU 소요(5분 곡): Demucs 약 450초 + CREPE 채보 약 480초 = **약 15분**. 정상이다.

---

## 확정된 AlphaTex 문법 — 다시 실험하지 마라

`tools/validate_alphatex.mjs`로 직접 검증한 결과다.

| 표기 | 문법 | 비고 |
|---|---|---|
| 음표 | `프렛.현.음길이` | 현 1 = 가장 얇은 현(G) |
| **타이** | `-.현.음길이` | 예 `-.4.8`. **현 번호가 반드시 필요하다** |
| 붙임점 | `{d}` 접미 | `0.4.8{d}` |
| 셋잇단 | `{tu 3}` | `{tuplet 3}` 풀네임은 거부됨 |
| 오선보+TAB | `\staff{score tabs}` | `\staff{tabs}`면 TAB만 나오고 프론트엔드 설정이 무시된다 |
| 낮은음자리표 | `\clef bass` | **빼면 파싱은 통과하지만 조용히 높은음자리표(G2)로 남는다** |
| **조표** | `\ks Ab` | 헤더에 둔다. `masterBars[0].keySignature`로 확인(A♭ = raw −4, Major) |
| **멀티트랙** | `\track "이름"` 반복 | 트랙마다 `\staff`·`\clef`·`\tuning`을 따로 준다 |
| **가사** | `\lyrics "음절 음절 ..."` | 트랙 헤더. **공백으로 나눠 비트에 순서대로 배정된다. 한국어도 된다** |
| **코드 심볼** | `프렛.현.음길이{ch "Ab"}` | 비트에 붙는다 |
| **슬라이드** | `프렛.현{sl}.음길이` | `{sl}`=Legato(글리산도), `{ss}`=Shift(S 표기) |
| 해머온·스타카토 | `프렛.현{h}.음길이` / `{st}` | |

**중괄호를 연달아 쓸 수 없다.** `0.4.4{d}{ch "E"}`는 파서가 `Unexpected 'LBrace'`로 거부하고 `0.4.4{d ch "E"}`는 통과한다. 수식을 더할 때는 **기존 중괄호 안에 공백으로 나열**해야 한다. 붙임점이 붙은 음표에 코드를 얹을 때 실제로 걸렸다.

**코드 심볼은 음표에만 붙는다.** 쉼표(`r.4`)·타이(`-.4.8`)에 붙이면 거부된다. 마디가 쉼표뿐이면 코드를 생략한다 — 코드는 오디오 분석 산출물이라 노트 필터(음량 게이트)가 그 마디 음을 다 버려도 남아 있다. 두 산출물이 서로를 모른다.

**워커는 `--reload` 없이 띄우면 파이썬 변경이 반영되지 않는다.** 파이프라인을 고친 뒤 브라우저에서 옛 동작이 보이면 워커를 재시작한다. 조합 검증(`tools/diag/test_variants.py`)은 워커를 거치지 않으므로 통과하는데 브라우저만 실패하는 상황이 나온다.

**`{}`는 위치에 따라 뜻이 다르다.** 음길이 **뒤**면 duration 수식(`0.4.8{d}` 붙임점, `{tu 3}` 셋잇단), 현 번호 **뒤**면 음표 효과(`4.4{sl}.8`). 효과를 음길이 뒤에 쓰면(`4.4.8{sl}`) **파싱이 실패한다.** 효과 이름이 틀린 것으로 오해하기 쉬우니 위치를 먼저 의심해라.

거부되는 형태: `-.8`(현 생략), `-`(단독), `{t}`/`{-}` 효과 문법, `:8 0.4 -` 듀레이션 모드, `4.4.8{sl}`(효과를 음길이 뒤에).

**파싱 통과 ≠ 적용됨.** `\clef`처럼 조용히 무시되는 지시자가 있다. 모델을 직접 읽어 확인하려면 `tools/probe_notation.mjs <file>`(조표·트랙·staff·코드·가사·효과) 또는 `tools/probe_clef.mjs`를 쓴다.

---

## 절대 건드리면 안 되는 것

**`bpm_variance`를 균일 격자 기준으로 재계산하지 마라.** `beats.py`가 균일 격자를 채택해도 이 값은 **원본 검출 비트 기준을 유지**한다. 이유 두 가지:
- `quality.py`의 `beatStability`가 이 값을 쓴다 → 0으로 만들면 "비트 완벽"이라는 거짓 보고가 된다
- `quantize.SWING_MAX_BPM_VARIANCE = 0.05` 게이트가 이 값을 쓴다 → 0이 되면 스윙 판정이 열려 **전곡 셋잇단 문제가 재발**한다

**`apps/web/public/vendor/`는 생성물이다.** 직접 수정 금지. `apps/web/scripts/sync-vendor.mjs`가 소스이고, signalsmith-stretch 1.3.2의 벤더 버그를 자동 패치한다(비활성 분기 TypeError로 오디오 프로세서가 영구 사망하는 문제). 패턴 미발견 시 빌드가 실패하도록 해두었다 — 업스트림 업데이트 때 재검토를 강제하려는 것이다.

**격자(subdivision)를 하드코딩하지 마라.** 스트레이트 곡의 격자는 `quantize.choose_subdivision()`이 온셋을 보고 2 또는 4로 고른다(임계 5%, IDMT 17곡 근거). 악보를 읽는 도구는 `manifest.subdivision`을 읽어야 한다 — 4로 가정하면 8분 격자 악보에서 4분음표처럼 두 표에 같은 슬롯 수로 들어 있는 음길이만 우연히 통과해 **위반을 놓친다.** `tools/diag/review_score.py`가 그래서 스윙 악보를 한 번도 검산하지 못했다.

**행당 마디 수는 트랙에도 넣어야 한다.** `LayoutMode.Parchment`에서 행당 마디 수는 모델의 `defaultSystemsLayout`이 정하는데, **트랙 값이 악보 값보다 우선한다.** `score`에만 넣으면 바뀌지 않는다. `systemsLayout`(행별 마디 수 배열)도 비워야 기본값이 이긴다. 마디 폭은 `displayScale` 기본값 1로 자동 균등해지므로 따로 설정할 필요가 없다.

**alphaTab 컨테이너 폭을 0으로 만들지 마라.** 폭이 0이면 렌더링을 건너뛴다. "준비되면 보여주기" 패턴으로 `hidden`을 걸면 준비 신호가 `renderFinished`에서 오므로 교착이 생긴다. 자리를 잡아두고 `opacity`만 조절해라.

**alphaTab 커서는 CSS를 직접 줘야 보인다.** 요소는 만들어지지만 색이 없어 투명하다. `apps/web/app/globals.css`의 `.at-cursor-bar` / `.at-cursor-beat` / `.at-highlight` 규칙이 그것이다.

---

## 측정 — 픽스처가 아니라 정답 데이터셋을 믿어라

`data/`는 gitignore 대상이라 클론 직후에는 비어 있다.

**정답 데이터셋(필수)**: [IDMT-SMT-BASS-SINGLE-TRACKS](https://zenodo.org/records/7544099) (20.5MB, CC BY-NC-ND 4.0, 신청 불필요)
실제 4현 일렉베이스 17곡·948음. 튜닝 28/33/38/43 = 우리 standard와 동일. XML에 onset/offset/pitch/**string/fret**/주법까지.
`data/_datasets/idmt_single/`에 풀어라. **주의: IDMT 현번호는 1=E, 4=G로 alphaTex와 반대다.**

**합성 픽스처(`data/_fixture/`)는 스모크 테스트용이다.** `scripts/make_fixture.py`로 생성한다. 16초 순음이라 실제 녹음의 어택·감쇠 포락선이 없다 → **진폭 기반 로직을 검증할 수 없다.** 이 프로젝트에서 픽스처만 보고 판단해 두 번 잘못된 결론에 도달했다.

### 현재 수치 (IDMT 17곡, 온셋+음높이, 허용 ±150ms)

| 엔진 | P | R | F | 거짓 음 | 누락 |
|---|---|---|---|---|---|
| basic-pitch + 전체 후처리 | 0.770 | 0.874 | 0.815 | 22.8% | 12.4% |
| **crepe (기본)** | **0.893** | 0.856 | **0.861** | **9.7%** | 14.3% |

주법별(crepe): 뮤트 0.938 / 픽 0.924 / 핑거 0.912 / **슬랩 0.577 (누락 51.7%)**.
**슬랩은 이 엔진의 구조적 약점이다.** 어택이 타악기적이어서 피치 추적기가 음으로 인식하지 못한다.

외부 기준(FiloBass 논문, 콘트라베이스, 동일 허용오차): basic-pitch 0.627 / CREPE Notes 0.729 / Melodyne 0.790.

---

## 채보 엔진 두 개

기본은 **crepe**(`transcribe_crepe.py`, torchcrepe). 프레임당 피치가 하나라 **배음 거짓 음을 구조적으로 만들지 않는다.**

`bassclean.clean(..., monophonic_source=True)`로 호출하면 배음 제거·단선율 강제·병합을 건너뛴다. 그 세 단계는 다성 모델 출력의 거짓 음을 걷어내는 것이 목적이므로, 단선율 엔진 출력에서는 걸러낼 대상 없이 실제 음만 깎는다.

`basic-pitch`(`transcribe.py`)는 비교용으로 남겨둔다. `--engine basic-pitch`.

---

## 함정 모음

- 검증기·프로브는 **`apps/web`에서 실행**해야 모듈이 해석된다.
- 인라인 heredoc으로 AlphaTex 프로브를 만들면 순정 케이스도 FAIL한다(하니스 문제). **파일로 써서 검증기에 넘겨라.**
- `data/{hash}/beats.json`은 캐시다. 비트 로직을 바꿨으면 **지우고 재생성**해야 반영된다.
- `ingest(url, workdir)`의 `workdir`는 **최상위 `data/`**를 넘긴다. 내부에서 `workdir / hash`를 만든다. hash 디렉토리를 직접 넘기면 중첩된다.
- yt-dlp가 403을 내면 `ytdlp.py`의 `PLAYER_CLIENT_FALLBACKS`가 `android` 클라이언트로 재시도한다.
- `notes.json`은 schemaVersion 2부터 저장된다. **그 이전에 만든 산출물에는 없다** — 악보 변형(레벨·이조·튜닝)을 만들 수 없고 재진단에 `transcribe()` 재실행이 필요하다. `data/` 기존 디렉토리 대부분이 여기 해당한다.
- **악보를 만드는 경로는 `pipeline/compose.py` 하나다.** CLI·웹 잡·변형 요청이 전부 이 함수를 쓴다. 셋잇단을 적을 수 없을 때 격자를 되돌리는 폴백이 여기 있으므로, 어느 한 경로에만 표기 로직을 넣으면 경로마다 다른 악보가 나온다.
- `eval/golden/champagne_bars25_28.json`은 **어택 개수·리듬 평가에 쓰면 안 된다.** 그 곡 오디오에 베이스가 둘 섞여 있다(원곡 반주 + 커버 연주). 파일 안 `_WARNING`에 근거가 있다. **단 `champagne_video_*.json`은 쓸 수 있다** — 음량 게이트가 큰 소리 쪽(커버)만 남기므로 우리 출력과 화면 악보가 같은 연주자를 가리킨다.
- **`gemini_analyze_image` MCP 도구는 어떤 이미지에도 `400 Unable to process input image`를 낸다.** jpg·png·리사이즈·크롭 다 실패한다. 같은 키로 REST에 직접 붙으면 정상이다. 이미지가 필요하면 `tools/gemini_vision.py`를 써라. 텍스트 대화(`gemini_chat`)는 MCP가 정상이다.
- **`gemini-3.1-pro`는 없는 모델 이름이다**(404). `gemini-3.1-pro-preview`다. 목록은 `curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$KEY"`.
- **`inertia.USE_SECTIONS`를 켜지 마라.** 구조 분할이 경계를 맞게 찾는데도 타현 정확도가 63%→53%로 떨어진다. 섹션이 짧아져 최빈 패턴 투표의 표본이 부족해지는 것이 원인이다. 근거와 해결 후보는 `NEXT.md` 7.5절.
- **워커를 재시작할 때 `taskkill //F //PID`가 안 먹는 경우가 있다.** netstat이 LISTENING으로 보고하는 PID가 실제 프로세스와 다르게 나온다. `Get-NetTCPConnection -LocalPort 8000`으로 소유 PID를 찾고 `Get-Process python`으로 실제 프로세스를 찾아 `Stop-Process`해야 한다. 이걸 놓치면 **옛 코드가 계속 응답해서 새로 만든 라우트가 404로 보인다** — 코드가 아니라 프로세스 문제다. 확인법: `curl -s localhost:8000/openapi.json`으로 등록된 경로를 본다.
- **파일명에 한글이 들어가면 `Content-Disposition`에 `filename*=UTF-8''...`를 함께 써야 한다.** `filename=`만 쓰면 깨지고 `filename*=`만 쓰면 옛 브라우저가 못 읽는다. 둘 다 넣는다(`main.py` score_export).
- **XML을 만들 때 `minidom.parseString`으로 들여쓰기하지 말 것.** 우리가 만든 문자열이라도 파서를 한 번 더 통과시키는 것이고, 그 자리가 XXE·엔티티 폭탄의 통로다. `ET.indent()`를 쓴다.
- **`if elem or 기본값`으로 ElementTree 요소를 검사하면 안 된다.** 자식이 없는 Element는 falsy라서 유효한 요소를 찾았는데도 기본값으로 넘어간다(파이썬 3.12는 DeprecationWarning을 낸다). `is not None`으로 본다.
- **`bassclean._bar_of`를 분석에 쓰지 마라.** 독스트링에 "위상은 정확하지 않아도 된다"고 적혀 있다 — 게이트가 마디를 통째로 비우지 않게 하는 용도다. 이것으로 피치 귀속을 분석해 **"다른 피치 끼어듦 21%"라는 없는 문제를 만들었다.** `quantize`의 마디 귀속으로 다시 재니 어긋난 피치가 **0%**였다. 마디 단위 분석은 `quantize.quantize()`를 거친 `QuantizedScore.bars`를 봐라.
- **`reattack.USE_REATTACK`을 켜지 마라.** 재타현 분리(스펙트럼 플럭스)는 측정에서 졌다. 조건을 강하게 두면 분할이 안 일어나고(IDMT 나눔 0건) 조금만 풀면 실곡 반복 구간이 40/47 → 0/47로 붕괴한다. 근거 표는 `reattack.py` 머리말. 다음 후보는 드럼 킥 동기화다(`playing.json` kickLock).
- **게이트 발동 판정과 감량 목표는 다른 지표다.** 발동은 `_grid_ratio`(16분·셋잇단 중 최선, 임계 0.95), 감량은 `_converge_ratio`(8분, 목표 0.85). 하나로 합치려는 시도가 두 번 실패했다(`bassclean.py` 주석에 수치 있음).

---

## 작업 방식

- **추측으로 결론 내지 마라.** 이 프로젝트에서 그렇게 해서 세 번 틀렸다(병합 손실 원인, 악보-오디오 불일치, 라이브 소스가 더 좋을 것이라는 판단). 정답 데이터셋이 있으니 재라.
- 파이프라인 변경 후에는 **픽스처 3종 + IDMT**를 둘 다 돌려라. 둘이 반대 방향을 가리키면 IDMT를 믿어라.
- 사용자 대면 텍스트는 **한국어**. 코드 주석도 한국어이고 "왜 그렇게 하는지"를 설명하는 톤이다. 변경 이력 서술("기존에는", "버그였다")은 넣지 마라.

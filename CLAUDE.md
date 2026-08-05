# Lowend — Claude용 프로젝트 규칙

유튜브 링크나 오디오 파일에서 **베이스 파트를 자동 채보하고 연습 도구를 붙인** 웹앱.
개인 학습 목적. 상업화 계획 없음.

**작업 시작 전 이 순서로 읽어라**
1. `HANDOFF.md` — 현재 상태·실측 수치·미해결 과제. **가장 먼저.**
2. `PRD.md` — 설계 결정과 근거. 부록 A에 실측 확인된 API가 정리돼 있다.
3. 이 파일 — 재발견하지 말아야 할 확정 사실들

---

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
cd apps/web && node ../../tools/validate_alphatex.mjs <file.alphatex>
cd apps/web && node ../../tools/probe_clef.mjs <file.alphatex>
```

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

거부되는 형태: `-.8`(현 생략), `-`(단독), `{t}`/`{-}` 효과 문법, `:8 0.4 -` 듀레이션 모드.

**파싱 통과 ≠ 적용됨.** `\clef`처럼 조용히 무시되는 지시자가 있다. 모델을 직접 읽어 확인하려면 `tools/probe_clef.mjs`를 쓰거나 같은 방식으로 확장해라.

---

## 절대 건드리면 안 되는 것

**`bpm_variance`를 균일 격자 기준으로 재계산하지 마라.** `beats.py`가 균일 격자를 채택해도 이 값은 **원본 검출 비트 기준을 유지**한다. 이유 두 가지:
- `quality.py`의 `beatStability`가 이 값을 쓴다 → 0으로 만들면 "비트 완벽"이라는 거짓 보고가 된다
- `quantize.SWING_MAX_BPM_VARIANCE = 0.05` 게이트가 이 값을 쓴다 → 0이 되면 스윙 판정이 열려 **전곡 셋잇단 문제가 재발**한다

**`apps/web/public/vendor/`는 생성물이다.** 직접 수정 금지. `apps/web/scripts/sync-vendor.mjs`가 소스이고, signalsmith-stretch 1.3.2의 벤더 버그를 자동 패치한다(비활성 분기 TypeError로 오디오 프로세서가 영구 사망하는 문제). 패턴 미발견 시 빌드가 실패하도록 해두었다 — 업스트림 업데이트 때 재검토를 강제하려는 것이다.

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
- 실곡 데이터에 `notes.json`은 저장되지 않는다. 재진단 시 `transcribe()` 재실행이 필요하다.
- `eval/golden/champagne_bars25_28.json`은 **어택 개수·리듬 평가에 쓰면 안 된다.** 그 곡 오디오에 베이스가 둘 섞여 있다(원곡 반주 + 커버 연주). 파일 안 `_WARNING`에 근거가 있다.

---

## 작업 방식

- **추측으로 결론 내지 마라.** 이 프로젝트에서 그렇게 해서 세 번 틀렸다(병합 손실 원인, 악보-오디오 불일치, 라이브 소스가 더 좋을 것이라는 판단). 정답 데이터셋이 있으니 재라.
- 파이프라인 변경 후에는 **픽스처 3종 + IDMT**를 둘 다 돌려라. 둘이 반대 방향을 가리키면 IDMT를 믿어라.
- 사용자 대면 텍스트는 **한국어**. 코드 주석도 한국어이고 "왜 그렇게 하는지"를 설명하는 톤이다. 변경 이력 서술("기존에는", "버그였다")은 넣지 마라.

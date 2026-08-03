# Lowend

유튜브 링크나 오디오 파일을 넣으면 **베이스 라인을 자동 채보**하고, 배속·악기별
부스트·탭 악보가 되는 연습 플레이어.

개인 학습·연습 목적. 상업화 계획 없음.

- 기획: [PRD.md](./PRD.md)
- 실측 확인된 라이브러리 API와 설치 함정: PRD 부록 A

## 상태

| 마일스톤 | 내용 | 상태 |
|---|---|---|
| M0 | 파이프라인 관통 (CLI) | 완료 |
| M1 | 오디오 엔진 + 스템 믹서 | 완료 |
| M2 | alphaTab 악보 + 커서 동기화 | 완료 |
| M3 | 웹 파이프라인 (FastAPI + SSE) | 완료 |
| M4 | 품질 게이트 + 평가 도구 | 완료 |

실시간 재생 체감(배속이 자연스러운지, 게인 조작에 클릭 노이즈가 없는지)은
헤드리스 브라우저로 검증할 수 없어 사람이 직접 들어봐야 한다.

## 실행

```bash
# 워커 (파이프라인)
cd apps/worker
../../.venv/Scripts/python -m uvicorn main:app --port 8000

# 웹
cd apps/web
npm run dev        # predev에서 sync-vendor가 자동 실행된다
```

http://localhost:3000 에서 링크를 넣거나 파일을 올리면 진행률이 실시간으로 뜨고,
끝나면 플레이어로 넘어간다.

CLI만 쓰려면:

```bash
python scripts/make_fixture.py                    # 테스트용 픽스처 생성
python scripts/run_pipeline.py data/_fixture/mix.wav
node tools/validate_alphatex.mjs data/{hash}/score.alphatex
python eval/run_eval.py data/{hash} data/_fixture/truth.json
```

## 측정 결과

합성 픽스처(120BPM 4/4 8마디, 정답 30음) 기준.

| 경로 | 노트 F1 | Precision | Recall | 품질 점수 |
|---|---|---|---|---|
| 베이스 단독 입력 (분리 생략) | **0.931** | 0.964 | 0.900 | — |
| 믹스 → Demucs → 채보 (전체) | **0.815** | 0.917 | 0.733 | 81 (good) |

두 경우 모두 온셋 오차 **0.0ms**, 비트 F-measure **1.000**, BPM·마디 수 정확.
MVP 목표(F1 ≥ 0.75) 통과.

### 병목은 채보가 아니라 스템 분리다

Demucs를 거치면서 **recall이 0.900 → 0.733으로 떨어진다.** 리듬·타이밍·양자화는
두 경우 모두 완벽하므로, 잃는 것은 음 자체다. 품질을 더 올리려면 채보
파라미터가 아니라 분리 모델을 손대야 한다 (PRD 5의 `python-audio-separator`
BS-RoFormer).

> 합성 신호 기준이라 **파이프라인 상한**이다. 실제 밴드 믹스는 더 어렵다.

## 구조

```
apps/
├── worker/                  # FastAPI + 파이프라인
│   ├── main.py              # 잡 API, SSE, 라이브러리
│   ├── jobs.py              # 오케스트레이션 (큐 없이 asyncio.to_thread)
│   └── pipeline/
│       ├── ingest/          # 수집 어댑터 (yt-dlp / 파일업로드)
│       ├── separate.py      # Demucs htdemucs 4스템
│       ├── beats.py         # beat_this (원본 믹스에 적용)
│       ├── transcribe.py    # basic-pitch (베이스 전용 파라미터)
│       ├── bassclean.py     # 배음 제거·단선율 강제·옥타브 보정
│       ├── quantize.py      # 비트 그리드 양자화 + 다운비트 위상 교정
│       ├── fretting.py      # 운지 배정 (자체 Viterbi DP)
│       ├── alphatex.py      # AlphaTex + sync 포인트 생성
│       └── quality.py       # 품질 게이트 3단계
└── web/                     # Next.js 16
    ├── lib/player/
    │   ├── engine.ts        # 8채널 단일 스트레처 오디오 그래프
    │   └── alphatab.ts      # 로더 + 외부 미디어 브리지
    └── components/player/   # 믹서·트랜스포트·악보·자체검증

eval/run_eval.py             # 노트 F1, 비트 F-measure
tools/validate_alphatex.mjs  # alphaTab 파서로 문법 검증
tools/probe_syntax.mjs       # AlphaTex 문법 탐침
tools/poc/stretch8.html      # 8채널 스트레처 PoC
```

## 설치

Python 3.12 + Node 24 + ffmpeg.

```bash
python -m venv .venv && .venv\Scripts\activate
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r apps/worker/requirements.txt

# basic-pitch / tuttut은 Python 3.12에서 의존성이 깨진다 (PRD 부록 A.1)
pip install basic-pitch==0.4.0 --no-deps
pip install tuttut==0.0.6 --no-deps

# 모델 사전 다운로드
python -c "from demucs.pretrained import get_model; get_model('htdemucs')"
python -c "from beat_this.inference import File2Beats; File2Beats(device='cpu')"

cd apps/web && npm install
```

## 스택

| 역할 | 라이브러리 | 라이선스 |
|---|---|---|
| 유튜브 추출 | yt-dlp | Unlicense |
| 스템 분리 | Demucs v4 (htdemucs) | MIT |
| 채보 | spotify/basic-pitch | Apache-2.0 |
| 비트 추적 | CPJKU/beat_this | MIT |
| 악보 렌더 | alphaTab | MPL-2.0 |
| 타임스트레치 | signalsmith-stretch | MIT |

`signalsmith-stretch`와 `@coderline/alphatab`은 **번들러를 태우면 안 된다.**
전자는 워크릿 코드를 함수 `toString()`으로 직렬화하고, 후자는 자체
Worker/AudioWorklet을 만들며 폰트를 상대경로로 찾는다. Turbopack용 공식
플러그인이 없어서 `scripts/sync-vendor.mjs`가 원본을 `public/vendor/`로
복사하고 런타임에 `turbopackIgnore`로 로드한다. 자세한 내용은
`apps/web/lib/player/engine.ts` 상단 주석.

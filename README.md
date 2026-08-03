# Lowend

유튜브 링크나 오디오 파일을 넣으면 **베이스 라인을 자동 채보**하고, 배속·악기별
부스트·탭 악보가 되는 연습 플레이어.

개인 학습·연습 목적. 상업화 계획 없음.

- 기획: [PRD.md](./PRD.md)
- 실측 확인된 라이브러리 API와 설치 이슈: PRD 부록 A

## 현재 상태

| 마일스톤 | 내용 | 상태 |
|---|---|---|
| M0 | 파이프라인 관통 (CLI) | **완료** |
| M1 | 오디오 엔진 (8채널 스트레처 + 스템 믹서) | 다음 |
| M2 | alphaTab 악보 + 커서 동기화 | 대기 |
| M3 | 웹 파이프라인 (FastAPI + SSE) | 대기 |
| M4 | 품질 게이트 + 골든셋 평가 | 부분 (eval 도구 완성) |

### M0 결과

합성 픽스처(120BPM 4/4 8마디, 정답 30음)로 전 구간 관통 + 정량 평가.

```
$ python scripts/run_pipeline.py data/_fixture/bass_only.wav \
      --skip-separate --beat-source data/_fixture/mix.wav

[transcribe] 60 note events
[bassclean]  60 -> 29  (배음 25, 겹침 3, 병합 3)
[quantize]   29 -> 28 in 8 bars, 4/4, phase=0 (다운비트 위상 교정됨), 잔차 0.113
[fretting]   standard [43,38,33,28]: 28 notes, 연주불가 0

   G ||----------------|----------------|----------------|----------------|
   D ||----------------|----------------|----------------|0---------------|
   A ||------------00--|0---0---2---3---|------------0---|----3---2---0---|
   E ||0-------3-------|----------------|0-------3-------|----------------|
```

```
$ node tools/validate_alphatex.mjs data/{hash}/score.alphatex
PARSE OK   bars=8  notes=28  time sig=4/4  syncPoints=8
           staff tuning=[28, 33, 38, 43]
```

### 두 경로 비교 — 병목은 채보가 아니라 스템 분리다

| 경로 | 노트 F1 | Precision | Recall | 처리시간 |
|---|---|---|---|---|
| 베이스 단독 입력 (분리 생략) | **0.931** | 0.964 | 0.900 | 4.4s |
| 믹스 → Demucs → 채보 (전체) | **0.778** | 0.875 | 0.700 | 32.3s |

둘 다 MVP 목표(F1 ≥ 0.75)를 넘겼다. 하지만 **Demucs를 거치면서 recall이
0.900 → 0.700으로 떨어진다.** 온셋 오차는 두 경우 모두 0.0ms, 비트 F-measure는
1.000, BPM·마디 수도 정확하다.

즉 리듬·타이밍·양자화는 이미 정확하고, 잃는 것은 **음 자체**다. 품질을 더
올리려면 채보 파라미터가 아니라 **분리 모델**을 손대야 한다
(PRD 5의 대안: `python-audio-separator`의 BS-RoFormer).

> 합성 신호 기준이라 **파이프라인 상한**이다. 실제 밴드 믹스는 더 어렵다.

## 설치

Python 3.12 + ffmpeg 필요.

```bash
python -m venv .venv
.venv\Scripts\activate

pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install demucs beat-this yt-dlp fastapi "uvicorn[standard]" mir_eval pretty_midi soundfile

# basic-pitch / tuttut은 Python 3.12에서 의존성이 깨진다 (PRD 부록 A.1)
pip install basic-pitch --no-deps
pip install onnxruntime librosa resampy scikit-learn typing-extensions
pip install tuttut --no-deps
pip install networkx matplotlib
```

모델 사전 다운로드:

```bash
python -c "from demucs.pretrained import get_model; get_model('htdemucs')"
python -c "from beat_this.inference import File2Beats; File2Beats(device='cpu')"
```

## 구조

```
apps/worker/pipeline/
├── ingest/          # 수집 어댑터 (yt-dlp / 파일업로드)
├── separate.py      # Demucs htdemucs 4스템 분리
├── beats.py         # beat_this 비트·다운비트 (원본 믹스에 적용)
├── bassclean.py     # 배음 제거·단선율 강제·옥타브 보정
├── quantize.py      # 비트 그리드 양자화          (미구현)
├── fretting.py      # tuttut 운지 배정            (미구현)
└── alphatex.py      # AlphaTex + \sync 생성       (미구현)
```

## 스택

| 역할 | 라이브러리 | 라이선스 |
|---|---|---|
| 유튜브 추출 | yt-dlp | Unlicense |
| 스템 분리 | Demucs v4 (htdemucs) | MIT |
| 채보 | spotify/basic-pitch | Apache-2.0 |
| 비트 추적 | CPJKU/beat_this | MIT |
| MIDI→탭 | natecdr/tuttut | MIT |
| 악보 렌더 | alphaTab | MPL-2.0 |
| 타임스트레치 | signalsmith-stretch | MIT |

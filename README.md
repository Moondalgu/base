# Lowend

유튜브 링크나 오디오 파일을 넣으면 **베이스 라인을 자동 채보**하고, 배속·악기별
부스트·탭 악보가 되는 연습 플레이어.

개인 학습·연습 목적. 상업화 계획 없음.

- 기획: [PRD.md](./PRD.md)
- 실측 확인된 라이브러리 API와 설치 이슈: PRD 부록 A

## 현재 상태

| 마일스톤 | 내용 | 상태 |
|---|---|---|
| M0 | 파이프라인 관통 (CLI) | 진행 중 — 채보·운지 체인 검증 완료 |
| M1 | 오디오 엔진 (8채널 스트레처 + 스템 믹서) | 대기 |
| M2 | alphaTab 악보 + 커서 동기화 | 대기 |
| M3 | 웹 파이프라인 (FastAPI + SSE) | 대기 |
| M4 | 품질 게이트 + 골든셋 평가 | 대기 |

### 검증된 것

`scripts/smoke_transcribe.py` — 합성 베이스 라인 8음으로 채보→운지 체인 검증.

```
basic-pitch 원본:  29개 이벤트 (배음이 별도 음으로 검출)
bassclean 후:      8개, 정답과 100% 일치

G ||--------------------|--------------|
D ||--------------------|--------------|
A ||---------0----2-----|-----0--------|
E ||0---3-------------0-|3---------0---|
```

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

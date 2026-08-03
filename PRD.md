# PRD — 베이스 자동 채보 연습 플레이어 (가칭 **Lowend**)

| 항목 | 내용 |
|---|---|
| 문서 ID | PRD-LOWEND-001 |
| 버전 | 1.2.0 |
| 작성일 | 2026-08-03 |
| 상태 | draft |
| 작성자 | Finn(문정민) |
| 용도 | **개인 학습·연습 목적. 상업화 계획 없음** |

---

## 1. Context — 왜 만드는가

Songsterr를 웹앱 레벨에서 실측 분석한 결과 두 가지가 확인됐다.

**첫째, 커버리지가 구조적 한계다.** Songsterr의 100만 탭은 전부 사람이 만든 것이다. 인기 서구 록/메탈에 편중되고 K-pop·국내 인디는 사실상 없다. 유저가 찾는 곡이 없으면 그 서비스는 존재하지 않는 것과 같다.

**둘째, 원가 구조에 빈틈이 있다.** Songsterr의 유료 기능(배속·솔로·백킹트랙)은 서버에서 미리 인코딩한 오디오 파일이다 — 속도 2종(100%/50%) × 모드 3종(full/solo/minus) × 트랙 수. 5트랙 곡이면 30개 파일 약 90MB. 스토리지 원가가 실제로 붙기 때문에 유료이고, 그래서 속도가 두 종류뿐이다. **스템을 클라이언트에서 실시간 믹싱하면 같은 기능이 원가 0이 되고 연속 가변이 된다.**

그래서 만들려는 것: **유튜브 링크나 오디오 파일을 넣으면 자동으로 스템을 분리하고 베이스를 채보해서, 배속·악기별 부스트·베이스 탭이 되는 연습 플레이어.**

커버리지는 무한, 정확도는 사람 채보보다 낮다. 이 트레이드오프가 제품의 정체성이고, 숨기지 않고 설계에 반영한다.

### 1.1 왜 베이스 전용인가

악기를 하나로 좁히는 것은 타협이 아니라 **이 파이프라인이 실제로 잘 동작하는 유일한 구간을 고른 것**이다. 근거 네 가지:

1. **htdemucs에 bass는 전용 고품질 스템이다.** 4스템 구성은 drums / **bass** / vocals / other. 기타는 스템이 아예 없어서 신스·키보드·스트링과 함께 `other`에 뭉친다. 베이스만 유일하게 깨끗이 분리된다.
2. **베이스는 단선율이다.** basic-pitch 공식 문서는 "악기당 하나씩 처리할 때 가장 잘 작동"한다고 명시한다. 다성 기타 코드가 정확도가 무너지는 지점인데, 베이스는 그 문제 자체가 없다.
3. **운지 탐색 공간이 작다.** 4현 × 주로 낮은 포지션 → tuttut의 Viterbi 탐색이 훨씬 안정적이고, 오답이 나와도 연주 가능한 오답이다.
4. **수요가 실제로 거기 있다.** Songsterr 실측 데이터 — "Master of Puppets"의 트랙별 조회수는 **베이스 292,648 vs 리드기타 28,831**. 베이스는 10배 더 많이 보는데 공급은 압도적으로 적다.

기타 지원은 **범위 밖**이다.

### 1.2 참고 — 유사 서비스

| 서비스 | 기능 | 베이스 관점 한계 |
|---|---|---|
| Songsterr | 사람 채보 탭 + 재생 | 커버리지 편중. 있는 곡은 최고, 없는 곡은 없음 |
| Moises.ai | 스템분리 + 코드감지 + 배속 | **탭 미생성** — 연습 도구일 뿐 악보가 없음 |
| Audio2guitar | 탭 + 코드 + 가사 | 기타 중심 |
| Klangio | 탭 + 스템 + 비트 + 코드 | 무료는 20초 미리보기 |

만들려는 자리: **"내가 원하는 곡의 베이스 라인을, 연습 도구까지 붙여서."**

---

## 2. 목표 / 비목표

### 2.1 목표
1. 오디오 소스 하나로 **베이스 연습 가능한 상태**를 만든다: 배속·악기 부스트·베이스 탭·재생 커서.
2. 자동 채보가 실패해도 **연습 도구는 항상 동작**한다 (스템 플레이어 단독으로도 가치가 있다).
3. 로컬 CPU에서 전 구간이 실제로 돌아간다.

### 2.2 비목표 (Non-goals)
- **기타·드럼·건반 채보** — 베이스 외 악기는 재생/부스트만 지원하고 채보하지 않는다
- **5현 베이스** — 4현만 지원
- 사람 수준의 채보 정확도
- 주법 표기 (슬랩/팝, 고스트 노트, 해머온/풀오프, 슬라이드) — 4.8 참조
- 탭 편집기 / UGC 커뮤니티 / 리비전 관리
- 모바일 앱
- 실시간(스트리밍) 처리
- 악보 인쇄 / GP·MusicXML 내보내기 (P2)
- **상업화 / 외부 서비스 공개**

---

## 3. 확정된 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| 용도 | **개인 학습·연습. 상업화 없음** | 라이선스·법적 제약이 크게 완화됨 (10 참조) |
| 수집 방식 | 어댑터 패턴 (yt-dlp + 파일업로드) | 구조가 깔끔하고 비용이 없어서 유지. 정책 게이팅은 불필요 |
| 채보 대상 | **베이스 단일 트랙, 4현** | 1.1 |
| 재생 대상 | 스템 4종 전부 (drums/bass/vocals/other) | 채보는 베이스만, 믹싱은 전체 |
| 실행 환경 | 로컬 CPU (Windows 11, Python 3.12) | |
| 스택 | Next.js(App Router)+TS / FastAPI+Python | |

---

## 4. 기술 결정과 근거

### 4.1 멀티채널 단일 스트레처 (핵심 아키텍처)

스템 4개 × 2ch = **8채널을 signalsmith-stretch 한 인스턴스**에 통과시킨다.

```
[8ch AudioBuffer — 스템 인터리브]
        ↓
[SignalsmithStretch AudioWorkletNode]   ← 속도·피치를 여기서 한 번만
        ↓
[ChannelSplitter(8)]
   ├─ ch0,1 → Gain(drums)  ─┐
   ├─ ch2,3 → Gain(bass)   ─┤   ← 베이스 부스트가 이 제품의 주 용도
   ├─ ch4,5 → Gain(vocals) ─┼→ [ChannelMerger] → destination
   └─ ch6,7 → Gain(other)  ─┘
```

얻는 것:
- 스트레처가 하나라서 **스템 간 드리프트가 구조적으로 불가능**
- Songsterr가 서버에 3벌씩 렌더링하던 full/solo/minus가 **0~200% 연속 게인**으로 대체
- 속도가 100/50 두 종류가 아니라 **연속 가변**
- 베이시스트 프리셋이 공짜로 나온다: **"베이스만"**(카피), **"베이스 빼고"**(minus-one 연습), **"베이스+드럼"**(리듬 섹션)

### 4.2 alphaTab은 렌더러 + 커서로만 쓴다

alphaTab 1.6+ **External Media Control API**:
- `IExternalMediaHandler`: `backingTrackDuration`, `playbackRate`(get/set), `masterVolume`, `seekTo()`, `play()`, `pause()`
- 위치 주입: `(api.player.output as IExternalMediaSynthOutput).updatePosition(ms)` — 공식 문서상 **50ms 주기면 빠른 곡도 커서 추종**
- 내장 신디사이저 alphaSynth는 **끈다**. 소리는 100% 우리 스템 플레이어가 낸다.
- alphaTab은 피치 조정을 지원하지 않으므로 배속/피치는 signalsmith 전담

> **Songsterr보다 유리한 지점**: Songsterr는 사람이 만든 탭을 제3자 YouTube 영상에 수동 정렬해야 해서 `video-points`를 사람이 찍는다. 우리는 악보와 오디오를 **같은 소스에서 생성**하므로 싱크가 원리적으로 정확하다.

### 4.3 산출물은 AlphaTex 텍스트 한 개

음표 + 튜닝 + 박자/템포 + `\sync` 포인트를 한 파일에 담는다. MusicXML/GuitarPro 중간 변환을 건너뛴다.

- sync 문법: `\sync (barIndex occurence millisecondOffset ratioPosition)`
- **다운비트마다 1개**씩 발행 (마디 단위). 50ms 커서 갱신 기준 충분하고, 비트마다 찍으면 파일만 커진다.
- 마디 내 템포 분산이 10% 초과면 마디 중간에 추가 발행

### 4.4 비트 그리드 양자화 (생략 불가)

basic-pitch는 초 단위 온셋을 낸다. 그리드 스냅 없이는 32분음표 쓰레기가 나온다.

| 단계 | 처리 | 기본값 |
|---|---|---|
| 1 | beat_this → `beats[]`, `downbeats[]` (**원본 믹스에 적용**) | `File2Beats(checkpoint_path="final0", device="cpu")` |
| 2 | 다운비트 간 비트 수 → 박자표 추론 | 4개→4/4, 3개→3/4 |
| 3 | 비트를 N등분해 그리드 생성 | N=4 (16분음표). 스윙 감지 시 3 |
| 4 | 노트 온셋을 최근접 그리드에 스냅 | 잔차 > 그리드 간격의 50% → 저신뢰 플래그 |
| 5 | 듀레이션 양자화 | 최소 1/16 |
| 6 | 노이즈 제거 | 길이 < 60ms 또는 진폭 하위 임계 미만 → 폐기 |
| 7 | 마디별 로컬 BPM | `60 / median(비트 간격)` → alphaTex 템포 오토메이션 |

> 비트 추적은 **베이스 스템이 아니라 원본 믹스**에 돌린다. 드럼이 있어야 비트가 잡힌다.

### 4.5 베이스 특화 후처리

단선율 전제를 살린 정리 단계. 기타였다면 못 하는 것들이다.

| 규칙 | 내용 |
|---|---|
| 단선율 강제 | 동시 발음 노트가 검출되면 진폭이 큰 것만 남긴다 |
| 옥타브 오류 보정 | 베이스 음역(E1 41.2Hz ~ G4 392Hz) 밖 노트는 옥타브 접기 또는 폐기 |
| 주파수 범위 제한 | basic-pitch `minimum_frequency=35`, `maximum_frequency=450` 지정 |
| 지속음 병합 | 같은 피치가 그리드 1칸 이내 간격으로 연속되면 타이로 병합 |

### 4.6 운지 배정

**tuttut** (MIT, HMM + Viterbi, 프렛보드를 완전그래프로 모델링).

| 항목 | MVP | 이후 |
|---|---|---|
| 튜닝 기본값 | 4현 `E A D G` = MIDI `[43, 38, 33, 28]` | — |
| 대체 튜닝 | Drop D `[43, 38, 33, 26]` 선택 제공 | 자동 감지 (P2) |
| 포지션 선호 | 낮은 포지션 + 개방현 가중 | 유저 선호 설정 (P2) |
| 카포 | 미지원 (베이스는 사실상 불필요) | — |

배제: `open-fret` — 커밋 7개·스타 5개·가중치 미배포·CPU 추론 로드맵 상태로 부적합.

### 4.7 품질 게이트 — 실패를 설계에 넣는다

복합 신뢰도 점수(0~100)를 산출한다.

| 구성요소 | 산출 방식 |
|---|---|
| 채보 신뢰도 | basic-pitch 노트 confidence 평균 |
| 비트 안정성 | 비트 간격 표준편차 |
| 양자화 잔차 | 평균 \|온셋 − 스냅위치\| / 그리드 간격 |
| 밀도 이상치 | 마디당 노트 수 분포의 이상치 비율 |
| 음역 이탈률 | 베이스 음역 밖으로 검출돼 폐기된 노트 비율 |

| 점수 | 상태 | UX |
|---|---|---|
| ≥ 70 | 좋음 | 악보 정상 노출 |
| 40–69 | 참고용 | 악보 노출 + "자동 생성된 악보입니다" 배너 |
| < 40 | 채보 실패 | **악보 숨김. 스템 플레이어는 그대로 동작** |

**핵심**: 채보가 실패해도 배속·베이스 부스트·솔로/뮤트는 전부 살아있다.

### 4.8 주법을 표기하지 않는 이유 (명시적 결정)

슬랩/팝, 고스트 노트, 해머온/풀오프, 슬라이드는 베이스 탭의 핵심 정보다. 하지만 basic-pitch는 **피치와 온셋만** 낸다 — 주법 정보가 원리적으로 없다.

억지로 추정하면 틀린 주법을 자신 있게 표기하게 되고, 이건 정보가 없는 것보다 나쁘다. **MVP는 음정과 리듬만 정확히 주고 주법은 비운다.** 이 한계를 UI에 명시한다.

---

## 5. 오픈소스 스택

개인 학습 용도이므로 라이선스 제약이 없다. 그럼에도 **유지보수 활성도와 성숙도** 기준으로 선정했다.

| 역할 | 라이브러리 | 라이선스 | 선정 이유 |
|---|---|---|---|
| 유튜브 추출 | **yt-dlp** | Unlicense | 사실상 표준. ffmpeg 연동 |
| 스템 분리 | **Demucs v4 (htdemucs)** | MIT (코드+가중치) | **bass 전용 스템 제공 — 이 제품의 전제**. CPU ≈ 길이×1.5, RAM 3GB+ |
| 채보 | **spotify/basic-pitch** | Apache-2.0 | 다성 + 피치벤드. Windows는 ONNX 런타임 |
| 비트/다운비트 | **CPJKU/beat_this** | MIT | ISMIR 2024. DBN 후처리 불필요, madmom보다 설치가 단순 |
| MIDI→탭 | **natecdr/tuttut** | MIT | HMM+Viterbi, 튜닝 커스터마이즈 |
| 악보 렌더 | **alphaTab** | MPL-2.0 | Bravura 폰트 + SF2 번들 포함. **React 통합 없음 → DOM 직접 매핑** |
| 타임스트레치 | **signalsmith-stretch** | MIT | WASM + AudioWorkletProcessor, 멀티채널 |
| 평가 | mir_eval, pretty_midi | MIT | 골든셋 회귀용 |

**대안으로 남겨둔 것** (상업화 제약이 없으므로 언제든 교체 가능):
- `madmom` — 비트 추적. 모델이 CC BY-NC-SA지만 비상업 용도라 사용 가능. beat_this가 안 맞으면 전환
- `python-audio-separator` — UVR의 BS-RoFormer 모델. Demucs보다 분리 품질이 높다는 벤치마크가 있음
- `Rubber Band` (GPL) — signalsmith 품질이 부족하면 교체 가능

---

## 6. 시스템 설계

### 6.1 파이프라인

```
[입력] YouTube URL │ 오디오 파일
   ↓ IngestionAdapter (yt-dlp │ upload)          ~30s │ 즉시
[원본 오디오 wav 44.1kHz stereo]
   ├──────────────────────────────┐
   ↓ Demucs htdemucs              ↓ beat_this (원본 믹스)   7.5분 │ 20s
[스템 4종]                    [beats[], downbeats[]]
   ├→ opus 인코딩 → 프론트 재생용 (4종 전부)
   ↓ bass 스템만
   ↓ basic-pitch (35~450Hz 제한)                          40s
[MIDI 노트: 온셋/듀레이션/피치/confidence]
   ↓ 베이스 후처리 (4.5)                                  <1s
   ↓ 양자화 (4.4의 7단계)                                 <1s
[마디·박자·음표길이가 붙은 노트]
   ↓ tuttut (HMM+Viterbi, 4현 EADG)                       <5s
[string/fret 배정 완료]
   ↓ AlphaTex 생성기 (+ \sync)                            <1s
[score.alphatex + manifest.json]
```

5분 곡 CPU 기준 총 **약 9~10분**. Demucs가 전체의 80%.

### 6.2 저장소 구조

```
lowend/
├── apps/
│   ├── web/                        # Next.js (App Router, TS)
│   │   ├── app/
│   │   │   ├── page.tsx            # 입력 (URL/업로드)
│   │   │   ├── play/[hash]/page.tsx
│   │   │   └── api/                # 프록시만
│   │   ├── components/
│   │   │   ├── player/
│   │   │   │   ├── StemMixer.tsx   # 4스템 게인 + 프리셋
│   │   │   │   ├── SpeedControl.tsx
│   │   │   │   └── engine.ts       # Web Audio 그래프
│   │   │   └── score/
│   │   │       └── AlphaTabView.tsx
│   │   └── next.config.ts          # alphaTab 번들러 설정
│   └── worker/                     # FastAPI + 파이프라인
│       ├── main.py
│       ├── pipeline/
│       │   ├── ingest/
│       │   │   ├── base.py         # IngestionAdapter ABC
│       │   │   ├── ytdlp.py
│       │   │   └── upload.py
│       │   ├── separate.py         # Demucs
│       │   ├── beats.py            # beat_this
│       │   ├── transcribe.py       # basic-pitch
│       │   ├── bassclean.py        # 4.5 베이스 후처리
│       │   ├── quantize.py         # 4.4
│       │   ├── fretting.py         # tuttut
│       │   └── alphatex.py         # 생성기
│       ├── jobs.py
│       ├── schema.py               # Pydantic
│       └── requirements.txt
├── eval/
│   ├── golden/                     # 베이스 골든셋 메타
│   └── run_eval.py                 # mir_eval 회귀
└── data/                           # 캐시 (gitignore)
    └── {contentHash}/
        ├── source.wav
        ├── stems/{drums,bass,vocals,other}.opus
        ├── beats.json
        ├── notes.json
        ├── score.alphatex
        └── manifest.json
```

### 6.3 잡 처리 — 큐 없이 시작한다

Celery/Redis를 도입하지 않는다. 로컬 단일 사용자에 과하다.

- `asyncio.to_thread()`로 CPU 바운드 단계 실행 (torch가 GIL을 놓으므로 이벤트 루프가 살아있음)
- 잡 상태는 `data/{hash}/manifest.json`에 기록 — 프로세스 재시작에도 생존
- 진행률은 **SSE**로 스트리밍

### 6.4 캐시 키

`contentHash = sha256(youtube_video_id)` 또는 `sha256(업로드 파일 바이트)`.
동일 소스 재요청 시 파이프라인 전체 스킵. 튜닝만 바꾸면 운지 배정부터 재실행.

### 6.5 API

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | `/api/jobs` | `{source:{type:"youtube"\|"upload", url?, file?}, tuning?:"standard"\|"dropD"}` | `{jobId, contentHash, cached:bool}` |
| GET | `/api/jobs/{id}/events` | — | SSE: `{stage, progress, message}` / `[DONE]` |
| GET | `/api/jobs/{id}` | — | `manifest.json` |
| GET | `/api/artifacts/{hash}/stems/{name}.opus` | — | audio/ogg (Range 지원) |
| GET | `/api/artifacts/{hash}/score.alphatex` | — | text/plain |

### 6.6 manifest.json 스키마

```jsonc
{
  "contentHash": "a3f2…",
  "schemaVersion": 1,
  "source": { "type": "youtube", "id": "…", "title": "…", "durationSec": 312 },
  "status": "done",              // queued|running|done|failed
  "stages": {
    "ingest":     { "status": "done", "ms": 28400 },
    "separate":   { "status": "done", "ms": 451000 },
    "beats":      { "status": "done", "ms": 19800 },
    "transcribe": { "status": "done", "ms": 39100 },
    "bassclean":  { "status": "done", "ms": 340 },
    "quantize":   { "status": "done", "ms": 620 },
    "fretting":   { "status": "done", "ms": 4300 },
    "alphatex":   { "status": "done", "ms": 180 }
  },
  "stems": ["drums", "bass", "vocals", "other"],
  "instrument": "bass",
  "tuning": { "preset": "standard", "midi": [43, 38, 33, 28], "strings": 4 },
  "tempo": { "medianBpm": 122.4, "variance": 0.03 },
  "timeSignature": [4, 4],
  "barCount": 96,
  "noteCount": 412,
  "quality": {
    "score": 74,
    "level": "good",              // good|reference|failed
    "components": {
      "transcriptionConfidence": 0.81,
      "beatStability": 0.94,
      "quantizationResidual": 0.12,
      "densityOutlierRatio": 0.04,
      "outOfRangeRatio": 0.02
    }
  }
}
```

### 6.7 프론트엔드 오디오 엔진

> API는 부록 A.5에서 실측 확인했다. 아래는 검증된 형태다.

```ts
// components/player/engine.ts
const ctx = new AudioContext();
const stretch = await SignalsmithStretch(ctx, {
  numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [8],
});
await stretch.addBuffers(stemChannels);   // Float32Array 8개 (스템4 × 스테레오2)

const splitter = ctx.createChannelSplitter(8);
const merger   = ctx.createChannelMerger(2);
stretch.connect(splitter);

STEMS.forEach((name, i) => {              // drums, bass, vocals, other
  const g = ctx.createGain();             // 0.0 ~ 2.0 (부스트)
  splitter.connect(g, i * 2);
  splitter.connect(g, i * 2 + 1);
  g.connect(merger, 0, 0); g.connect(merger, 0, 1);
  gains[name] = g;
});
merger.connect(ctx.destination);

// 속도·피치·루프는 전부 schedule() 하나로
stretch.schedule({ output: ctx.currentTime, active: true, input: 0,
                   rate: 0.5, semitones: 0 });
stretch.start();

// alphaTab에 위치만 주입 (소리는 내지 않음)
setInterval(() => {
  (api.player.output as IExternalMediaSynthOutput)
    .updatePosition(stretch.inputTime * 1000);
}, 50);
```

---

## 7. 기능 요구사항

### 7.1 수집 (Ingestion)

| ID | 기능 | 설명 | 우선순위 | 수용 기준 |
|---|---|---|---|---|
| ING-01 | 어댑터 인터페이스 | `IngestionAdapter` ABC — `fetch(source) -> Path` | P0 | 어댑터 추가 시 파이프라인 코드 무수정 |
| ING-02 | 유튜브 어댑터 | yt-dlp로 bestaudio 추출 → wav 44.1k 변환 | P0 | 5분 영상 60초 이내 wav 생성 |
| ING-03 | 업로드 어댑터 | mp3/wav/m4a/flac 수용, 최대 100MB | P0 | 동일 파일 재업로드 시 캐시 히트 |
| ING-04 | 길이 제한 | 10분 초과 거부 | P1 | 초과 시 명확한 안내 메시지 |

### 7.2 파이프라인

| ID | 기능 | 설명 | 우선순위 | 수용 기준 |
|---|---|---|---|---|
| PIP-01 | 스템 분리 | htdemucs 4스템 | P0 | 5분 곡 CPU 8분 이내, 스템 4개 생성 |
| PIP-02 | 비트 추적 | beat_this를 **원본 믹스**에 적용 | P0 | 골든셋 비트 F-measure ≥ 0.85 (70ms 허용) |
| PIP-03 | 채보 | bass 스템에 basic-pitch (35~450Hz) | P0 | 노트 이벤트 + confidence 반환 |
| PIP-04 | 베이스 후처리 | 단선율 강제 / 옥타브 보정 / 지속음 병합 | P0 | 출력에 동시 발음 노트 0건, 음역 이탈 0건 |
| PIP-05 | 양자화 | 4.4의 7단계 | P0 | 출력 노트가 전부 그리드 위. 잔차 통계 manifest 기록 |
| PIP-06 | 운지 배정 | tuttut, 4현 EADG 기본 | P0 | 모든 노트에 string/fret 배정, 프렛 범위 이탈 0건 |
| PIP-07 | Drop D 지원 | 튜닝 프리셋 선택 | P1 | 선택 시 운지가 해당 튜닝으로 재계산 |
| PIP-08 | AlphaTex 생성 | 음표+튜닝+템포+`\sync` | P0 | alphaTab이 에러 없이 렌더 |
| PIP-09 | 캐시 | contentHash 기반 스킵 | P0 | 동일 소스 2회차 5초 이내 응답 |
| PIP-10 | 부분 재실행 | 튜닝 변경 시 운지부터 | P1 | 스템·비트·채보 재계산 안 함 |
| PIP-11 | SSE 진행률 | 단계별 스트리밍 | P0 | 각 단계 시작/종료가 1초 이내 클라이언트 반영 |

### 7.3 플레이어

| ID | 기능 | 설명 | 우선순위 | 수용 기준 |
|---|---|---|---|---|
| PLY-01 | 스템 재생 | 8채널 단일 스트레처 → 스템별 게인 | P0 | 4스템 동시 재생, 드리프트 0 |
| PLY-02 | 배속 | 25~200% 연속, 피치 유지 | P0 | 50% 재생 시 음정 변화 없음. 슬라이더 조작 중 끊김 없음 |
| PLY-03 | 스템 부스트 | 스템별 0~200% 게인 | P0 | 슬라이더 즉시 반영, 클릭 노이즈 없음 |
| PLY-04 | 솔로 / 뮤트 | 스템별 토글 | P0 | 솔로 시 나머지 게인 0 |
| PLY-05 | **베이시스트 프리셋** | 베이스만 / 베이스 빼고 / 베이스+드럼 | P0 | 원클릭으로 게인 조합 적용 |
| PLY-06 | 구간 반복 | 마디 단위 A-B 루프 | P1 | 루프 경계에서 끊김·클릭 없음 |
| PLY-07 | 피치 시프트 | ±12 반음 | P1 | `setTransposeSemitones()` 반영 |
| PLY-08 | 메트로놈 | 비트 그리드 기반 클릭 | P2 | 다운비트 강세 구분 |

### 7.4 악보

| ID | 기능 | 설명 | 우선순위 | 수용 기준 |
|---|---|---|---|---|
| SCR-01 | 베이스 탭 렌더 | alphaTab으로 AlphaTex 렌더 (4현) | P0 | 96마디 곡이 2초 이내 렌더 |
| SCR-02 | 커서 동기화 | `updatePosition()` 50ms 주기 | P0 | 120BPM 곡에서 커서 오차 ±100ms 이내 |
| SCR-03 | 배속 연동 | 배속 변경이 커서에 반영 | P0 | 50% 재생 시 커서도 절반 속도 |
| SCR-04 | 클릭 탐색 | 악보 클릭 → 해당 위치 재생 | P0 | `seekTo()` 왕복 동작 |
| SCR-05 | 자동 스크롤 | 커서 따라 뷰포트 이동 | P1 | 커서가 항상 화면 내 |
| SCR-06 | 품질 배너 | 40~69점 시 경고 노출 | P0 | 4.7 기준대로 분기 |
| SCR-07 | 튜닝 표시 | 현별 튜닝 노출 | P1 | manifest tuning 반영 |
| SCR-08 | 주법 미표기 고지 | "슬랩·고스트노트 등 주법은 표기되지 않습니다" | P0 | 악보 영역에 상시 노출 |

### 7.5 품질 게이트

| ID | 기능 | 설명 | 우선순위 | 수용 기준 |
|---|---|---|---|---|
| QLT-01 | 점수 산출 | 4.7의 5개 구성요소 복합 | P0 | manifest에 점수+구성요소 전부 기록 |
| QLT-02 | 3단계 분기 | good / reference / failed | P0 | failed 시 악보 숨김, **플레이어는 정상 동작** |
| QLT-03 | 실패 안내 | 사유를 사람 말로 | P1 | "이 곡은 베이스가 다른 악기에 묻혀서 악보를 만들지 못했어요" 수준 |

---

## 8. 비기능 요구사항

| 항목 | 목표 (로컬 CPU) |
|---|---|
| 5분 곡 전체 처리 | 10분 이내 |
| 캐시 히트 응답 | 5초 이내 |
| 플레이어 초기 로딩 | 스템 로딩 포함 10초 이내 |
| 배속 변경 반응 | 200ms 이내 무중단 |
| 동시 잡 | 1건 (직렬) |
| 브라우저 | Chrome/Edge 최신 2버전 (AudioWorklet + WASM 필수) |
| 디스크 | 곡당 약 60MB |

---

## 9. 성공 지표 (품질)

**골든셋 20곡 — 전부 베이스 기준 정답 보유.** 구성:
- 라인이 명확한 록/펑크 8곡
- 베이스가 묻히는 밀집 믹스 4곡 (하드 케이스)
- 템포 변화 있는 곡 3곡
- K-pop / 국내 인디 3곡
- 클린 솔로 베이스 녹음 2곡 (상한 측정)

| 지표 | 도구 | 목표 | 비고 |
|---|---|---|---|
| 노트 F1 | mir_eval, 온셋 허용 50ms | **≥ 0.75** | 단선율 + 전용 스템이라 기타보다 높게 잡을 수 있다 |
| 노트 F1 (클린 솔로) | 동일 | ≥ 0.90 | 파이프라인 상한 확인용 |
| 노트 F1 (밀집 믹스) | 동일 | ≥ 0.50 | 하한 확인용. 품질 게이트 검증 대상 |
| 비트 F-measure | mir_eval, 허용 70ms | ≥ 0.85 | |
| 탭 정확도 | string/fret 완전일치 | ≥ 0.85 (노트 F1로 정규화) | 4현은 탐색공간이 작아 높아야 정상 |
| 커서 동기화 오차 | 수동 계측 | ±100ms 이내 | |
| 품질 게이트 적중률 | 사람 판정 대비 | ≥ 0.80 | "쓸 만함/아님" 판정이 점수와 일치하는 비율 |

**회귀 테스트**: 파이프라인 변경 시 골든셋 자동 실행. 노트 F1이 3%p 이상 하락하면 실패.

---

## 10. 리스크 및 대응

개인 학습 용도이므로 상업 서비스였다면 가장 컸을 리스크(라이선스·ToS·저작권)가 대부분 완화된다.

| 리스크 | 성격 | 심각도 | 대응 |
|---|---|---|---|
| **밀집 믹스에서 베이스 검출 실패** | 제품 | 중간 | 베이스는 전용 스템이 있어 유리하지만, 신스베이스·808·저역 과밀 믹스는 여전히 어렵다. 품질 게이트 3단계로 방어하고, **채보 실패해도 플레이어는 동작** |
| **주법 정보 부재로 인한 체감 품질** | 제품 | 중간 | 슬랩 곡에서 음정만 맞고 뉘앙스가 없으면 "틀린 것처럼" 느껴질 수 있다. UI에 상시 고지(SCR-08) |
| **Next.js Turbopack + alphaTab** | 빌드 | 중간 | alphaTab이 WebWorker/AudioWorklet 생성 → 공식 플러그인은 Webpack/Vite만. **폴백: `next dev --webpack`** |
| **signalsmith 8채널 실증 미확인** | 기술 | 중간 | 문서상 `outputChannelCount` 설정 가능하나 8채널 실동작 미검증. **M1 첫 작업으로 PoC.** 실패 시 폴백: 스템별 스트레처 4개 + 동일 파라미터 동기 구동 |
| **CPU 처리 시간 10분** | UX | 낮음 | 개인 용도라 감내 가능. SSE 진행률로 체감 완화 |
| **채보 품질이 목표 F1 미달** | 전략 | 중간 | 대안 스택으로 교체 (5의 "대안으로 남겨둔 것"). 특히 `python-audio-separator`의 BS-RoFormer |
| **YouTube 다운로드** | 법적 | 낮음 | 개인 학습 목적·비공개·비상업. 외부 배포하지 않는다는 전제가 유지되는 한 실질 리스크 낮음 |

---

## 11. 마일스톤

각 단계는 **눈으로 확인 가능한 완료 조건**을 갖는다.

### M0 — 파이프라인 관통 (웹 없음)
CLI로 `python -m pipeline run song.wav` 실행 시 `score.alphatex` 생성.
**완료 조건**: 생성된 AlphaTex를 alphaTab Playground에 붙여넣어 베이스 탭이 렌더된다. 아는 곡으로 돌려서 "대충 맞다"가 확인된다.

### M1 — 오디오 엔진
8채널 단일 스트레처 PoC → 스템 믹서 UI + 베이시스트 프리셋.
**완료 조건**: 악보 없이도 배속·베이스 부스트·베이스 빼고 듣기가 되는 연습 도구로 쓸 만하다.

### M2 — 악보 + 커서
alphaTab 렌더 + External Media 동기화.
**완료 조건**: 120BPM 곡을 50% 배속으로 재생할 때 커서가 음과 맞는다.

### M3 — 웹 파이프라인
FastAPI 잡 + SSE + 캐시 + 업로드/유튜브 어댑터.
**완료 조건**: 브라우저에서 링크 붙여넣고 기다리면 플레이어가 뜬다.

### M4 — 품질 게이트 + 평가
베이스 골든셋 20곡 + mir_eval 회귀 + 3단계 분기.
**완료 조건**: 노트 F1 ≥ 0.75 달성.

---

## 12. 오픈 이슈

1. 서비스명 미정 (Lowend는 가칭)
2. 튜닝 자동 감지 방식 미정 (P2)
3. 골든셋 20곡의 정답 탭을 어떻게 확보할지 (직접 채보 vs 기존 검증된 탭 활용)

---

## 부록 A. 실측 확인된 API (2026-08-03, 로컬 환경)

문서만으로 확정하지 못했던 항목을 실제 설치 후 확인한 결과.

### A.1 설치 이슈 — Python 3.12

`basic-pitch`와 `tuttut`은 **`pip install`이 실패한다.** 옛 numpy 핀을 소스 빌드하려다
`pkgutil.ImpImporter` 제거(Python 3.12) 때문에 깨진다. 또한 basic-pitch 0.4.0은
런타임 의존성 조건이 `python_version < "3.11"`로 박혀 있어 3.12에서는 ONNX/TF를
아예 설치하지 않는다.

**해결**: 두 패키지를 `--no-deps`로 설치하고 런타임을 직접 넣는다.

```bash
pip install basic-pitch --no-deps
pip install onnxruntime librosa resampy scikit-learn typing-extensions
pip install tuttut --no-deps
pip install networkx matplotlib
```

TF/CoreML/TFLite 미설치 경고는 무시해도 된다. ONNX 런타임으로 동작한다.

### A.2 basic-pitch

```python
predict(audio_path,
        model_or_model_path=<saved_models/icassp_2022/nmp.onnx>,
        onset_threshold=0.5, frame_threshold=0.3,
        minimum_note_length=127.7,      # ms
        minimum_frequency=None, maximum_frequency=None,
        multiple_pitch_bends=False, melodia_trick=True,
        midi_tempo=120)
  -> (model_output: dict, midi_data: PrettyMIDI, note_events: list[tuple])
```

**`note_events` 튜플 = `(start_sec, end_sec, pitch_midi, amplitude, pitch_bends)`**
— 4번째 원소가 confidence 역할을 한다. 품질 게이트(4.7)의 입력으로 그대로 쓴다.

**베이스용 파라미터 (중요)**

| 파라미터 | 기본값 | 베이스 설정 | 이유 |
|---|---|---|---|
| `minimum_note_length` | 127.7ms | **60** | 기본값이 빠른 베이스 라인을 잘라먹는다. 120BPM 16분음표 = 125ms로 기본값에 걸린다 |
| `minimum_frequency` | None | **35** | E1 = 41.2Hz |
| `maximum_frequency` | None | **450** | 4현 20프렛 상한 |

### A.3 tuttut

```python
Tuning(strings=["E4","B3","G3","D3","A2","E2"])   # 기본은 기타. thin -> thick
Tab(name, tuning, midi: PrettyMIDI, output_dir=None, weights=None)
```

- **4현 베이스 튜닝**: `Tuning(strings=["G2","D2","A1","E1"])` → `tab.tab["tuning"] == [43, 38, 33, 28]` (PRD 6.6과 일치 확인)
- **`weights`가 운지 비용함수 노브**: `{"b":1, "height":1, "length":1, "n_changed_strings":1}`
- 생성자가 `populate()` + `gen_tab()`을 자동 호출한다
- **`to_ascii()`는 파일에 쓰고 `None`을 반환한다.** 구조화 데이터는 `tab.tab` 딕셔너리:
  ```python
  tab.tab["tuning"]    # [43, 38, 33, 28]
  tab.tab["measures"]  # [{"events": [{"time","time_ticks","measure_timing",
                       #               "notes":[{"degree","octave","string","fret"}]}]}]
  ```
  → AlphaTex 생성기는 이 구조를 입력으로 받는다
- `nfrets` 기본 20
- `tuttut 0.0.6`은 `pretty-midi==0.2.9`를 요구하지만 0.2.11에서 정상 동작 확인

### A.4 스모크 테스트 결과 — 배음 문제 실증

합성 베이스 라인 8음(E1-G1-A1-B1-E1-G1-A1-E1)으로 채보→운지 체인 검증
(`scripts/smoke_transcribe.py`).

| 단계 | 결과 |
|---|---|
| basic-pitch 원본 출력 | **29개 이벤트** (기대 8개) |
| 후처리(`bassclean`) 후 | **8개, 정답과 100% 일치** |
| 제거 내역 | 배음 17, 겹침 2, 병합 2 |

후처리 전 탭에는 9·12·14·16프렛에 존재하지 않는 음이 찍혔다. 전부 E1의
배음(+24 = E3 등)이 별도 음으로 검출된 것이다. **4.5의 단선율 강제 후처리는
선택이 아니라 필수라는 것이 수치로 확인됐다.**

후처리 후 탭:
```
G ||--------------------|--------------|
D ||--------------------|--------------|
A ||---------0----2-----|-----0--------|
E ||0---3-------------0-|3---------0---|
```

> 주의: 이 수치는 합성 신호 기준이라 **파이프라인 상한**이다. 실제 밴드 믹스에서는
> Demucs 분리 품질이 변수로 추가되므로 9의 목표치(노트 F1 ≥ 0.75)가 현실적 기준이다.

### A.5 signalsmith-stretch — 실제 API와 8채널 검증

`signalsmith-stretch@1.3.2`. **6.7에 처음 적었던 `setState({sample:{buffers}})`는 존재하지 않는다.**
실제 API:

```js
const stretch = await SignalsmithStretch(audioContext, channelOptions);
// channelOptions = AudioWorkletNode 옵션 그대로
//   { numberOfInputs, numberOfOutputs, outputChannelCount }

await stretch.addBuffers([ch0, ch1, ...]);  // 채널당 TypedArray 하나. 여러 번 호출 가능(스트리밍)
stretch.schedule({ output, active, input, rate, semitones,
                   loopStart, loopEnd, tonalityHz, formantSemitones });
stretch.start(when);  stretch.stop(when);
stretch.inputTime;    // 현재 입력 버퍼 내 재생 위치(초)
stretch.setUpdateInterval(seconds, callback);
stretch.dropBuffers(toSeconds);
stretch.configure({ blockMs, intervalMs, splitComputation });
```

**예상보다 유리한 점**: `loopStart`/`loopEnd`가 내장이라 구간 반복(PLY-06)이 공짜고,
`semitones`로 피치 시프트(PLY-07)도 같은 호출에서 처리된다. 별도 구현이 필요 없다.

**8채널 PoC 결과** (`tools/poc/stretch8.html`, OfflineAudioContext 렌더링으로 결정적 검증):

스템 4종에 각각 다른 주파수(110/220/440/880Hz)를 넣고 Goertzel로 출력 에너지를 측정.

| 검증 | 결과 |
|---|---|
| 8채널 노드 생성 + 4스템 동시 출력 | 통과 — 4개 주파수 전부 검출 |
| 베이스 솔로 (게인 `[0,1,0,0]`) | 통과 — 220Hz만 0.0591, 나머지 0.0003 이하 |
| 베이스 2배 부스트 | 통과 — 에너지 비율 **정확히 2.00** |
| 반배속 피치 유지 | 통과 — 220Hz 유지, 110Hz로 안 내려감 |
| 반배속 길이 확장 | 통과 — 2초 소스가 4초로, 후반부 RMS 0.6995 |

**4.1의 멀티채널 단일 스트레처 구조가 실증됐다.** PRD에서 유일하게 미검증으로
남아 있던 기술 가정이었고, 폴백(스템별 스트레처 4개)은 불필요하다.

### A.6 번들러 함정 — signalsmith와 alphaTab 모두 번들에 태우면 안 된다

10의 리스크 표에 "alphaTab이 번들러 플러그인 필요"라고 적었는데, **같은 문제가
signalsmith에도 있었다.** 원인은 서로 다르지만 처방은 같다.

| 라이브러리 | 왜 깨지는가 | 증상 |
|---|---|---|
| signalsmith-stretch | 워크릿 코드를 함수 `toString()`으로 직렬화해 Blob URL을 만든다(`SignalsmithStretch.mjs:392`). 번들러가 함수를 변형하면 직렬화된 소스가 모듈 스코프 변수를 참조하는데 워크릿 스코프엔 없다 | **에러 없이** `addBuffers()`의 Promise가 영원히 대기 |
| @coderline/alphatab | 자체 Worker/AudioWorklet을 만들고 Bravura 폰트를 상대경로로 찾는다. 공식 플러그인은 webpack/vite용만 존재 | 스크립트·폰트 경로 해석 실패 |

**처방**: `scripts/sync-vendor.mjs`가 원본을 `public/vendor/`로 복사하고,
런타임에 `/* turbopackIgnore: true */` 동적 import로 불러온다. 원본을 그대로
서빙하면 alphaTab은 자기 스크립트 경로를 스스로 찾아낸다.

부수 주의사항:
- TypeScript가 `/vendor/...` 리터럴을 모듈로 해석하려 하므로 경로를 **변수에
  담아** 넘긴다. 리터럴이면 `Cannot find module` 에러가 난다.
- ESLint가 벤더 코드를 검사하므로 `public/vendor/**`를 무시 목록에 넣는다.

### A.7 AudioContext는 suspended면 워크릿이 돌지 않는다

`addBuffers()`는 워크릿의 응답을 기다리므로, 컨텍스트가 suspended면 영원히
완료되지 않는다. 그래서 `StemPlayer.create()`는 **디코딩만** 하고 오디오 그래프
생성은 첫 재생(사용자 제스처) 시점으로 미룬다. 브라우저 자동재생 정책상
어차피 그때가 아니면 소리를 낼 수 없으므로 구조적으로도 옳다.

디코딩은 **실제 재생에 쓸 AudioContext로** 해야 한다. `decodeAudioData`가
컨텍스트의 `sampleRate`로 리샘플링하므로 다른 컨텍스트를 쓰면 재생 속도가 어긋난다.

### A.8 alphaTab 컨테이너를 숨기면 렌더링이 안 된다

폭이 0이면 alphaTab은 렌더링을 건너뛴다(`AlphaTab skipped rendering because of
width=0`). "준비되면 보여주기" 패턴으로 `hidden`을 걸면, 준비 신호가
`renderFinished`에서 오므로 서로를 기다리는 교착이 생긴다. 항상 자리를 잡아두고
`opacity`만 조절해야 한다.

### A.9 다운비트 위상은 통째로 어긋날 수 있다

beat_this는 비트를 매우 정확히 잡지만(합성 픽스처에서 F-measure 1.000)
**다운비트 위상은 반 마디 밀릴 수 있다.** 실측: 킥 1·3박 + 스네어 2·4박 패턴에서
백비트를 1박으로 듣고 다운비트를 1.0/3.0/5.0초에 찍었다(정답 0.0/2.0/4.0).

이러면 악보 전체가 밀린다. `quantize.choose_phase()`가 **"곡의 첫 음은 거의 항상
마디 1박"**이라는 사전정보로 교정한다. 픽업 마디로 시작하는 곡에서는 틀리지만
소수다.

또한 다운비트를 마디 경계로 직접 쓰면 4/4가 2박 마디로 쪼개진다. 비트 배열을
기준으로 `beats_per_bar`개씩 묶어야 한다. 이 수정으로 양자화 잔차가
0.267 → 0.113으로 떨어졌다.

**교정에 쓴 위상은 manifest에 반드시 기록한다.** 이 값 없이는 산출물에서 마디
시각을 재구성할 수 없어 평가 결과가 실제보다 나쁘게 나온다.

### A.10 AlphaTex 타이 문법은 일부만 통과한다

`-.2` / `-.4`는 파싱되지만 **`-.8` / `-.16`은 거부된다**
(`tools/probe_syntax.mjs`로 탐침). 원인 추적 대신 타이를 쓰지 않고, 음길이를
2의 거듭제곱으로 내림한 뒤 남는 만큼을 쉼표로 채운다. 대가는 음이 실제보다
조금 짧게 표기되는 것이고 리듬 위치는 정확하다.

### A.11 최종 측정 결과

| 경로 | 노트 F1 | Precision | Recall | 품질 점수 |
|---|---|---|---|---|
| 베이스 단독 입력 | 0.931 | 0.964 | 0.900 | — |
| 믹스 → Demucs → 채보 | 0.815 | 0.917 | 0.733 | 81 (good) |

두 경우 모두 온셋 오차 0.0ms, 비트 F-measure 1.000, BPM·마디 수 정확.
**병목은 채보가 아니라 스템 분리다** — 리듬·타이밍은 완벽한데 Demucs를 거치며
recall만 떨어진다. 다음 개선은 분리 모델 교체(5의 BS-RoFormer)가 가장 레버리지가 크다.

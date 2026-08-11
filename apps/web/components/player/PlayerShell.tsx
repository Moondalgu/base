"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  DEFAULT_GAINS,
  PRESETS,
  SYNTH_DEFAULT_GAIN,
  StemPlayer,
  snapToDownbeat,
  stemUrls,
  type BeatGrid,
  type Gains,
  type StemName,
} from "@/lib/player/engine";
import ScoreControls, { ORIGINAL_LEVEL, TRANSPOSE_LIMIT } from "./ScoreControls";
import ScoreView, { type ScoreControl } from "./ScoreView";
import StemMixer from "./StemMixer";
import TransportBar from "./TransportBar";
import { BADGE } from "../ui";

interface Manifest {
  source?: { title?: string; durationSec?: number };
  tempo?: { medianBpm?: number };
  timeSignature?: [number, number];
  barCount?: number;
  noteCount?: number;
  tuning?: { preset?: string; midi?: number[] };
  quality?: { level?: "good" | "reference" | "failed"; score?: number };
  /** 스템 파일 확장자. 없으면 wav (구버전 아티팩트) */
  stemFormat?: string;
  /** 음량 게이트 결과. 두 연주가 섞인 입력을 감지하는 신호다 */
  loudnessGate?: {
    applied: boolean;
    dropped: number;
    // 게이트 판정이 8분 격자에서 16분·셋잇단 격자로 바뀌면서 manifest 키도
    // 바뀌었다. 옛 이름을 읽으면 undefined가 되어 경고가 조용히 사라진다.
    gridBefore: number;
    gridAfter: number;
  };
  scoreVariants?: {
    /** 이 곡에 제공할 난이도 단계. 원곡이 이미 쉬우면 원본 하나뿐이다 */
    levels?: number[];
    transposeRange?: [number, number];
    tunings?: string[];
  };
  /** 원곡 자체의 난이도 판정. 단계를 하나만 주는 이유가 여기 있다 */
  originalDifficulty?: { alreadyEasy?: boolean; reason?: string };
  /** 입력 종류 판정. 연습 영상이면 하향 단계를 만들지 않는다 */
  /**
   * 입력 진단. `practiceVideo`는 **항상 false다** — 연습 영상 판정은 신호를
   * 찾지 못해 버렸다(`pipeline/diagnose.py` 머리말). 쓸 것은 `rhythmConfident`다.
   */
  inputDiagnosis?: {
    practiceVideo?: boolean;
    rhythmConfident?: boolean;
    reason?: string;
  };
}

type Status = "loading" | "ready" | "error";

export default function PlayerShell({ hash }: { hash: string }) {
  const playerRef = useRef<StemPlayer | null>(null);
  const scoreControlRef = useRef<ScoreControl | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string>("");
  const [manifest, setManifest] = useState<Manifest | null>(null);

  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRate] = useState(1);
  // 재생 피치와 악보 이조는 같은 값이다. 상태를 하나만 두어 어긋날 수 없게 한다.
  const [semitones, setSemitones] = useState(0);
  // 지금 악보에 찍힌 조표 이름. 워커가 이조를 반영해 내려주는 값을 그대로
  // 들고 있다가 하단 바에 보여준다 (프론트에서 다시 계산하지 않는다).
  const [keyName, setKeyName] = useState("");
  const [level, setLevel] = useState(ORIGINAL_LEVEL);
  const [tuning, setTuning] = useState("standard");
  const [gains, setGains] = useState<Gains>({ ...DEFAULT_GAINS });
  const [activePreset, setActivePreset] = useState<string | null>("all");
  // 마디 스냅과 메트로놈이 같은 격자를 쓴다. 없으면 둘 다 원래 값으로 동작한다.
  const [beatGrid, setBeatGrid] = useState<BeatGrid | null>(null);
  const [loopStart, setLoopStart] = useState<number | null>(null);
  const [loopEnd, setLoopEnd] = useState<number | null>(null);
  const [metronome, setMetronome] = useState(false);
  const [scoreReady, setScoreReady] = useState(false);
  // 악보 연주 — 원곡 베이스를 빼고 화면 악보를 샘플러로 연주한다.
  const [synthOn, setSynthOn] = useState(false);
  const [synthGain, setSynthGain] = useState(SYNTH_DEFAULT_GAIN);
  // 켜기 직전 베이스 볼륨. 끌 때 사용자가 쓰던 값으로 되돌린다.
  const bassBeforeSynth = useRef(1);
  // 사용자 보정이 저장될 때마다 +1 — 악보·연주 이벤트가 같은 판을 다시 받는다.
  const [editsVersion, setEditsVersion] = useState(0);
  // 악보 소스(자동/내 악보) — 악보 연주(신스)가 보이는 악보의 음을 내야 한다.
  const [scoreSource, setScoreSource] = useState<"auto" | "reference">("auto");

  // 유튜브 제목의 "X (X)" 중복 괄호를 접는다 — 워커(jobs.clean_title)와 같은 규칙.
  const cleanTitle = (t: string) => {
    const m = /^(.*?)\s*[([](.*?)[)\]]\s*$/.exec(t);
    return m && m[1].trim().toLowerCase() === m[2].trim().toLowerCase() ? m[1].trim() : t;
  };
  const title = manifest?.source?.title ? cleanTitle(manifest.source.title) : undefined;

  // 브라우저 탭에 곡 제목 — 여러 곡을 탭으로 열어두고 연습하는 사용 방식에서
  // 탭을 구분할 유일한 단서다.
  useEffect(() => {
    if (title) document.title = `${title} — Lowend`;
  }, [title]);

  useEffect(() => {
    let disposed = false;
    let player: StemPlayer | null = null;

    (async () => {
      try {
        let stemFormat: string | undefined;
        const manifestRes = await fetch(`/api/artifacts/${hash}/manifest.json`);
        if (manifestRes.ok) {
          const data: Manifest = await manifestRes.json();
          setManifest(data);
          stemFormat = data.stemFormat;
        }

        // 비트 격자는 없어도 재생은 된다 — 실패해도 로딩을 세우지 않는다.
        let grid: BeatGrid | null = null;
        try {
          const beatsRes = await fetch(`/api/artifacts/${hash}/beats.json`);
          if (beatsRes.ok) {
            const data = await beatsRes.json();
            if (Array.isArray(data?.beats) && data.beats.length > 0) {
              grid = {
                beats: data.beats as number[],
                downbeats: Array.isArray(data.downbeats) ? (data.downbeats as number[]) : [],
              };
            }
          }
        } catch {
          grid = null;
        }
        if (!disposed) setBeatGrid(grid);

        player = await StemPlayer.create({
          urls: stemUrls(hash, stemFormat),
          onPosition: (t) => {
            if (!disposed) setPosition(t);
          },
        });

        if (disposed) {
          await player.close();
          return;
        }
        player.setBeatGrid(grid);
        playerRef.current = player;
        setDuration(player.duration);
        // 곡이 바뀌면 새 엔진에는 구간·메트로놈·악보 연주가 없다. 표시도 같이 되돌린다.
        setLoopStart(null);
        setLoopEnd(null);
        setMetronome(false);
        setSynthOn(false);
        setSynthGain(SYNTH_DEFAULT_GAIN);
        setStatus("ready");
        if (process.env.NODE_ENV !== "production") {
          // 브라우저 콘솔·자동화에서 엔진 상태를 들여다보기 위한 개발용 훅
          (window as unknown as { __player?: StemPlayer }).__player = player;
        }
      } catch (e) {
        if (!disposed) {
          setError(e instanceof Error ? e.message : String(e));
          setStatus("error");
        }
      }
    })();

    return () => {
      disposed = true;
      playerRef.current?.close();
      playerRef.current = null;
    };
  }, [hash]);

  /** 엔진 직접 제어 — alphaTab의 handler.play/pause가 도착하는 곳 */
  const toggleTo = useCallback(async (shouldPlay: boolean) => {
    const player = playerRef.current;
    if (!player) return;
    if (shouldPlay && !player.playing) {
      await player.play();
      setPlaying(true);
    } else if (!shouldPlay && player.playing) {
      player.pause();
      setPlaying(false);
    }
  }, []);

  const toggle = useCallback(async () => {
    const player = playerRef.current;
    if (!player) return;
    const shouldPlay = !player.playing;
    // 악보가 있으면 alphaTab을 경유한다 — alphaTab이 handler.play()로 엔진을
    // 켜면서 자기 상태도 "재생 중"이 되어 커서가 움직인다. 엔진만 직접 켜면
    // alphaTab은 정지 상태로 남아 어디를 연주 중인지 표시하지 않는다.
    const scoreControl = scoreControlRef.current;
    if (scoreControl) {
      scoreControl.setPlaying(shouldPlay);
      return;
    }
    await toggleTo(shouldPlay);
  }, [toggleTo]);

  const handleSeek = useCallback((seconds: number) => {
    playerRef.current?.seek(seconds);
    setPosition(seconds);
  }, []);

  const handleRate = useCallback((value: number) => {
    playerRef.current?.setRate(value);
    setRate(playerRef.current?.rate ?? value);
  }, []);

  /**
   * 키 조절 — 재생 피치와 악보를 함께 옮긴다.
   *
   * 엔진에만 넣으면 들리는 음과 악보가 어긋난다. semitones 상태가 ScoreView에도
   * 내려가므로 악보가 같은 값으로 다시 그려진다.
   */
  const handleSemitones = useCallback((value: number) => {
    const clamped = Math.max(-TRANSPOSE_LIMIT, Math.min(TRANSPOSE_LIMIT, value));
    playerRef.current?.setSemitones(clamped);
    setSemitones(playerRef.current?.semitones ?? clamped);
  }, []);

  /**
   * A-B 구간 반복.
   *
   * 경계는 마디 시작으로 맞춘다 — 마디 중간에서 되감기면 박자가 어긋나 따라
   * 칠 수가 없다. 격자가 없는 곡이면 찍은 위치를 그대로 쓴다.
   * 엔진에는 입력 타임라인 초를 그대로 넘긴다(배속과 무관).
   */
  const markLoop = useCallback(
    (edge: "a" | "b") => {
      const player = playerRef.current;
      if (!player) return;
      const downbeats = beatGrid?.downbeats ?? [];
      const at = snapToDownbeat(player.position, downbeats);

      let start = loopStart;
      let end = loopEnd;
      if (edge === "a") start = loopStart === null ? at : null;
      else end = loopEnd === null ? at : null;

      // 끝이 시작보다 앞이면 무시한다. 지우는 쪽(null)은 언제나 통과시킨다.
      if (start !== null && end !== null && end <= start) return;

      setLoopStart(start);
      setLoopEnd(end);
      player.setLoop(start, end);
    },
    [beatGrid, loopStart, loopEnd],
  );

  /** 악보 드래그로 잡은 마디 구간(0-based, 양끝 포함) → A-B 반복 */
  const handleDragLoop = useCallback(
    (startBar: number, endBar: number) => {
      const player = playerRef.current;
      const downs = beatGrid?.downbeats;
      if (!player || !downs?.length) return;
      const a = downs[Math.min(startBar, downs.length - 1)];
      const b = endBar + 1 < downs.length ? downs[endBar + 1] : player.duration;
      if (a === undefined || b === undefined || b <= a) return;
      setLoopStart(a);
      setLoopEnd(b);
      player.setLoop(a, b);
    },
    [beatGrid],
  );

  const toggleMetronome = useCallback(() => {
    const player = playerRef.current;
    if (!player) return;
    const next = !player.metronome;
    player.setMetronome(next);
    setMetronome(next);
  }, []);

  const handleGain = useCallback((stem: StemName, value: number) => {
    const player = playerRef.current;
    if (!player) return;
    player.setGain(stem, value);
    setGains(player.gains);
    setActivePreset(null);
  }, []);

  const handlePreset = useCallback((key: string) => {
    const player = playerRef.current;
    if (!player) return;
    player.applyPreset(key as keyof typeof PRESETS);
    setGains(player.gains);
    setActivePreset(key);
  }, []);

  /**
   * 악보 연주 토글 — 켜면 원곡 베이스를 뮤트하고 화면 악보를 샘플러로
   * 연주한다(끌 때 쓰던 볼륨으로 복귀). 같은 소리가 두 겹으로 어긋나게
   * 울리는 것이 최악이라, 토글이 뮤트까지 책임진다.
   */
  const toggleSynth = useCallback(() => {
    const player = playerRef.current;
    if (!player) return;
    const next = !player.synthEnabled;
    if (next) {
      bassBeforeSynth.current = player.gains.bass;
      player.setGain("bass", 0);
    } else {
      player.setGain("bass", bassBeforeSynth.current || 1);
    }
    player.setSynthEnabled(next);
    setGains(player.gains);
    setActivePreset(null);
    setSynthOn(next);
  }, []);

  const handleSynthGain = useCallback((value: number) => {
    playerRef.current?.setSynthGain(value);
    setSynthGain(playerRef.current?.synthGain ?? value);
  }, []);

  // 악보 연주 이벤트는 화면 악보와 같은 변형(난이도·키·튜닝)이어야 한다.
  // 켜져 있는 동안 그 값이 바뀌면 같은 인자로 다시 받는다.
  useEffect(() => {
    if (!synthOn) return;
    const player = playerRef.current;
    if (!player) return;
    let stale = false;
    (async () => {
      try {
        const query = new URLSearchParams({
          level: String(level),
          transpose: String(semitones),
        });
        if (tuning && tuning !== "standard") query.set("tuning", tuning);
        if (scoreSource === "reference") query.set("source", "reference");
        const res = await fetch(`/api/scores/${hash}/synth-notes?${query}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!stale && Array.isArray(data?.notes)) {
          // 드럼 히트는 같은 타임라인에 얹는다. +1ms 오프셋은 같은 시각의
          // 베이스 음이 스케줄러 중복 가드(0.5ms)에 걸려 떨어지지 않게 한다.
          const drums = Array.isArray(data?.drums)
            ? data.drums.map((d: { t: number; k: string }) => ({
                t: d.t + 0.001, d: 0.1, midi: 0, v: 1, k: d.k,
              }))
            : [];
          player.setSynthNotes([...data.notes, ...drums]);
        }
      } catch {
        // 워커가 없으면 연주 모드도 없다 — 반주는 그대로 나온다.
      }
    })();
    return () => {
      stale = true;
    };
  }, [synthOn, hash, level, semitones, tuning, editsVersion, scoreSource]);

  if (status === "loading") {
    return <p className="text-sm text-neutral-500">스템을 불러오는 중…</p>;
  }
  if (status === "error") {
    return (
      <div className="space-y-2">
        <p className="text-sm text-red-600">스템을 불러오지 못했습니다.</p>
        <pre className="overflow-x-auto rounded-lg bg-neutral-100 p-3 text-xs dark:bg-neutral-900">
          {error}
        </pre>
        <p className="text-xs text-neutral-500">
          {`파이프라인을 먼저 돌려 data/${hash}/stems/ 를 만들어야 합니다.`}
        </p>
      </div>
    );
  }

  /*
    화면 순서는 "곡 정보 → 악보 → 설정"이다. 연습 중에 계속 보는 것은 악보
    하나뿐이라 첫 화면에 악보가 들어와야 하고, 난이도·키·볼륨은 한 번 정하면
    잘 안 만지는 값이라 아래로 내려 접어 두었다.

    재생 컨트롤만 아래 고정 바로 뺐다 — 악보를 스크롤하는 동안에도 손이 닿아야
    하는 것은 그것뿐이다. 아래 여백은 그 바가 가리는 만큼인데, 좁은 화면에서는
    바가 두세 줄로 접히므로 더 준다.
  */
  return (
    <div className="pb-48 sm:pb-40 lg:pb-32">
      <header className="mb-4 space-y-2">
        <h1 className="text-lg font-semibold tracking-tight sm:text-xl">
          {title ?? hash}
        </h1>
        <div className="flex flex-wrap items-center gap-1.5">
          {manifest?.tempo?.medianBpm ? (
            <span className={BADGE}>{`${manifest.tempo.medianBpm} BPM`}</span>
          ) : null}
          {manifest?.timeSignature ? (
            <span className={BADGE}>{manifest.timeSignature.join("/")}</span>
          ) : null}
          {manifest?.barCount ? <span className={BADGE}>{`${manifest.barCount}마디`}</span> : null}
          {manifest?.noteCount ? <span className={BADGE}>{`${manifest.noteCount}음`}</span> : null}
        </div>
      </header>

      <ScoreView
        hash={hash}
        position={position}
        controlRef={scoreControlRef}
        qualityLevel={manifest?.quality?.level}
        barStarts={beatGrid?.downbeats}
        level={level}
        transpose={semitones}
        tuning={tuning}
        onReady={setScoreReady}
        editsVersion={editsVersion}
        onEditsChanged={() => setEditsVersion((v) => v + 1)}
        levels={manifest?.scoreVariants?.levels}
        onLevel={setLevel}
        onSourceChange={setScoreSource}
        onDragLoop={handleDragLoop}
        onKeyName={setKeyName}
        callbacks={{
          play: () => {
            void toggleTo(true);
          },
          pause: () => {
            void toggleTo(false);
          },
          seekTo: handleSeek,
          setRate: handleRate,
          setVolume: () => {
            /* 마스터 볼륨은 스템 믹서가 담당한다 */
          },
          durationSeconds: () => playerRef.current?.duration ?? 0,
        }}
      />

      <div className="mt-4 space-y-3">
        <ScoreControls
          contentHash={hash}
          level={level}
          transpose={semitones}
          tuning={tuning}
          gate={manifest?.loudnessGate}
          levels={manifest?.scoreVariants?.levels}
          /*
            단계를 없앤 이유를 그대로 보여준다. "원곡이 이미 쉽다"와 "리듬 검출을
            믿을 수 없다"는 완전히 다른 얘기이고, 후자는 사용자가 취할 행동
            (원곡 음원을 넣어 본다)이 있다.

            **`practiceVideo`를 보지 않는다.** 그 판정은 버렸다 — 공식 스튜디오
            음원 세 곡을 전부 "베이스가 둘 섞였다"고 단정했던 자리다.
          */
          levelReason={
            manifest?.inputDiagnosis?.rhythmConfident === false
              ? manifest.inputDiagnosis.reason
              : manifest?.originalDifficulty?.reason
          }
          onLevel={setLevel}
          onTuning={setTuning}
          onPrint={scoreReady ? () => scoreControlRef.current?.print() : undefined}
        />

        <StemMixer
          gains={gains}
          onGainChange={handleGain}
          onPreset={handlePreset}
          activePreset={activePreset}
          synthOn={synthOn}
          synthGain={synthGain}
          onSynthToggle={toggleSynth}
          onSynthGain={handleSynthGain}
        />
      </div>

      <TransportBar
        playing={playing}
        position={position}
        duration={duration}
        rate={rate}
        semitones={semitones}
        keyName={keyName}
        loopStart={loopStart}
        loopEnd={loopEnd}
        metronome={metronome}
        metronomeAvailable={Boolean(beatGrid)}
        synthOn={synthOn}
        onToggle={toggle}
        onSeek={handleSeek}
        onRate={handleRate}
        onSemitones={handleSemitones}
        onLoopA={() => markLoop("a")}
        onLoopB={() => markLoop("b")}
        onMetronome={toggleMetronome}
        onSynthToggle={toggleSynth}
      />
    </div>
  );
}

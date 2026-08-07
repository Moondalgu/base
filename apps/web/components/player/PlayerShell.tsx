"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  DEFAULT_GAINS,
  PRESETS,
  StemPlayer,
  stemUrls,
  type Gains,
  type StemName,
} from "@/lib/player/engine";
import ScoreControls, { ORIGINAL_LEVEL, TRANSPOSE_LIMIT } from "./ScoreControls";
import ScoreView, { type ScoreControl } from "./ScoreView";
import StemMixer from "./StemMixer";
import TransportBar from "./TransportBar";

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
  inputDiagnosis?: { practiceVideo?: boolean; reason?: string };
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
  const [level, setLevel] = useState(ORIGINAL_LEVEL);
  const [tuning, setTuning] = useState("standard");
  const [gains, setGains] = useState<Gains>({ ...DEFAULT_GAINS });
  const [activePreset, setActivePreset] = useState<string | null>("all");

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
        playerRef.current = player;
        setDuration(player.duration);
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

  if (status === "loading") {
    return <p className="text-sm text-neutral-500">스템을 불러오는 중…</p>;
  }
  if (status === "error") {
    return (
      <div className="space-y-2">
        <p className="text-sm text-red-600">스템을 불러오지 못했습니다.</p>
        <pre className="overflow-x-auto rounded bg-neutral-100 p-3 text-xs dark:bg-neutral-900">
          {error}
        </pre>
        <p className="text-xs text-neutral-500">
          {`파이프라인을 먼저 돌려 data/${hash}/stems/ 를 만들어야 합니다.`}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">
          {manifest?.source?.title ?? hash}
        </h1>
        <p className="text-sm text-neutral-500">
          {manifest?.tempo?.medianBpm ? `${manifest.tempo.medianBpm} BPM` : null}
          {manifest?.timeSignature ? ` · ${manifest.timeSignature.join("/")}` : null}
          {manifest?.barCount ? ` · ${manifest.barCount}마디` : null}
          {manifest?.noteCount ? ` · ${manifest.noteCount}음` : null}
        </p>
      </header>

      <TransportBar
        playing={playing}
        position={position}
        duration={duration}
        rate={rate}
        semitones={semitones}
        onToggle={toggle}
        onSeek={handleSeek}
        onRate={handleRate}
        onSemitones={handleSemitones}
      />

      <ScoreControls
        contentHash={hash}
        level={level}
        transpose={semitones}
        tuning={tuning}
        gate={manifest?.loudnessGate}
        levels={manifest?.scoreVariants?.levels}
        // 연습 영상 판정이 있으면 그 사유를 먼저 보여준다. "원곡이 이미 쉽다"와
        // "베이스가 둘 섞였다"는 단계를 없애는 이유가 완전히 다르고, 후자는
        // 사용자가 취할 행동(원곡 음원을 넣는다)이 있다.
        levelReason={
          manifest?.inputDiagnosis?.practiceVideo
            ? manifest.inputDiagnosis.reason
            : manifest?.originalDifficulty?.reason
        }
        onLevel={setLevel}
        onTranspose={handleSemitones}
        onTuning={setTuning}
      />

      <ScoreView
        hash={hash}
        position={position}
        controlRef={scoreControlRef}
        qualityLevel={manifest?.quality?.level}
        level={level}
        transpose={semitones}
        tuning={tuning}
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

      <StemMixer
        gains={gains}
        onGainChange={handleGain}
        onPreset={handlePreset}
        activePreset={activePreset}
      />
    </div>
  );
}

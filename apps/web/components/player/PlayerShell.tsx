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
  const [semitones, setSemitones] = useState(0);
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

  const handleSemitones = useCallback((value: number) => {
    playerRef.current?.setSemitones(value);
    setSemitones(playerRef.current?.semitones ?? value);
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

      <ScoreView
        hash={hash}
        position={position}
        controlRef={scoreControlRef}
        qualityLevel={manifest?.quality?.level}
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

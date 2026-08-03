/**
 * 스템 플레이어 엔진.
 *
 * 핵심 구조 (PRD 4.1, tools/poc/stretch8.html에서 실증):
 *
 *   [8ch 버퍼: 스템4 × 스테레오2]
 *          ↓
 *   [SignalsmithStretch]   ← 속도·피치를 여기서 한 번만
 *          ↓
 *   [ChannelSplitter(8)] → 스템별 GainNode → [ChannelMerger(2)] → destination
 *
 * 스트레처가 하나라서 스템 간 드리프트가 구조적으로 불가능하다.
 * 솔로/뮤트/부스트는 GainNode 값만 바꾸면 되므로 원가가 0이다.
 */

/**
 * signalsmith-stretch는 번들러를 태우면 안 된다.
 *
 * 이 라이브러리는 워크릿 코드를 함수의 toString()으로 직렬화해 Blob URL로
 * 만든다(SignalsmithStretch.mjs:392). 번들러가 그 함수를 변형·최소화하면
 * 직렬화된 소스가 모듈 스코프 변수를 참조하게 되고, 워크릿 스코프에는 그게
 * 없어서 조용히 깨진다. addBuffers()의 Promise가 영원히 대기하는 증상으로 나타난다.
 *
 * 그래서 원본 .mjs를 public/vendor/에 두고 런타임에 그대로 불러온다.
 * (scripts/sync-vendor.mjs가 node_modules에서 복사한다)
 */
type SignalsmithStretchFn = (
  ctx: BaseAudioContext,
  options?: Record<string, unknown>,
) => Promise<AudioNode>;

let stretchFactory: SignalsmithStretchFn | null = null;

async function loadSignalsmith(): Promise<SignalsmithStretchFn> {
  if (stretchFactory) return stretchFactory;
  const mod = await import(
    /* webpackIgnore: true */ /* turbopackIgnore: true */ "/vendor/SignalsmithStretch.mjs"
  );
  stretchFactory = (mod.default ?? mod) as SignalsmithStretchFn;
  return stretchFactory;
}

export const STEM_ORDER = ["drums", "bass", "vocals", "other"] as const;
export type StemName = (typeof STEM_ORDER)[number];

export type Gains = Record<StemName, number>;

export const DEFAULT_GAINS: Gains = { drums: 1, bass: 1, vocals: 1, other: 1 };

/** 베이시스트 프리셋 — 8채널 게인 구조에서 공짜로 나온다 */
export const PRESETS: Record<string, { label: string; gains: Gains }> = {
  all: { label: "전체", gains: { drums: 1, bass: 1, vocals: 1, other: 1 } },
  bassOnly: { label: "베이스만", gains: { drums: 0, bass: 1, vocals: 0, other: 0 } },
  minusBass: { label: "베이스 빼고", gains: { drums: 1, bass: 0, vocals: 1, other: 1 } },
  rhythm: { label: "베이스+드럼", gains: { drums: 1, bass: 1, vocals: 0, other: 0 } },
};

export interface StemPlayerOptions {
  /** 스템 이름 → 오디오 URL */
  urls: Record<StemName, string>;
  onPosition?: (seconds: number) => void;
  /** 위치 콜백 주기(초). alphaTab 커서는 50ms면 충분하다 */
  positionInterval?: number;
  /**
   * 오디오 컨텍스트를 직접 주입한다. 생략하면 AudioContext를 새로 만든다.
   * OfflineAudioContext를 넣으면 결정적 렌더링으로 그래프를 검증할 수 있다
   * (헤드리스 브라우저에는 실제 오디오 장치가 없어 실시간 경로를 못 쓴다).
   */
  context?: AudioContext | OfflineAudioContext;
}

interface StretchNode extends AudioNode {
  addBuffers(buffers: Float32Array[]): Promise<number>;
  schedule(opts: Record<string, unknown>): void;
  start(when?: number): void;
  stop(when?: number): void;
  setUpdateInterval(seconds: number, callback?: (t: number) => void): void;
  readonly inputTime: number;
}

export class StemPlayer {
  private ctx: AudioContext | OfflineAudioContext;
  private channels: Float32Array[];
  private options: StemPlayerOptions;
  private stretch: StretchNode | null = null;
  private gainNodes: Partial<Record<StemName, GainNode>> = {};
  private _duration = 0;
  private _playing = false;
  private _rate = 1;
  private _semitones = 0;
  private _gains: Gains = { ...DEFAULT_GAINS };
  private _loop: { start: number; end: number } | null = null;

  private constructor(
    ctx: AudioContext | OfflineAudioContext,
    channels: Float32Array[],
    duration: number,
    options: StemPlayerOptions,
  ) {
    this.ctx = ctx;
    this.channels = channels;
    this._duration = duration;
    this.options = options;
  }

  /**
   * 스템을 내려받아 디코딩까지만 한다.
   *
   * 오디오 그래프는 여기서 만들지 않는다. AudioContext가 suspended 상태면
   * AudioWorklet이 돌지 않아 addBuffers()의 Promise가 영원히 대기하기 때문이다.
   * 그래프 생성은 첫 재생(사용자 제스처) 시점으로 미룬다. 브라우저 자동재생
   * 정책상 어차피 그때가 아니면 소리를 낼 수 없다.
   *
   * 디코딩은 실제 AudioContext로 한다. decodeAudioData가 컨텍스트의
   * sampleRate로 리샘플링하므로, 다른 컨텍스트를 쓰면 재생 속도가 어긋난다.
   */
  static async create(options: StemPlayerOptions): Promise<StemPlayer> {
    const ctx = options.context ?? new AudioContext();
    const { channels, duration } = await loadStems(ctx, options.urls);
    return new StemPlayer(ctx, channels, duration, options);
  }

  /** 오프라인 렌더링용 — 그래프를 즉시 만들고 스케줄까지 건다 */
  async prepareOffline(rate = 1): Promise<void> {
    const stretch = await this.ensureGraph();
    this._rate = rate;
    this.applySchedule({ active: true, input: 0 });
    stretch.start(0);
    this._playing = true;
  }

  private async ensureGraph(): Promise<StretchNode> {
    if (this.stretch) return this.stretch;

    const ctx = this.ctx;
    const SignalsmithStretch = await loadSignalsmith();
    const stretch = (await SignalsmithStretch(ctx, {
      numberOfInputs: 0,
      numberOfOutputs: 1,
      outputChannelCount: [STEM_ORDER.length * 2],
    })) as StretchNode;

    await stretch.addBuffers(this.channels);

    const splitter = ctx.createChannelSplitter(STEM_ORDER.length * 2);
    const merger = ctx.createChannelMerger(2);
    stretch.connect(splitter);

    STEM_ORDER.forEach((name, i) => {
      const g = ctx.createGain();
      g.gain.value = this._gains[name];
      splitter.connect(g, i * 2);
      splitter.connect(g, i * 2 + 1);
      g.connect(merger, 0, 0);
      g.connect(merger, 0, 1);
      this.gainNodes[name] = g;
    });
    merger.connect(ctx.destination);

    if (this.options.onPosition) {
      stretch.setUpdateInterval(
        this.options.positionInterval ?? 0.05,
        this.options.onPosition,
      );
    }

    this.stretch = stretch;
    return stretch;
  }

  get duration(): number {
    return this._duration;
  }

  get position(): number {
    return this.stretch?.inputTime ?? 0;
  }

  /** 그래프가 만들어졌는지 (첫 재생 이후 true) */
  get activated(): boolean {
    return this.stretch !== null;
  }

  get playing(): boolean {
    return this._playing;
  }

  get rate(): number {
    return this._rate;
  }

  get semitones(): number {
    return this._semitones;
  }

  get gains(): Gains {
    return { ...this._gains };
  }

  get loop(): { start: number; end: number } | null {
    return this._loop ? { ...this._loop } : null;
  }

  async play(): Promise<void> {
    // 브라우저 자동재생 정책 — 사용자 제스처 이후에만 resume이 통한다.
    // resume을 먼저 해야 워크릿이 돌기 시작하고, 그래야 addBuffers가 완료된다.
    if (this.ctx.state === "suspended") await this.ctx.resume();
    const stretch = await this.ensureGraph();
    this.applySchedule({ active: true });
    stretch.start();
    this._playing = true;
  }

  pause(): void {
    this.stretch?.stop();
    this._playing = false;
  }

  seek(seconds: number): void {
    const clamped = Math.max(0, Math.min(seconds, this._duration));
    this.applySchedule({ active: this._playing, input: clamped });
  }

  setRate(rate: number): void {
    this._rate = Math.max(0.25, Math.min(2, rate));
    this.applySchedule({ active: this._playing });
  }

  setSemitones(semitones: number): void {
    this._semitones = Math.max(-12, Math.min(12, semitones));
    this.applySchedule({ active: this._playing });
  }

  /** 0 ~ 2.0. 1을 넘으면 부스트 */
  setGain(stem: StemName, value: number): void {
    const v = Math.max(0, Math.min(2, value));
    this._gains[stem] = v;
    // 급격한 변화는 클릭 노이즈를 만든다. 짧은 램프로 넘긴다.
    // 그래프가 아직 없으면 값만 기억했다가 생성 시점에 반영한다.
    this.gainNodes[stem]?.gain.setTargetAtTime(v, this.ctx.currentTime, 0.01);
  }

  applyPreset(key: keyof typeof PRESETS): void {
    const preset = PRESETS[key];
    if (!preset) return;
    for (const stem of STEM_ORDER) this.setGain(stem, preset.gains[stem]);
  }

  setLoop(start: number, end: number): void {
    if (end <= start) return;
    this._loop = { start, end };
    this.applySchedule({ active: this._playing, input: start });
  }

  clearLoop(): void {
    this._loop = null;
    this.applySchedule({ active: this._playing });
  }

  async close(): Promise<void> {
    this.stretch?.stop();
    // OfflineAudioContext에는 close()가 없다
    if ("close" in this.ctx) await (this.ctx as AudioContext).close();
  }

  /**
   * 속도·피치·루프를 한 번에 넘긴다.
   * loopStart와 loopEnd가 같으면 루프 해제라고 문서에 명시돼 있다.
   */
  private applySchedule(extra: Record<string, unknown>): void {
    if (!this.stretch) return;  // 아직 재생 전 — 값만 기억해두고 첫 play에서 반영된다
    this.stretch.schedule({
      output: this.ctx.currentTime,
      rate: this._rate,
      semitones: this._semitones,
      loopStart: this._loop?.start ?? 0,
      loopEnd: this._loop?.end ?? 0,
      ...extra,
    });
  }
}

/**
 * 스템들을 받아 8채널 Float32Array 배열로 만든다.
 * 순서는 STEM_ORDER를 따라 [s0L, s0R, s1L, s1R, ...].
 */
async function loadStems(
  ctx: BaseAudioContext,
  urls: Record<StemName, string>,
): Promise<{ channels: Float32Array[]; duration: number }> {
  const buffers = await Promise.all(
    STEM_ORDER.map(async (name) => {
      const res = await fetch(urls[name]);
      if (!res.ok) throw new Error(`스템 로딩 실패: ${name} (${res.status})`);
      return ctx.decodeAudioData(await res.arrayBuffer());
    }),
  );

  // 스템 길이가 미세하게 다를 수 있으므로 가장 긴 것에 맞춰 패딩한다.
  // 길이가 어긋난 채로 넣으면 스템마다 끝나는 시점이 달라진다.
  const length = Math.max(...buffers.map((b) => b.length));
  const duration = length / buffers[0].sampleRate;

  const channels: Float32Array[] = [];
  for (const buffer of buffers) {
    for (let ch = 0; ch < 2; ch++) {
      const src = buffer.getChannelData(Math.min(ch, buffer.numberOfChannels - 1));
      if (src.length === length) {
        channels.push(src);
      } else {
        const padded = new Float32Array(length);
        padded.set(src);
        channels.push(padded);
      }
    }
  }
  return { channels, duration };
}

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

// 경로를 변수로 둔다. 리터럴로 쓰면 TypeScript가 모듈 해석을 시도해
// "Cannot find module '/vendor/...'"로 실패한다. 이 파일은 런타임에만 존재한다.
const SIGNALSMITH_URL = "/vendor/SignalsmithStretch.mjs";

async function loadSignalsmith(): Promise<SignalsmithStretchFn> {
  if (stretchFactory) return stretchFactory;
  const mod = await import(
    /* webpackIgnore: true */ /* turbopackIgnore: true */ SIGNALSMITH_URL
  );
  stretchFactory = (mod.default ?? mod) as SignalsmithStretchFn;
  return stretchFactory;
}

export const STEM_ORDER = ["drums", "bass", "vocals", "other"] as const;
export type StemName = (typeof STEM_ORDER)[number];

/**
 * 파이프라인 산출물의 스템 URL 목록.
 * 확장자는 manifest의 stemFormat을 따른다. 필드가 없는 구버전 아티팩트는 wav.
 */
export function stemUrls(hash: string, format = "wav"): Record<StemName, string> {
  return Object.fromEntries(
    STEM_ORDER.map((name) => [name, `/api/artifacts/${hash}/stems/${name}.${format}`]),
  ) as Record<StemName, string>;
}

export type Gains = Record<StemName, number>;

export const DEFAULT_GAINS: Gains = { drums: 1, bass: 1, vocals: 1, other: 1 };

/**
 * 비트 격자 (`data/{hash}/beats.json`).
 * 값은 전부 **입력 타임라인의 초**다 — 배속을 바꿔도 이 값은 변하지 않는다.
 */
export interface BeatGrid {
  beats: number[];
  downbeats: number[];
}

/** 메트로놈 스케줄러 주기(초). 타이머 지터를 흡수하려면 lookahead가 이보다 넉넉해야 한다 */
const METRONOME_TICK_SEC = 0.025;
/** 앞서 채워둘 창(초) */
const METRONOME_LOOKAHEAD_SEC = 0.1;
/** 클릭 한 방의 길이(초) */
const CLICK_SEC = 0.05;
const DOWNBEAT_HZ = 1000;
const BEAT_HZ = 800;
const DOWNBEAT_PEAK = 0.6;
const BEAT_PEAK = 0.3;
/**
 * 입력→출력 환산 기준점을 다시 잡는 임계(초).
 * 워크릿 메시지 도착 지연(수 ms~수십 ms)에 반응해 기준점이 흔들리면 클릭 간격이
 * 그대로 떨린다. 시크·되감기 같은 큰 점프만 걸러낼 만큼 크게 잡는다.
 */
const CLOCK_RESYNC_SEC = 0.15;
/** 검출 다운비트를 비트 배열에 붙일 때 허용하는 오차(초). 균일 격자면 값이 정확히 일치한다 */
const DOWNBEAT_MATCH_SEC = 0.06;

/** 정렬된 배열에서 key(item) ≥ value 인 첫 인덱스 */
function lowerBoundBy<T>(items: T[], value: number, key: (item: T) => number): number {
  let lo = 0;
  let hi = items.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (key(items[mid]) < value) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** 정렬된 배열에서 value 이상인 첫 인덱스 */
function lowerBound(values: number[], value: number): number {
  let lo = 0;
  let hi = values.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (values[mid] < value) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/**
 * 가장 가까운 마디 시작 시각으로 맞춘다. A-B 구간을 마디 단위로 잡기 위한 것 —
 * 사람이 초 단위로 찍은 경계는 거의 항상 마디 중간이라 반복이 어색해진다.
 */
export function snapToDownbeat(seconds: number, downbeats: number[]): number {
  if (downbeats.length === 0) return seconds;
  const i = lowerBound(downbeats, seconds);
  if (i === 0) return downbeats[0];
  if (i >= downbeats.length) return downbeats[downbeats.length - 1];
  const before = downbeats[i - 1];
  const after = downbeats[i];
  return seconds - before <= after - seconds ? before : after;
}

/** 베이시스트 프리셋 — 8채널 게인 구조에서 공짜로 나온다 */
export const PRESETS: Record<string, { label: string; gains: Gains }> = {
  all: { label: "전체", gains: { drums: 1, bass: 1, vocals: 1, other: 1 } },
  bassOnly: { label: "베이스만", gains: { drums: 0, bass: 1, vocals: 0, other: 0 } },
  minusBass: { label: "베이스 빼고", gains: { drums: 1, bass: 0, vocals: 1, other: 1 } },
  rhythm: { label: "베이스+드럼", gains: { drums: 1, bass: 1, vocals: 0, other: 0 } },
};

/**
 * 악보 연주 이벤트 (`/api/scores/{hash}/synth-notes`).
 * 시각·길이는 **입력 타임라인의 초** — 배속 환산은 스케줄러가 한다.
 */
export interface SynthNote {
  t: number;
  d: number;
  midi: number;
  v: number;
  /** 드럼 히트면 악기 문자("K"킥 "S"스네어 "H"햇 조합). midi는 무시된다 */
  k?: string;
}

/** 단음 샘플 에셋 범위 (tools/gen_bass_samples.py와 같은 값) */
const SAMPLE_MIDI_LO = 22;
const SAMPLE_MIDI_HI = 62;
/** 릴리스 엔벨로프(초). 샘플 꼬리를 듀레이션에 맞춰 자를 때 쓴다 */
const VOICE_RELEASE_SEC = 0.09;
/** 악보 연주 기본 게인 — 원곡 베이스 자리를 대신하므로 또렷하게(부스트) */
export const SYNTH_DEFAULT_GAIN = 1.3;

/**
 * 베이스 단음 샘플러 — 사운드폰트(sonivox.sf2)에서 미리 구운 단음 PCM을
 * 받아 AudioBufferSourceNode로 튼다. sf2 런타임을 통째로 들이는 것보다
 * 코드가 압도적으로 작고, 같은 입력이면 같은 소리가 난다.
 */
class BassSampler {
  private ctx: AudioContext | OfflineAudioContext;
  private buffers = new Map<number, AudioBuffer>();
  private loading = new Map<number, Promise<void>>();

  constructor(ctx: AudioContext | OfflineAudioContext) {
    this.ctx = ctx;
  }

  /** 음역 밖 피치는 샘플이 있는 옥타브로 접는다 */
  static fold(midi: number): number {
    let m = midi;
    while (m < SAMPLE_MIDI_LO) m += 12;
    while (m > SAMPLE_MIDI_HI) m -= 12;
    return m;
  }

  get(midi: number): AudioBuffer | null {
    return this.buffers.get(BassSampler.fold(midi)) ?? null;
  }

  /** 필요한 피치를 미리 내려받아 디코딩해 둔다. 스케줄 시점 fetch는 늦다 */
  prefetch(midis: Iterable<number>): void {
    for (const raw of new Set([...midis].map(BassSampler.fold))) {
      if (this.buffers.has(raw) || this.loading.has(raw)) continue;
      const p = (async () => {
        try {
          const res = await fetch(`/synth/bass/${raw}.wav`);
          if (!res.ok) return;
          const buf = await this.ctx.decodeAudioData(await res.arrayBuffer());
          this.buffers.set(raw, buf);
        } catch {
          // 샘플 하나가 없다고 연주 전체를 세우지 않는다 — 그 음만 쉰다.
        } finally {
          this.loading.delete(raw);
        }
      })();
      this.loading.set(raw, p);
    }
  }
}

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
  /** 그래프 생성 전에 들어온 seek. 첫 play에서 반영한다 */
  private _pendingSeek: number | null = null;

  // --- 메트로놈 ---
  private _beats: number[] = [];
  /** _beats와 같은 길이. 다운비트면 true */
  private _accents: boolean[] = [];
  private _metronome = false;
  private _metroTimer: number | null = null;
  /** 입력 시각 t의 출력 시각 = _metroBase + t / _rate. null이면 아직 기준점이 없다 */
  private _metroBase: number | null = null;
  /** 다음에 볼 _beats 인덱스. -1이면 현재 위치에서 다시 찾는다 */
  private _metroCursor = -1;
  private _metroLastOutput = 0;
  /** 이미 예약해둔 클릭. 끌 때 취소하지 않으면 lookahead만큼 더 울린다 */
  private _pendingClicks: OscillatorNode[] = [];

  // --- 악보 연주 (베이스 샘플러) ---
  // 메트로놈과 같은 시계(_metroBase)·같은 lookahead 방식으로 악보 음표를
  // 예약한다. 스트레치 그래프에 트랙을 넣지 않는 이유: 이 방식은 배속을
  // 바꿔도 음정이 안 변하고, 난이도·이조 전환이 음표 목록 교체 하나로 끝난다.
  private _sampler: BassSampler | null = null;
  private _synthNotes: SynthNote[] = [];
  private _synthOn = false;
  private _synthGain = SYNTH_DEFAULT_GAIN;
  private _synthTimer: number | null = null;
  private _synthCursor = -1;
  private _synthLastOutput = 0;
  private _pendingVoices: AudioScheduledSourceNode[] = [];
  /** 드럼 합성용 노이즈 버퍼 — 첫 타에서 만들어 재사용 */
  private _noiseBuffer: AudioBuffer | null = null;

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
  async prepareOffline(rate = 1, startSec = 0): Promise<void> {
    await this.ensureGraph();
    this._rate = rate;
    this.applySchedule({ active: true, input: startSec });
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
    // 워크릿이 버퍼를 복사해 갔고 여기서 다시 쓸 일이 없다. 5분 곡 기준
    // 디코딩된 PCM이 ~474MB라, 사본을 놓아줘야 메모리가 절반이 된다.
    this.channels = [];

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

    // 위치 콜백은 부모에게 전달하기 전에 메트로놈의 시계 기준점부터 잡는다.
    // 입력 타임라인을 알 수 있는 통로가 이것뿐이다.
    stretch.setUpdateInterval(this.options.positionInterval ?? 0.05, (t) =>
      this.handleTime(t),
    );

    this.stretch = stretch;
    return stretch;
  }

  get duration(): number {
    return this._duration;
  }

  get position(): number {
    return this.stretch?.inputTime ?? this._pendingSeek ?? 0;
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

  get metronome(): boolean {
    return this._metronome;
  }

  async play(): Promise<void> {
    // 브라우저 자동재생 정책 — 사용자 제스처 이후에만 resume이 통한다.
    // resume을 먼저 해야 워크릿이 돌기 시작하고, 그래야 addBuffers가 완료된다.
    if (this.ctx.state === "suspended") await this.ctx.resume();
    await this.ensureGraph();
    // 그래프 생성 전에 사용자가(또는 alphaTab이) 옮겨둔 위치가 있으면 거기서 시작.
    // stretch.start()는 쓰지 않는다 — 벤더의 start()는 schedule({input: 0, ...})의
    // 설탕이라, 일시정지 후 재개할 때마다 곡 처음으로 되감아 버린다.
    this.applySchedule(
      this._pendingSeek !== null
        ? { active: true, input: this._pendingSeek }
        : { active: true },
    );
    this._pendingSeek = null;
    this._playing = true;
    if (this._metronome) this.startMetronomeTimer();
    if (this._synthOn) this.startSynthTimer();
  }

  pause(): void {
    this.stretch?.stop();
    this._playing = false;
    this.stopMetronomeTimer();
    this.stopSynthTimer();
  }

  seek(seconds: number): void {
    const clamped = Math.max(0, Math.min(seconds, this._duration));
    if (!this.stretch) {
      // applySchedule은 그래프가 없으면 무시된다. rate·gain과 달리 seek 위치는
      // 필드에 안 남으므로 여기서 따로 기억해뒀다가 첫 play에서 반영한다.
      this._pendingSeek = clamped;
      return;
    }
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

  /**
   * A-B 구간 반복. 한쪽이라도 null이거나 끝이 시작보다 앞이면 해제로 본다.
   *
   * 경계는 **입력 타임라인 기준**이라 배속·피치를 바꿔도 다시 환산할 필요가 없다.
   * 워크릿이 입력 시각으로 되감기 때문이다(SignalsmithStretch.mjs의 process:
   * `inputTime >= loopEnd`면 segment.input을 loopLength만큼 뺀다).
   */
  setLoop(start: number | null, end: number | null): void {
    if (start === null || end === null || end <= start) {
      if (!this._loop) return;
      this._loop = null;
      this.applySchedule({ active: this._playing });
      return;
    }
    this._loop = { start, end };
    // 이미 구간 안에 있으면 위치를 건드리지 않는다. 재생 중에 B를 찍었다고
    // 소리가 앞으로 튀면 어디를 반복하는지 확인할 수가 없다.
    const pos = this.position;
    const inside = pos >= start && pos < end;
    this.applySchedule(
      inside ? { active: this._playing } : { active: this._playing, input: start },
    );
  }

  clearLoop(): void {
    this.setLoop(null, null);
  }

  /**
   * 메트로놈이 칠 비트 격자. beats.json을 그대로 넘긴다.
   * downbeats는 beats와 값이 같을 수도(균일 격자) 따로 검출된 것일 수도 있어
   * 최근접 매칭으로 강세를 붙인다.
   */
  setBeatGrid(grid: BeatGrid | null): void {
    this._metroCursor = -1;
    if (!grid || grid.beats.length === 0) {
      this._beats = [];
      this._accents = [];
      return;
    }
    const beats = [...grid.beats].sort((a, b) => a - b);
    const accents = new Array<boolean>(beats.length).fill(false);
    for (const d of grid.downbeats ?? []) {
      const i = lowerBound(beats, d);
      for (const c of [i - 1, i]) {
        if (c >= 0 && c < beats.length && Math.abs(beats[c] - d) <= DOWNBEAT_MATCH_SEC) {
          accents[c] = true;
          break;
        }
      }
    }
    this._beats = beats;
    this._accents = accents;
  }

  setMetronome(enabled: boolean): void {
    this._metronome = enabled;
    if (enabled && this._playing) this.startMetronomeTimer();
    else this.stopMetronomeTimer();
  }

  get synthEnabled(): boolean {
    return this._synthOn;
  }

  get synthGain(): number {
    return this._synthGain;
  }

  /**
   * 악보 연주 이벤트 교체 — 난이도·이조를 바꾸면 화면 악보와 함께 이 목록도
   * 같은 변형으로 다시 받아야 한다(보이는 TAB ≠ 들리는 소리 금지).
   */
  setSynthNotes(notes: SynthNote[] | null): void {
    this._synthNotes = notes ? [...notes].sort((a, b) => a.t - b.t) : [];
    this._synthCursor = -1;
    const pitched = this._synthNotes.filter((n) => !n.k);
    if (pitched.length > 0) {
      this._sampler ??= new BassSampler(this.ctx);
      this._sampler.prefetch(pitched.map((n) => n.midi));
    }
  }

  setSynthEnabled(enabled: boolean): void {
    this._synthOn = enabled;
    if (enabled && this._playing) this.startSynthTimer();
    else this.stopSynthTimer();
  }

  /** 0 ~ 2.5. 원곡 베이스 대신 울리는 소리라 기본이 이미 부스트(1.3)다 */
  setSynthGain(value: number): void {
    this._synthGain = Math.max(0, Math.min(2.5, value));
  }

  async close(): Promise<void> {
    this.stopMetronomeTimer();
    this.stopSynthTimer();
    this.stretch?.stop();
    // OfflineAudioContext에는 close()가 없다
    if ("close" in this.ctx) await (this.ctx as AudioContext).close();
  }

  /**
   * 워크릿이 알려주는 입력 시각. 부모 콜백보다 먼저 시계 기준점을 갱신한다.
   *
   * 입력·출력 시각 모두 같은 AudioContext 시계를 쓰므로 기울기(1/rate)는 정확하다.
   * 그래서 기준점만 유지하면 드리프트가 없고, 매번 다시 잡으면 메시지 도착
   * 지터가 그대로 클릭 흔들림이 된다. 큰 점프일 때만 다시 잡는다.
   */
  private handleTime(input: number): void {
    const base = this.ctx.currentTime - input / this._rate;
    if (this._metroBase === null || Math.abs(base - this._metroBase) > CLOCK_RESYNC_SEC) {
      this._metroBase = base;
      this._metroCursor = -1;
      this._synthCursor = -1;
    }
    this.options.onPosition?.(input);
  }

  private startMetronomeTimer(): void {
    if (this._metroTimer !== null) return;
    // OfflineAudioContext에는 실시간 시계가 없어 lookahead 스케줄링이 성립하지 않는다
    if (!("close" in this.ctx)) return;
    this._metroTimer = window.setInterval(
      () => this.metronomeTick(),
      METRONOME_TICK_SEC * 1000,
    );
  }

  private stopMetronomeTimer(): void {
    if (this._metroTimer === null) return;
    window.clearInterval(this._metroTimer);
    this._metroTimer = null;
    this._metroCursor = -1;
    this._metroLastOutput = 0;
    for (const osc of this._pendingClicks) osc.stop();
    this._pendingClicks = [];
  }

  /**
   * 앞으로 METRONOME_LOOKAHEAD_SEC 안에 울릴 클릭을 미리 예약한다.
   * setInterval은 시각이 부정확하지만, 예약 자체는 AudioContext 시계로 하므로
   * 타이머가 늦어도 소리 위치는 흔들리지 않는다.
   */
  private metronomeTick(): void {
    if (!this._playing || !this._metronome || this._beats.length === 0) return;
    let base = this._metroBase;
    if (base === null) return;

    const now = this.ctx.currentTime;
    const horizon = now + METRONOME_LOOKAHEAD_SEC;
    if (this._metroCursor < 0) {
      this._metroCursor = lowerBound(this._beats, (now - base) * this._rate);
    }

    // 되감기 구간에 비트가 하나도 없으면 무한 루프가 되므로 횟수를 묶는다
    let wraps = 0;
    while (wraps <= 2) {
      const loop = this._loop;
      const cursor = this._metroCursor;
      const beat = cursor < this._beats.length ? this._beats[cursor] : null;

      if (loop && (beat === null || beat >= loop.end)) {
        // 워크릿보다 앞서 스케줄하므로 되감기도 우리가 먼저 반영해야 클릭이 끊기지
        // 않는다. 입력 시각이 loopLength만큼 뒤로 가는 것과 같은 뜻이다.
        base += (loop.end - loop.start) / this._rate;
        this._metroBase = base;
        this._metroCursor = lowerBound(this._beats, loop.start);
        wraps++;
        continue;
      }
      if (beat === null) return; // 루프가 없으면 곡 끝에서 멈춘다

      const out = base + beat / this._rate;
      if (out > horizon) return;
      this._metroCursor = cursor + 1;
      // 기준점이 다시 잡히면 같은 비트를 두 번 볼 수 있다. 출력 시각으로 거른다.
      if (out >= now && out > this._metroLastOutput + 0.001) {
        this.scheduleClick(out, this._accents[cursor]);
        this._metroLastOutput = out;
      }
    }
  }

  private startSynthTimer(): void {
    if (this._synthTimer !== null) return;
    if (!("close" in this.ctx)) return; // OfflineAudioContext — 실시간 시계 없음
    this._synthTimer = window.setInterval(
      () => this.synthTick(),
      METRONOME_TICK_SEC * 1000,
    );
  }

  private stopSynthTimer(): void {
    if (this._synthTimer === null) return;
    window.clearInterval(this._synthTimer);
    this._synthTimer = null;
    this._synthCursor = -1;
    this._synthLastOutput = 0;
    this.killVoices();
  }

  /** 울리는 중이거나 예약된 음을 전부 끊는다 — 시크·정지 후 잔향 방지 */
  private killVoices(): void {
    for (const v of this._pendingVoices) {
      try {
        v.stop();
      } catch {
        // 아직 start 전이면 stop이 던진다 — 버릴 노드라 상관없다.
      }
    }
    this._pendingVoices = [];
  }

  /**
   * 악보 연주 스케줄러 — metronomeTick과 같은 구조, 같은 시계(_metroBase).
   * 비트 대신 음표를 예약하고, 루프 되감기도 같은 방식으로 앞서 반영한다.
   */
  private synthTick(): void {
    if (!this._playing || !this._synthOn || this._synthNotes.length === 0) return;
    let base = this._metroBase;
    if (base === null) return;

    const now = this.ctx.currentTime;
    const horizon = now + METRONOME_LOOKAHEAD_SEC;
    if (this._synthCursor < 0) {
      this._synthCursor = lowerBoundBy(
        this._synthNotes, (now - base) * this._rate, (n) => n.t,
      );
    }

    let wraps = 0;
    while (wraps <= 2) {
      const loop = this._loop;
      const cursor = this._synthCursor;
      const note = cursor < this._synthNotes.length ? this._synthNotes[cursor] : null;

      if (loop && (note === null || note.t >= loop.end)) {
        base += (loop.end - loop.start) / this._rate;
        this._metroBase = base;
        this._synthCursor = lowerBoundBy(this._synthNotes, loop.start, (n) => n.t);
        // 메트로놈 커서는 건드리지 않는다 — 자기 틱에서 같은 base로 다시 잡는다.
        this._metroCursor = -1;
        wraps++;
        continue;
      }
      if (note === null) return;

      const out = base + note.t / this._rate;
      if (out > horizon) return;
      this._synthCursor = cursor + 1;
      if (out >= now && out > this._synthLastOutput + 0.0005) {
        this.scheduleVoice(note, out);
        this._synthLastOutput = out;
      }
    }
  }

  /** 음표 한 개 — 단음 샘플 + 듀레이션 엔벨로프. 길이는 출력 시간으로 환산 */
  private scheduleVoice(note: SynthNote, at: number): void {
    if (note.k) {
      for (const c of note.k) this.scheduleDrum(c, at);
      return;
    }
    const buffer = this._sampler?.get(note.midi);
    if (!buffer) return; // 아직 디코딩 전이거나 없는 샘플 — 그 음만 쉰다

    const ctx = this.ctx;
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    const gain = ctx.createGain();
    const peak = Math.max(0.05, Math.min(2.5, note.v * this._synthGain));
    // 배속을 늦추면 음 간격이 늘어나므로 지속도 같이 늘린다(음정은 불변).
    const durOut = Math.max(0.12, note.d / this._rate);
    const sustainEnd = at + Math.min(durOut, buffer.duration - VOICE_RELEASE_SEC);
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(peak, at + 0.004);
    gain.gain.setValueAtTime(peak, sustainEnd);
    gain.gain.exponentialRampToValueAtTime(0.0001, sustainEnd + VOICE_RELEASE_SEC);
    src.connect(gain);
    gain.connect(ctx.destination);
    src.start(at);
    src.stop(sustainEnd + VOICE_RELEASE_SEC + 0.02);
    this._pendingVoices.push(src);
    src.onended = () => {
      const i = this._pendingVoices.indexOf(src);
      if (i >= 0) this._pendingVoices.splice(i, 1);
    };
  }

  /**
   * 드럼 한 타 — 샘플 없이 합성한다(킥=사인 스윕, 스네어=노이즈+톤,
   * 햇=하이패스 노이즈). 악보 드럼 트랙과 같은 격자의 리듬 가이드라
   * 존재감은 낮게(베이스 연주를 가리면 안 된다).
   */
  private scheduleDrum(kind: string, at: number): void {
    const ctx = this.ctx;
    const g = ctx.createGain();
    g.connect(ctx.destination);
    if (kind === "K") {
      const osc = ctx.createOscillator();
      osc.frequency.setValueAtTime(140, at);
      osc.frequency.exponentialRampToValueAtTime(45, at + 0.1);
      g.gain.setValueAtTime(0.0001, at);
      g.gain.exponentialRampToValueAtTime(0.55, at + 0.004);
      g.gain.exponentialRampToValueAtTime(0.0001, at + 0.16);
      osc.connect(g);
      osc.start(at);
      osc.stop(at + 0.18);
      this._pendingVoices.push(osc);
      return;
    }
    // 스네어·햇은 노이즈 기반. 버퍼는 한 번 만들어 재사용한다.
    if (!this._noiseBuffer) {
      const len = Math.floor(ctx.sampleRate * 0.2);
      const buf = ctx.createBuffer(1, len, ctx.sampleRate);
      const ch = buf.getChannelData(0);
      for (let i = 0; i < len; i++) ch[i] = Math.random() * 2 - 1;
      this._noiseBuffer = buf;
    }
    const src = ctx.createBufferSource();
    src.buffer = this._noiseBuffer;
    const filter = ctx.createBiquadFilter();
    if (kind === "S") {
      filter.type = "bandpass";
      filter.frequency.value = 1800;
      filter.Q.value = 0.7;
      g.gain.setValueAtTime(0.0001, at);
      g.gain.exponentialRampToValueAtTime(0.35, at + 0.003);
      g.gain.exponentialRampToValueAtTime(0.0001, at + 0.14);
    } else {
      filter.type = "highpass";
      filter.frequency.value = 7000;
      g.gain.setValueAtTime(0.0001, at);
      g.gain.exponentialRampToValueAtTime(0.16, at + 0.002);
      g.gain.exponentialRampToValueAtTime(0.0001, at + 0.05);
    }
    src.connect(filter);
    filter.connect(g);
    src.start(at);
    src.stop(at + 0.16);
    this._pendingVoices.push(src);
    src.onended = () => {
      const i = this._pendingVoices.indexOf(src);
      if (i >= 0) this._pendingVoices.splice(i, 1);
    };
  }

  /** 클릭 한 방. 오실레이터 + 짧은 감쇠 엔벨로프 */
  private scheduleClick(at: number, accent: boolean): void {
    const ctx = this.ctx;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = accent ? DOWNBEAT_HZ : BEAT_HZ;
    // exponentialRampToValueAtTime은 0을 받지 못한다(값이 그대로 멈춘다)
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(accent ? DOWNBEAT_PEAK : BEAT_PEAK, at + 0.002);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + CLICK_SEC);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(at);
    osc.stop(at + CLICK_SEC + 0.02);
    this._pendingClicks.push(osc);
    osc.onended = () => {
      const i = this._pendingClicks.indexOf(osc);
      if (i >= 0) this._pendingClicks.splice(i, 1);
    };
  }

  /**
   * 속도·피치·루프를 한 번에 넘긴다.
   * loopStart와 loopEnd가 같으면 루프 해제라고 문서에 명시돼 있다.
   */
  private applySchedule(extra: Record<string, unknown>): void {
    if (!this.stretch) return;  // 아직 재생 전 — 값만 기억해두고 첫 play에서 반영된다
    // 속도·위치가 바뀌면 입력→출력 환산이 통째로 달라진다. 다음 위치 콜백에서
    // 다시 잡게 비워둔다.
    this._metroBase = null;
    this._metroCursor = -1;
    this._synthCursor = -1;
    // 시크하면 옛 위치의 음이 울리는 중일 수 있다. 클릭(50ms)과 달리 음표는
    // 초 단위로 지속되므로 반드시 끊어야 한다.
    this.killVoices();
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

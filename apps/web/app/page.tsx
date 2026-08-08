import Link from "next/link";
import JobRunner from "@/components/JobRunner";
import { BADGE, CARD } from "@/components/ui";

const WORKER = process.env.WORKER_URL ?? "http://localhost:8000";

interface LibraryItem {
  contentHash: string;
  title: string;
  durationSec?: number;
  bpm?: number;
  barCount?: number;
  noteCount?: number;
  quality?: { score?: number; level?: string };
}

async function loadLibrary(): Promise<LibraryItem[]> {
  try {
    const res = await fetch(`${WORKER}/api/library`, { cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    // 워커가 안 떠 있어도 첫 화면은 보여준다
    return [];
  }
}

const LEVEL_LABEL: Record<string, string> = {
  good: "좋음",
  reference: "참고용",
  failed: "악보 없음",
};

export default async function Home() {
  const library = await loadLibrary();

  return (
    <main className="mx-auto max-w-3xl space-y-10 px-4 py-12 sm:px-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Lowend<span className="text-amber-500">.</span>
        </h1>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          곡을 넣으면 베이스 라인을 자동으로 채보하고, 배속·악기별 볼륨·탭 악보가 되는
          연습 플레이어를 만들어 줍니다.
        </p>
      </header>

      <div className={`${CARD} p-5`}>
        <JobRunner />
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300">
          처리한 곡
        </h2>
        {library.length === 0 ? (
          <p className="text-sm text-neutral-500">
            아직 없습니다. 위에 링크를 넣거나 파일을 올려보세요.
          </p>
        ) : (
          <ul className="space-y-2">
            {library.map((item) => (
              <li key={item.contentHash}>
                <Link
                  href={`/play/${item.contentHash}`}
                  className={`${CARD} flex items-center justify-between gap-4 px-4 py-3 transition hover:border-amber-400 hover:bg-neutral-50 dark:hover:border-amber-500/50 dark:hover:bg-neutral-900`}
                >
                  <span className="min-w-0 flex-1 truncate text-sm">{item.title}</span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    {item.bpm ? <span className={BADGE}>{`${item.bpm} BPM`}</span> : null}
                    {item.barCount ? <span className={BADGE}>{`${item.barCount}마디`}</span> : null}
                    {item.quality?.level ? (
                      <span className={BADGE}>
                        {LEVEL_LABEL[item.quality.level] ?? item.quality.level}
                      </span>
                    ) : null}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className="border-t border-neutral-200 pt-6 text-xs text-neutral-500 dark:border-neutral-800">
        개인 학습·연습 목적. 자동 채보는 사람이 만든 악보보다 정확하지 않고, 슬랩·고스트노트
        같은 주법은 표기되지 않습니다.
      </footer>
    </main>
  );
}

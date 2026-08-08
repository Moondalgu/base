import PlayerShell from "@/components/player/PlayerShell";

export default async function PlayPage({
  params,
}: {
  params: Promise<{ hash: string }>;
}) {
  const { hash } = await params;
  // 재생 페이지는 넓게 쓴다 — 672px에서는 행당 4마디 악보가 눌려서
  // 음표 간격이 참조 악보(A4)보다 훨씬 좁아진다.
  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <PlayerShell hash={hash} />
    </main>
  );
}

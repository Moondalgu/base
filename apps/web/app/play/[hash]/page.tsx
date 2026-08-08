import PlayerShell from "@/components/player/PlayerShell";

export default async function PlayPage({
  params,
}: {
  params: Promise<{ hash: string }>;
}) {
  const { hash } = await params;
  // 재생 페이지는 넓게 쓴다 — 672px에서는 행당 4마디 악보가 눌려서
  // 음표 간격이 참조 악보(A4)보다 훨씬 좁아진다.
  // 아래 여백은 PlayerShell이 직접 준다(고정 트랜스포트 바가 가리는 만큼).
  return (
    <main className="mx-auto max-w-5xl px-4 pt-8 sm:px-6">
      <PlayerShell hash={hash} />
    </main>
  );
}
